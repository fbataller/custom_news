"""
Pipeline principal de generación de noticias.
Orquesta todo el proceso desde la petición hasta el audio final.
"""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from src.config import get_config
from src.database.models import init_database, AsyncSessionLocal
from src.database import crud
from src.rss.parser import RSSParser, RSSArticle
from src.rss.cache import NewsCache
from src.llm.category_selector import CategorySelector
from src.llm.news_filter import NewsFilter
from src.llm.script_generator import ScriptGenerator
from src.scraper.article_extractor import ArticleExtractor
from src.tts.openai_tts import get_tts_client

logger = logging.getLogger(__name__)


class NewsPipeline:
    """Pipeline principal de generación de noticias."""
    
    def __init__(self):
        self.config = get_config()
        self.rss_parser = RSSParser()
        self.news_cache = NewsCache()
        self.category_selector = CategorySelector()
        self.news_filter = NewsFilter()
        self.script_generator = ScriptGenerator()
        self.article_extractor = ArticleExtractor()
        self.tts_client = get_tts_client()
    
    async def _record_token_usage(
        self,
        model: str,
        provider: str,
        usage_type: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        """Registra el uso de tokens en la base de datos."""
        if AsyncSessionLocal is None:
            await init_database()
        
        async with AsyncSessionLocal() as session:
            await crud.record_token_usage(
                session,
                model=model,
                provider=provider,
                usage_type=usage_type,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
    
    async def generate_news_audio(
        self,
        user_id: int,
        topic: str,
        duration_minutes: Optional[int] = None,
    ) -> Optional[Tuple[Path, str]]:
        """
        Genera un audio de noticias completo.
        
        Args:
            user_id: ID del usuario
            topic: Tema de las noticias
            duration_minutes: Duración objetivo en minutos (opcional)
        
        Returns:
            Tuple de (path del audio, texto del guion) o None si falla
        """
        start_time = time.time()
        total_tokens = 0
        
        try:
            logger.info(f"Starting news generation for user {user_id}: {topic}")
            
            # 1. Verificar caché de audio
            cached_audio = await self._check_audio_cache(topic)
            if cached_audio:
                logger.info(f"Using cached audio for topic: {topic}")
                return cached_audio
            
            # 2. Seleccionar categorías relevantes
            logger.info("Selecting categories...")
            categories = await self.category_selector.select_categories(topic)
            logger.info(f"Selected categories: {categories}")
            
            # 3. Obtener feeds RSS
            logger.info("Fetching RSS feeds...")
            all_articles = await self._fetch_feeds(categories)
            logger.info(f"Fetched {len(all_articles)} articles")
            
            if not all_articles:
                logger.warning("No articles found")
                return None
            
            # 4. Filtrar noticias relevantes
            logger.info("Filtering relevant news...")
            filtered_articles = await self.news_filter.filter_news(
                all_articles,
                topic,
                max_news=12,
            )
            logger.info(f"Filtered to {len(filtered_articles)} articles")
            
            if not filtered_articles:
                logger.warning("No relevant articles found")
                return None
            
            # 5. Extraer contenido completo
            logger.info("Extracting full article content...")
            articles_with_content = await self._extract_article_content(filtered_articles)
            logger.info(f"Extracted content for {len(articles_with_content)} articles")
            
            # 6. Generar guion
            logger.info("Generating script...")
            script, tokens = await self.script_generator.generate_script(
                articles_with_content,
                topic,
                duration_minutes,
            )
            total_tokens += tokens
            logger.info(f"Generated script with {len(script.split())} words")
            
            # Registrar uso de tokens LLM
            await self._record_token_usage(
                model=self.config.llm.model,
                provider=self.config.llm.provider,
                usage_type="llm",
                total_tokens=total_tokens,
                prompt_tokens=int(total_tokens * 0.7),  # Estimación
                completion_tokens=int(total_tokens * 0.3),
            )
            
            # 7. Generar audio
            logger.info("Generating audio...")
            audio_path = await self.tts_client.generate_audio(script)
            logger.info(f"Audio generated: {audio_path}")
            
            # Registrar uso de TTS (caracteres como tokens para TTS)
            tts_chars = len(script)
            await self._record_token_usage(
                model=self.config.tts.model,
                provider=self.config.tts.provider,
                usage_type="tts",
                total_tokens=tts_chars,
                prompt_tokens=tts_chars,
                completion_tokens=0,
            )
            
            # 8. Guardar en caché
            await self._cache_audio(topic, audio_path, script)
            
            # 9. Registrar métricas
            processing_time = time.time() - start_time
            await self._update_request_metrics(
                user_id,
                topic,
                categories,
                len(filtered_articles),
                processing_time,
                total_tokens,
                str(audio_path),
                script,
            )
            
            logger.info(
                f"News generation completed in {processing_time:.2f}s, "
                f"tokens used: {total_tokens}"
            )
            
            return audio_path, script
            
        except Exception as e:
            logger.error(f"Error in news pipeline: {e}", exc_info=True)
            return None
    
    async def _check_audio_cache(self, topic: str) -> Optional[Tuple[Path, str]]:
        """Verifica si hay un audio cacheado para el tema."""
        if not self.config.cache.enabled:
            return None
        
        if AsyncSessionLocal is None:
            await init_database()
        
        async with AsyncSessionLocal() as session:
            cached = await crud.get_cached_audio(session, topic)
            
            if cached:
                audio_path = Path(cached.audio_path)
                if audio_path.exists():
                    return audio_path, cached.script_text or ""
        
        return None
    
    async def _fetch_feeds(self, categories: list[str]) -> list[RSSArticle]:
        """Obtiene los feeds RSS de las categorías seleccionadas."""
        all_articles = []
        
        for category in categories:
            # Verificar caché primero
            if await self.news_cache.is_fresh(category):
                cached_articles = await self.news_cache.get_cached_articles(category)
                all_articles.extend(cached_articles)
                logger.info(f"Using {len(cached_articles)} cached articles from {category}")
            else:
                # Obtener desde RSS
                articles = await self.rss_parser.fetch_category(category)
                all_articles.extend(articles)
                
                # Cachear los artículos
                for feed in self.rss_parser.get_categories()[category].feeds:
                    feed_articles = [a for a in articles if a.source == feed.name]
                    if feed_articles:
                        await self.news_cache.cache_articles(
                            feed_articles,
                            category,
                            feed.url,
                        )
        
        # Eliminar duplicados por ID
        seen_ids = set()
        unique_articles = []
        for article in all_articles:
            if article.id not in seen_ids:
                seen_ids.add(article.id)
                unique_articles.append(article)
        
        return unique_articles
    
    async def _extract_article_content(
        self,
        articles: list[RSSArticle],
    ) -> list[RSSArticle]:
        """Extrae el contenido completo de los artículos."""
        
        # Verificar caché primero
        articles_to_fetch = []
        
        for article in articles:
            cached_content = await self.news_cache.get_article_content(article.id)
            if cached_content:
                article.full_content = cached_content
            else:
                articles_to_fetch.append(article)
        
        # Extraer contenido de los que no están en caché
        if articles_to_fetch:
            extracted = await self.article_extractor.extract_articles(
                articles_to_fetch,
                max_concurrent=5,
            )
            
            # Actualizar caché
            for article in extracted:
                if article.full_content and article.full_content != article.summary:
                    await self.news_cache.update_article_content(
                        article.id,
                        article.full_content,
                    )
        
        return articles
    
    async def _cache_audio(
        self,
        topic: str,
        audio_path: Path,
        script: str,
    ) -> None:
        """Cachea el audio generado."""
        if not self.config.cache.enabled:
            return
        
        if AsyncSessionLocal is None:
            await init_database()
        
        async with AsyncSessionLocal() as session:
            await crud.cache_audio(
                session,
                topic=topic,
                audio_path=str(audio_path),
                script_text=script,
                cache_hours=self.config.cache.news_cache_hours,
            )
    
    async def _update_request_metrics(
        self,
        user_id: int,
        topic: str,
        categories: list[str],
        news_count: int,
        processing_time: float,
        tokens_used: int,
        audio_path: str,
        script: str,
    ) -> None:
        """Actualiza las métricas de la petición."""
        if AsyncSessionLocal is None:
            await init_database()
        
        async with AsyncSessionLocal() as session:
            # Buscar la petición más reciente del usuario con este tema
            requests = await crud.get_user_requests(session, user_id, limit=1)
            
            if requests and requests[0].topic == topic:
                await crud.update_news_request(
                    session,
                    request_id=requests[0].id,
                    status="completed",
                    audio_path=audio_path,
                    script_text=script,
                    categories_used=",".join(categories),
                    news_count=news_count,
                    processing_time_seconds=processing_time,
                    tokens_used=tokens_used,
                )


# Instancia global del pipeline
_pipeline: Optional[NewsPipeline] = None


def get_pipeline() -> NewsPipeline:
    """Obtiene la instancia del pipeline."""
    global _pipeline
    if _pipeline is None:
        _pipeline = NewsPipeline()
    return _pipeline


async def generate_news(user_id: int, topic: str) -> Optional[Tuple[Path, str]]:
    """Función de conveniencia para generar noticias."""
    pipeline = get_pipeline()
    return await pipeline.generate_news_audio(user_id, topic)
