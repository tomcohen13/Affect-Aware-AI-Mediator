"""
Initialize LLMs used by the mediator
"""
import os
from typing import List, Optional
from langchain.chat_models import BaseChatModel
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AnyMessage

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


summarization_llm = ChatAnthropic( 
    model=os.getenv("SUMMARIZATION_LLM", os.getenv("DEFAULT_LLM")), # haiku
    temperature=0.0,
    max_tokens=2048,
    max_retries=2,
    timeout=10.0,
)

primary_llm = ChatAnthropic( # type: ignore
    model=os.getenv("DEFAULT_LLM"),
    temperature=0.3,
    max_tokens=1000,
    max_retries=3,
    timeout=10.0,
    model_kwargs={
        "extra_headers": {"anthropic-beta": "prompt-caching-2024-07-31"}
    }
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
        return await model.with_structured_output(output_type, strict=False).ainvoke(input=messages)
