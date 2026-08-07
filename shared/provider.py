"""
LLM Provider Abstraction.
Defines a common interface for different LLM providers (OpenAI, Gemini, etc.).
"""
import time
from abc import ABC, abstractmethod
from typing import Optional, AsyncGenerator, Type, TypeVar, Any
from pydantic import BaseModel
from shared.response import LLMResponse, TokenUsage
from config.settings import settings
from config.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate(
        self, 
        user_prompt: str, 
        system_prompt: Optional[str] = None, 
        temperature: float = 0.7, 
        max_tokens: Optional[int] = None,
        json_mode: bool = False
    ) -> LLMResponse:
        pass

    @abstractmethod
    async def structured_generate(
        self, 
        response_model: Type[T],
        user_prompt: str, 
        system_prompt: Optional[str] = None, 
        temperature: float = 0.0, 
        max_tokens: Optional[int] = None
    ) -> LLMResponse:
        pass

    @abstractmethod
    async def stream(
        self, 
        user_prompt: str, 
        system_prompt: Optional[str] = None, 
        temperature: float = 0.7, 
        max_tokens: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        pass

class OpenAIProvider(BaseLLMProvider):
    def __init__(self):
        if not settings.openai.api_key:
            raise RuntimeError("OpenAI provider selected.\nOPENAI_API_KEY is missing.\nPlease update your .env.")
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise RuntimeError("OpenAI SDK not installed.\nRun\npip install openai")
            
        self.client = AsyncOpenAI(api_key=settings.openai.api_key)
        self.default_model = settings.openai.model

    def _build_messages(self, user_prompt: str, system_prompt: Optional[str]) -> list:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return messages

    async def generate(self, user_prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: Optional[int] = None, json_mode: bool = False) -> LLMResponse:
        start_time = time.time()
        response = await self.client.chat.completions.create(
            model=self.default_model,
            messages=self._build_messages(user_prompt, system_prompt),
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

    async def structured_generate(self, response_model: Type[T], user_prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.0, max_tokens: Optional[int] = None) -> LLMResponse:
        start_time = time.time()
        response = await self.client.beta.chat.completions.parse(
            model=self.default_model,
            messages=self._build_messages(user_prompt, system_prompt),
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

    async def stream(self, user_prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: Optional[int] = None) -> AsyncGenerator[str, None]:
        stream_response = await self.client.chat.completions.create(
            model=self.default_model,
            messages=self._build_messages(user_prompt, system_prompt),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True
        )
        async for chunk in stream_response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

class GeminiProvider(BaseLLMProvider):
    def __init__(self):
        if not settings.gemini.api_key:
            raise RuntimeError("Gemini provider selected.\nGOOGLE_API_KEY is missing.\nPlease update your .env.")
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise RuntimeError("Gemini SDK not installed.\nRun\npip install google-genai")
            
        self.genai = genai
        self.types = types
        self.client = genai.Client(api_key=settings.gemini.api_key)
        self.default_model = settings.gemini.model

    async def generate(self, user_prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: Optional[int] = None, json_mode: bool = False) -> LLMResponse:
        start_time = time.time()
        
        config = self.types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_prompt,
            response_mime_type="application/json" if json_mode else "text/plain"
        )
        response = await self.client.aio.models.generate_content(
            model=self.default_model,
            contents=user_prompt,
            config=config
        )
        latency = (time.time() - start_time) * 1000
        
        prompt_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        completion_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
        total_tokens = response.usage_metadata.total_token_count if response.usage_metadata else 0
        
        finish_reason = None
        if response.candidates and response.candidates[0].finish_reason:
            finish_reason = response.candidates[0].finish_reason.name

        return LLMResponse(
            text=response.text or "",
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens
            ),
            latency_ms=latency,
            finish_reason=finish_reason
        )

    async def structured_generate(self, response_model: Type[T], user_prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.0, max_tokens: Optional[int] = None) -> LLMResponse:
        start_time = time.time()
        
        config = self.types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=response_model
        )
        response = await self.client.aio.models.generate_content(
            model=self.default_model,
            contents=user_prompt,
            config=config
        )
        latency = (time.time() - start_time) * 1000
        
        prompt_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        completion_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
        total_tokens = response.usage_metadata.total_token_count if response.usage_metadata else 0
        
        finish_reason = None
        if response.candidates and response.candidates[0].finish_reason:
            finish_reason = response.candidates[0].finish_reason.name

        parsed_obj = response_model.model_validate_json(response.text)
        
        return LLMResponse(
            text=response.text or "",
            structured_output=parsed_obj,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens
            ),
            latency_ms=latency,
            finish_reason=finish_reason
        )

    async def stream(self, user_prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: Optional[int] = None) -> AsyncGenerator[str, None]:
        config = self.types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_prompt,
        )
        response = await self.client.aio.models.generate_content_stream(
            model=self.default_model,
            contents=user_prompt,
            config=config
        )
        async for chunk in response:
            if chunk.text:
                yield chunk.text

class OpenRouterProvider(OpenAIProvider):
    def __init__(self):
        if not settings.openai.api_key:
            raise RuntimeError("OpenRouter provider selected.\nOPENAI_API_KEY is missing.\nPlease update your .env.")
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise RuntimeError("OpenAI SDK not installed.\nRun\npip install openai")
            
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openai.api_key,
        )
        self.default_model = settings.openai.model

class ProviderFactory:
    @staticmethod
    def get_provider() -> BaseLLMProvider:
        provider_name = settings.llm.provider.lower()
        if provider_name == "openai":
            return OpenAIProvider()
        elif provider_name == "gemini":
            return GeminiProvider()
        elif provider_name == "openrouter":
            return OpenRouterProvider()
        else:
            raise ValueError(f"Unsupported LLM provider: {provider_name}. Supported: openai, gemini, openrouter")
