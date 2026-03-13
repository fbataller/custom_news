"""
Aplicación web Streamlit para Custom News.
"""

import streamlit as st
import asyncio
from datetime import datetime
from pathlib import Path
import sys
from sqlalchemy import func

# Añadir el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import get_config
from src.database.crud import (
    sync_get_all_users,
    sync_get_stats,
    sync_get_recent_requests,
    sync_get_user_by_telegram_id,
)
from src.database.models import get_sync_session, User, ScheduledNews, NewsRequest, DailyUsage
from src.pipeline import generate_news


def _run_async(coro):
    """Ejecuta una coroutine desde contexto síncrono de Streamlit."""
    return asyncio.run(coro)


def _get_or_create_web_user(telegram_id: str) -> User:
    """Obtiene o crea un usuario para operaciones desde web."""
    session = get_sync_session()
    try:
        user = session.query(User).filter(User.telegram_id == telegram_id).first()
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=f"web_{telegram_id}" if telegram_id != "web_dashboard" else "web_dashboard",
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        return user
    finally:
        session.close()


def _get_ondemand_count_today(user_id: int) -> int:
    """Obtiene el número de peticiones on-demand del día para un usuario."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    session = get_sync_session()
    try:
        usage = session.query(DailyUsage).filter(
            DailyUsage.user_id == user_id,
            DailyUsage.date == today,
        ).first()
        return usage.ondemand_count if usage else 0
    finally:
        session.close()


def _increment_daily_usage(user_id: int, request_type: str = "ondemand") -> None:
    """Incrementa el uso diario para on-demand o scheduled."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    session = get_sync_session()
    try:
        usage = session.query(DailyUsage).filter(
            DailyUsage.user_id == user_id,
            DailyUsage.date == today,
        ).first()
        if usage is None:
            usage = DailyUsage(user_id=user_id, date=today, ondemand_count=0, scheduled_count=0)
            session.add(usage)

        if request_type == "ondemand":
            usage.ondemand_count += 1
        else:
            usage.scheduled_count += 1

        session.commit()
    finally:
        session.close()


def _create_news_request(user_id: int, topic: str) -> int:
    """Crea una petición de noticias y devuelve su ID."""
    session = get_sync_session()
    try:
        req = NewsRequest(user_id=user_id, topic=topic, request_type="ondemand", status="pending")
        session.add(req)
        session.commit()
        session.refresh(req)
        return req.id
    finally:
        session.close()


def _complete_news_request(request_id: int, audio_path: str, script: str) -> None:
    """Marca la petición como completada."""
    session = get_sync_session()
    try:
        req = session.query(NewsRequest).filter(NewsRequest.id == request_id).first()
        if req:
            req.status = "completed"
            req.audio_path = audio_path
            req.script_text = script
            req.completed_at = datetime.utcnow()
            session.commit()
    finally:
        session.close()


def _fail_news_request(request_id: int, error_message: str) -> None:
    """Marca la petición como fallida."""
    session = get_sync_session()
    try:
        req = session.query(NewsRequest).filter(NewsRequest.id == request_id).first()
        if req:
            req.status = "failed"
            req.error_message = error_message
            session.commit()
    finally:
        session.close()

# Configuración de la página
st.set_page_config(
    page_title="Custom News - Dashboard",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main():
    """Función principal de Streamlit."""
    
    # Sidebar para navegación
    st.sidebar.title("📰 Custom News")
    st.sidebar.markdown("---")
    
    page = st.sidebar.radio(
        "Navegación",
        ["🏠 Inicio", "📰 Generar Noticias", "⏰ Programar", "📊 Estadísticas", "⚙️ Configuración"],
    )
    
    st.sidebar.markdown("---")
    st.sidebar.info("MVP v0.1.0")
    
    if page == "🏠 Inicio":
        show_home_page()
    elif page == "📰 Generar Noticias":
        show_generate_page()
    elif page == "⏰ Programar":
        show_schedule_page()
    elif page == "📊 Estadísticas":
        show_stats_page()
    elif page == "⚙️ Configuración":
        show_config_page()


def show_home_page():
    """Página de inicio."""
    st.title("🏠 Dashboard - Custom News")
    st.markdown("Bienvenido al panel de control de Custom News.")
    
    # Métricas principales
    try:
        stats = sync_get_stats()
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("👥 Usuarios", stats["total_users"])
        
        with col2:
            st.metric("📰 Peticiones Totales", stats["total_requests"])
        
        with col3:
            st.metric("✅ Completadas", stats["completed_requests"])
        
        with col4:
            st.metric("⏰ Programadas Activas", stats["active_scheduled"])
        
    except Exception as e:
        st.warning(f"No se pudieron cargar las estadísticas: {e}")
    
    st.markdown("---")
    
    # Últimas peticiones
    st.subheader("📋 Últimas Peticiones")
    
    try:
        requests = sync_get_recent_requests(limit=10)
        
        if requests:
            for req in requests:
                status_icon = {
                    "pending": "🟡",
                    "processing": "🔵",
                    "completed": "🟢",
                    "failed": "🔴",
                }.get(req.status, "⚪")
                
                with st.expander(
                    f"{status_icon} {req.topic[:50]}... - {req.created_at.strftime('%d/%m %H:%M')}"
                ):
                    st.write(f"**Estado:** {req.status}")
                    st.write(f"**Tipo:** {req.request_type}")
                    st.write(f"**Creado:** {req.created_at}")
                    if req.completed_at:
                        st.write(f"**Completado:** {req.completed_at}")
                    if req.error_message:
                        st.error(f"Error: {req.error_message}")
        else:
            st.info("No hay peticiones recientes.")
            
    except Exception as e:
        st.warning(f"No se pudieron cargar las peticiones: {e}")


def show_generate_page():
    """Página para generar noticias on-demand."""
    st.title("📰 Generar Noticias")
    st.markdown("Genera un resumen de noticias sobre cualquier tema.")
    
    # Formulario
    with st.form("news_form"):
        topic = st.text_input(
            "Tema de las noticias",
            placeholder="Ej: inteligencia artificial, geopolítica, cambio climático...",
        )
        
        col1, col2 = st.columns(2)
        with col1:
            duration = st.slider("Duración (minutos)", 3, 10, 5)
        with col2:
            telegram_id = st.text_input(
                "Tu Telegram ID (opcional)",
                help="Si introduces tu ID, recibirás el audio también por Telegram.",
            )
        
        submitted = st.form_submit_button("🎙️ Generar Resumen", type="primary")
    
    if submitted:
        if not topic:
            st.error("Por favor, introduce un tema.")
            return

        effective_telegram_id = telegram_id.strip() if telegram_id else "web_dashboard"
        config = get_config()
        request_id = None

        with st.spinner("⏳ Generando resumen real... Esto puede tardar 1-3 minutos."):
            try:
                user = _get_or_create_web_user(effective_telegram_id)
                ondemand_today = _get_ondemand_count_today(user.id)

                if ondemand_today >= config.users.max_ondemand_per_day:
                    st.error(
                        f"❌ Has alcanzado el límite diario de {config.users.max_ondemand_per_day} peticiones."
                    )
                    return

                request_id = _create_news_request(user.id, topic)
                result = _run_async(generate_news(user.id, topic))

                if not result:
                    raise RuntimeError("No se pudo generar el audio para este tema.")

                audio_path, script = result
                audio_path = Path(audio_path)

                _complete_news_request(request_id, str(audio_path), script)
                _increment_daily_usage(user.id, "ondemand")

                st.success("✅ Audio generado correctamente")
                st.write(f"Tema: **{topic}**")
                st.write(f"Duración solicitada: **{duration} min**")

                if audio_path.exists():
                    audio_bytes = audio_path.read_bytes()
                    st.audio(audio_bytes, format="audio/mp3")
                    st.download_button(
                        "⬇️ Descargar audio",
                        data=audio_bytes,
                        file_name=audio_path.name,
                        mime="audio/mpeg",
                    )
                else:
                    st.warning("El audio se generó, pero no se encontró el archivo en disco.")

            except Exception as e:
                if request_id is not None:
                    _fail_news_request(request_id, str(e))
                st.error(f"❌ Error al generar noticias: {e}")


def show_schedule_page():
    """Página para programar noticias."""
    st.title("⏰ Programar Noticias")
    st.markdown("Configura noticias diarias programadas.")
    
    # Formulario para nueva programación
    st.subheader("➕ Nueva Programación")
    
    with st.form("schedule_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            telegram_id = st.text_input(
                "Tu Telegram ID",
                help="Necesario para enviarte las noticias.",
            )
        
        with col2:
            schedule_time = st.time_input("Hora de envío")
        
        topic = st.text_input(
            "Tema",
            placeholder="Ej: noticias tecnológicas, economía...",
        )
        
        submitted = st.form_submit_button("📅 Programar", type="primary")
    
    if submitted:
        if not telegram_id or not topic:
            st.error("Por favor, completa todos los campos.")
        else:
            try:
                config = get_config()
                user = _get_or_create_web_user(telegram_id.strip())

                session = get_sync_session()
                try:
                    current_count = session.query(func.count(ScheduledNews.id)).filter(
                        ScheduledNews.user_id == user.id,
                        ScheduledNews.is_active == True,
                    ).scalar() or 0

                    if current_count >= config.users.max_scheduled_news:
                        st.error(
                            f"❌ Ya tienes el máximo de {config.users.max_scheduled_news} noticias programadas."
                        )
                    else:
                        scheduled = ScheduledNews(
                            user_id=user.id,
                            topic=topic,
                            hour=schedule_time.hour,
                            minute=schedule_time.minute,
                        )
                        session.add(scheduled)
                        session.commit()
                        session.refresh(scheduled)

                        st.success(
                            f"✅ Programación creada (ID: {scheduled.id})\n"
                            f"Recibirás noticias sobre '{topic}' a las {schedule_time.strftime('%H:%M')}."
                        )
                finally:
                    session.close()
            except Exception as e:
                st.error(f"❌ Error creando la programación: {e}")
    
    st.markdown("---")
    
    # Listar programaciones existentes
    st.subheader("📋 Programaciones Existentes")
    
    try:
        session = get_sync_session()
        scheduled = session.query(ScheduledNews).filter(
            ScheduledNews.is_active == True
        ).all()
        session.close()
        
        if scheduled:
            for s in scheduled:
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.write(f"📰 **{s.topic}**")
                with col2:
                    st.write(f"⏰ {s.hour:02d}:{s.minute:02d}")
                with col3:
                    st.write(f"👤 User #{s.user_id}")
        else:
            st.info("No hay programaciones activas.")
            
    except Exception as e:
        st.warning(f"No se pudieron cargar las programaciones: {e}")


def show_stats_page():
    """Página de estadísticas."""
    st.title("📊 Estadísticas")
    st.markdown("Métricas y análisis del sistema.")
    
    try:
        stats = sync_get_stats()
        
        # Métricas generales
        st.subheader("📈 Métricas Generales")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Tasa de Éxito",
                f"{(stats['completed_requests'] / max(stats['total_requests'], 1)) * 100:.1f}%",
            )
        
        with col2:
            st.metric("Artículos en Caché", stats["cached_articles"])
        
        with col3:
            st.metric("Programadas Activas", stats["active_scheduled"])
        
        st.markdown("---")
        
        # Lista de usuarios
        st.subheader("👥 Usuarios Registrados")
        
        users = sync_get_all_users()
        
        if users:
            user_data = []
            for user in users:
                user_data.append({
                    "ID": user.id,
                    "Telegram ID": user.telegram_id,
                    "Username": user.username or "N/A",
                    "Registrado": user.created_at.strftime("%d/%m/%Y %H:%M"),
                    "Activo": "✅" if user.is_active else "❌",
                })
            
            st.dataframe(user_data, width="stretch")
        else:
            st.info("No hay usuarios registrados.")
        
        st.markdown("---")
        
        # Últimas peticiones
        st.subheader("📋 Historial de Peticiones")
        
        requests = sync_get_recent_requests(limit=20)
        
        if requests:
            request_data = []
            for req in requests:
                request_data.append({
                    "ID": req.id,
                    "Tema": req.topic[:40] + "..." if len(req.topic) > 40 else req.topic,
                    "Estado": req.status,
                    "Tipo": req.request_type,
                    "Creado": req.created_at.strftime("%d/%m %H:%M"),
                    "Tiempo (s)": f"{req.processing_time_seconds:.1f}" if req.processing_time_seconds else "N/A",
                })
            
            st.dataframe(request_data, width="stretch")
        else:
            st.info("No hay peticiones registradas.")
            
    except Exception as e:
        st.error(f"Error cargando estadísticas: {e}")


def show_config_page():
    """Página de configuración."""
    st.title("⚙️ Configuración")
    st.markdown("Configuración del sistema.")
    
    config = get_config()
    
    # Mostrar configuración actual (solo lectura)
    st.subheader("📝 Configuración Actual")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**🤖 LLM**")
        st.write(f"- Proveedor: {config.llm.provider}")
        st.write(f"- Modelo: {config.llm.model}")
        st.write(f"- Temperatura: {config.llm.temperature}")
        
        st.markdown("**🔊 TTS**")
        st.write(f"- Proveedor: {config.tts.provider}")
        st.write(f"- Modelo: {config.tts.model}")
        st.write(f"- Voz: {config.tts.voice}")
    
    with col2:
        st.markdown("**🎙️ Audio**")
        st.write(f"- Duración objetivo: {config.audio.target_duration_minutes} min")
        st.write(f"- Retención: {config.audio.retention_days} días")
        
        st.markdown("**👥 Usuarios**")
        st.write(f"- Máx. programadas: {config.users.max_scheduled_news}")
        st.write(f"- Máx. on-demand/día: {config.users.max_ondemand_per_day}")
    
    st.markdown("---")
    
    st.subheader("📂 Categorías RSS Disponibles")
    
    from src.rss.parser import RSSParser
    parser = RSSParser()
    categories = parser.get_categories()
    
    for cat_id, category in categories.items():
        with st.expander(f"📁 {category.name} ({cat_id})"):
            st.write(f"*{category.description}*")
            st.write("**Feeds:**")
            for feed in category.feeds:
                st.write(f"- {feed.name}")
    
    st.markdown("---")
    
    st.info(
        "💡 Para modificar la configuración, edita los archivos:\n"
        "- `config.yaml` - Configuración general\n"
        "- `data/rss_feeds.yaml` - Fuentes RSS\n"
        "- `data/prompts/*.txt` - Prompts del LLM"
    )


if __name__ == "__main__":
    main()
