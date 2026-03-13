"""
Operaciones CRUD para la base de datos.
"""

from datetime import datetime, timedelta
from typing import Optional
import hashlib

from sqlalchemy import select, delete, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from .models import (
    User,
    ScheduledNews,
    NewsRequest,
    NewsCache,
    AudioCache,
    DailyUsage,
    TokenUsage,
    get_sync_session,
)


# ============== USUARIOS ==============

async def get_or_create_user(
    session: AsyncSession,
    telegram_id: str,
    username: Optional[str] = None
) -> User:
    """Obtiene o crea un usuario por su telegram_id."""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    elif username and user.username != username:
        user.username = username
        await session.commit()
    
    return user


async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    """Obtiene un usuario por su ID."""
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: str) -> Optional[User]:
    """Obtiene un usuario por su telegram_id."""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_all_users(session: AsyncSession) -> list[User]:
    """Obtiene todos los usuarios."""
    result = await session.execute(select(User).where(User.is_active == True))
    return list(result.scalars().all())


# ============== NOTICIAS PROGRAMADAS ==============

async def create_scheduled_news(
    session: AsyncSession,
    user_id: int,
    topic: str,
    hour: int,
    minute: int = 0
) -> ScheduledNews:
    """Crea una noticia programada."""
    scheduled = ScheduledNews(
        user_id=user_id,
        topic=topic,
        hour=hour,
        minute=minute,
    )
    session.add(scheduled)
    await session.commit()
    await session.refresh(scheduled)
    return scheduled


async def get_user_scheduled_news(
    session: AsyncSession,
    user_id: int
) -> list[ScheduledNews]:
    """Obtiene las noticias programadas de un usuario."""
    result = await session.execute(
        select(ScheduledNews)
        .where(and_(ScheduledNews.user_id == user_id, ScheduledNews.is_active == True))
    )
    return list(result.scalars().all())


async def get_scheduled_news_count(session: AsyncSession, user_id: int) -> int:
    """Obtiene el número de noticias programadas de un usuario."""
    result = await session.execute(
        select(func.count(ScheduledNews.id))
        .where(and_(ScheduledNews.user_id == user_id, ScheduledNews.is_active == True))
    )
    return result.scalar() or 0


async def delete_scheduled_news(session: AsyncSession, scheduled_id: int, user_id: int) -> bool:
    """Elimina una noticia programada."""
    result = await session.execute(
        select(ScheduledNews)
        .where(and_(ScheduledNews.id == scheduled_id, ScheduledNews.user_id == user_id))
    )
    scheduled = result.scalar_one_or_none()
    
    if scheduled:
        await session.delete(scheduled)
        await session.commit()
        return True
    return False


async def get_pending_scheduled_news(session: AsyncSession, hour: int, minute: int) -> list[ScheduledNews]:
    """Obtiene las noticias programadas para una hora específica."""
    result = await session.execute(
        select(ScheduledNews)
        .where(and_(
            ScheduledNews.hour == hour,
            ScheduledNews.minute == minute,
            ScheduledNews.is_active == True
        ))
    )
    return list(result.scalars().all())


async def update_scheduled_last_sent(session: AsyncSession, scheduled_id: int) -> None:
    """Actualiza la fecha de último envío de una noticia programada."""
    result = await session.execute(
        select(ScheduledNews).where(ScheduledNews.id == scheduled_id)
    )
    scheduled = result.scalar_one_or_none()
    if scheduled:
        scheduled.last_sent_at = datetime.utcnow()
        await session.commit()


# ============== PETICIONES DE NOTICIAS ==============

async def create_news_request(
    session: AsyncSession,
    user_id: int,
    topic: str,
    request_type: str = "ondemand"
) -> NewsRequest:
    """Crea una petición de noticias."""
    request = NewsRequest(
        user_id=user_id,
        topic=topic,
        request_type=request_type,
    )
    session.add(request)
    await session.commit()
    await session.refresh(request)
    return request


async def update_news_request(
    session: AsyncSession,
    request_id: int,
    status: Optional[str] = None,
    audio_path: Optional[str] = None,
    script_text: Optional[str] = None,
    error_message: Optional[str] = None,
    categories_used: Optional[str] = None,
    news_count: Optional[int] = None,
    processing_time_seconds: Optional[float] = None,
    tokens_used: Optional[int] = None,
) -> Optional[NewsRequest]:
    """Actualiza una petición de noticias."""
    result = await session.execute(
        select(NewsRequest).where(NewsRequest.id == request_id)
    )
    request = result.scalar_one_or_none()
    
    if request:
        if status:
            request.status = status
        if audio_path:
            request.audio_path = audio_path
        if script_text:
            request.script_text = script_text
        if error_message:
            request.error_message = error_message
        if categories_used:
            request.categories_used = categories_used
        if news_count is not None:
            request.news_count = news_count
        if processing_time_seconds is not None:
            request.processing_time_seconds = processing_time_seconds
        if tokens_used is not None:
            request.tokens_used = tokens_used
        
        if status == "completed":
            request.completed_at = datetime.utcnow()
        
        await session.commit()
        await session.refresh(request)
    
    return request


async def get_news_request(session: AsyncSession, request_id: int) -> Optional[NewsRequest]:
    """Obtiene una petición de noticias por su ID."""
    result = await session.execute(
        select(NewsRequest).where(NewsRequest.id == request_id)
    )
    return result.scalar_one_or_none()


async def get_user_requests(
    session: AsyncSession,
    user_id: int,
    limit: int = 10
) -> list[NewsRequest]:
    """Obtiene las últimas peticiones de un usuario."""
    result = await session.execute(
        select(NewsRequest)
        .where(NewsRequest.user_id == user_id)
        .order_by(NewsRequest.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ============== USO DIARIO ==============

async def get_daily_usage(session: AsyncSession, user_id: int, date: str) -> Optional[DailyUsage]:
    """Obtiene el uso diario de un usuario."""
    result = await session.execute(
        select(DailyUsage)
        .where(and_(DailyUsage.user_id == user_id, DailyUsage.date == date))
    )
    return result.scalar_one_or_none()


async def increment_daily_usage(
    session: AsyncSession,
    user_id: int,
    request_type: str = "ondemand"
) -> DailyUsage:
    """Incrementa el uso diario de un usuario."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    usage = await get_daily_usage(session, user_id, today)
    
    if usage is None:
        usage = DailyUsage(user_id=user_id, date=today, ondemand_count=0, scheduled_count=0)
        session.add(usage)

    if usage.ondemand_count is None:
        usage.ondemand_count = 0
    if usage.scheduled_count is None:
        usage.scheduled_count = 0
    
    if request_type == "ondemand":
        usage.ondemand_count += 1
    else:
        usage.scheduled_count += 1
    
    await session.commit()
    await session.refresh(usage)
    return usage


async def get_ondemand_count_today(session: AsyncSession, user_id: int) -> int:
    """Obtiene el número de peticiones on-demand de hoy."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    usage = await get_daily_usage(session, user_id, today)
    if not usage or usage.ondemand_count is None:
        return 0
    return usage.ondemand_count


# ============== CACHÉ DE NOTICIAS ==============

async def cache_news_article(
    session: AsyncSession,
    category: str,
    feed_url: str,
    article_id: str,
    title: str,
    link: str,
    summary: Optional[str] = None,
    full_content: Optional[str] = None,
    published_at: Optional[datetime] = None,
) -> NewsCache:
    """Cachea un artículo de noticias."""
    # Verificar si ya existe
    result = await session.execute(
        select(NewsCache).where(NewsCache.article_id == article_id)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        # Actualizar si hay contenido nuevo
        if full_content and not existing.full_content:
            existing.full_content = full_content
            existing.content_extracted = True
        existing.fetched_at = datetime.utcnow()
        await session.commit()
        return existing
    
    # Crear nuevo
    article = NewsCache(
        category=category,
        feed_url=feed_url,
        article_id=article_id,
        title=title,
        link=link,
        summary=summary,
        full_content=full_content,
        published_at=published_at,
        content_extracted=bool(full_content),
    )
    session.add(article)
    await session.commit()
    await session.refresh(article)
    return article


async def get_cached_news_by_category(
    session: AsyncSession,
    category: str,
    hours: int = 3
) -> list[NewsCache]:
    """Obtiene noticias cacheadas de una categoría."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    result = await session.execute(
        select(NewsCache)
        .where(and_(NewsCache.category == category, NewsCache.fetched_at >= cutoff))
        .order_by(NewsCache.published_at.desc())
    )
    return list(result.scalars().all())


async def get_cached_article(session: AsyncSession, article_id: str) -> Optional[NewsCache]:
    """Obtiene un artículo cacheado por su ID."""
    result = await session.execute(
        select(NewsCache).where(NewsCache.article_id == article_id)
    )
    return result.scalar_one_or_none()


async def cleanup_old_cache(session: AsyncSession, hours: int = 24) -> int:
    """Limpia el caché antiguo."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    result = await session.execute(
        delete(NewsCache).where(NewsCache.fetched_at < cutoff)
    )
    await session.commit()
    return result.rowcount


# ============== CACHÉ DE AUDIO ==============

def generate_topic_hash(topic: str) -> str:
    """Genera un hash para el tema."""
    normalized = topic.lower().strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


async def get_cached_audio(session: AsyncSession, topic: str) -> Optional[AudioCache]:
    """Obtiene un audio cacheado por tema."""
    topic_hash = generate_topic_hash(topic)
    now = datetime.utcnow()
    
    result = await session.execute(
        select(AudioCache)
        .where(and_(AudioCache.topic_hash == topic_hash, AudioCache.expires_at > now))
    )
    cached = result.scalar_one_or_none()
    
    if cached:
        cached.times_used += 1
        await session.commit()
    
    return cached


async def cache_audio(
    session: AsyncSession,
    topic: str,
    audio_path: str,
    script_text: Optional[str] = None,
    cache_hours: int = 3
) -> AudioCache:
    """Cachea un audio generado."""
    topic_hash = generate_topic_hash(topic)
    expires_at = datetime.utcnow() + timedelta(hours=cache_hours)
    
    # Eliminar caché anterior del mismo tema
    await session.execute(
        delete(AudioCache).where(AudioCache.topic_hash == topic_hash)
    )
    
    audio_cache = AudioCache(
        topic_hash=topic_hash,
        topic=topic,
        audio_path=audio_path,
        script_text=script_text,
        expires_at=expires_at,
    )
    session.add(audio_cache)
    await session.commit()
    await session.refresh(audio_cache)
    return audio_cache


async def cleanup_expired_audio_cache(session: AsyncSession) -> int:
    """Limpia los audios expirados del caché."""
    now = datetime.utcnow()
    result = await session.execute(
        delete(AudioCache).where(AudioCache.expires_at < now)
    )
    await session.commit()
    return result.rowcount


# ============== ESTADÍSTICAS ==============

async def get_stats(session: AsyncSession) -> dict:
    """Obtiene estadísticas generales."""
    # Total de usuarios
    users_result = await session.execute(select(func.count(User.id)))
    total_users = users_result.scalar() or 0
    
    # Total de peticiones
    requests_result = await session.execute(select(func.count(NewsRequest.id)))
    total_requests = requests_result.scalar() or 0
    
    # Peticiones completadas
    completed_result = await session.execute(
        select(func.count(NewsRequest.id))
        .where(NewsRequest.status == "completed")
    )
    completed_requests = completed_result.scalar() or 0
    
    # Noticias programadas activas
    scheduled_result = await session.execute(
        select(func.count(ScheduledNews.id))
        .where(ScheduledNews.is_active == True)
    )
    active_scheduled = scheduled_result.scalar() or 0
    
    # Artículos en caché
    cache_result = await session.execute(select(func.count(NewsCache.id)))
    cached_articles = cache_result.scalar() or 0
    
    return {
        "total_users": total_users,
        "total_requests": total_requests,
        "completed_requests": completed_requests,
        "active_scheduled": active_scheduled,
        "cached_articles": cached_articles,
    }


# ============== FUNCIONES SÍNCRONAS PARA STREAMLIT ==============

def sync_get_all_users() -> list[User]:
    """Versión síncrona para obtener todos los usuarios."""
    session = get_sync_session()
    try:
        result = session.query(User).filter(User.is_active == True).all()
        return result
    finally:
        session.close()


def sync_get_stats() -> dict:
    """Versión síncrona para obtener estadísticas."""
    session = get_sync_session()
    try:
        total_users = session.query(func.count(User.id)).scalar() or 0
        total_requests = session.query(func.count(NewsRequest.id)).scalar() or 0
        completed_requests = session.query(func.count(NewsRequest.id)).filter(
            NewsRequest.status == "completed"
        ).scalar() or 0
        active_scheduled = session.query(func.count(ScheduledNews.id)).filter(
            ScheduledNews.is_active == True
        ).scalar() or 0
        cached_articles = session.query(func.count(NewsCache.id)).scalar() or 0
        
        return {
            "total_users": total_users,
            "total_requests": total_requests,
            "completed_requests": completed_requests,
            "active_scheduled": active_scheduled,
            "cached_articles": cached_articles,
        }
    finally:
        session.close()


def sync_get_recent_requests(limit: int = 20) -> list[NewsRequest]:
    """Versión síncrona para obtener peticiones recientes."""
    session = get_sync_session()
    try:
        result = session.query(NewsRequest).order_by(
            NewsRequest.created_at.desc()
        ).limit(limit).all()
        return result
    finally:
        session.close()


def sync_get_user_by_telegram_id(telegram_id: str) -> Optional[User]:
    """Versión síncrona para obtener usuario por telegram_id."""
    session = get_sync_session()
    try:
        return session.query(User).filter(User.telegram_id == telegram_id).first()
    finally:
        session.close()


# ============== TRACKING DE TOKENS ==============

# Precios aproximados por 1M tokens (USD) - Actualizar según pricing actual
TOKEN_PRICES = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "tts-1": {"input": 15.00, "output": 0},  # $15 per 1M characters
    "tts-1-hd": {"input": 30.00, "output": 0},
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estima el costo en USD basado en el modelo y tokens."""
    prices = TOKEN_PRICES.get(model, {"input": 0, "output": 0})
    input_cost = (prompt_tokens / 1_000_000) * prices["input"]
    output_cost = (completion_tokens / 1_000_000) * prices["output"]
    return input_cost + output_cost


async def record_token_usage(
    session: AsyncSession,
    model: str,
    provider: str,
    usage_type: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
) -> TokenUsage:
    """Registra el uso de tokens."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    # Buscar registro existente
    result = await session.execute(
        select(TokenUsage)
        .where(and_(
            TokenUsage.date == today,
            TokenUsage.model == model,
            TokenUsage.usage_type == usage_type,
        ))
    )
    usage = result.scalar_one_or_none()
    
    estimated_cost = estimate_cost(model, prompt_tokens, completion_tokens)
    
    if usage:
        usage.prompt_tokens += prompt_tokens
        usage.completion_tokens += completion_tokens
        usage.total_tokens += total_tokens
        usage.requests_count += 1
        usage.estimated_cost_usd += estimated_cost
    else:
        usage = TokenUsage(
            date=today,
            model=model,
            provider=provider,
            usage_type=usage_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            requests_count=1,
            estimated_cost_usd=estimated_cost,
        )
        session.add(usage)
    
    await session.commit()
    await session.refresh(usage)
    return usage


async def get_token_usage_by_date(
    session: AsyncSession,
    date: Optional[str] = None,
) -> list[TokenUsage]:
    """Obtiene el uso de tokens por fecha."""
    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")
    
    result = await session.execute(
        select(TokenUsage)
        .where(TokenUsage.date == date)
        .order_by(TokenUsage.model)
    )
    return list(result.scalars().all())


async def get_token_usage_summary(
    session: AsyncSession,
    days: int = 7,
) -> dict:
    """Obtiene un resumen del uso de tokens en los últimos N días."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    result = await session.execute(
        select(TokenUsage)
        .where(TokenUsage.date >= cutoff)
    )
    usages = result.scalars().all()
    
    # Agrupar por modelo
    by_model = {}
    total_tokens = 0
    total_cost = 0.0
    total_requests = 0
    
    for usage in usages:
        if usage.model not in by_model:
            by_model[usage.model] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "requests": 0,
                "cost_usd": 0.0,
            }
        
        by_model[usage.model]["prompt_tokens"] += usage.prompt_tokens
        by_model[usage.model]["completion_tokens"] += usage.completion_tokens
        by_model[usage.model]["total_tokens"] += usage.total_tokens
        by_model[usage.model]["requests"] += usage.requests_count
        by_model[usage.model]["cost_usd"] += usage.estimated_cost_usd
        
        total_tokens += usage.total_tokens
        total_cost += usage.estimated_cost_usd
        total_requests += usage.requests_count
    
    return {
        "period_days": days,
        "by_model": by_model,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "total_requests": total_requests,
    }


# ============== ESTADÍSTICAS DE ADMIN ==============

async def get_admin_stats(session: AsyncSession) -> dict:
    """Obtiene estadísticas completas para admin."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    week_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    # Usuarios
    total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0
    active_users = (await session.execute(
        select(func.count(User.id)).where(User.is_active == True)
    )).scalar() or 0
    
    # Usuarios nuevos esta semana
    new_users_week = (await session.execute(
        select(func.count(User.id))
        .where(User.created_at >= datetime.utcnow() - timedelta(days=7))
    )).scalar() or 0
    
    # Peticiones
    total_requests = (await session.execute(select(func.count(NewsRequest.id)))).scalar() or 0
    completed_requests = (await session.execute(
        select(func.count(NewsRequest.id))
        .where(NewsRequest.status == "completed")
    )).scalar() or 0
    failed_requests = (await session.execute(
        select(func.count(NewsRequest.id))
        .where(NewsRequest.status == "failed")
    )).scalar() or 0
    
    # Peticiones hoy
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    requests_today = (await session.execute(
        select(func.count(NewsRequest.id))
        .where(NewsRequest.created_at >= today_start)
    )).scalar() or 0
    
    # Peticiones esta semana
    requests_week = (await session.execute(
        select(func.count(NewsRequest.id))
        .where(NewsRequest.created_at >= datetime.utcnow() - timedelta(days=7))
    )).scalar() or 0
    
    # Noticias programadas
    active_scheduled = (await session.execute(
        select(func.count(ScheduledNews.id))
        .where(ScheduledNews.is_active == True)
    )).scalar() or 0
    
    # Tiempo promedio de procesamiento
    avg_time_result = await session.execute(
        select(func.avg(NewsRequest.processing_time_seconds))
        .where(and_(
            NewsRequest.status == "completed",
            NewsRequest.processing_time_seconds.isnot(None)
        ))
    )
    avg_processing_time = avg_time_result.scalar() or 0
    
    # Tokens (últimos 7 días)
    token_summary = await get_token_usage_summary(session, days=7)
    
    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "new_this_week": new_users_week,
        },
        "requests": {
            "total": total_requests,
            "completed": completed_requests,
            "failed": failed_requests,
            "today": requests_today,
            "this_week": requests_week,
            "success_rate": (completed_requests / total_requests * 100) if total_requests > 0 else 0,
        },
        "scheduled": {
            "active": active_scheduled,
        },
        "performance": {
            "avg_processing_time_sec": round(avg_processing_time, 2),
        },
        "tokens": token_summary,
    }
