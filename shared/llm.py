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

T = TypeVar("T", bound=BaseModel)

class LLMClient:
    """
    Singleton client for robust OpenAI interactions.
    Reads configuration directly from the central settings module.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LLMClient, cls).__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        """Initializes the AsyncOpenAI SDK client."""
        self.client = AsyncOpenAI(api_key=settings.openai.api_key)
        self.default_model = settings.openai.model

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
        """
        Generates a standard text response from the LLM.
        
        Args:
            user_prompt (str): The main prompt payload.
            system_prompt (Optional[str]): System instructions.
            temperature (float): Model creativity (0.0 to 2.0).
            max_tokens (Optional[int]): Cap on generation length.
            json_mode (bool): Forces the model to output valid JSON.
            
        Returns:
            LLMResponse: A strongly typed response with tokens, latency, and text.
        """
        messages = self._build_messages(user_prompt, system_prompt)
        
        start_time = time.time()
        try:
            response = await self.client.chat.completions.create(
                model=self.default_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"} if json_mode else {"type": "text"}
            )
            
            latency = (time.time() - start_time) * 1000
            choice = response.choices[0]
            usage = response.usage
            
            return LLMResponse(
                text=choice.message.content or "",
                usage=TokenUsage(
                    prompt_tokens=usage.prompt_tokens if usage else 0,
                    completion_tokens=usage.completion_tokens if usage else 0,
                    total_tokens=usage.total_tokens if usage else 0
                ),
                latency_ms=latency,
                finish_reason=choice.finish_reason
            )
            
        except AuthenticationError as e:
            logger.error("Authentication failed with OpenAI. Please check OPENAI_API_KEY in configuration.")
            raise e
        except Exception as e:
            logger.error(f"Error during standard LLM generation: {e}")
            raise e

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
        """
        Generates a response strictly adhering to a Pydantic schema using Structured Outputs.
        
        Args:
            response_model (Type[T]): The Pydantic model class to enforce.
            user_prompt (str): The main prompt payload.
            system_prompt (Optional[str]): System instructions.
            temperature (float): Generally 0.0 for structured data.
            max_tokens (Optional[int]): Cap on generation length.
            
        Returns:
            LLMResponse: A typed response containing the parsed `structured_output`.
        """
        messages = self._build_messages(user_prompt, system_prompt)
        
        start_time = time.time()
        try:
            response = await self.client.beta.chat.completions.parse(
                model=self.default_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_model
            )
            
            latency = (time.time() - start_time) * 1000
            choice = response.choices[0]
            usage = response.usage
            
            return LLMResponse(
                text=choice.message.content or "",
                structured_output=choice.message.parsed,
                usage=TokenUsage(
                    prompt_tokens=usage.prompt_tokens if usage else 0,
                    completion_tokens=usage.completion_tokens if usage else 0,
                    total_tokens=usage.total_tokens if usage else 0
                ),
                latency_ms=latency,
                finish_reason=choice.finish_reason
            )
            
        except AuthenticationError as e:
            logger.error("Authentication failed with OpenAI. Please check OPENAI_API_KEY in configuration.")
            raise e
        except Exception as e:
            logger.error(f"Error during structured generation: {e}")
            raise e

    async def stream(
        self, 
        user_prompt: str, 
        system_prompt: Optional[str] = None, 
        temperature: float = 0.7, 
        max_tokens: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        """
        Streams the response text from the LLM asynchronously.
        Useful for providing real-time CLI feedback to developers.
        
        Args:
            user_prompt (str): The main prompt payload.
            system_prompt (Optional[str]): System instructions.
            temperature (float): Model creativity.
            max_tokens (Optional[int]): Cap on generation length.
            
        Yields:
            str: Chunks of the text generated by the model.
        """
        messages = self._build_messages(user_prompt, system_prompt)
        
        try:
            stream_response = await self.client.chat.completions.create(
                model=self.default_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            
            async for chunk in stream_response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except AuthenticationError as e:
            logger.error("Authentication failed with OpenAI. Please check OPENAI_API_KEY.")
            raise e
        except Exception as e:
            logger.error(f"Error during LLM streaming: {e}")
            raise e

    def _build_messages(self, user_prompt: str, system_prompt: Optional[str]) -> list:
        """Helper to build message array cleanly."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return messages

# Expose a singleton instance of the client
llm_client = LLMClient()
