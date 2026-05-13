"""FastAPI application for the agent and event manager"""
import asyncio
import os
import secrets
import sys
import uvicorn
import redis.asyncio as redis
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel as PydanticBaseModel
from langgraph.checkpoint.redis import AsyncRedisSaver
from markdown_it import MarkdownIt
from starlette.middleware.sessions import SessionMiddleware

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

# Configure logging
import logging

from agent.affective_mediator import AffectiveMediator
from agent.base_models import AffectiveEvent
from agent.event_manager import EventManager
from agent.utils import check_required_env_vars


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("AffectiveMediatorApp")
logger.setLevel(logging.INFO)

redis_client = None
checkpointer = None
event_manager = None
mediator = None

GLOBAL_SESSION_ID = os.getenv("GLOBAL_SESSION_ID", "global")


class ChatMessageRequest(PydanticBaseModel):
    participant_id: str
    content: str
    session_id: str | None = None

class ChatJoinRequest(PydanticBaseModel):
    participant_id: str
    session_id: str | None = None

class ChatLeaveRequest(PydanticBaseModel):
    participant_id: str
    session_id: str | None = None


# Define app middleware
middleware = [
    Middleware(
        SessionMiddleware,
        secret_key=os.environ.get("SECRET_KEY", secrets.token_urlsafe(16)),
    )
]


@asynccontextmanager
async def lifespan(app: FastAPI):

    global redis_client, checkpointer, event_manager, mediator
    from agent.llms import primary_llm, summarization_llm   # or build them here

    try:
        check_required_env_vars()
    except Exception as e:
        logger.error(e)
        sys.exit(1)

    redis_client = redis.Redis(
        host=os.getenv('REDIS_HOST'),
        port=int(os.getenv('REDIS_PORT')),
        username=os.getenv('REDIS_USERNAME'),
        password=os.getenv('REDIS_PASSWORD'),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=None,
    )
    if not await redis_client.ping():
        raise ConnectionError("could not connect to Redis client")
    logger.info("Connected to Redis successfully.")
    
    checkpointer = AsyncRedisSaver(
        redis_client=redis_client,
        ttl={  # TODO: move to config file
            "default_ttl": 30,
            "refresh_on_read": False,
        }
    )
    await checkpointer.asetup()

    mediator = AffectiveMediator(
        checkpointer=checkpointer,
        llm=primary_llm,
        summarization_llm=summarization_llm,
        logger=logger,
    )

    event_manager = EventManager(
        study_id=os.getenv("STUDY_ID"),
        mediator=mediator,
        redis_client=redis_client,
        firebase_url=os.getenv("FIREBASE_URL"),
        service_account_str=os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"),
    )
    app.state.event_manager_task = asyncio.create_task(event_manager.start())
    logger.info("EventManager started successfully")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await redis_client.aclose()
    try:
        app.state.event_manager_task.cancel()
        logger.info("EventManager stopped successfully")
    except Exception as e:
        logger.error(f"Error stopping EventManager: {e}", exc_info=True)


logger.info("Initializing AffectiveMediator application...")

app = FastAPI(middleware=middleware, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[
    "https://affect-aware-ai-mediator.onrender.com",
    "https://talktocharlie.io",
    "https://www.talktocharlie.io",
    "http://localhost:5173",
], allow_methods=["*"], allow_headers=["*"])


def _valid_sessions() -> set[str]:
    extra = os.getenv("VALID_SESSIONS", "")
    sessions = {s.strip() for s in extra.split(",") if s.strip()}
    sessions.add(GLOBAL_SESSION_ID)
    return sessions


# Health check endpoints
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "event_manager": "running" if event_manager else "stopped"
    }


@app.get("/session/{code}", status_code=status.HTTP_200_OK)
async def validate_session(code: str, response: Response):
    if code not in _valid_sessions():
        response.status_code = status.HTTP_404_NOT_FOUND
        return {"valid": False}
    return {"valid": True}


async def _process_and_maybe_intervene(content: str):
    try:
        decision = await mediator.process_new_message(
            discussion_id=GLOBAL_SESSION_ID,
            new_message=content,
            window=None,
        )
        if decision.should_intervene:
            event_manager.post_message_to_session(
                content=decision.response,
                session_id=GLOBAL_SESSION_ID,
            )
    except Exception as e:
        logger.error(f"Mediator error: {e}", exc_info=True)


@app.post("/chat/join", status_code=status.HTTP_201_CREATED)
async def user_joined(msg: ChatJoinRequest):
    from firebase_admin import db
    from agent.utils import create_raw_message

    session = msg.session_id or GLOBAL_SESSION_ID
    raw = create_raw_message(content=msg.participant_id, type="join", sender_id=msg.participant_id)
    db.reference(f"{os.getenv('STUDY_ID')}/states/{session}/chat/messages/{raw['id']}").set(raw)
    return {"status": "ok"}


@app.post("/chat/leave", status_code=status.HTTP_200_OK)
async def user_left(request: Request):
    import json
    from firebase_admin import db
    from agent.utils import create_raw_message

    data = json.loads(await request.body())
    participant_id = data.get("participant_id", "")
    session = data.get("session_id") or GLOBAL_SESSION_ID
    raw = create_raw_message(content=participant_id, type="leave", sender_id=participant_id)
    logger.info(f"Leave event: participant={participant_id!r}, session={session!r}, stored type={raw['type']!r}")
    db.reference(f"{os.getenv('STUDY_ID')}/states/{session}/chat/messages/{raw['id']}").set(raw)
    return {"status": "ok"}


@app.post("/chat/message", status_code=status.HTTP_201_CREATED)
async def send_chat_message(msg: ChatMessageRequest):
    from firebase_admin import db
    from agent.utils import create_raw_message

    session = msg.session_id or GLOBAL_SESSION_ID
    raw = create_raw_message(content=msg.content, type="user", sender_id=msg.participant_id)
    db.reference(f"{os.getenv('STUDY_ID')}/states/{session}/chat/messages/{raw['id']}").set(raw)

    asyncio.create_task(_process_and_maybe_intervene(msg.content))
    return {"status": "ok", "message_id": raw["id"]}


@app.post("/event", status_code=status.HTTP_201_CREATED)
async def process_new_event(event: AffectiveEvent, response: Response):
    """
    Enqueue incoming event, ensuring idempotency.
    """
    
    # 1. idempotency check
    idempotency_key = event.event_id

    if not await redis_client.set(f"seen:{idempotency_key}", "1", ex=360, nx=True):
        # key already exists
        response.status_code = status.HTTP_200_OK
        return {"status": "accepted", "duplicate": True}

    # 3. enqueue
    await redis_client.publish(channel="events", message=event.model_dump_json())

    return {"status": "accepted", "event_id": idempotency_key}

@app.get("/")
async def index():
    return "hello"



@app.get("/about", response_class=HTMLResponse)
async def about():
    """Display the agent context and flow documentation."""
    md_file_path = os.path.join(os.path.dirname(__file__), "README.md")
    try:
        with open(md_file_path, "r", encoding="utf-8") as f:
            markdown_content = f.read()
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Documentation not found</h1>",
            status_code=404,
        )

    # Convert markdown to HTML
    md = MarkdownIt()
    html_content = md.render(markdown_content)

    # Wrap in a styled HTML page
    styled_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Affective Mediator - Documentation</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .container {{
                background-color: white;
                padding: 40px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #2c3e50;
                border-bottom: 3px solid #3498db;
                padding-bottom: 10px;
            }}
            h2 {{
                color: #34495e;
                margin-top: 30px;
                border-bottom: 2px solid #ecf0f1;
                padding-bottom: 8px;
            }}
            h3 {{
                color: #555;
                margin-top: 25px;
            }}
            code {{
                background-color: #f4f4f4;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Monaco', 'Courier New', monospace;
                font-size: 0.9em;
            }}
            pre {{
                background-color: #2c3e50;
                color: #ecf0f1;
                padding: 15px;
                border-radius: 5px;
                overflow-x: auto;
            }}
            pre code {{
                background-color: transparent;
                padding: 0;
                color: inherit;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 20px 0;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 12px;
                text-align: left;
            }}
            th {{
                background-color: #3498db;
                color: white;
                font-weight: bold;
            }}
            tr:nth-child(even) {{
                background-color: #f9f9f9;
            }}
            blockquote {{
                border-left: 4px solid #3498db;
                margin: 20px 0;
                padding-left: 20px;
                color: #666;
                font-style: italic;
            }}
            ul, ol {{
                margin: 15px 0;
                padding-left: 30px;
            }}
            li {{
                margin: 8px 0;
            }}
            a {{
                color: #3498db;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            {html_content}
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=styled_html)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
