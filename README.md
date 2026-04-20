# Affective Mediator Agent: Context Window and Information Flow

This document summarizes the context window and information flow at different stages of the Affective Mediator agent's execution pipeline.

## Overview

The Affective Mediator (CHARLIE) is an affect-aware AI agent that monitors online group discussions and intervenes when necessary to promote positive interactions. The system operates through two main components:

1. **EventManager**: Listens to Firebase RTDB for affective events and manages temporal windows
2. **AffectiveMediator**: Contains the decision-making workflow using LangGraph

## Execution Pipeline

The agent follows a multi-stage pipeline with distinct context windows at each stage:

```
New Event → Is Interesting? → Affective Window → Should Intervene? → Intervention
```

---

## Stage 1: Event Reception

**Location**: `EventManager.handle_new_event()`

### Context Window
- **Input**: Raw Firebase event data
- **Data Structure**: 
  ```python
  {
    "event_id": str,
    "participant_id": str,
    "timestamp": ISO8601 string,
    "modality": "text" | "vision" | "audio",
    "emotion_activations": [EmotionAnnotation],
    "payload": {
      "content": str,  # for text messages
      "ts": unix timestamp,
      "senderId": str
    }
  }
  ```

### Information Flow
1. Event received from Firebase RTDB listener
2. Event parsed into `AffectiveEvent` object
3. Affective state of participant updated (running emotional state across modalities)
4. Decision point: Check if active window exists

### State Updates
- `EventManager.affective_states[session_id/participant_id]` updated with new emotion activations
- Running states use exponential moving average: `0.5 * old + 0.5 * new`
- Dominant emotions extracted (threshold: 0.6 activation)

---

## Stage 2: Is Interesting? (Fast Gating)

**Location**: `AffectiveMediator.is_interesting()`

### Context Window
- **Model**: Fast gating model (`gating_model`)
- **Input Messages**:
  1. System prompt: `is_interesting_prompt.txt`
  2. Human message: Last message content from discussion
     ```python
     f"User {participant_id} sent: {message_content}"
     ```

### Information Flow
- **Trigger**: New text event with no active window
- **Input**:
  ```python
  {
    "discussion_id": unique discussion id,
    "event": {
      "event_id": str,
      "participant_id": str,
      "timestamp": ISO8601 string,
      "modality": "text" | "vision" | "audio",
      "emotion_activations": [...],
      "payload": {
        "content": str
        "session_id": str
        }
    }
  }
  ```
- **Graph State Initialization** (if first event):
  - `discussion_id`: session_id
  - `topic`: topicId (from meta)
  - `condition`: condition (from meta)
  - `messages`: [event.to_human_message()]

### Decision Output
- **Type**: `IsInterestingDecision`
- **Fields**:
  - `is_interesting`: bool
  - `reason`: Optional[str]

### Routing
- `is_interesting == True` → Continue to "affective_window" node
- `is_interesting == False` → END (no window created)

---

## Stage 3: Affective Window Creation & Management

**Location**: `EventManager` (window creation) + `AffectiveMediator.affective_window()` (placeholder)

### Context Window
- **Window Structure**: `AffectiveWindow`
  ```python
  {
    "window_id": UUID,
    "discussion_id": str,
    "first_message": HumanMessage,
    "all_messages": List[HumanMessage],  # accumulates during window lifetime
    "start_time": datetime,
    "expiration_time": datetime,  # start_time + lifespan (default: 5 seconds)
    "affective_states": List[AffectiveState],  # snapshot at window creation
    "last_update": datetime
  }
  ```

### Information Flow
1. **Window Creation** (when `is_interesting == True`):
   - Creates new `AffectiveWindow` with:
     - First message: triggering event
     - Affective states: snapshot of all participants' current states
     - Default lifespan: 5 seconds (configurable)
   
2. **Window Updates** (while active):
   - New events added to `all_messages` (if text modality)
   - `last_update` timestamp refreshed
   - Window stored in `EventManager.windows[session_id]`

3. **Window Expiration Check**:
   - On each new event, check if `datetime.now() >= expiration_time`
   - If expired: window sent to mediator for intervention decision

### State Management
- Windows stored in-memory: `EventManager.windows[session_id]`
- Only one active window per session at a time
- Windows cannot overlap in time or content

---

## Stage 4: Should Intervene? (Reasoning Decision)

**Location**: `AffectiveMediator.should_intervene()`

### Context Window
- **Model**: Reasoning model (`reasoning_model`)
- **Input Messages**:
  1. System prompt: `should_intervene_prompt.txt`
  2. All messages in window: `window.all_messages` (HumanMessage objects)
  3. Group affective state report: `window.to_model_context()` (SystemMessage)
     - Time range of window
     - Top 5 emotions observed in group
     - Distribution of dominant emotions across participants
     - Per-participant breakdown of dominant emotions

### Information Flow
1. **State Update** (time-travel style):
   ```python
   new_values = window.to_graph_state(exclude_first_message=True)
   # Sets: {"last_affective_window": window}
   ```
   - Graph state updated with window at "affective_window" node
   
2. **Cooldown Check**:
   - If `last_intervention_time` exists and within cooldown period → skip decision
   - Returns: `ShouldInterveneDecision(should_intervene=False, reason="<COOLDOWN_PERIOD_ACTIVE>")`

3. **Window Validation**:
   - If `last_affective_window` is None → skip decision
   - Returns: `ShouldInterveneDecision(should_intervene=False, reason=NO_AFFECTIVE_WINDOW_RECEIVED_TOKEN)`

4. **Model Reasoning**:
   - Model receives:
     - System prompt with intervention guidelines
     - All messages in the window (chronological sequence)
     - Aggregated group affective state report

### Group Affective State Report Structure
```python
"""
### Group Affective State Report

Time range: {start_time} - {expiration_time}:

Top 5 emotions observed in the group: **{top_group_emotions}**

Distribution of dominant emotions across the participants: {distribution}

#### Participant Breakdown:

*  {participant_1_affective_summary}
*  {participant_2_affective_summary}
...
"""
```

### Decision Output
- **Type**: `ShouldInterveneDecision`
- **Fields**:
  - `should_intervene`: bool
  - `intervention_message`: Optional[str] (if should_intervene == True)
  - `reason`: Optional[str]

### State Updates
- `last_intervention_decision`: ShouldInterveneDecision
- `messages`: Full message sequence sent to model (for logging/debugging)

### Routing
- `should_intervene == True` → Continue to "intervene" node
- `should_intervene == False` → END

---

## Stage 5: Intervention

**Location**: `AffectiveMediator.send_intervention()` (placeholder) + `EventManager` (message writing)

### Context Window
- **Input**: Current graph state with `last_intervention_decision`
- **Intervention Message**: `decision.intervention_message`

### Information Flow
1. **Message Creation**:
   ```python
   {
     "id": UUID,
     "content": decision.intervention_message,
     "type": "mediator",
     "senderId": "__mediator__",
     "ts": current_timestamp
   }
   ```

2. **Firebase Write**:
   - Message written to: `/{study_id}/states/{session_id}/chat/messages/{message_id}`
   - Appears in chat as mediator message

3. **State Updates**:
   - `last_intervention_time`: Current timestamp
   - Cooldown period activated (prevents rapid successive interventions)

### Cooldown Mechanism
- Default cooldown: 30 seconds (configurable via `post_intervention_cooldown`)
- Prevents mediator from intervening too frequently
- Checked in `should_intervene()` before making decision

---

## Graph State Schema

**Location**: `GroupDiscussionState` (extends `AgentState`)

### Persistent State Fields
```python
{
  "discussion_id": str,
  "topic": str,
  "condition": "none" | "no_affect" | "affect",
  "messages": List[AnyMessage],  # inherited from AgentState
  "chat_summary": str,  # running summary (via SummarizationMiddleware)
  "last_affective_window": Optional[AffectiveWindow],
  "last_intervention_decision": ShouldInterveneDecision,
  "last_intervention_time": Optional[datetime],
  "post_intervention_cooldown": int  # default: 30 seconds
}
```

### State Persistence
- Uses LangGraph `MemorySaver` checkpointer (in-memory by default)
- Thread ID = `discussion_id` (session_id)
- State persists across multiple events in the same discussion

---

## Middleware & Context Management

### PIIMiddleware
- **Purpose**: Redact personal information (e.g., emails)
- **Strategy**: Redaction
- **Applied**: To all messages in the agent workflow

### SummarizationMiddleware
- **Purpose**: Maintain running summary of chat to manage context window
- **Model**: Fast model (`gating_model`)
- **Trigger**: When messages exceed `max_tokens_before_summary` (1000 tokens)
- **Effect**: Older messages summarized, reducing token usage

---

## Key Data Structures

### AffectiveEvent
- Represents a single event with emotion annotations
- Contains: event_id, participant_id, timestamp, modality, emotion_activations, payload
- Can convert to `HumanMessage` for LLM consumption

### AffectiveState
- Tracks participant's emotional state across modalities (text, vision, audio)
- Maintains running states per modality (exponential moving average)
- Extracts dominant emotions (threshold: 0.6)
- Updates with each new event from that participant

### AffectiveWindow
- Temporal window capturing messages and affective states
- Default lifespan: 5 seconds
- Aggregates individual states into group affective state
- Provides rich context for intervention decisions

---

## Information Flow Summary

```
Firebase RTDB Event
    ↓
EventManager.handle_new_event()
    ↓
Update AffectiveState (participant)
    ↓
[Active Window Exists?]
    ├─ Yes → Add event to window
    │         ↓
    │    [Window Expired?]
    │         ├─ Yes → Send to mediator (should_intervene)
    │         └─ No → Return
    │
    └─ No → [Event is text?]
              ├─ Yes → Send to mediator (is_interesting)
              │         ↓
              │    [Is Interesting?]
              │         ├─ Yes → Create AffectiveWindow
              │         └─ No → Return
              └─ No → Return

[Should Intervene?]
    ├─ Yes → Write intervention message to Firebase
    └─ No → Return
```

---

## Context Window Sizes

| Stage | Model | Input Size | Notes |
|-------|-------|------------|-------|
| Is Interesting | Fast (gating) | ~1 message + system prompt | Single message evaluation |
| Should Intervene | Reasoning | Variable (window size) | All messages in window + group state report |
| Intervention | N/A | Decision object only | No model call, just message writing |

### Token Management
- SummarizationMiddleware prevents unbounded growth
- Window-based approach limits temporal scope
- Group state report provides compact summary of affective information

---

## Notes

- Windows are non-overlapping and sequential
- Only one active window per session
- Cooldown period prevents intervention spam
- State persists across events via LangGraph checkpointer
- Affective states are continuously updated, not just at window creation

