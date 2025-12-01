"""FastAPI application for the agent and event manager"""
import os
import secrets
import sys
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent.affective_mediator import AffectiveMediator
from agent.event_manager import EventManager

from dotenv import load_dotenv
load_dotenv()

# Configure logging
import logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
log_level_map = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
log_level = log_level_map.get(log_level, logging.INFO)

logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("AffectiveMediatorApp")
logger.setLevel(log_level)


# TODO: add a bunch more
required_env_vars = ["FIREBASE_URL", "STUDY_ID", "FIREBASE_SERVICE_ACCOUNT_JSON"]
missing = [var for var in required_env_vars if not os.getenv(var)]
if missing:
    logger.error(f"Missing required environment variables: {missing}")
    sys.exit(1)


try: 
    mediator = AffectiveMediator(
        # memory=...,  # TODO: add checkpointer -- Mongo/Postgres/Redis
        logger=logger
    )

    event_manager = EventManager(
        study_id=os.getenv("STUDY_ID"),
        mediator=mediator,
        database_url=os.getenv("FIREBASE_URL"),
        service_account_str=os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"),
    )
except Exception as e:
    logger.error(f"Failed to initialize the mediator or the event manager.. {e}")
    sys.exit(1)


# Define app middleware
middleware = [
    Middleware(
        SessionMiddleware,
        secret_key=os.environ.get("SECRET_KEY", secrets.token_urlsafe(16)),
    )
]

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting EventManager...")
    try:
        event_manager.start()
        logger.info("EventManager started successfully")
    except Exception as e:
        logger.error(f"Failed to start EventManager: {e}", exc_info=True)
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down EventManager...")
    try:
        event_manager.stop()
        logger.info("EventManager stopped successfully")
    except Exception as e:
        logger.error(f"Error stopping EventManager: {e}", exc_info=True)


logger.info("Initializing AffectiveMediator application...")

app = FastAPI(middleware=middleware, lifespan=lifespan)


# Health check endpoints
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "event_manager": "running" if event_manager._listener else "stopped"
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)