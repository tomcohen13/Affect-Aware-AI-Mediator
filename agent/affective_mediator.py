"""Main agent class for the Affective Mediator agent."""
from datetime import datetime
from typing import Literal, Mapping
from langchain.agents import create_agent
from langchain.agents.middleware import (
    PIIMiddleware,  # we'll definitely need that for redacting personal information
    SummarizationMiddleware,  # could be good for the agent to hold a running summary of chat as opposed to all messages
)
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage
from langchain.chat_models.base import BaseChatModel
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph
from langgraph.graph.state import END, START

import logging

from agent.base_models import AffectiveWindow, IsInterestingDecision, ShouldInterveneDecision
from agent.constants import (
    NO_AFFECTIVE_WINDOW_RECEIVED_TOKEN,
    TOPIC_OPTIONS
)
from agent.state import GroupDiscussionState
from agent.utils import load_prompt
from agent.llms import call_model_async, gating_model, reasoning_model


class AffectiveMediator:
    """

    Affective Mediator (CHARLIE):
    
    An Affect-aware AI agent that facilitates online group discussions by monitoring participants' emotional states
    and intervening when necessary to promote positive interactions.


    Parameters:
        ...
    """

    def __init__(self, memory = None, logger = None, debug_mode: bool = False):

        self.name = "__mediator__"
        self.fast_model: BaseChatModel = gating_model
        self.reasoning_model: BaseChatModel = reasoning_model  # TODO: change to reasoning_model for production
        self.logger: logging.Logger = logger

        self.is_interesting_prompt = load_prompt(func=self.is_interesting.__name__)
        self.should_intervene_prompt = load_prompt(func=self.should_intervene.__name__)
        self.initial_response_prompt = load_prompt("initial_response")
        self.post_intervention_cooldown = 30  # seconds in between two interventions

        self.memory = MemorySaver() if memory is None else memory
        
        self.react_agent = create_agent(
            model=self.reasoning_model,
            middleware=[
                PIIMiddleware(pii_type='email', strategy='redact'),
                SummarizationMiddleware(
                    model=self.fast_model,
                    max_tokens_before_summary=500,
                    messages_to_keep=3,
                ),
            ],
            system_prompt=self.should_intervene_prompt,
            checkpointer=self.memory,
            state_schema=GroupDiscussionState,
            response_format=ShouldInterveneDecision,
        )
        
        workflow: StateGraph = self.initialize_workflow()
        self.graph = workflow.compile(
            interrupt_before=["affective_window"], # interrupt to fetch affective window from EventManager
            checkpointer=self.memory
        )

        self.debug_mode = debug_mode

    async def start_discussion(
        self,
        discussion_id: str,
        initial_responses: Mapping[str, str],
        topic_id: str,
        condition: str,
    ):
        """
        Synthessize participatns initial responses into a welcoming first message.

        Parameters:
            discussion_id
            initial_responses: a dictionary of {participant_id: initial response}
            metadata: a dictionary containing the following keys (must)
                topicId: the topic identifier assigned to the discussion
                condition: mediation condition of discussion: 'none', 'affect', 'no-affect'
        
        """

        config = {'configurable': {'thread_id': discussion_id}}
       
        if topic_id != "" and topic_id in TOPIC_OPTIONS:
            topic_prompt = " ".join([TOPIC_OPTIONS[topic_id].get("label"), TOPIC_OPTIONS[topic_id].get("prompt")])
        else:
            topic_prompt = topic_id

        initial_state = {
            "discussion_id": discussion_id,
            "initial_responses": initial_responses,
            "topic": topic_id,
            "condition": condition,
            "messages": [],
            "post_intervention_cooldown": self.post_intervention_cooldown,
            "started_discussion": True,
        }

        _ = await self.graph.aupdate_state(config, values=initial_state)

        initial_responses_msgs = [
            HumanMessage(f"Participant {k} wrote: {v}")
            for k, v in initial_responses.items()
        ]

        response = await self.fast_model.ainvoke(
            input=[
                SystemMessage(self.initial_response_prompt.format(topic_prompt=topic_prompt)), 
                *initial_responses_msgs,
            ]
        )
        return response.content

    # TODO: refine signature and add docstring
    async def run(self, input: dict | AffectiveWindow, pathway: Literal['is_interesting', 'should_intervene', 'initial_response']):
        '''

        Pathways:

        1. is_interesting: initial gating judgment of a message, whether it could lead to something interesting
            for that pathway, a fast model is used over an affective "package" (see below).
            
        2. should_intervene: judgment over a affective window, following an initial positive judgment.
            for that pathway, a reasoning model is used, over an AffectiveWindow object.

        Parameters:
            input: either an affective "package" or an affective window.
                package structure:
                {
                    "discussion_id": unique ID of discussion
                    "event": AffectiveEvent - a message event
                    "affective_sperm": AffectiveState - the affective state of the message sender
                    "meta": Dict - discussion metadata
                }
                affective_window: AffectiveWindow
        
        Returns: a decision object given the pathway
            if pathway=is_interesting --> IsInteretingDecision ("is_interesting" / "nah")
            if pathway=should_intervene --> ShouldInterveneDecision 
        '''

        # first half of execution graph
        if pathway == "is_interesting":

            config = {'configurable': {'thread_id': input['discussion_id']}}
 
            state = {"messages": [input["event"].to_human_message()]}

            _ = await self.graph.ainvoke(state, config=config)
            return

        elif pathway == "should_intervene":

            config = {'configurable': {'thread_id': input.discussion_id}}
            
            new_values = {"last_affective_window": input}
            
            _ = await self.graph.aupdate_state(config=config, values=new_values, as_node="affective_window")

            async for update in self.graph.astream(None, config=config, stream_mode="updates"):
                self.logger.info(f"[AGENT WORKFLOW]: {update}")
            return update


    def initialize_workflow(self) -> StateGraph:
        """
        Build the agent's workflow using LangGraph.
        """
        workflow = StateGraph(GroupDiscussionState)
        
        # workflow.add_node("is_interesting", ...)  # decide if interesting enough to start a window
        workflow.add_node("affective_window", self.affective_window)  # start affective window
        workflow.add_node("should_intervene", self.should_intervene)  # decide if intervention is needed

        workflow.add_conditional_edges(START, self.is_interesting, {"interesting": "affective_window", "nah": END})
        workflow.add_edge("affective_window", "should_intervene")
        workflow.add_edge("should_intervene", END)

        return workflow


    async def is_interesting(self, state: GroupDiscussionState) -> bool:
        """
        Determine if the current affective event is interesting enough to start an affective window.
        """

        if not state.get('messages') or len(state['messages']) == 0:
            return "nah"

        messages = [
            SystemMessage(content=self.is_interesting_prompt),
            HumanMessage(content=state['messages'][-1].content),  # last message in the discussion
        ]

        decision: IsInterestingDecision = await call_model_async(
            messages=messages,
            model=self.fast_model,
            output_type=IsInterestingDecision,
        )

        return "interesting" if decision.is_interesting else "nah"


    async def affective_window(self, state: GroupDiscussionState) -> GroupDiscussionState:
        """
        A placeholder function relaying the affective window state from the EventManager.

        NOTE: the workflow assumes that the state will have "last_affective_window" populated by this point.
        """
        return state


    async def should_intervene(self, state: GroupDiscussionState):
        """
        Determine if an intervention is needed in the current affective window.
        """
        # enforce cooldown period between interventions
        
        if not state.get('last_affective_window'):
            decision = ShouldInterveneDecision(
                should_intervene=False,
                reason=NO_AFFECTIVE_WINDOW_RECEIVED_TOKEN
            )
            return {
                "last_intervention_decision": decision
            }

        if (  # within cooldown period, don't intervene
            state.get('last_intervention_time') and
            (datetime.now() - state['last_intervention_time']).total_seconds() < state['post_intervention_cooldown']
        ):

            decision = ShouldInterveneDecision(
                should_intervene=False,
                reason="<COOLDOWN_PERIOD_ACTIVE>"
            )
            return {"last_intervention_decision": decision}

        # fetch affective window
        window = state['last_affective_window']

        prompt_with_topic = self.should_intervene_prompt.format(
            topic_prompt="\n".join(
                [
                    TOPIC_OPTIONS[state['topic']].get("label"),
                    TOPIC_OPTIONS[state['topic']].get("prompt"),
                ]
            )
        )

        messages = [
            SystemMessage(content=prompt_with_topic), 
            *window.all_messages,  # all messages from window
            window.to_system_message(),  # group affective state report
        ]

        response = await self.react_agent.ainvoke(
            input={"messages": messages},
            config={'configurable': {'thread_id': state['discussion_id']}},
        )
        return {"last_intervention_decision": response['structured_response']}
    

# TODO: either remove or move inside AffectiveMediator
@tool
def check_time_left():
    """Check the current time."""
    
    # MOCK
    return "5 minutes left"

