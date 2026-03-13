"""
Filtro de noticias basado en LLM.
"""

import logging
from typing import Optional

from src.config import get_config
from src.rss.parser import RSSArticle, RSSParser
from .base import BaseLLMClient
from .openai_client import get_llm_client

logger = logging.getLogger(__name__)


class NewsFilter:
    """Filtra las noticias más relevantes para una petición."""
    
    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.config = get_config()
        self.llm = llm_client or get_llm_client()
        self.rss_parser = RSSParser()
    
    async def filter_news(
        self,
        articles: list[RSSArticle],
        user_request: str,
        max_news: int = 12,
    ) -> list[RSSArticle]:
        """
        Filtra las noticias más relevantes para la petición del usuario.
        
        Args:
            articles: Lista de artículos disponibles
            user_request: La petición del usuario
            max_news: Número máximo de noticias a seleccionar
        
        Returns:
            Lista de artículos filtrados
        """
        
        if not articles:
            return []
        
        # Cargar prompts
        system_prompt = self.config.load_prompt("filter_news_system")
        user_prompt_template = self.config.load_prompt("filter_news_user")
        
        # Formatear lista de noticias para el LLM
        news_list = self.rss_parser.format_articles_for_llm(articles)
        
        # Formatear prompt
        user_prompt = user_prompt_template.format(
            user_request=user_request,
            news_list=news_list,
        )
        
        try:
            result = await self.llm.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
            )
            
            selected_ids = result.get("selected_news_ids", [])
            
            # Crear mapeo de ID -> artículo
            articles_map = {article.id: article for article in articles}
            
            # Filtrar artículos seleccionados
            filtered_articles = []
            for article_id in selected_ids:
                if article_id in articles_map:
                    filtered_articles.append(articles_map[article_id])
                
                if len(filtered_articles) >= max_news:
                    break
            
            logger.info(
                f"Filtered {len(filtered_articles)} articles from {len(articles)} "
                f"for request: '{user_request}'"
            )
            
            return filtered_articles
            
        except Exception as e:
            logger.error(f"Error filtering news: {e}")
            # Fallback: devolver las primeras N noticias
            return articles[:max_news]
