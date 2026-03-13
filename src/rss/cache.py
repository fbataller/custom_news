"""
Sistema de caché para noticias RSS.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import NewsCache as NewsCacheModel, init_database, AsyncSessionLocal
from src.database import crud
from src.config import get_config
from .parser import RSSArticle

logger = logging.getLogger(__name__)


class NewsCache:
    """Gestor de caché de noticias."""
    
    def __init__(self):
        self.config = get_config()
        self._session: Optional[AsyncSession] = None
    
    async def _get_session(self) -> AsyncSession:
        """Obtiene una sesión de base de datos."""
        if AsyncSessionLocal is None:
            await init_database()
        return AsyncSessionLocal()
    
    async def get_cached_articles(self, category: str) -> list[RSSArticle]:
        """Obtiene artículos cacheados de una categoría."""
        if not self.config.cache.enabled:
            return []
        
        session = await self._get_session()
        try:
            cached = await crud.get_cached_news_by_category(
                session,
                category,
                hours=self.config.cache.news_cache_hours
            )
            
            articles = []
            for item in cached:
                article = RSSArticle(
                    id=item.article_id,
                    title=item.title,
                    link=item.link,
                    summary=item.summary or "",
                    published_at=item.published_at,
                    source=item.feed_url.split("/")[2] if "/" in item.feed_url else item.feed_url,
                    category=item.category,
                    full_content=item.full_content,
                )
                articles.append(article)
            
            logger.info(f"Retrieved {len(articles)} cached articles for category {category}")
            return articles
            
        finally:
            await session.close()
    
    async def cache_articles(
        self,
        articles: list[RSSArticle],
        category: str,
        feed_url: str
    ) -> None:
        """Cachea una lista de artículos."""
        if not self.config.cache.enabled:
            return
        
        session = await self._get_session()
        try:
            for article in articles:
                await crud.cache_news_article(
                    session,
                    category=category,
                    feed_url=feed_url,
                    article_id=article.id,
                    title=article.title,
                    link=article.link,
                    summary=article.summary,
                    full_content=article.full_content,
                    published_at=article.published_at,
                )
            
            logger.info(f"Cached {len(articles)} articles for category {category}")
            
        finally:
            await session.close()
    
    async def update_article_content(self, article_id: str, full_content: str) -> None:
        """Actualiza el contenido completo de un artículo cacheado."""
        session = await self._get_session()
        try:
            cached = await crud.get_cached_article(session, article_id)
            if cached:
                cached.full_content = full_content
                cached.content_extracted = True
                await session.commit()
                logger.info(f"Updated content for article {article_id}")
        finally:
            await session.close()
    
    async def get_article_content(self, article_id: str) -> Optional[str]:
        """Obtiene el contenido completo de un artículo cacheado."""
        session = await self._get_session()
        try:
            cached = await crud.get_cached_article(session, article_id)
            if cached and cached.full_content:
                return cached.full_content
            return None
        finally:
            await session.close()
    
    async def is_fresh(self, category: str) -> bool:
        """Verifica si el caché de una categoría está fresco."""
        if not self.config.cache.enabled:
            return False
        
        session = await self._get_session()
        try:
            cached = await crud.get_cached_news_by_category(
                session,
                category,
                hours=self.config.cache.news_cache_hours
            )
            return len(cached) > 0
        finally:
            await session.close()
    
    async def cleanup(self, hours: int = 24) -> int:
        """Limpia el caché antiguo."""
        session = await self._get_session()
        try:
            deleted = await crud.cleanup_old_cache(session, hours)
            logger.info(f"Cleaned up {deleted} old cached articles")
            return deleted
        finally:
            await session.close()
