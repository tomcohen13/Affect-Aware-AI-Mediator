"""Main agent class for the Affective Mediator agent."""
from datetime import datetime
from typing import Mapping
from langchain.agents import create_agent
from langchain.agents.middleware import (
    PIIMiddleware,  # we'll definitely need that for redacting personal information
    SummarizationMiddleware,  # could be good for the agent to hold a running summary of chat as opposed to all messages
)
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from langchain_core.tools import tool
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain.chat_models.base import BaseChatModel
from langgraph.checkpoint.memory import MemorySaver

import logging

from agent.base_models import AffectiveWindow, ShouldInterveneDecision
from agent.constants import (
    TOPIC_OPTIONS
)
from agent.state import GroupDiscussionState
from agent.utils import load_prompt


class AffectiveMediator:
    """

    Affective Mediator (CHARLIE):
    
    An Affect-aware AI agent that facilitates online group discussions by monitoring participants' emotional states
    and intervening when necessary to promote positive interactions.


    Parameters:
        # TODO
    """

    def __init__(
        self,
        llm: BaseChatModel,
        summarization_llm: BaseChatModel | None = None,
        checkpointer = None,
        logger = None,
        debug_mode: bool = False
    ):

        self.name = "__mediator__"

        self.agent = None
        
        self.llm: BaseChatModel = llm
        self.summarization_llm = summarization_llm
        
        self.logger: logging.Logger = logger # TODO: add StdOut as default?
        self.debug_mode = debug_mode

        # Load prompts
        self.initial_response_prompt = load_prompt("initial_response")
        self.should_intervene_prompt = load_prompt("should_intervene")

        # load memory component
        if checkpointer is None:
            self.memory = MemorySaver()
            self.logger.warning("No checkpointer specified, using in-memory saver! (NOT to be used in production..!)")
        else:
            self.memory = checkpointer        
        
        self._initialize_agent()
    

    def _initialize_agent(self):

        self.agent = create_agent(
            model=self.llm,
            tools=[],
            middleware=[
                AnthropicPromptCachingMiddleware(ttl="1h"),
                PIIMiddleware(pii_type='email', strategy='redact'),
                SummarizationMiddleware(
                    model=self.summarization_llm,
                    keep=("messages", 8),
                    trigger=("tokens", 3000),
                ),
            ],
            system_prompt=self.should_intervene_prompt, # TODO: implement dynamic prompt: https://docs.langchain.com/oss/python/concepts/context
            checkpointer=self.memory,
            state_schema=GroupDiscussionState,
            response_format=ShouldInterveneDecision,
        )

    async def start_discussion(
        self,
        discussion_id: str,
        initial_responses: Mapping[str, str],
        topic_id: str,
        condition: str,
    ):
        """
        Synthesize participants' initial responses into a welcoming first message.

        Parameters:
            discussion_id: unique identifier of group discussion
            initial_responses: a dictionary of {participant_id: initial response}
            topic_id: the topic identifier assigned to the discussion
            condition: mediation condition of discussion: 'none', 'affect', 'no-affect'
        
        """

        config = {'configurable': {'thread_id': discussion_id}}
       
        if topic_id != "" and topic_id in TOPIC_OPTIONS:
            topic_prompt = " ".join([TOPIC_OPTIONS[topic_id].get("label"), TOPIC_OPTIONS[topic_id].get("prompt")])
        else:
            topic_prompt = topic_id

        # TODO: move into function
        initial_state = {
            "discussion_id": discussion_id,
            "initial_responses": initial_responses,
            "topic": topic_id,
            "condition": condition,
            "messages": [],
            "started_discussion": True,
            "start_time": datetime.now(),
            "notes": [],
        }

        _ = await self.agent.aupdate_state(config, values=initial_state)

        initial_responses_msgs = [
            HumanMessage(f"Participant {k} wrote: {v}")
            for k, v in initial_responses.items()
        ]

        response = await self.summarization_llm.ainvoke(
            input=[
                SystemMessage(self.initial_response_prompt.format(topic_prompt=topic_prompt)), 
                *initial_responses_msgs,
            ]
        )
        return response
    
    async def process_new_message(
        self,
        discussion_id: str,
        new_message: str,
        window: AffectiveWindow | None,
    ) -> ShouldInterveneDecision:
        """
        Processes a new message within a discussion and determines whether intervention is needed.

        Args:
            discussion_id (str): Unique identifier for the group discussion.
            new_message (str): The new message from a participant to evaluate.
            window (AffectiveWindow | None): The affective window object for the discussion, if any.

        Returns:
            ShouldInterveneDecision: A decision object indicating whether an intervention should occur, and the details.
        """

        config = {'configurable': {'thread_id': discussion_id}}
        messages = []
        
        # pull previous self notes
        prev_state = await self.agent.aget_state(config)
        notes = prev_state.values.get('notes')
        if notes:
            last_note = f"Last note you wrote to self: \n\n {notes}"
            messages.append(
                AIMessage(content=last_note, sender="__CHARLIE_INTERNAL__"),
            )
        messages.append(HumanMessage(content=new_message))

        if window:
            messages.append(window.to_system_message())

        result = await self.agent.ainvoke(
            input={"messages": messages},
            config=config,
        )
        return result['structured_response']


# TODO: either remove or move inside AffectiveMediator
@tool
def check_time_left():
    """Check the current time."""
    
    # MOCK
    return "5 minutes left"

