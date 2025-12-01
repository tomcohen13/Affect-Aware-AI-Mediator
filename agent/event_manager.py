"""
EventManager that consumes AffectiveEvent objects written by the frontend.

Frontend writes:
  /{studyId}/states/{sessionId}/events/{eventId} = AffectiveEvent (JSON)

Here we:
  - listen to /states
  - on new events/{eventId}, update / create an affective window per session
  - when window closes, call mediator, and optionally write a 'mediator' chat message
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Dict

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import firebase_admin
from firebase_admin import credentials, db

from agent.affective_mediator import AffectiveMediator
from agent.base_models import (
    AffectiveEvent,
    AffectiveState,
    AffectiveWindow,
    EmotionAnnotation,
)
from agent.constants import (
    HUME_EMOTIONS_LIST_TEXT,
    HUME_EMOTIONS_LIST_VISION_AUDIO,
)
from agent.utils import create_human_message_from_raw, datetime_to_string

class EventManager:
    """
    EventManager watches RTDB and coordinates with the AffectiveMediator.

    One EventManager instance typically runs as a single process, listening to a
    particular studyId (e.g. 'pilot-nov28').
    """

    def __init__(
        self,
        study_id: str,
        mediator: AffectiveMediator,
        database_url: str,
        service_account_str: str,
        window_seconds: int = 30,
        cooldown_seconds: int = 60,
    ):
        self.study_id = study_id
        self.mediator = mediator
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds

        self.logger = logging.getLogger("EventManager")
        self.logger.setLevel(logging.INFO)
        self.mediator.logger = self.logger

        # maps "session_id/participant_id" -> affective state
        self.affective_states: Dict[str, AffectiveState] = {}
        # key: sessionId -> WindowState
        self.windows: Dict[str, AffectiveWindow] = {}

        # Firebase admin init (idempotent)
        if not firebase_admin._apps:
            service_account_json = json.loads(service_account_str)
            cred = credentials.Certificate(service_account_json)
            firebase_admin.initialize_app(cred, {"databaseURL": database_url})

        self._listener = None

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def start(self):
        """Start listening to RTDB state changes."""
        states_ref = db.reference(f"{self.study_id}/states")
        self.logger.info("Starting RTDB listener at %s/states", self.study_id)
        self._listener = states_ref.listen(self._on_state_event)

    def stop(self):
        """Stop RTDB listener (if any)."""
        if self._listener is not None:
            self.logger.info("Stopping RTDB listener")
            self._listener.close()
            self._listener = None

    # -------------------------------------------------------------------------
    # RTDB event callback
    # -------------------------------------------------------------------------

    def _on_state_event(self, event):
        """
        Firebase callback signature:
          event.event_type: 'put' | 'patch'
          event.path: path from the reference we listened on.
                      e.g. '/' for the initial full dump,
                           '/-SESSION_ID/events/EVENT_ID'
          event.data: the value at that path
        """
        if event.path == "/" or event.data is None:
            return

        path = event.path.lstrip("/")  # e.g. '-SESSION_ID/events/EVENT_ID'
        parts = path.split("/")
        if len(parts) < 3:
            return

        session_id, maybe_events, event_id = parts[:3]
        if maybe_events != "events":
            return

        ev = event.data
        if not isinstance(ev, dict):
            return

        # run coroutine in this thread (firebase-admin listener has no loop)
        asyncio.run(self.handle_new_event(session_id, event_id, ev))

    # -------------------------------------------------------------------------
    # Core logic: window management
    # -------------------------------------------------------------------------

    async def handle_new_event(self, session_id: str, event_id: str, ev: dict):
        """
        Called for each new AffectiveEvent.

        ev schema (from frontend / base_models.AffectiveEvent):
        {
          "event_id": str,
          "participant_id": str,
          "timestamp": ISO8601 string,
          "modality": "text" | "vision" | "audio",
          "emotion_activations": [...],
          "payload": {
            raw sensory input. For example, a message would have the following attributes:
            content: str
            ts: unix timestamp
            senderId: str
            }
        }
        """
        # TODO: handle AI message from mediator

        self.logger.info(str(ev))

        try:
            event = AffectiveEvent.create_from_raw(ev)  # validate input
        except Exception as e:
            self.logger.error(f"Could not parse event {ev}, error: {e}. skipping.")
            return
        
        if event.emotion_activations == []:
            self.logger.warn(f"Event {event.event_id} from session {session_id} did not have any annotations")


        self.logger.info(f"Updating affective state of participant: {event.participant_id}")
        self._update_affective_state_of_participant(session_id=session_id, event=event)

        # 2. check for existing window
        window = self.windows.get(session_id)


        if window:
            
            if not window.is_expired():
                # active window exists, add event and move on to next event
                window.add_event(event=event)
                # self.logger.info(f"Active window exists (id: {window.window_id}), added {event}.")
                return
            
            else:
                # Window expired, clear out from session and send to model
                window = window.model_copy()
                del self.windows[session_id]
                
                response = await self.mediator.run(window, pathway="should_intervene")

                decision = response['last_intervention_decision']

                if decision.should_intervene:
                    
                    # create new message in chat
                    new_message = {
                        "id": str(uuid.uuid4()),
                        "content": decision.intervention_message,
                        "type": "mediator",
                        "senderId": "__mediator__",
                        "ts": int(datetime.now(timezone.utc).timestamp()),
                    }
                    db.reference(
                        f"{self.study_id}/states/{session_id}/chat/messages/{new_message['id']}"
                    ).set(new_message)
                else:
                    # no intervention needed, continue
                    pass

        if event.modality == "text":
            # No active window

            conversation_meta = db.reference(f"{self.study_id}/states/{session_id}/meta").get()
            if conversation_meta is None: 
                conversation_meta = {}
            
            affective_package = {  # ooops too much?
                "discussion_id": session_id,
                "event": event,
                "affective_sperm": self.affective_states[f"{session_id}/{event.participant_id}"],
                "meta": conversation_meta
            }
            
            _ = await self.mediator.run(affective_package, pathway="is_interesting")
            # now let's check the state of the graph
            next_step = self.mediator.graph.get_state(config={'configurable': {'thread_id': session_id}}).next
            if next_step == ():
                # not interesting, break
                self.logger.info("decided not interesting!")
                return
            
             # TODO: instead of in-memory move to redis
            self.windows[session_id] = AffectiveWindow.create(
                discussion_id=session_id,
                first_message=event.to_human_message(),
                affective_states=[state for state in self.affective_states.values()],
            )
          
            self.logger.info("Opened affective window for session: %s, (event %s)")
            return


    def _update_affective_state_of_participant(self, session_id: str, event: AffectiveEvent):
        """
        Update the Affective State of a participant given a new event generated by them.
        """

        # Fetch affective state of sender
        affective_state = self.affective_states.get(f"{session_id}/{event.participant_id}")
        if affective_state is None:
            # Create affective state for participant
            affective_state = AffectiveState(
                participant_id=event.participant_id,
                last_update=event.timestamp,
                running_states={
                    "text": [EmotionAnnotation(name=name, activation=0.5) for name in HUME_EMOTIONS_LIST_TEXT],
                    "vision": [EmotionAnnotation(name=name, activation=0.5) for name in HUME_EMOTIONS_LIST_VISION_AUDIO],
                    "audio": [EmotionAnnotation(name=name, activation=0.5) for name in HUME_EMOTIONS_LIST_VISION_AUDIO],
                }
            )
            self.affective_states[f"{session_id}/{event.participant_id}"] = affective_state
        
        if event.emotion_activations != []:
            success, reason = affective_state.update(event)
            if not success:
                self.logger.error(reason)

            else:
                self.logger.info(
                    f"Updated affective state of participant {event.participant_id}. "
                    f"Dominant emotions: {affective_state.dominant_emotions}."
                )

            affective_state_row = affective_state.model_dump()
            affective_state_row['last_update'] = datetime_to_string(affective_state_row['last_update'])
            db.reference(f"{self.study_id}/states/{session_id}/affect/{event.participant_id}").set(affective_state_row)
