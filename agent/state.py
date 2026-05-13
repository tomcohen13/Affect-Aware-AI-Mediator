"""Execution graph states for the affective mediator agent."""

import operator
from datetime import datetime
from typing import Dict, Literal, NotRequired, Optional, Annotated, List
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

    last_affective_window: Optional[AffectiveWindow]

    last_intervention_decision: Optional[ShouldInterveneDecision]

    notes: Annotated[List[str], operator.add]

    started_discussion: bool

    start_time: datetime
