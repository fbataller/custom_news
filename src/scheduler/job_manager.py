"""
Gestor de trabajos programados.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional, Any
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.config import get_config
from src.database.models import init_database, AsyncSessionLocal
from src.database import crud

logger = logging.getLogger(__name__)


class JobManager:
    """Gestor de trabajos programados."""
    
    def __init__(self):
        self.config = get_config()
        self.scheduler = AsyncIOScheduler()
        self._news_generator_callback: Optional[Callable] = None
        self._send_callback: Optional[Callable] = None
    
    def set_news_generator_callback(self, callback: Callable) -> None:
        """
        Establece el callback para generar noticias.
        
        Args:
            callback: Función async que recibe (user_id, topic) y devuelve audio_path
        """
        self._news_generator_callback = callback
    
    def set_send_callback(self, callback: Callable) -> None:
        """
        Establece el callback para enviar noticias.
        
        Args:
            callback: Función async que recibe (telegram_id, audio_path, topic)
        """
        self._send_callback = callback
    
    async def start(self) -> None:
        """Inicia el scheduler."""
        # Inicializar base de datos
        await init_database()
        
        # Añadir job para verificar noticias programadas cada minuto
        self.scheduler.add_job(
            self._check_scheduled_news,
            IntervalTrigger(minutes=self.config.scheduler.check_interval_minutes),
            id="check_scheduled_news",
            replace_existing=True,
        )
        
        # Añadir job para limpieza de archivos antiguos
        self.scheduler.add_job(
            self._cleanup_old_files,
            IntervalTrigger(hours=self.config.scheduler.cleanup_interval_hours),
            id="cleanup_old_files",
            replace_existing=True,
        )
        
        # Añadir job para limpieza de caché expirado
        self.scheduler.add_job(
            self._cleanup_cache,
            IntervalTrigger(hours=6),
            id="cleanup_cache",
            replace_existing=True,
        )
        
        self.scheduler.start()
        logger.info("Scheduler started")
    
    def stop(self) -> None:
        """Detiene el scheduler."""
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")
    
    async def _check_scheduled_news(self) -> None:
        """Verifica y procesa las noticias programadas."""
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        
        if AsyncSessionLocal is None:
            await init_database()
        
        async with AsyncSessionLocal() as session:
            try:
                # Obtener noticias programadas para esta hora
                scheduled_news = await crud.get_pending_scheduled_news(
                    session,
                    current_hour,
                    current_minute,
                )
                
                for scheduled in scheduled_news:
                    # Verificar si no se ha enviado hoy
                    if scheduled.last_sent_at:
                        if scheduled.last_sent_at.date() == now.date():
                            continue
                    
                    # Obtener usuario
                    user = await crud.get_user_by_id(session, scheduled.user_id)
                    if not user or not user.telegram_id:
                        continue
                    
                    logger.info(
                        f"Processing scheduled news for user {user.telegram_id}: "
                        f"{scheduled.topic}"
                    )
                    
                    # Procesar en background
                    asyncio.create_task(
                        self._process_scheduled_news(
                            user.id,
                            user.telegram_id,
                            scheduled.id,
                            scheduled.topic,
                        )
                    )
                    
            except Exception as e:
                logger.error(f"Error checking scheduled news: {e}")
    
    async def _process_scheduled_news(
        self,
        user_id: int,
        telegram_id: str,
        scheduled_id: int,
        topic: str,
    ) -> None:
        """Procesa una noticia programada."""
        try:
            if not self._news_generator_callback:
                logger.error("News generator callback not set")
                return
            
            if not self._send_callback:
                logger.error("Send callback not set")
                return
            
            # Generar el audio
            audio_path = await self._news_generator_callback(user_id, topic)
            
            if audio_path:
                # Enviar al usuario
                await self._send_callback(telegram_id, audio_path, topic)
                
                # Actualizar last_sent_at
                if AsyncSessionLocal is None:
                    await init_database()
                
                async with AsyncSessionLocal() as session:
                    await crud.update_scheduled_last_sent(session, scheduled_id)
                    await crud.increment_daily_usage(session, user_id, "scheduled")
                
                logger.info(f"Scheduled news sent to {telegram_id}: {topic}")
            
        except Exception as e:
            logger.error(f"Error processing scheduled news: {e}")
    
    async def _cleanup_old_files(self) -> None:
        """Limpia archivos de audio antiguos."""
        try:
            output_dir = self.config.get_audio_output_path()
            retention_days = self.config.audio.retention_days
            cutoff = datetime.now() - timedelta(days=retention_days)
            
            deleted_count = 0
            
            for file_path in output_dir.glob("*.mp3"):
                try:
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_time < cutoff:
                        file_path.unlink()
                        deleted_count += 1
                except Exception as e:
                    logger.warning(f"Error deleting file {file_path}: {e}")
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old audio files")
                
        except Exception as e:
            logger.error(f"Error cleaning up old files: {e}")
    
    async def _cleanup_cache(self) -> None:
        """Limpia el caché expirado."""
        try:
            if AsyncSessionLocal is None:
                await init_database()
            
            async with AsyncSessionLocal() as session:
                # Limpiar caché de noticias (más de 24 horas)
                news_deleted = await crud.cleanup_old_cache(session, hours=24)
                
                # Limpiar caché de audio expirado
                audio_deleted = await crud.cleanup_expired_audio_cache(session)
                
                if news_deleted > 0 or audio_deleted > 0:
                    logger.info(
                        f"Cache cleanup: {news_deleted} news articles, "
                        f"{audio_deleted} audio files"
                    )
                    
        except Exception as e:
            logger.error(f"Error cleaning up cache: {e}")
