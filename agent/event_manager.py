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
import os
import redis  # TODO: replace in-memory windows with redis
from datetime import datetime, timedelta, timezone
from typing import Dict

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import firebase_admin
from firebase_admin import credentials, db

from agent.affective_mediator import AffectiveMediator
from agent.base_models import (
    AffectiveEvent,
    AffectiveState,
    AffectiveWindow,
    EmotionAnnotation,
    IsInterestingDecision,
    ShouldInterveneDecision,
)
from agent.constants import (
    AFFECTIVE_WINDOW_DEFAULT_LIFESPAN,
    CONVERSATION_STARTED_TOKEN,
    HUME_EMOTIONS_LIST_TEXT,
    HUME_EMOTIONS_LIST_VISION_AUDIO,
)
from agent.utils import create_raw_message, datetime_to_string

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
        firebase_url: str,
        redis_client: redis.Redis, 
        service_account_str: str,
    ):
        self.study_id = study_id
        self.mediator = mediator
        self.redis_client = redis_client

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
            firebase_admin.initialize_app(cred, {"databaseURL": firebase_url})

        self._listener = None

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def start(self):
        """Start listening to RTDB state changes."""
        states_ref = db.reference(f"{self.study_id}/states")
        self._loop = asyncio.get_running_loop()
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

        parts = event.path.lstrip("/").split("/")  # e.g. '-SESSION_ID/events/EVENT_ID'
        if len(parts) < 3:
            return

        session_id, maybe_events, event_id = parts[:3]
        if maybe_events != "events":
            return

        # run coroutine in this thread (firebase-admin listener has no loop)
        try:
            asyncio.run_coroutine_threadsafe(self.handle_new_event(session_id, event.data), self._loop)
        except Exception as e:
            self.logger.error(f"There was an error processing event {event_id}: {e}")

    # -------------------------------------------------------------------------
    # Core logic: window management
    # -------------------------------------------------------------------------

    async def handle_new_event(self, session_id: str, ev: dict):
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
            content: str
            session_id: str
            }
        }
        """
        # obtain 'lock' for processing event, or drop (other instance did)
        if not await self.redis_client.set(f"processed:{ev['event_id']}", "1", ex=30, nx=True):
            return

        if ev.get("text", "") == CONVERSATION_STARTED_TOKEN:
            # synthesize initial message from initial responses and send in chat
            self.logger.info(f"Conversation started! session id: {session_id}")

            # fetch initial responses and send first message from mediator
            session_data = db.reference(f"{self.study_id}/states/{session_id}/").get()
            metadata = session_data.get('meta')
            initial_responses = {
                pid: response.get('text', '')
                for pid, response
                in session_data.get('initial_responses', {}).items()
            }

            response: str = await self.mediator.start_discussion(
                discussion_id=session_id,
                initial_responses=initial_responses,
                topic_id=metadata.get('topicId'),
                condition=metadata.get('condition')
            )

            # create new message in chat
            new_message = create_raw_message(
                content=response,
                type="mediator",
                sender_id=self.mediator.name,
            )

            db.reference(
                f"{self.study_id}/states/{session_id}/chat/messages/{new_message['id']}"
            ).set(new_message)

            return 
            

        try:
            event = AffectiveEvent.create_from_raw(ev)  # validate input
        except Exception as e:
            self.logger.error(f"Could not parse event {ev}, error: {e}. skipping.")
            return
        
        self.logger.info(
            f"[NEW EVENT] {event.timestamp} | Participant: {event.participant_id} | " 
            f"modality: {event.modality} | payload {event.payload} "
        )
        
        if event.emotion_activations == []:
            self.logger.warn(f"Event {event.event_id} from session {session_id} did not have any annotations")

        self._update_affective_state_of_participant(session_id=session_id, event=event)

        # 2. check for existing window
        window = self.windows.get(session_id)


        if window:
            
            if not window.is_expired():
                # active window exists, add event and move on to next event
                window.add_event(event=event)

                # expand window slightly if messages are coming in
                if event.modality == "text":
                    window.expiration_time += timedelta(seconds=2)
                return
            
            else:
                # Window expired, clear out from session and send to model
                window = window.model_copy()
                del self.windows[session_id]
                
                last_update = await self.mediator.run(window, pathway='should_intervene')
                decision: ShouldInterveneDecision = last_update['should_intervene']['last_intervention_decision']

                if decision.should_intervene:
                    
                    # send message in chat
                    new_message = create_raw_message(
                        content=decision.intervention_message,
                        type="mediator",
                        sender_id=self.mediator.name,
                    )
                    try:
                        db.reference(f"{self.study_id}/states/{session_id}/chat/messages/{new_message['id']}").set(new_message)
                    except Exception as e:
                        self.logger.error(f"Couldn't write message {new_message} to DB: {e}")
                
                # regardless, update 'charlie' path in DB with window
                path = f"{self.study_id}/states/{session_id}/charlie/{int(datetime.now().timestamp())}-should_intervene"
                try:
                    db.reference(path).set(
                        {
                            'context': {
                                'window': window.to_system_message().content,
                                'trigger': window.first_message.content,
                            },
                            'decision': decision.model_dump(),
                        }
                    )
                except Exception as e:
                    self.logger.error(f"Couldn't right decision {decision} to DB: {e}")

        if event.modality == "text":
            # No active window
            
            affective_package = {  # ooops too much?
                "discussion_id": session_id,
                "event": event,
                "affective_sperm": self.affective_states[f"{session_id}/{event.participant_id}"],
            }
            
            decision: IsInterestingDecision = await self.mediator.run(affective_package, pathway="is_interesting")
            
            if not decision.is_interesting:
                self.logger.info(f"[AGENT] message: {event.payload['content']} | Decision: do NOT trigger a window.")
            else:
                # TODO: instead of in-memory move to redis
                self.logger.info(f"[EM] Starting affective window for session: {session_id}")
                self.windows[session_id] = AffectiveWindow.create(
                    discussion_id=session_id,
                    first_message=event.to_human_message(),
                    affective_states=[state for state in self.affective_states.values()],  # link to current states
                    lifespan=AFFECTIVE_WINDOW_DEFAULT_LIFESPAN,
                )

            # write decision to DB
            # TODO: move all paths to a path generator function for consistecy!
            path = f"{self.study_id}/states/{session_id}/charlie/{int(datetime.now().timestamp())}-is_interesting"
            payload = {
                "message": event.payload,
                "decision": decision.model_dump()
            }
            try:
                db.reference(path).set(payload)  
            except Exception as e:
                self.logger.error(f"Could not write decision to RTDB: {e}")
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
                    "text": [EmotionAnnotation(name=name, activation=0.3) for name in HUME_EMOTIONS_LIST_TEXT],
                    "vision": [EmotionAnnotation(name=name, activation=0.3) for name in HUME_EMOTIONS_LIST_VISION_AUDIO],
                    "audio": [EmotionAnnotation(name=name, activation=0.3) for name in HUME_EMOTIONS_LIST_VISION_AUDIO],
                }
            )
            self.affective_states[f"{session_id}/{event.participant_id}"] = affective_state
        
        if event.emotion_activations != []:
            success, reason = affective_state.update(event)
            if not success:
                self.logger.error(reason)
            else:
                affective_state_row = affective_state.model_dump()
                affective_state_row['last_update'] = datetime_to_string(affective_state_row['last_update'])
                db.reference(f"{self.study_id}/states/{session_id}/affect/{event.participant_id}").set(affective_state_row)
                self.logger.info(f"Wrote new affective state of {event.participant_id} into --> {self.study_id}/states/{session_id}/affect/{event.participant_id}")
                self.logger.info(
                    f"[AFFECTIVE STATE] Updated affective state of participant {event.participant_id} "
                    f"into --> {self.study_id}/states/{session_id}/affect/{event.participant_id}. "
                    f"Dominant emotions: {affective_state.dominant_emotions}."
                )
