"""Execution graph states for the affective mediator agent."""

from datetime import datetime
from typing import Literal, Optional
from langchain.agents import AgentState
from pydantic import Field

from agent.base_models import AffectiveWindow, ShouldInterveneDecision


# reduction functions
def add_dicts(d1, d2):
    return {**d1, **d2}


# TODO
class GroupDiscussionState(AgentState):
    """
    State schema for the Affective Mediator agent in group discussions.
    """
    
    discussion_id: str = Field(..., description="Unique identifier of the group discussion")
    
    topic: str = Field(..., description="The topic of the group discussion")

    condition: Literal['none', 'no_affect', 'affect'] = Field(..., description="Condition")
    
    # participants: List[str] = Field(default_factory=list, description="List of participant IDs in the discussion")
    
    # messages: inherited from AgentState

    chat_summary: str = Field(default="", description="Running summary of chat so far")

    last_affective_window: Optional[AffectiveWindow] = Field(
        default_factory=None,
        description="The most recent affective states of participants in the discussion"
    )

    last_intervention_decision: ShouldInterveneDecision = Field(
        default=None,
        description="The decision made by the mediator on whether to intervene in the last check"
    )

    last_intervention_time: datetime = Field(
        default=None,
        description="Timestamp of the last intervention made by the mediator"
    )

    post_intervention_cooldown: int = Field(description="Minimum interval in seconds between mediator interventions", default=30)
