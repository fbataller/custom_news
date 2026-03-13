"""
Parser de feeds RSS.
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from pathlib import Path

import feedparser
import httpx
import yaml
from dateutil import parser as date_parser

from src.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class RSSArticle:
    """Representa un artículo de RSS."""
    
    id: str
    title: str
    link: str
    summary: str = ""
    published_at: Optional[datetime] = None
    source: str = ""
    category: str = ""
    full_content: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convierte el artículo a diccionario."""
        return {
            "id": self.id,
            "title": self.title,
            "link": self.link,
            "summary": self.summary,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "source": self.source,
            "category": self.category,
        }
    
    @staticmethod
    def generate_id(link: str, title: str) -> str:
        """Genera un ID único para el artículo."""
        content = f"{link}{title}"
        return hashlib.md5(content.encode()).hexdigest()[:16]


@dataclass
class RSSFeed:
    """Representa un feed RSS."""
    
    name: str
    url: str
    category: str = ""
    articles: list[RSSArticle] = field(default_factory=list)


@dataclass
class RSSCategory:
    """Representa una categoría de feeds."""
    
    id: str
    name: str
    description: str
    feeds: list[RSSFeed] = field(default_factory=list)


class RSSParser:
    """Parser de feeds RSS."""
    
    def __init__(self):
        self.config = get_config()
        self._categories: dict[str, RSSCategory] = {}
        self._load_feeds()
    
    def _load_feeds(self) -> None:
        """Carga los feeds desde el archivo YAML."""
        feeds_path = self.config.get_feeds_path()
        
        if not feeds_path.exists():
            logger.warning(f"Feeds file not found: {feeds_path}")
            return
        
        with open(feeds_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        categories_data = data.get("categories", {})
        
        for cat_id, cat_info in categories_data.items():
            feeds = []
            for feed_data in cat_info.get("feeds", []):
                feed = RSSFeed(
                    name=feed_data["name"],
                    url=feed_data["url"],
                    category=cat_id,
                )
                feeds.append(feed)
            
            category = RSSCategory(
                id=cat_id,
                name=cat_info.get("name", cat_id),
                description=cat_info.get("description", ""),
                feeds=feeds,
            )
            self._categories[cat_id] = category
    
    def get_categories(self) -> dict[str, RSSCategory]:
        """Obtiene todas las categorías disponibles."""
        return self._categories
    
    def get_category_names(self) -> dict[str, str]:
        """Obtiene un mapeo de ID -> nombre de categoría."""
        return {cat_id: cat.name for cat_id, cat in self._categories.items()}
    
    def get_categories_description(self) -> str:
        """Obtiene una descripción formateada de las categorías."""
        lines = []
        for cat_id, cat in self._categories.items():
            lines.append(f"- {cat_id}: {cat.name} - {cat.description}")
        return "\n".join(lines)
    
    async def fetch_feed(self, feed: RSSFeed) -> list[RSSArticle]:
        """Obtiene los artículos de un feed."""
        articles = []
        
        try:
            async with httpx.AsyncClient(timeout=self.config.rss.timeout_seconds) as client:
                response = await client.get(
                    feed.url,
                    headers={"User-Agent": self.config.scraper.user_agent},
                    follow_redirects=True,
                )
                response.raise_for_status()
                content = response.text
            
            parsed = feedparser.parse(content)
            
            max_articles = self.config.rss.max_articles_per_feed
            
            for entry in parsed.entries[:max_articles]:
                try:
                    # Parsear fecha
                    published_at = None
                    if hasattr(entry, "published"):
                        try:
                            published_at = date_parser.parse(entry.published)
                        except Exception:
                            pass
                    elif hasattr(entry, "updated"):
                        try:
                            published_at = date_parser.parse(entry.updated)
                        except Exception:
                            pass
                    
                    # Obtener resumen
                    summary = ""
                    if hasattr(entry, "summary"):
                        summary = entry.summary
                    elif hasattr(entry, "description"):
                        summary = entry.description
                    
                    # Limpiar HTML del resumen
                    summary = self._clean_html(summary)
                    
                    # Generar ID único
                    link = entry.get("link", "")
                    title = entry.get("title", "")
                    article_id = RSSArticle.generate_id(link, title)
                    
                    article = RSSArticle(
                        id=article_id,
                        title=title,
                        link=link,
                        summary=summary[:2000],  # Limitar longitud
                        published_at=published_at,
                        source=feed.name,
                        category=feed.category,
                    )
                    articles.append(article)
                    
                except Exception as e:
                    logger.warning(f"Error parsing entry from {feed.name}: {e}")
                    continue
            
            logger.info(f"Fetched {len(articles)} articles from {feed.name}")
            
        except httpx.TimeoutException:
            logger.warning(f"Timeout fetching {feed.name}")
        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error fetching {feed.name}: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching {feed.name}: {e}")
        
        return articles
    
    async def fetch_category(self, category_id: str) -> list[RSSArticle]:
        """Obtiene todos los artículos de una categoría."""
        if category_id not in self._categories:
            logger.warning(f"Category not found: {category_id}")
            return []
        
        category = self._categories[category_id]
        all_articles = []
        
        # Fetch all feeds in parallel
        tasks = [self.fetch_feed(feed) for feed in category.feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error fetching feed: {result}")
                continue
            all_articles.extend(result)
        
        # Ordenar por fecha (más recientes primero)
        all_articles.sort(
            key=lambda x: x.published_at or datetime.min,
            reverse=True
        )
        
        logger.info(f"Fetched {len(all_articles)} total articles from category {category_id}")
        return all_articles
    
    async def fetch_categories(self, category_ids: list[str]) -> dict[str, list[RSSArticle]]:
        """Obtiene artículos de múltiples categorías."""
        results = {}
        
        # Fetch categories in parallel
        tasks = {cat_id: self.fetch_category(cat_id) for cat_id in category_ids}
        
        for cat_id, task in tasks.items():
            try:
                results[cat_id] = await task
            except Exception as e:
                logger.error(f"Error fetching category {cat_id}: {e}")
                results[cat_id] = []
        
        return results
    
    def _clean_html(self, text: str) -> str:
        """Limpia HTML del texto."""
        from bs4 import BeautifulSoup
        
        if not text:
            return ""
        
        try:
            soup = BeautifulSoup(text, "html.parser")
            return soup.get_text(separator=" ", strip=True)
        except Exception:
            return text
    
    def format_articles_for_llm(self, articles: list[RSSArticle]) -> str:
        """Formatea los artículos para enviar al LLM."""
        lines = []
        
        for article in articles:
            published = ""
            if article.published_at:
                published = article.published_at.strftime("%Y-%m-%d %H:%M")
            
            lines.append(f"""
ID: {article.id}
Título: {article.title}
Fuente: {article.source}
Fecha: {published}
Resumen: {article.summary}
---""")
        
        return "\n".join(lines)
