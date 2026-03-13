"""
Módulo de configuración centralizada.
Carga la configuración desde config.yaml y variables de entorno.
"""

import os
from pathlib import Path
from typing import Any, Optional
import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Directorio base del proyecto
BASE_DIR = Path(__file__).parent.parent


class LLMConfig(BaseModel):
    """Configuración del LLM."""
    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 4096


class TTSConfig(BaseModel):
    """Configuración del TTS."""
    provider: str = "openai"
    model: str = "tts-1"
    voice: str = "nova"
    speed: float = 1.0
    output_format: str = "mp3"


class AudioConfig(BaseModel):
    """Configuración del audio."""
    target_duration_minutes: int = 5
    words_per_minute: int = 150
    output_directory: str = "audio_output"
    retention_days: int = 2


class CacheConfig(BaseModel):
    """Configuración del caché."""
    enabled: bool = True
    news_cache_hours: int = 3
    feeds_cache_minutes: int = 30


class RSSConfig(BaseModel):
    """Configuración de RSS."""
    feeds_file: str = "data/rss_feeds.yaml"
    timeout_seconds: int = 30
    max_articles_per_feed: int = 20


class ScraperConfig(BaseModel):
    """Configuración del scraper."""
    timeout_seconds: int = 15
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    max_article_length: int = 10000


class UsersConfig(BaseModel):
    """Configuración de usuarios."""
    max_scheduled_news: int = 3
    max_ondemand_per_day: int = 3
    default_timezone: str = "Europe/Madrid"


class SchedulerConfig(BaseModel):
    """Configuración del scheduler."""
    check_interval_minutes: int = 1
    cleanup_interval_hours: int = 6


class TelegramConfig(BaseModel):
    """Configuración de Telegram."""
    enabled: bool = True
    admin_chat_ids: list[int] = []


class StreamlitConfig(BaseModel):
    """Configuración de Streamlit."""
    enabled: bool = True
    port: int = 8501
    theme: str = "dark"


class DatabaseConfig(BaseModel):
    """Configuración de la base de datos."""
    url: str = "sqlite+aiosqlite:///./data/news_app.db"
    echo: bool = False


class PromptsConfig(BaseModel):
    """Configuración de prompts."""
    directory: str = "data/prompts"


class LoggingConfig(BaseModel):
    """Configuración de logging."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: str = "logs/app.log"


class AppConfig(BaseModel):
    """Configuración general de la aplicación."""
    name: str = "Custom News"
    version: str = "0.1.0"
    debug: bool = False


class Settings(BaseSettings):
    """Configuración principal desde variables de entorno."""
    
    openai_api_key: str = ""
    telegram_bot_token: str = ""
    database_url: str = "sqlite+aiosqlite:///./data/news_app.db"
    environment: str = "development"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


class Config:
    """Clase principal de configuración que combina YAML y variables de entorno."""
    
    _instance: Optional["Config"] = None
    _config_data: dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self) -> None:
        """Carga la configuración desde el archivo YAML."""
        config_path = BASE_DIR / "config.yaml"
        
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self._config_data = yaml.safe_load(f) or {}
        else:
            self._config_data = {}
        
        # Cargar settings desde variables de entorno
        self._settings = Settings()
        
        # Inicializar configuraciones
        self.app = AppConfig(**self._config_data.get("app", {}))
        self.llm = LLMConfig(**self._config_data.get("llm", {}))
        self.tts = TTSConfig(**self._config_data.get("tts", {}))
        self.audio = AudioConfig(**self._config_data.get("audio", {}))
        self.cache = CacheConfig(**self._config_data.get("cache", {}))
        self.rss = RSSConfig(**self._config_data.get("rss", {}))
        self.scraper = ScraperConfig(**self._config_data.get("scraper", {}))
        self.users = UsersConfig(**self._config_data.get("users", {}))
        self.scheduler = SchedulerConfig(**self._config_data.get("scheduler", {}))
        self.telegram = TelegramConfig(**self._config_data.get("telegram", {}))
        self.streamlit = StreamlitConfig(**self._config_data.get("streamlit", {}))
        self.database = DatabaseConfig(**self._config_data.get("database", {}))
        self.prompts = PromptsConfig(**self._config_data.get("prompts", {}))
        self.logging = LoggingConfig(**self._config_data.get("logging", {}))
    
    @property
    def openai_api_key(self) -> str:
        """Obtiene la API key de OpenAI."""
        return self._settings.openai_api_key
    
    @property
    def telegram_bot_token(self) -> str:
        """Obtiene el token del bot de Telegram."""
        return self._settings.telegram_bot_token
    
    def get_prompts_path(self) -> Path:
        """Obtiene la ruta a los prompts."""
        return BASE_DIR / self.prompts.directory
    
    def get_feeds_path(self) -> Path:
        """Obtiene la ruta al archivo de feeds RSS."""
        return BASE_DIR / self.rss.feeds_file
    
    def get_audio_output_path(self) -> Path:
        """Obtiene la ruta de salida de audio."""
        path = BASE_DIR / self.audio.output_directory
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def get_database_path(self) -> Path:
        """Obtiene la ruta de la base de datos."""
        # Extraer el path del URL de SQLite
        url = self.database.url
        if "sqlite" in url:
            db_path = url.split("///")[-1]
            path = BASE_DIR / db_path
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        return Path(url)
    
    def load_prompt(self, prompt_name: str) -> str:
        """Carga un prompt desde archivo."""
        prompt_path = self.get_prompts_path() / f"{prompt_name}.txt"
        if prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        raise FileNotFoundError(f"Prompt not found: {prompt_name}")
    
    def reload(self) -> None:
        """Recarga la configuración."""
        self._load_config()


# Instancia global de configuración
def get_config() -> Config:
    """Obtiene la instancia de configuración."""
    return Config()
