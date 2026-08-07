"""
Production-quality OpenAI client wrapper.
Provides robust methods for generation, streaming, and structured output.
Implements retry logic with exponential backoff for resilience against rate limits and timeouts.
"""
import time
from typing import Optional, Any, AsyncGenerator, Type, TypeVar
from pydantic import BaseModel
from openai import AsyncOpenAI, OpenAIError, RateLimitError, APITimeoutError, AuthenticationError
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from config.settings import settings
from config.logging import get_logger
from shared.response import LLMResponse, TokenUsage

logger = get_logger(__name__)

from shared.provider import ProviderFactory

class LLMClient:
    """
    Singleton client for robust LLM interactions.
    Delegates generation, streaming, and structured output to the active provider.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LLMClient, cls).__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        """Initializes the active LLM Provider."""
        self.provider = ProviderFactory.get_provider()

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((RateLimitError, APITimeoutError, OpenAIError)),
        reraise=True
    )
    async def generate(
        self, 
        user_prompt: str, 
        system_prompt: Optional[str] = None, 
        temperature: float = 0.7, 
        max_tokens: Optional[int] = None,
        json_mode: bool = False
    ) -> LLMResponse:
        return await self.provider.generate(user_prompt, system_prompt, temperature, max_tokens, json_mode)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((RateLimitError, APITimeoutError, OpenAIError)),
        reraise=True
    )
    async def structured_generate(
        self, 
        response_model: Type[T],
        user_prompt: str, 
        system_prompt: Optional[str] = None, 
        temperature: float = 0.0, 
        max_tokens: Optional[int] = None
    ) -> LLMResponse:
        return await self.provider.structured_generate(response_model, user_prompt, system_prompt, temperature, max_tokens)

    async def stream(
        self, 
        user_prompt: str, 
        system_prompt: Optional[str] = None, 
        temperature: float = 0.7, 
        max_tokens: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        async for chunk in self.provider.stream(user_prompt, system_prompt, temperature, max_tokens):
            yield chunk

# Expose a singleton instance of the client
llm_client = LLMClient()
