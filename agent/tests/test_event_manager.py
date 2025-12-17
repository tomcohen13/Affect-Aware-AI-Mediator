"""Unit tests for base models logic"""

import os
import pytest
from datetime import datetime, timedelta
from langchain_core.messages import HumanMessage

from agent.affective_mediator import AffectiveMediator
from agent.base_models import (
    AffectiveState,
    AffectiveEvent,
    AffectiveWindow,
    EmotionAnnotation,
)
from agent.constants import HUME_EMOTIONS_LIST_TEXT, HUME_EMOTIONS_LIST_VISION_AUDIO
from agent.event_manager import EventManager



"""
Reminder:
ev schema (from frontend / base_models.AffectiveEvent):
{
    "event_id": str,
    "participant_id": str,
    "timestamp": ISO8601 string,
    "modality": "text" | "vision" | "audio",
    "emotion_activations": [...],
    "payload": {
    content: str
    session_id: str
    }
}
"""

@pytest.mark.asyncio
@pytest.mark.parametrize("test_input, expected_output", [
    (
        {
            "text": "I'm an ill-formatted event!",
        },
        None
    ),
])
async def test_handle_new_event(test_input, expected_output):

    em = EventManager(
        study_id=os.getenv("STUDY_ID"),
        mediator=AffectiveMediator(),
        firebase_url=os.getenv("FIREBASE_URL"),
        service_account_str=os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"),
    )

    response = await em.handle_new_event(
        session_id="testy-test",
        ev=test_input
    )

    assert response == expected_output