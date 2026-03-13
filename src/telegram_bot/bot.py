"""
Bot de Telegram principal.
"""

import logging
from typing import Callable, Optional
from pathlib import Path

from telegram import Update
from telegram.ext import Application, ApplicationBuilder

from src.config import get_config
from .handlers import setup_handlers

logger = logging.getLogger(__name__)


class TelegramBot:
    """Bot de Telegram para Custom News."""
    
    def __init__(self):
        self.config = get_config()
        self.app: Optional[Application] = None
        self._news_generator_callback: Optional[Callable] = None
    
    def set_news_generator_callback(self, callback: Callable) -> None:
        """
        Establece el callback para generar noticias.
        
        Args:
            callback: Función async que recibe (user_id, topic) y devuelve (audio_path, script)
        """
        self._news_generator_callback = callback
    
    async def initialize(self) -> None:
        """Inicializa el bot."""
        if not self.config.telegram_bot_token:
            raise ValueError("Telegram bot token not configured")
        
        self.app = (
            ApplicationBuilder()
            .token(self.config.telegram_bot_token)
            .build()
        )
        
        # Configurar handlers
        setup_handlers(self.app, self._news_generator_callback)
        
        logger.info("Telegram bot initialized")
    
    async def start(self) -> None:
        """Inicia el bot en modo polling."""
        if self.app is None:
            await self.initialize()
        
        logger.info("Starting Telegram bot...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)
    
    async def stop(self) -> None:
        """Detiene el bot."""
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            logger.info("Telegram bot stopped")
    
    async def send_audio(
        self,
        telegram_id: str,
        audio_path: str,
        topic: str,
    ) -> bool:
        """
        Envía un audio a un usuario.
        
        Args:
            telegram_id: ID de Telegram del usuario
            audio_path: Ruta al archivo de audio
            topic: Tema de las noticias
        
        Returns:
            True si se envió correctamente
        """
        try:
            if self.app is None:
                await self.initialize()
                await self.app.initialize()
            
            chat_id = int(telegram_id)
            
            with open(audio_path, "rb") as audio_file:
                await self.app.bot.send_audio(
                    chat_id=chat_id,
                    audio=audio_file,
                    title=f"Noticias: {topic[:50]}",
                    caption=f"📰 Tu resumen de noticias sobre: {topic}",
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending audio to {telegram_id}: {e}")
            return False
    
    async def send_message(
        self,
        telegram_id: str,
        message: str,
    ) -> bool:
        """
        Envía un mensaje a un usuario.
        
        Args:
            telegram_id: ID de Telegram del usuario
            message: Mensaje a enviar
        
        Returns:
            True si se envió correctamente
        """
        try:
            if self.app is None:
                await self.initialize()
                await self.app.initialize()
            
            chat_id = int(telegram_id)
            await self.app.bot.send_message(chat_id=chat_id, text=message)
            return True
            
        except Exception as e:
            logger.error(f"Error sending message to {telegram_id}: {e}")
            return False
