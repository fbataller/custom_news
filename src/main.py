"""
Punto de entrada principal de la aplicación Custom News.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


async def main():
    """Función principal que inicia todos los servicios."""
    from src.config import get_config
    from src.database.models import init_database
    from src.telegram_bot.bot import TelegramBot
    from src.scheduler.job_manager import JobManager
    from src.pipeline import generate_news
    
    config = get_config()
    
    logger.info("=" * 50)
    logger.info("Starting Custom News Application")
    logger.info("=" * 50)
    
    # Crear directorios necesarios
    config.get_audio_output_path()
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Inicializar base de datos
    logger.info("Initializing database...")
    await init_database()
    
    # Inicializar componentes
    telegram_bot = TelegramBot()
    job_manager = JobManager()
    
    # Configurar callbacks
    async def news_generator_callback(user_id: int, topic: str):
        """Callback para generar noticias."""
        return await generate_news(user_id, topic)
    
    async def send_audio_callback(telegram_id: str, audio_path: str, topic: str):
        """Callback para enviar audio por Telegram."""
        return await telegram_bot.send_audio(telegram_id, audio_path, topic)
    
    telegram_bot.set_news_generator_callback(news_generator_callback)
    job_manager.set_news_generator_callback(news_generator_callback)
    job_manager.set_send_callback(send_audio_callback)
    
    # Iniciar servicios
    try:
        # Iniciar scheduler
        logger.info("Starting scheduler...")
        await job_manager.start()
        
        # Iniciar bot de Telegram
        if config.telegram.enabled:
            logger.info("Starting Telegram bot...")
            await telegram_bot.start()
        
        logger.info("=" * 50)
        logger.info("Custom News is running!")
        logger.info("Press Ctrl+C to stop")
        logger.info("=" * 50)
        
        # Mantener la aplicación corriendo
        while True:
            await asyncio.sleep(1)
            
    except asyncio.CancelledError:
        logger.info("Shutting down...")
    finally:
        # Detener servicios
        if config.telegram.enabled:
            await telegram_bot.stop()
        job_manager.stop()
        logger.info("Application stopped")


def run_telegram_only():
    """Ejecuta solo el bot de Telegram."""
    asyncio.run(main())


def run_streamlit():
    """Ejecuta la interfaz web de Streamlit."""
    import subprocess
    import sys
    
    streamlit_app = Path(__file__).parent / "web" / "streamlit_app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(streamlit_app)])


def run_all():
    """Ejecuta Telegram y Streamlit en paralelo."""
    import subprocess
    import sys
    from threading import Thread
    
    # Iniciar Streamlit en un proceso separado
    streamlit_app = Path(__file__).parent / "web" / "streamlit_app.py"
    streamlit_process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(streamlit_app), "--server.headless", "true"]
    )
    
    try:
        # Ejecutar Telegram en el hilo principal
        asyncio.run(main())
    finally:
        streamlit_process.terminate()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Custom News Application")
    parser.add_argument(
        "--mode",
        choices=["telegram", "web", "all"],
        default="all",
        help="Modo de ejecución: telegram, web (Streamlit), o all (ambos)",
    )
    
    args = parser.parse_args()
    
    if args.mode == "telegram":
        run_telegram_only()
    elif args.mode == "web":
        run_streamlit()
    else:
        run_all()
