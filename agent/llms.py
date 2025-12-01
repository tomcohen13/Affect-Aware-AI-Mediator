"""
Initialize LLMs used by the mediator
"""
import os
from typing import List, Optional
from langchain.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

GATING_MODEL_NAME = "google/gemini-2.5-flash"
REASONING_MODEL_NAME = "google/gemini-3-pro-preview"


gating_model = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1", # OpenRouter base URL
    api_key=os.getenv("OPENROUTER_API_KEY"), # OpenRouter API key from environment variable
    model=GATING_MODEL_NAME,
    temperature=0.0,
    max_retries=3,
)

reasoning_model = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1", # OpenRouter base URL
    api_key=os.getenv("OPENROUTER_API_KEY"), # OpenRouter API key from environment variable
    model=REASONING_MODEL_NAME,
    temperature=0.7,
    max_retries=3,
)


async def call_model_async(
    model: BaseChatModel,
    messages: List[AnyMessage],
    output_type: Optional[BaseModel] = None,
) -> str:  # type: ignore
    """
    Calls OpenAI model with the given messages and returns (structured) output.

    Parameters:
        model (str): name of the model to use, from [...]
        messages (list): list of LangGraph messages to send to the model
        output_type (TypedDict): type of structured output to return
    """
    if output_type is None:
        return await model.ainvoke(input=messages)
    else:
        return await model.with_structured_output(output_type).ainvoke(input=messages)
