"""
Extractor de contenido de artículos web.
"""

import asyncio
import logging
from typing import Optional
from bs4 import BeautifulSoup
import httpx

from src.config import get_config
from src.rss.parser import RSSArticle

logger = logging.getLogger(__name__)


class ArticleExtractor:
    """Extrae el contenido completo de artículos web."""
    
    def __init__(self):
        self.config = get_config()
    
    async def extract_content(self, url: str) -> Optional[str]:
        """
        Extrae el contenido de un artículo desde su URL.
        
        Args:
            url: URL del artículo
        
        Returns:
            Contenido del artículo o None si falla
        """
        try:
            # Intentar con newspaper3k primero (extracción inteligente)
            content = await self._extract_with_newspaper(url)
            if content and len(content) > 100:
                return self._clean_content(content)
            
            # Fallback a extracción manual con BeautifulSoup
            content = await self._extract_with_beautifulsoup(url)
            if content and len(content) > 100:
                return self._clean_content(content)
            
            logger.warning(f"Could not extract content from {url}")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting content from {url}: {e}")
            return None
    
    async def _extract_with_newspaper(self, url: str) -> Optional[str]:
        """Extrae contenido usando newspaper3k."""
        try:
            from newspaper import Article
            
            # Ejecutar en un thread porque newspaper es síncrono
            loop = asyncio.get_event_loop()
            
            def download_and_parse():
                article = Article(url)
                article.download()
                article.parse()
                return article.text
            
            content = await loop.run_in_executor(None, download_and_parse)
            return content
            
        except Exception as e:
            logger.debug(f"newspaper extraction failed for {url}: {e}")
            return None
    
    async def _extract_with_beautifulsoup(self, url: str) -> Optional[str]:
        """Extrae contenido usando BeautifulSoup."""
        try:
            async with httpx.AsyncClient(
                timeout=self.config.scraper.timeout_seconds,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": self.config.scraper.user_agent},
                )
                response.raise_for_status()
                html = response.text
            
            soup = BeautifulSoup(html, "html.parser")
            
            # Eliminar scripts, estilos, navegación, etc.
            for tag in soup(["script", "style", "nav", "header", "footer", 
                           "aside", "form", "noscript", "iframe"]):
                tag.decompose()
            
            # Buscar el contenido principal
            content = None
            
            # Intentar encontrar el artículo por selectores comunes
            selectors = [
                "article",
                "[itemprop='articleBody']",
                ".article-body",
                ".story-body",
                ".post-content",
                ".entry-content",
                ".content-body",
                ".article-content",
                ".news-content",
                "main",
            ]
            
            for selector in selectors:
                element = soup.select_one(selector)
                if element:
                    content = element.get_text(separator=" ", strip=True)
                    if len(content) > 200:
                        break
            
            # Fallback: obtener todo el body
            if not content or len(content) < 200:
                body = soup.find("body")
                if body:
                    # Obtener los párrafos
                    paragraphs = body.find_all("p")
                    content = " ".join(p.get_text(strip=True) for p in paragraphs)
            
            return content
            
        except Exception as e:
            logger.debug(f"BeautifulSoup extraction failed for {url}: {e}")
            return None
    
    def _clean_content(self, content: str) -> str:
        """Limpia el contenido extraído."""
        import re
        
        if not content:
            return ""
        
        # Eliminar múltiples espacios en blanco
        content = re.sub(r'\s+', ' ', content)
        
        # Eliminar caracteres de control
        content = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', content)
        
        # Eliminar texto común no deseado
        patterns_to_remove = [
            r'Subscribe to our newsletter.*?$',
            r'Sign up for.*?newsletter',
            r'Follow us on.*?$',
            r'Share this article.*?$',
            r'Advertisement',
            r'ADVERTISEMENT',
            r'Read more:.*?$',
            r'Related:.*?$',
            r'Cookie.*?policy',
            r'Privacy.*?policy',
        ]
        
        for pattern in patterns_to_remove:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE)
        
        # Truncar si es demasiado largo
        max_length = self.config.scraper.max_article_length
        if len(content) > max_length:
            # Intentar cortar en un punto final
            truncated = content[:max_length]
            last_period = truncated.rfind('.')
            if last_period > max_length * 0.7:
                content = truncated[:last_period + 1]
            else:
                content = truncated + "..."
        
        return content.strip()
    
    async def extract_articles(
        self,
        articles: list[RSSArticle],
        max_concurrent: int = 5,
    ) -> list[RSSArticle]:
        """
        Extrae el contenido completo de una lista de artículos.
        
        Args:
            articles: Lista de artículos
            max_concurrent: Número máximo de extracciones concurrentes
        
        Returns:
            Lista de artículos con contenido actualizado
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def extract_with_semaphore(article: RSSArticle) -> RSSArticle:
            async with semaphore:
                content = await self.extract_content(article.link)
                if content:
                    article.full_content = content
                else:
                    # Usar el resumen como fallback
                    article.full_content = article.summary
                return article
        
        tasks = [extract_with_semaphore(article) for article in articles]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filtrar errores
        extracted_articles = []
        for result in results:
            if isinstance(result, RSSArticle):
                extracted_articles.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Error extracting article: {result}")
        
        success_count = sum(
            1 for a in extracted_articles
            if a.full_content and a.full_content != a.summary
        )
        logger.info(
            f"Extracted content for {success_count}/{len(articles)} articles"
        )
        
        return extracted_articles
