"""
Generador de guiones de radio basado en LLM.
"""

import logging
from typing import Optional

from src.config import get_config
from src.rss.parser import RSSArticle
from .base import BaseLLMClient, LLMResponse
from .openai_client import get_llm_client

logger = logging.getLogger(__name__)


class ScriptGenerator:
    """Genera guiones de radio a partir de noticias."""
    
    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.config = get_config()
        self.llm = llm_client or get_llm_client()
    
    async def generate_script(
        self,
        articles: list[RSSArticle],
        user_request: str,
        duration_minutes: Optional[int] = None,
    ) -> tuple[str, int]:
        """
        Genera un guion de radio a partir de las noticias.
        
        Args:
            articles: Lista de artículos con contenido
            user_request: La petición original del usuario
            duration_minutes: Duración objetivo en minutos (opcional)
        
        Returns:
            Tuple de (script, tokens_used)
        """
        
        if not articles:
            return "No hay noticias disponibles para generar el resumen.", 0
        
        duration = duration_minutes or self.config.audio.target_duration_minutes
        words_per_minute = self.config.audio.words_per_minute
        target_words = duration * words_per_minute
        
        # Cargar prompts
        system_prompt = self.config.load_prompt("generate_script_system")
        user_prompt_template = self.config.load_prompt("generate_script_user")
        
        # Formatear prompts
        system_prompt = system_prompt.format(
            duration_minutes=duration,
            words_per_minute=words_per_minute,
        )
        
        # Preparar contenido de noticias
        news_content = self._format_news_content(articles)
        
        user_prompt = user_prompt_template.format(
            user_request=user_request,
            news_content=news_content,
            duration_minutes=duration,
            target_words=target_words,
        )
        
        try:
            response: LLMResponse = await self.llm.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.7,
                max_tokens=2000,
            )
            
            script = response.content.strip()
            
            # Limpiar el script si es necesario
            script = self._clean_script(script)
            
            logger.info(
                f"Generated script with ~{len(script.split())} words "
                f"(target: {target_words}), tokens used: {response.tokens_used}"
            )
            
            return script, response.tokens_used
            
        except Exception as e:
            logger.error(f"Error generating script: {e}")
            raise
    
    def _format_news_content(self, articles: list[RSSArticle]) -> str:
        """Formatea el contenido de las noticias para el prompt."""
        sections = []
        
        for i, article in enumerate(articles, 1):
            # Usar contenido completo si está disponible, sino el resumen
            content = article.full_content or article.summary
            
            # Limpiar y truncar si es necesario
            content = self._clean_text(content)
            max_length = self.config.scraper.max_article_length
            if len(content) > max_length:
                content = content[:max_length] + "..."
            
            published = ""
            if article.published_at:
                published = article.published_at.strftime("%Y-%m-%d")
            
            section = f"""
NOTICIA {i}:
Título: {article.title}
Fuente: {article.source}
Fecha: {published}
Contenido:
{content}
"""
            sections.append(section)
        
        return "\n---\n".join(sections)
    
    def _clean_text(self, text: str) -> str:
        """Limpia el texto de caracteres innecesarios."""
        import re
        
        if not text:
            return ""
        
        # Eliminar múltiples espacios en blanco
        text = re.sub(r'\s+', ' ', text)
        
        # Eliminar caracteres de control
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        
        # Eliminar URLs
        text = re.sub(r'https?://\S+', '', text)
        
        # Eliminar referencias a imágenes/videos
        text = re.sub(r'\[image\]|\[video\]|\[audio\]', '', text, flags=re.IGNORECASE)
        
        return text.strip()
    
    def _clean_script(self, script: str) -> str:
        """Limpia el guion generado."""
        # Eliminar posibles marcadores de código
        if script.startswith("```"):
            lines = script.split("\n")
            script = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        
        return script.strip()
