"""Execution graph states for the affective mediator agent."""

from datetime import datetime
from typing import Dict, Literal, NotRequired, Optional
from langchain.agents import AgentState
from pydantic import Field

from agent.base_models import AffectiveWindow, IsInterestingDecision, ShouldInterveneDecision


# reduction functions
def add_dicts(d1, d2):
    return {**d1, **d2}


class GroupDiscussionState(AgentState):
    """
    State schema for the Affective Mediator agent in group discussions.
    """
    
    # messages: inherited from AgentState
    
    discussion_id: str  # unique identifier of the group discussion
    
    topic: str # The topic of the group discussion

    condition: Literal['none', 'no_affect', 'affect']  # discussion condition

    initial_responses: Dict[str, str]

    last_message: Optional[str]

    last_is_interesting_decision: Optional[IsInterestingDecision]

    last_affective_window: Optional[AffectiveWindow]

    last_intervention_decision: Optional[ShouldInterveneDecision]

    last_intervention_time: Optional[datetime]

    post_intervention_cooldown: int # TODO: move this to constants

    started_discussion: bool
