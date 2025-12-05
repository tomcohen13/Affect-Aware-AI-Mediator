"""Unit tests for base models logic"""

from typing import Dict
import pytest
from datetime import datetime, timedelta
from langchain_core.messages import HumanMessage

from agent.base_models import (
    AffectiveState,
    AffectiveEvent,
    AffectiveWindow,
    EmotionAnnotation,
)
from agent.constants import HUME_EMOTIONS_LIST_TEXT, HUME_EMOTIONS_LIST_VISION_AUDIO


def create_mock_activations(val=0.3):
    return [
        EmotionAnnotation(name=emotion, activation=val)
        for emotion in HUME_EMOTIONS_LIST_VISION_AUDIO  # Use first 10 for simplicity
    ]


def create_initial_state(participant_id: str = "test_participant", activation_values = 0.3) -> AffectiveState:
    """Helper to create an initial AffectiveState with default running states"""
    base_time = datetime.now()
    
    # Create initial emotion vectors for each modality
    # Using a subset of emotions for testing
    initial_emotions = [
        EmotionAnnotation(name=emotion, activation=activation_values)
        for emotion in HUME_EMOTIONS_LIST_VISION_AUDIO  # Use first 10 for simplicity
    ]
    
    state = AffectiveState(
        participant_id=participant_id,
        last_update=base_time,
        running_states={
            'vision': [
                EmotionAnnotation(name=emotion, activation=activation_values)
                for emotion in HUME_EMOTIONS_LIST_VISION_AUDIO  # Use first 10 for simplicity
            ],
            'audio': [
                EmotionAnnotation(name=emotion, activation=activation_values)
                for emotion in HUME_EMOTIONS_LIST_VISION_AUDIO  # Use first 10 for simplicity
            ],
            'text': [
                EmotionAnnotation(name=emotion, activation=activation_values)
                for emotion in HUME_EMOTIONS_LIST_TEXT  # Use first 10 for simplicity
            ],
        },
        dominant_emotions=[],
    )
    state._update_dominant_emotions()
    return state

def create_affective_event(
    modality: str,
    emotion_activations: list[EmotionAnnotation] = create_mock_activations(),
    timestamp: datetime = datetime.now(),
    payload: Dict = {},
) -> AffectiveEvent:
    """Helper to create an AffectiveEvent"""
    if timestamp is None:
        timestamp = datetime.now()
    
    return AffectiveEvent(
        participant_id="test_participant",
        event_id="test_event_1",
        timestamp=timestamp,
        modality=modality,
        emotion_activations=emotion_activations,
        payload=payload,
    )


def create_affective_window(
        discussion_id="1",
        first_message: HumanMessage = HumanMessage("hello everyone!"),
        lifespan=7,
        affective_states = [],
    ) -> AffectiveWindow:

    window = AffectiveWindow.create(
        discussion_id=discussion_id,
        first_message=first_message,
        lifespan=lifespan,
        affective_states=affective_states
    )
    return window


class TestAffectiveStateUpdateEmotions:
    """Test suite for AffectiveState update emotions logic"""

    def test_update_emotions_basic_averaging(self):
        """Test that emotions are updated using the 0.5 * old + 0.5 * new formula"""
        state = create_initial_state()
        
        # Create new emotions with different activations
        new_emotions = [
            EmotionAnnotation(name=emotion, activation=0.7)
            for emotion in HUME_EMOTIONS_LIST_VISION_AUDIO
        ]
        
        event = create_affective_event(
            modality='vision',
            emotion_activations=new_emotions,
        )
        
        # Store original emotions
        original_emotions = state.running_states['vision'].copy()
        
        # Update the state
        state.update(event)
        
        # Check that each emotion was updated correctly: 0.5 * 0.3 + 0.5 * 0.7 = 0.5
        for i, updated_emo in enumerate(state.running_states['vision']):
            expected_activation = 0.5 * original_emotions[i].activation + 0.5 * new_emotions[i].activation
            assert updated_emo.activation == pytest.approx(expected_activation, abs=0.001)
            assert updated_emo.name == original_emotions[i].name


    def test_to_message(self):
        state = create_initial_state(activation_values=0.7)

        message = state.to_message()

        assert message.type == 'human'
        assert all([emotion in message.content for emotion in HUME_EMOTIONS_LIST_TEXT])


class TestAffectiveWindow:
    
    def test_affective_window_creation(self):

        window = create_affective_window()
        assert window.expiration_time - window.start_time == timedelta(seconds=7)
        assert window.affective_states == []
        assert len(window.all_messages) == 1
        assert window.all_messages[0] == window.first_message

    def test_state_update(self):
        """
        Test that updates to affective state are reflected on window
        """
        
        participants = ["1", "2", "3"]
        
        # Create Affective states for participants, activations set to 0.3 by default
        affective_states = [
            create_initial_state(participant_id=pid)
            for pid in participants
        ]
        curr_activations_value = 0.3
        new_activations_value = 0.7
        expected_activations_value = 0.5 * (0.3 + 0.7)

        window = create_affective_window(affective_states=affective_states)

        new_event = create_affective_event(
            modality='vision',
            emotion_activations=[
                EmotionAnnotation(name=emotion, activation=new_activations_value)
                for emotion in HUME_EMOTIONS_LIST_VISION_AUDIO
            ]
        )
        affective_state_2 = affective_states[1]
        affective_state_2.update(event=new_event)
        assert window.affective_states[1].running_states[new_event.modality] == [
            EmotionAnnotation(name=n, activation=expected_activations_value)
            for n in HUME_EMOTIONS_LIST_VISION_AUDIO
        ]
