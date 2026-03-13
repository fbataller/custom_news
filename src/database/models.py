"""
Modelos de base de datos SQLAlchemy.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    Float,
    create_engine,
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class User(Base):
    """Modelo de usuario."""
    
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(String(50), unique=True, nullable=True, index=True)
    username = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    timezone = Column(String(50), default="Europe/Madrid")
    
    # Relaciones
    scheduled_news = relationship("ScheduledNews", back_populates="user", cascade="all, delete-orphan")
    news_requests = relationship("NewsRequest", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id={self.telegram_id})>"


class ScheduledNews(Base):
    """Modelo de noticias programadas."""
    
    __tablename__ = "scheduled_news"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    topic = Column(String(500), nullable=False)
    hour = Column(Integer, nullable=False)  # Hora del día (0-23)
    minute = Column(Integer, default=0)  # Minuto (0-59)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_sent_at = Column(DateTime, nullable=True)
    
    # Relaciones
    user = relationship("User", back_populates="scheduled_news")
    
    def __repr__(self) -> str:
        return f"<ScheduledNews(id={self.id}, topic={self.topic[:30]}..., hour={self.hour})>"


class NewsRequest(Base):
    """Modelo de peticiones de noticias (on-demand)."""
    
    __tablename__ = "news_requests"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    topic = Column(String(500), nullable=False)
    status = Column(String(50), default="pending")  # pending, processing, completed, failed
    audio_path = Column(String(500), nullable=True)
    script_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    request_type = Column(String(20), default="ondemand")  # ondemand, scheduled
    
    # Métricas
    categories_used = Column(String(200), nullable=True)
    news_count = Column(Integer, nullable=True)
    processing_time_seconds = Column(Float, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    
    # Relaciones
    user = relationship("User", back_populates="news_requests")
    
    def __repr__(self) -> str:
        return f"<NewsRequest(id={self.id}, topic={self.topic[:30]}..., status={self.status})>"


class NewsCache(Base):
    """Modelo de caché de noticias."""
    
    __tablename__ = "news_cache"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(50), nullable=False, index=True)
    feed_url = Column(String(500), nullable=False)
    article_id = Column(String(200), nullable=False, unique=True, index=True)
    title = Column(String(500), nullable=False)
    summary = Column(Text, nullable=True)
    full_content = Column(Text, nullable=True)
    link = Column(String(500), nullable=False)
    published_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    content_extracted = Column(Boolean, default=False)
    
    def __repr__(self) -> str:
        return f"<NewsCache(id={self.id}, title={self.title[:30]}...)>"


class AudioCache(Base):
    """Modelo de caché de audios generados."""
    
    __tablename__ = "audio_cache"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_hash = Column(String(64), nullable=False, index=True)
    topic = Column(String(500), nullable=False)
    audio_path = Column(String(500), nullable=False)
    script_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    times_used = Column(Integer, default=1)
    
    def __repr__(self) -> str:
        return f"<AudioCache(id={self.id}, topic={self.topic[:30]}...)>"


class DailyUsage(Base):
    """Modelo para rastrear uso diario de usuarios."""
    
    __tablename__ = "daily_usage"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    ondemand_count = Column(Integer, default=0)
    scheduled_count = Column(Integer, default=0)
    
    def __repr__(self) -> str:
        return f"<DailyUsage(user_id={self.user_id}, date={self.date}, ondemand={self.ondemand_count})>"


class TokenUsage(Base):
    """Modelo para rastrear consumo de tokens por modelo."""
    
    __tablename__ = "token_usage"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    model = Column(String(100), nullable=False, index=True)
    provider = Column(String(50), nullable=False)  # openai, anthropic, etc.
    usage_type = Column(String(50), nullable=False)  # llm, tts
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    requests_count = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    
    def __repr__(self) -> str:
        return f"<TokenUsage(date={self.date}, model={self.model}, total={self.total_tokens})>"


# Motor y sesión async
async_engine = None
AsyncSessionLocal = None


def get_database_url() -> str:
    """Obtiene la URL de la base de datos desde la configuración."""
    from src.config import get_config
    config = get_config()
    return config.database.url


async def init_database() -> None:
    """Inicializa la base de datos y crea las tablas."""
    global async_engine, AsyncSessionLocal
    
    database_url = get_database_url()
    
    async_engine = create_async_engine(
        database_url,
        echo=False,
    )
    
    AsyncSessionLocal = sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Obtiene una sesión de base de datos."""
    if AsyncSessionLocal is None:
        await init_database()
    async with AsyncSessionLocal() as session:
        yield session


def get_sync_session():
    """Obtiene una sesión síncrona para Streamlit."""
    from src.config import get_config
    config = get_config()
    
    # Convertir URL async a sync
    sync_url = config.database.url.replace("+aiosqlite", "")
    engine = create_engine(sync_url, echo=False)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    return Session()
