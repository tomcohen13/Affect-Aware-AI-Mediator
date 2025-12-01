"""Main agent class for the Affective Mediator agent."""
from datetime import datetime
from typing import Literal
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
from agent.constants import AFFECTIVE_WINDOW_DEFAULT_LIFESPAN, NO_AFFECTIVE_WINDOW_RECEIVED_TOKEN
from agent.state import GroupDiscussionState
from agent.utils import create_human_message_from_raw, load_prompt
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

        self.fast_model: BaseChatModel = gating_model
        self.reasoning_model: BaseChatModel = gating_model  # TODO: change to reasoning_model for production
        self.logger: logging.Logger = logger

        self.is_interesting_prompt = load_prompt(func=self.is_interesting.__name__)
        self.should_intervene_prompt = load_prompt(func=self.should_intervene.__name__)

        self.memory = MemorySaver() if memory is None else memory
        
        self.react_agent = create_agent(
            model=reasoning_model,
            middleware=[ # TODO: add middleware for summarization and de-identification
                PIIMiddleware(pii_type='email', strategy='redact'),
                SummarizationMiddleware(model=self.fast_model, max_tokens_before_summary=1000),
            ],
            system_prompt=self.should_intervene_prompt,
            checkpointer=self.memory,
        )
        
        workflow: StateGraph = self.initialize_workflow()
        self.graph = workflow.compile(
            interrupt_before=["affective_window"], # interrupt to fetch affective window from EventManager
            checkpointer=self.memory
        )

        self.debug_mode = debug_mode

    # TODO: refine signature and add docstring
    async def run(self, input: dict | AffectiveWindow, pathway: Literal['is_interesting', 'should_intervene']):
        '''

        Two pathways:

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

        
        if pathway == "is_interesting":

            config = {'configurable': {'thread_id': input['discussion_id']}}

            self.logger.info(config)
            
            # check if the discussion has a state
            current_state = self.graph.get_state(config=config)

            state = {"messages": [create_human_message_from_raw(input["event"].payload)]}

            if current_state.values == {}:
                # no previous state found for the conversation
                state["discussion_id"] = input["discussion_id"]
                state["topic"] = input['meta'].get('topicId'),  # TODO: convert topic id to topic description!
                state["condition"] = input['meta'].get('condition')

            async for val in self.graph.astream(state, config=config, stream_mode="values"):
                # TODO: log this somewhere?
                if self.logger:
                    self.logger.info(val)

            return val

        elif pathway == "should_intervene":
            '''
            model should reason over a summarized version of the affective window...
            the langchain convention for resuming an execution graph is with input = None
            and just config, so I need to update the state with the window, time-travel-style,
            before exeucting.

            Rough pseudo-code:
                - state_update = window.to_model_input()
                - self.graph.update_state(config=config, values=state_update)
                - execute graph from affective_window
            '''
            config = {'configurable': {'thread_id': input.discussion_id}}
            
            new_values = input.to_graph_state(exclude_first_message=True)
            
            _ = await self.graph.aupdate_state(config=config, values=new_values, as_node="affective_window")

            final_state = await self.graph.ainvoke(None, config=config)

            return final_state


    def initialize_workflow(self) -> StateGraph:
        """
        Build the agent's workflow using LangGraph.
        """
        workflow = StateGraph(GroupDiscussionState)
        
        # workflow.add_node("is_interesting", ...)  # decide if interesting enough to start a window
        workflow.add_node("affective_window", self.affective_window)  # start affective window
        workflow.add_node("should_intervene", self.should_intervene)  # decide if intervention is needed
        workflow.add_node("intervene", self.send_intervention)  # craft intervention message

        workflow.add_conditional_edges(START, self.is_interesting, {"interesting": "affective_window", "nah": END})
        workflow.add_edge("affective_window", "should_intervene")
        workflow.add_conditional_edges("should_intervene", self.evaluate_intervention_decision, {"intervene": "intervene", "nah": END})
        workflow.add_edge("intervene", END)

        return workflow


    async def is_interesting(self, state: GroupDiscussionState) -> bool:
        """
        Determine if the current affective event is interesting enough to start an affective window.
        """
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


    async def should_intervene(self, state: GroupDiscussionState) -> GroupDiscussionState:
        """
        Determine if an intervention is needed in the current affective window.
        """
        # enforce cooldown period between interventions

        if state.get('last_intervention_time') and (datetime.now() - state['last_intervention_time']).total_seconds() < state['post_intervention_cooldown']:

            decision = ShouldInterveneDecision(
                should_intervene=False,
                reason="<COOLDOWN_PERIOD_ACTIVE>"
            )
            return {
                "last_intervention_decision": decision
            }
        
        if not state.get('last_affective_window'):
            decision = ShouldInterveneDecision(
                should_intervene=False,
                reason=NO_AFFECTIVE_WINDOW_RECEIVED_TOKEN
            )
            return {
                "last_intervention_decision": decision
            }

        # fetch affective window
        window = state['last_affective_window']

        new_messages = window.all_messages

        group_state_report = window.to_model_context()

        messages = [SystemMessage(content=self.should_intervene_prompt)] + new_messages + [group_state_report]

        decision: ShouldInterveneDecision = await call_model_async(
            messages=messages,
            model=self.reasoning_model,
            output_type=ShouldInterveneDecision,
        )
        return {
            "messages": messages,
            "last_intervention_decision": decision,
        }
    
    async def evaluate_intervention_decision(self, state: GroupDiscussionState) -> str:
        """Evaluate decision from previous state"""
        return "intervene" if state['last_intervention_decision'].should_intervene else "nah"


    async def send_intervention(self, state: GroupDiscussionState) -> GroupDiscussionState:
        """
        A placeholder function for crafting and sending an intervention message.
        """
        return state


# TODO: either remove or move inside AffectiveMediator
@tool
def check_time_left():
    """Check the current time."""
    
    # MOCK
    return "5 minutes left"

