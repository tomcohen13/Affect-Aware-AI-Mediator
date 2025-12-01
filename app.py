"""FastAPI application for the agent and event manager"""
import os
import secrets
import sys
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware import Middleware
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from markdown_it import MarkdownIt

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

@app.get("/agent-docs", response_class=HTMLResponse)
async def agent_docs():
    """Display the agent context and flow documentation."""
    md_file_path = os.path.join(os.path.dirname(__file__), "AGENT_CONTEXT_AND_FLOW.md")
    
    try:
        with open(md_file_path, "r", encoding="utf-8") as f:
            markdown_content = f.read()
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Documentation not found</h1><p>The documentation file could not be found.</p>",
            status_code=404
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