"""Utility functions to be used across agent modules."""

import asyncio
from datetime import datetime, timezone
import os
from typing import Any, Dict
from pydantic import BaseModel
from langchain_core.messages import HumanMessage


def create_human_message_from_raw(raw_message: dict) -> HumanMessage:
    """
    Helper function to create a LangChain-compatible human message
    from raw input (db row). Assumes the following structure:
    {
        "id": str
        "content": str,
        "senderId": str,
        "ts": int | datetime
    }
    
    """
    if raw_message.get('ts') and type(raw_message["ts"]) == int:
        timestamp = datetime.fromtimestamp(raw_message.get('ts') // 1000)
    else:
        timestamp: datetime | None = raw_message.get("ts")
    
    participant = raw_message.get('senderId')
    
    structured_content = f'''
    User {participant} sent: {raw_message.get("content")}
    '''

    return HumanMessage(
        content=structured_content,
        additional_kwargs={
            'participant_id': participant,
            'timestamp': timestamp,
        }
    )


def create_raw_message(content: str, type: str, sender_id, timestamp = None) -> Dict[str, Any]:
    return {
        "id": f"{int(datetime.now().timestamp())}-{sender_id}",
        "content": content,
        "type": type,
        "senderId": sender_id,
        "ts": int(datetime.now(timezone.utc).timestamp()) if timestamp is None else timestamp,
    }


def datetime_to_string(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def load_prompt(func: str) -> str:
    """Load the system prompt for the agent."""
    with open(f"agent/prompts/{func}_prompt.txt", "r") as file:
        prompt = file.read()
    return prompt


# Stream events to UI for better user experience
async def stream_thought_process(
    agent, # of type CompiledStateGraph
    state: BaseModel,
    config: dict,
):
    """
    Token-stream model outputs to frontend.

    Parameters:
        - agent: a LangGraph compiled state graph supporting token streaming.
        - input: agent state to run agent over.
        - config: Configurable object or dictionary of the format {"configurable": {...}}
            - must have at least "thread_id" configuration
        - debug_mode: if true, stream everything. otherwise, only stream user-facing outputs.

    Returns a generator of LLM tokens, streamed
    """

    mode = None
    out = ""
    type = ""
    # stream the final node of the graph
    async for token, metadata in agent.astream(input=state, config=config, stream_mode="messages"):
        try:
            content_block = token.content_blocks[0]
        except:
            continue
        if metadata.get("langgraph_node") != mode:
            mode = metadata.get("langgraph_node")
            out += f"\n\n===== {mode} ===\n"
        if content_block['type'] != type:
            type = content_block['type']
            out += "\n"
        if metadata.get("langgraph_node") == "model":
            if content_block['type'] == "text":
                out += content_block['text']
            elif content_block['type'] == "tool_call_chunk":
                out += content_block['args']
        elif metadata.get("langgraph_node") == "tools":
            try:
                out += f"{token.name}: {token.content_blocks[0]['text']}"
            except:
                continue
        # yield content
        yield out
        out = ""
        await asyncio.sleep(0.05)


def check_required_env_vars() -> None:
    """
    Before launching app, verify that all necessary environment variables are present.
    """
    required_env_vars = [
        "FIREBASE_URL",
        "STUDY_ID",
        "FIREBASE_SERVICE_ACCOUNT_JSON",
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_USERNAME",
        "REDIS_PASSWORD",
    ]
    
    missing = [var for var in required_env_vars if not os.getenv(var)]

    if missing != []:
        raise Exception(f"Missing environment variables: {missing}")


def redis_key(
    status: str = "", # 'processed', 'seen'
    type: str = "", # 'window', 'affective_state', 'event'
    session_id: str = "",
    participant_id: str = "",
    event_id: str = "",
) -> str:
    """
    Create a redis-formatted string hierarchical key
    Example:
        >> get_redis_type(type="window", participant_id="1234", session_id="5678)
        'window:5678:1234'
    """

    # TODO: maybe add prefix to each component to symbolize what it is (e.g., "s" for session, "p" for participant)
    return ":".join(
        [
            s
            for s in [status, type, session_id, participant_id, event_id]
            if s != ""
        ]
    )
