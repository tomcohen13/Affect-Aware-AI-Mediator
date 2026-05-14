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
from langchain_core.messages import AIMessage
from pydantic import ValidationError
import redis  # TODO: replace in-memory windows with redis
from datetime import datetime
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
from agent.utils import create_raw_message, redis_key

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
        redis_client: redis.Redis,
        firebase_url: str,
        service_account_str: str,
    ):
        self.study_id = study_id
        self.instance_id = os.getenv("RENDER_INSTANCE_ID", "local")
        self.mediator = mediator
        self.redis_client = redis_client

        self.logger = logging.getLogger("EventManager")
        self.logger.setLevel(logging.INFO)
        self.mediator.logger = self.logger

        # Firebase admin init (idempotent)
        if not firebase_admin._apps:
            service_account_json = json.loads(service_account_str)
            cred = credentials.Certificate(service_account_json)
            firebase_admin.initialize_app(cred, {"databaseURL": firebase_url})


    async def start(self):
        """Start EventManager, lister on new events from Redis Pubsub."""
        try:
            pubsub = self.redis_client.pubsub(ignore_subscribe_messages=True)
            await pubsub.subscribe("events")
            self.logger.info("Subscribed to 'events' channel.")

            async for message in pubsub.listen():
                if message is None:
                    self.logger.debug("Listener heartbeat...")
                try:
                    # {'type': , 'pattern': , 'channel': , 'data': }
                    event_dict = json.loads(message['data'])
                    event = AffectiveEvent.model_validate(event_dict)
                    
                
                except (json.JSONDecodeError, ValidationError) as e:
                    self.logger.exception("Failed to parse incoming event: %s", e)
                    continue
                
                self.logger.info("[Instance: %s] Received event %s", self.instance_id, event.event_id)

                try:
                    asyncio.create_task(self.handle_new_event(event))
                
                except Exception as e:
                    self.logger.exception("Error processing event %s: %s", event.event_id, e)

        except Exception as e:
            self.logger.exception("Redis pub/sub listener crashed: %s", e)
            self.logger.info("Reconnecting in 2 seconds...")
            await asyncio.sleep(2)

        finally:
            try:
                await pubsub.unsubscribe("events")
                await pubsub.close()
            except Exception:
                pass


    def stop(self):
        """Stop RTDB listener (if any)."""
        if self._listener is not None:
            self.logger.info("Stopping RTDB listener")
            self._listener.close()
            self._listener = None


    async def handle_new_event(self, event: AffectiveEvent):
        """
        Called for each new AffectiveEvent.

        event schema (from frontend / base_models.AffectiveEvent):
        {
          "event_id": str,
          "participant_id": str,
          "timestamp": ISO8601 string,
          "modality": "text" | "vision" | "audio",
          "emotion_activations": [...],
          "payload": {
                ...
            }
        }
        """
        # obtain 'lock' for processing event, or drop (other instance did)
        if not await self.redis_client.set(redis_key(status="processed", event_id=event.event_id), "1", ex=300, nx=True):
            return

        # TODO: make that entire thing into different API endpoint for starting discussion?
        if event.payload.get("text") == CONVERSATION_STARTED_TOKEN:
            # synthesize initial message from initial responses and send in chat
            self.logger.info(f"Conversation started! session id: {event.session_id}")

            # fetch initial responses and send first message from mediator
            session_data = db.reference(f"{self.study_id}/states/{event.session_id}/").get()
            metadata = session_data.get('meta')
            initial_responses = {
                pid: response.get('text', '')
                for pid, response
                in session_data.get('initial_responses', {}).items()
            }

            response: AIMessage = await self.mediator.start_discussion(
                discussion_id=event.session_id,
                initial_responses=initial_responses,
                topic_id=metadata.get('topicId'),
                condition=metadata.get('condition')
            )

            # create new message in chat
            if response:
                self.post_message_to_session(
                    content=response.content,
                    session_id=event.session_id
                )
            return
        
        self.logger.info(
            f"[NEW EVENT] {event.timestamp} | Participant: {event.participant_id} | " 
            f"modality: {event.modality} | payload {event.payload} "
        )
        
        if event.emotion_activations == []:
            self.logger.warning(f"Event {event.event_id} from session {event.session_id} did not have any annotations")

        # update participant state in background
        asyncio.create_task(self._update_affective_state_of_participant(event=event))
                
        if event.modality == "text":

            # TODO: expand it for more nonsensical stuff
            if event.payload.get("content", "").strip() == "":
                return

            decision: ShouldInterveneDecision = await self.mediator.process_new_message(
                discussion_id=event.session_id,
                new_message=event.payload["content"],
                window=None, # TODO, integrate window back
            )
            self.logger.info(f"mediator decided: {decision}")
            if decision.should_intervene:
                try:
                    self.post_message_to_session(
                        content=decision.response,
                        session_id=event.session_id,
                    )
                except Exception as e:
                    self.logger.error(f"Couldn't write message to DB: {e}")
        
            try:
                self.write_decision_to_db(
                    session_id=event.session_id,
                    decision=decision,
                    window=None,  # TODO: again, find how to integrate window
                )
            except Exception as e:
                self.logger.error(f"Couldn't write decision {decision} to DB: {e}")
        
        # 2. check for existing window
        window_id = redis_key(type="window", session_id=event.session_id)

        expiration = await self.redis_client.hget(f"{window_id}:meta", "expiration_time")
        if expiration and datetime.now().isoformat() >= expiration:
            # SEND AS MESSAGE/REPORT TO AGENT OTHERWISE CONTINUE AS USUAL
            # Write as snapshot to DB
            # reset expiration
            self._reset_window()
            pass
            
        else:
            # active window exists, add event and move on to next event
            if event.modality == "text":
                await self.redis_client.rpush(f"{window_id}:messages", event.payload.get("content"))
            await self.redis_client.hset(f"{window_id}:meta", "last_update", datetime.now().isoformat())

    def _reset_window(self):
        pass

    def write_decision_to_db(
        self,
        session_id: str,
        decision: ShouldInterveneDecision,
        window: AffectiveWindow | None,
    ) -> None:
        
        path = f"{self.study_id}/states/{session_id}/charlie/{int(datetime.now().timestamp())}-should_intervene"
        
        db.reference(path).set(
            {
                'context': {
                    'trigger': window.first_message.content,
                    'window': window.to_system_message().content if window else "",
                } if window else {},  # TODO: integrate window once decided on initialization
                'decision': decision.model_dump(),
            }
        )

    
    def post_message_to_session(
        self,
        content: str,
        session_id: str,
    ):
        """
        Posts a new message to a session on behalf of mediator
        """
        new_message = create_raw_message(
            content=content,
            type="mediator",
            sender_id=self.mediator.name,
        )
        # TODO: path-generating function instead of hard-wire
        db.reference(f"{self.study_id}/states/{session_id}/chat/messages/{new_message['id']}").set(new_message)


    async def _update_affective_state_of_participant(self, event: AffectiveEvent):
        """
        Update the Affective State of a participant given a new event generated by them.
        """

        # Fetch affective state of sender
        # affective_state = self.affective_states.get(f"{event.session_id}/{event.participant_id}")

        state_id = redis_key(
            type="affective_state",
            session_id=event.session_id,
            participant_id=event.participant_id
        )
        affective_state = await self.redis_client.hgetall(state_id)
        
        if affective_state is None or affective_state == {}:
            # Create affective state for participant
            affective_state = AffectiveState(
                participant_id=event.participant_id,
                last_update=event.timestamp,
                running_states={
                    "text": [EmotionAnnotation(name=name, activation=0.0) for name in HUME_EMOTIONS_LIST_TEXT],
                    "vision": [EmotionAnnotation(name=name, activation=0.0) for name in HUME_EMOTIONS_LIST_VISION_AUDIO],
                    "audio": [EmotionAnnotation(name=name, activation=0.0) for name in HUME_EMOTIONS_LIST_VISION_AUDIO],
                }
            )
        
        if event.emotion_activations != []:
            success, reason = affective_state.update(event)
            if success:
                self.logger.info(
                    f"[AFFECTIVE STATE] Updated affective state of participant {event.session_id + ':' + event.participant_id} | "
                    f"Dominant emotions: {affective_state.dominant_emotions}."
                )
                await self.redis_client.hset(state_id, mapping=affective_state.model_dump())

                # Maybe persist..?
                # affective_state_row = affective_state.model_dump()
                # affective_state_row['last_update'] = datetime_to_string(affective_state_row['last_update'])
                # db.reference(f"{self.study_id}/states/{session_id}/affect/{event.participant_id}").set(affective_state_row)
                # self.logger.info(f"Wrote new affective state of {event.participant_id} into --> {self.study_id}/states/{session_id}/affect/{event.participant_id}")
            else:
                self.logger.error(reason)
