"""
Selector de categorías RSS basado en LLM.
"""

import logging
from typing import Optional

from src.config import get_config
from src.rss.parser import RSSParser
from .base import BaseLLMClient
from .openai_client import get_llm_client

logger = logging.getLogger(__name__)


class CategorySelector:
    """Selecciona las categorías RSS más relevantes para una petición."""
    
    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.config = get_config()
        self.llm = llm_client or get_llm_client()
        self.rss_parser = RSSParser()
    
    async def select_categories(self, user_request: str) -> list[str]:
        """
        Selecciona las categorías más relevantes para la petición del usuario.
        
        Args:
            user_request: La petición del usuario (ej: "noticias sobre IA")
        
        Returns:
            Lista de IDs de categorías seleccionadas
        """
        
        # Cargar prompts
        system_prompt = self.config.load_prompt("select_categories_system")
        user_prompt_template = self.config.load_prompt("select_categories_user")
        
        # Obtener descripción de categorías disponibles
        categories_description = self.rss_parser.get_categories_description()
        
        # Formatear prompts
        system_prompt = system_prompt.format(categories=categories_description)
        user_prompt = user_prompt_template.format(user_request=user_request)
        
        try:
            result = await self.llm.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
            )
            
            categories = result.get("categories", ["general"])
            
            # Validar que las categorías existen
            available_categories = set(self.rss_parser.get_categories().keys())
            valid_categories = [
                cat for cat in categories
                if cat in available_categories
            ]
            
            # Asegurar que siempre hay al menos "general"
            if "general" not in valid_categories and "general" in available_categories:
                valid_categories.insert(0, "general")
            
            if not valid_categories:
                valid_categories = ["general"]
            
            logger.info(f"Selected categories for '{user_request}': {valid_categories}")
            return valid_categories
            
        except Exception as e:
            logger.error(f"Error selecting categories: {e}")
            # Fallback a categorías por defecto
            return ["general"]
