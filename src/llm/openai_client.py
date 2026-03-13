"""
Cliente de OpenAI para LLM.
"""

import logging
from typing import Optional

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import get_config
from .base import BaseLLMClient, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIClient(BaseLLMClient):
    """Cliente de OpenAI."""
    
    def __init__(
        self,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        config = get_config()
        
        super().__init__(
            model=model or config.llm.model,
            temperature=temperature or config.llm.temperature,
            max_tokens=max_tokens or config.llm.max_tokens,
        )
        
        self.client = AsyncOpenAI(api_key=config.openai_api_key)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Genera una respuesta del LLM."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
            )
            
            content = response.choices[0].message.content or ""
            usage = response.usage
            
            return LLMResponse(
                content=content,
                model=self.model,
                tokens_used=usage.total_tokens if usage else 0,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
            )
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
    ) -> dict:
        """Genera una respuesta JSON del LLM."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or 0.3,  # Menor temperatura para JSON
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
            )
            
            content = response.choices[0].message.content or "{}"
            return self._validate_json_response(content)
            
        except Exception as e:
            logger.error(f"OpenAI API error (JSON): {e}")
            raise


def get_llm_client() -> BaseLLMClient:
    """Factory para obtener el cliente LLM según la configuración."""
    config = get_config()
    provider = config.llm.provider.lower()
    
    if provider == "openai":
        return OpenAIClient()
    else:
        # Por defecto, usar OpenAI
        logger.warning(f"Unknown LLM provider: {provider}, using OpenAI")
        return OpenAIClient()
