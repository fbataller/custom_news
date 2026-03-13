"""
Clase base abstracta para clientes LLM.
Permite cambiar fácilmente entre proveedores.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    """Respuesta de un LLM."""
    
    content: str
    model: str
    tokens_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    
    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "model": self.model,
            "tokens_used": self.tokens_used,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


class BaseLLMClient(ABC):
    """Clase base abstracta para clientes LLM."""
    
    def __init__(
        self,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
    
    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        Genera una respuesta del LLM.
        
        Args:
            system_prompt: Prompt del sistema
            user_prompt: Prompt del usuario
            temperature: Temperatura (opcional, usa default si no se especifica)
            max_tokens: Máximo de tokens (opcional)
        
        Returns:
            LLMResponse con el contenido generado
        """
        pass
    
    @abstractmethod
    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
    ) -> dict:
        """
        Genera una respuesta JSON del LLM.
        
        Args:
            system_prompt: Prompt del sistema
            user_prompt: Prompt del usuario
            temperature: Temperatura (opcional)
        
        Returns:
            Diccionario parseado de la respuesta JSON
        """
        pass
    
    def _validate_json_response(self, content: str) -> dict:
        """Valida y parsea una respuesta JSON."""
        import json
        
        # Limpiar el contenido
        content = content.strip()
        
        # Intentar encontrar JSON en el contenido
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        
        content = content.strip()
        
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            # Intentar extraer JSON del contenido
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            raise ValueError(f"Invalid JSON response: {e}")
