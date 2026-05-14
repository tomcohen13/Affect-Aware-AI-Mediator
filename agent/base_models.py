"""Base models for the agent"""

import itertools
import uuid
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from typing import Dict, Iterable, List, Literal, Mapping, Optional, Set, Tuple

from agent.constants import (
    HUME_EMOTIONS_LIST_TEXT,
    HUME_EMOTIONS_LIST_VISION_AUDIO,
    SUPPORTED_MODALITIES,
)
from agent.utils import create_human_message_from_raw, datetime_to_string


# =============================================================================
# SECTION: Affective Base Models for Emotion and State Representation
# =============================================================================

class IsInterestingDecision(BaseModel):
    """
    Output schema for determining if an affective event is interesting.
    """

    is_interesting: bool = Field(description="Whether the event is interesting or not")
    reason: Optional[str] = Field(
        description="Optional reason why the event is considered interesting",
        default=None,
    )
    notes: Optional[str] = Field(
        description="notes to future self on what to be on the lookout for while considering intervention"
    )


class ShouldInterveneDecision(BaseModel):
    """
    Output schema for determining if an intervention is needed.
    """

    should_intervene: bool = Field(description="Whether to respond in the chat or not")
    response: str = Field(
        description="The message to be sent back to the chat, if applicable",
        default="",
    )
    in_response_to: str = Field(
        description="If applicable, a specific message ID the agent responds to",
        default=""
    )
    note: str = Field(
        description="If applicable, a note to future self regarding the current state",
        default=""
    )

# =============================================================================
# SECTION: Affective Base Models for Emotion and State Representation
# =============================================================================
class EmotionAnnotation(BaseModel):
    """
    An emotion with corresponding activation, outputted by a model.
    """

    name: Literal[*HUME_EMOTIONS_LIST_TEXT] = Field(description="Emotion label") # type: ignore
    activation: float = Field(
        description="Strength of perceived emotion, between [0.0, 1.0]"
    )
    
    def __repr__(self):
        # Represents the object in a clear, unambiguous way
        return f'{self.name}: {self.activation:.2f}'

    def __eq__(self, other):
        """Defines when two EmotionAnnotation objects are considered equal."""
        if not isinstance(other, EmotionAnnotation):
            return NotImplemented
        
        # Two emotions are equal if both their name and activation are the same.
        return (self.name == other.name and self.activation == other.activation)


    def __hash__(self):
        """Returns an immutable hash value for the object."""
        # We combine the hash of the immutable 'name' and 'activation'
        return hash((self.name, self.activation))


    def __add__(self, other):
        """Overloads the '+' operator for EmotionAnnotation + EmotionAnnotation."""
        
        if not isinstance(other, EmotionAnnotation):
            return NotImplemented

        # NOTE: Assuming name attribute should match!
        if self.name != other.name:
            raise Exception(f"Cannot add emotions of different types! got {self.name}, {other.name}")

        new_activation = self.activation + other.activation
        return EmotionAnnotation(name=self.name, activation=new_activation)


    def __mul__(self, other):
        """
        Overloads the '*' operator for multiplication.
        Handles both EmotionAnnotation * scalar (number)
        """
        
        # Case 1: Multiplying by another EmotionAnnotation object
        if isinstance(other, (int, float)):
            new_activation = self.activation * other
            # The name remains the same when scaling
            return EmotionAnnotation(name=self.name, activation=new_activation)
        
        # If the type is not recognized
        else:
            return NotImplemented
            
    # --- Reverse Multiplication for scalar * object ---
    def __rmul__(self, other):
        """
        Enables scalar * EmotionAnnotation (e.g., 2.0 * a).
        By default, if 2.0 * a is called, Python tries 2.0.__mul__(a).
        Since 'float' doesn't know how to multiply an EmotionAnnotation, 
        it returns NotImplemented, and Python then calls a.__rmul__(2.0).
        """
        # We can simply reuse the standard multiplication logic
        return self.__mul__(other)
    
    # --- Greater Than Implementation (Required for max()) ---
    def __gt__(self, other):
        """Overloads the '>' operator. Compares based on activation."""
        if isinstance(other, EmotionAnnotation):
            return self.activation > other.activation
        return NotImplemented

    # --- Less Than Implementation (Required for max()) ---
    def __lt__(self, other):
        """Overloads the '<' operator. Compares based on activation."""
        if isinstance(other, EmotionAnnotation):
            return self.activation < other.activation
        return NotImplemented


class Event(BaseModel):
    """Base event model"""
    event_id: str = Field(description="unique identifier of the event")
    session_id: str = Field(description="unique session/discussion ID of event")
    timestamp: datetime = Field(description="timestamp of event occurrence")
    payload: Dict = Field(description="associated raw data", default={})

class AffectiveEvent(Event):
    """
    Output from an emotion recognition model, per modality, with associated payload.

    For messages, the assumed structure of payload:
    {
        "content": str
        "session_id": str
    }
    """
    
    participant_id: str = Field(description="unique ID of participant generating the event")
    modality: Literal["vision", "audio", "text"] = Field(description="Modality of input data")
    emotion_activations: List[EmotionAnnotation] = Field(
        default=[],  # should generally be populated, but optional in case Hume API fails
        # min_length=len(HUME_EMOTIONS_LIST_VISION_AUDIO),
        max_length=len(HUME_EMOTIONS_LIST_TEXT),
        description="Array of all emotions with corresponding activations",
    )


    def to_human_message(self) -> HumanMessage:
        """Converts the affective event into an LLM compatible human message"""

            
        participant = self.participant_id
        
        structured_content = f'''
        User {participant} sent: {self.payload.get("content")}
        '''

        return HumanMessage(
            content=structured_content,
            additional_kwargs={
                'participant_id': participant,
                'timestamp': self.timestamp,
            }
        )

    @staticmethod
    def create_from_raw(raw: dict) -> "AffectiveEvent":
        """
        Factory method to create an affective event.
        """

        dt_object = datetime.fromisoformat(
            raw["timestamp"].replace('Z', '+00:00') 
            if raw["timestamp"].endswith('Z')
            else raw["timestamp"]
        )
        if raw['emotion_activations'] is None:
            raw['emotion_activations'] = []

        return AffectiveEvent(
            event_id=raw["event_id"],
            participant_id=raw["participant_id"],
            timestamp=dt_object,
            modality=raw["modality"],
            emotion_activations=[
                EmotionAnnotation(name=emo["name"], activation=emo["activation"])
                for emo in raw.get("emotion_activations", [])
            ],
            payload=raw.get("payload", {}),
        )


class AffectiveState(BaseModel):
    """
    The participant's affective state captures and tracks their emotional state across modalities during conversation.

    The affective state gets updated with every affective 'event' that pertains to the participant --
    a facial expression, vocal burst, or emotional content of message they sent.
    """

    participant_id: str = Field(description="participant id")
    
    last_update: datetime = Field(description="timestamp of the affective state")
    
    running_states: Mapping[Literal[*SUPPORTED_MODALITIES], List[EmotionAnnotation]] = Field(  # type:ignore
        description="Vector representations of participant's emotions extracted from different modalities"
    )
    
    dominant_emotions: List[EmotionAnnotation] = Field(
        default_factory=list,
        description="Dominant emotions extracted from all running states"
    )

    dominant_emotion_threshold: float = 0.55
    
    def update(self, event: AffectiveEvent) -> Tuple[bool, str]:
        """
        Updates the affective state of a participant given a new affective event, in place

        Returns the status of the update with error message if failed.
        """

        new_activations = sorted(event.emotion_activations, key=lambda emotion: emotion.name)

        # Update emotion activations of modality
        if not self.running_states.get(event.modality):
            self.running_states[event.modality] = new_activations
        else:
            try:
                self.running_states[event.modality] = [
                    self._update_running_emotion(curr, new)
                    for curr, new
                    in zip(self.running_states[event.modality], new_activations)
                ]
            except Exception as e:
                return (False, f"Could not update state with new event, reason {e}")

        # extract the dominant emotions 
        self._update_dominant_emotions()

        self.last_update = event.timestamp
        return (True, "")

    def _update_dominant_emotions(self):
        self.dominant_emotions = list(
            set.union(*[
                self.extract_dominant_emotions(self.running_states[modality])
                for modality in SUPPORTED_MODALITIES
            ])
        )

    @staticmethod
    def _update_running_emotion(old, new):
        return 0.75 * old + 0.25 * new

    def extract_dominant_emotions(self, activations: List[EmotionAnnotation]) -> Set[EmotionAnnotation]:
        """
        Extract dominant emotions from activation vector based on a threshold.
        """
        if not activations or activations == []:
            return set()
        
        return set([emo for emo in activations if emo.activation >= self.dominant_emotion_threshold])
    
    def to_message(self) -> HumanMessage:
        """
        Converts an affective state into a message, summarizing the state of the participant
        """

        dominant_emotions_str = (
            "none" if len(self.dominant_emotions) == 0
            else ", ".join([e.__repr__() for e in self.dominant_emotions])
        )

        content = f"my affective sensors have reported the following strong emotions: {dominant_emotions_str}"

        return create_human_message_from_raw(
            raw_message={
                "id": "",
                "content": content,
                "senderId": self.participant_id,
                "ts": self.last_update
            }
        )


class GroupAffectiveState(BaseModel):
    
    max_group_activations: List = Field(description="maximum activations per emotion")
    
    group_emotion_distribution: Counter = Field(description="distribution of emotions across participants")


class AffectiveWindow(BaseModel):
    """
    A dynamic, rolling window of messages, affective states, and metadata for the Mediator to reason over
    when deciding whether to intervene in the group chat.

    There should be only one active affective window per discussion at any given time, 
    and it should capture the most recent messages and affective states of participants that the model hasn't seen yet.
    As a direct consequence of this, affective windows cannot overlap in time or in content.

    Given the timeliness requirement of interventions, the window has a short but dynamic lifespan,
    which is determined by the Mediator agent when the window is created.

    Parameters:
        discussion_id: Unique identifier of the group discussion.
        first_message: The first message that triggered the creation of the window.
        lifespan: Lifespan of the window in seconds, prescribed by the Mediator agent.
    """

    window_id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique identifier of the affective window")
    
    discussion_id: str = Field(description="Unique identifier of the group discussion")
    
    first_message: AnyMessage = Field(description="The first message that triggered the creation of the window")
    
    all_messages: List[AnyMessage] = Field(default_factory=list, description="All messages since window creation")
    
    start_time: datetime = Field(default_factory=datetime.now, description="Window creation timestamp")
    
    expiration_time: datetime = Field(description="Timestamp when window expires")
    
    # keys of affective states in redis cache
    affective_states: List[str] = Field(default_factory=list, description="Recent affective states of participants")

    last_update: datetime = Field(description="timestamp of most recent event recorded in the window")


    @classmethod
    def create(cls, discussion_id: str, first_message: AnyMessage, affective_states = [], lifespan: int = 5):
        start_time = datetime.now()
        return cls(
            discussion_id=discussion_id,
            first_message=first_message,
            all_messages=[first_message],
            start_time=start_time,
            expiration_time=start_time + timedelta(seconds=lifespan),
            affective_states=affective_states,
            last_update=start_time,
        )

    def is_expired(self) -> bool:
        """Check if the window has expired."""
        return datetime.now() >= self.expiration_time
    
    def add_event(self, event: AffectiveEvent) -> None:
        """Add a new message to the window."""

        if event.modality == "text":
            new_message = event.to_human_message()
            self.all_messages.append(new_message)
        self.last_update = event.timestamp


    def aggregate_affective_states(self) -> GroupAffectiveState:
        """
        Aggregate individual affective states to describe the group's overall affective state.
        """
        def max_pooling(emotion_vectors: Iterable[List[EmotionAnnotation]]):
            
            activations_dict = defaultdict(list)
            for v in emotion_vectors:
                for e in v:
                    activations_dict[e.name].append(e.activation)
            
            return [EmotionAnnotation(name=e, activation=max(activations_dict[e])) for e in activations_dict]
        
        # max activations per participant across all modalities
        max_activation_per_participant = {
            s.participant_id: max_pooling(s.running_states.values())
            for s in self.affective_states
        }
        # max activations actoss all participants
        max_group_activations = max_pooling(max_activation_per_participant.values())
        
        all_dominant_emotions = itertools.chain.from_iterable(s.dominant_emotions for s in self.affective_states)
        all_dominant_emotions: List[str] = [e.name for e in all_dominant_emotions]
        group_emotion_distribution = Counter(all_dominant_emotions)

        group_affective_state = GroupAffectiveState(
            max_group_activations=max_group_activations,
            group_emotion_distribution=group_emotion_distribution,
        )

        return group_affective_state

    def to_graph_state(self, exclude_first_message=True) -> Dict:
        """
        Summarize all content and affective states within the window
        for mediator's context when deciding on interventions.
        """
        
        return {"last_affective_window": self}
    
    def to_system_message(self) -> SystemMessage:
        """
        Creates a textual report of the group's affective state from all the data,
        and returns it a system message ready for agent ingestion.
        """
        group_state = self.aggregate_affective_states()

        top_group_emotions: List[EmotionAnnotation] = sorted(group_state.max_group_activations, key = lambda e: e.activation, reverse=True)[:5]
        distribution = group_state.group_emotion_distribution

        participant_lines = []
        for s in self.affective_states:
            participant_lines.append(f'*  {s.to_message().content}')
        participant_breakdown = "\n".join(participant_lines)

        report_content = (
            "### Group Affective State Report\n"
            f"\nTime range: {datetime_to_string(self.start_time)} - {datetime_to_string(self.expiration_time)}:\n"
            f"\nTop 5 emotions observed in the group: **{top_group_emotions}**\n"
            f"\nDistribution of dominant emotions across the participants: {distribution}\n"
            "\n#### Participant Breakdown:\n"
            f"\n{participant_breakdown}\n"
        )
        return SystemMessage(content=report_content, name="Affect_Monitor")
    


