"""
Handlers para comandos de Telegram.
"""

import logging
from typing import Callable, Optional
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from src.config import get_config
from src.database.models import init_database, AsyncSessionLocal
from src.database import crud

logger = logging.getLogger(__name__)

# Variable global para el callback de generación de noticias
_news_generator_callback: Optional[Callable] = None


def setup_handlers(app: Application, news_callback: Optional[Callable] = None) -> None:
    """Configura los handlers del bot."""
    global _news_generator_callback
    _news_generator_callback = news_callback
    
    # Comandos de usuario
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("status", cmd_status))
    
    # Comandos de administrador
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("admin_users", cmd_admin_users))
    app.add_handler(CommandHandler("admin_tokens", cmd_admin_tokens))
    app.add_handler(CommandHandler("admin_requests", cmd_admin_requests))
    
    # Mensajes de texto (para peticiones on-demand rápidas)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text_message,
    ))


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /start - Bienvenida y registro."""
    user = update.effective_user
    
    if AsyncSessionLocal is None:
        await init_database()
    
    async with AsyncSessionLocal() as session:
        db_user = await crud.get_or_create_user(
            session,
            telegram_id=str(user.id),
            username=user.username,
        )
    
    welcome_message = f"""
👋 ¡Hola {user.first_name}!

Bienvenido a *Custom News* - Tu asistente de noticias personalizado.

📰 *¿Qué puedo hacer por ti?*
Genero resúmenes de noticias en audio de ~5 minutos basados en tus intereses.

🎯 *Comandos disponibles:*

*/news <tema>* - Genera noticias sobre un tema
  Ejemplo: `/news inteligencia artificial`

*/schedule <hora> <tema>* - Programa noticias diarias
  Ejemplo: `/schedule 08:00 geopolítica`

*/list* - Ver tus noticias programadas

*/delete <id>* - Eliminar una noticia programada

*/stats* - Ver estadísticas de uso

*/help* - Ver ayuda detallada

💡 *Tip:* También puedes escribir directamente un tema sin comandos para recibir noticias.

¡Comienza pidiendo noticias sobre cualquier tema! 🚀
"""
    
    await update.message.reply_text(welcome_message, parse_mode="Markdown")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /help - Ayuda detallada."""
    help_message = """
📖 *Guía de Custom News*

*🎙️ Noticias bajo demanda:*
`/news <tema>` - Genera un resumen de noticias
Ejemplos:
• `/news inteligencia artificial`
• `/news mercados financieros`
• `/news cambio climático`
• `/news política española`

*⏰ Noticias programadas:*
`/schedule <HH:MM> <tema>` - Programa noticias diarias
Puedes tener hasta 3 noticias programadas.
Ejemplos:
• `/schedule 07:30 noticias del día`
• `/schedule 18:00 tecnología`

*📋 Gestión:*
• `/list` - Ver tus noticias programadas
• `/delete <número>` - Eliminar programada
• `/stats` - Ver tus estadísticas
• `/status` - Estado del sistema

*💡 Modo rápido:*
Escribe directamente el tema sin comandos:
"noticias sobre startups en España"

*⚠️ Límites:*
• 3 peticiones on-demand por día
• 3 noticias programadas máximo
• Audio de ~5 minutos por resumen

*❓ Soporte:*
Si tienes problemas, contacta al administrador.
"""
    
    await update.message.reply_text(help_message, parse_mode="Markdown")


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /news - Genera noticias on-demand."""
    user = update.effective_user
    
    # Verificar que hay un tema
    if not context.args:
        await update.message.reply_text(
            "❌ Por favor, especifica un tema.\n"
            "Ejemplo: `/news inteligencia artificial`",
            parse_mode="Markdown",
        )
        return
    
    topic = " ".join(context.args)
    
    await _process_news_request(update, str(user.id), topic)


async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /schedule - Programa noticias diarias."""
    user = update.effective_user
    config = get_config()
    
    # Verificar argumentos
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Formato incorrecto.\n"
            "Uso: `/schedule HH:MM tema`\n"
            "Ejemplo: `/schedule 08:00 inteligencia artificial`",
            parse_mode="Markdown",
        )
        return
    
    # Parsear hora
    time_str = context.args[0]
    topic = " ".join(context.args[1:])
    
    try:
        hour, minute = map(int, time_str.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Invalid time")
    except ValueError:
        await update.message.reply_text(
            "❌ Hora inválida. Usa formato HH:MM (ej: 08:30)",
        )
        return
    
    if AsyncSessionLocal is None:
        await init_database()
    
    async with AsyncSessionLocal() as session:
        # Obtener usuario
        db_user = await crud.get_or_create_user(session, str(user.id), user.username)
        
        # Verificar límite
        count = await crud.get_scheduled_news_count(session, db_user.id)
        if count >= config.users.max_scheduled_news:
            await update.message.reply_text(
                f"❌ Ya tienes el máximo de {config.users.max_scheduled_news} "
                "noticias programadas.\n"
                "Usa `/list` para ver y `/delete <id>` para eliminar alguna.",
                parse_mode="Markdown",
            )
            return
        
        # Crear programación
        scheduled = await crud.create_scheduled_news(
            session,
            user_id=db_user.id,
            topic=topic,
            hour=hour,
            minute=minute,
        )
        
        await update.message.reply_text(
            f"✅ Noticia programada correctamente!\n\n"
            f"📰 *Tema:* {topic}\n"
            f"⏰ *Hora:* {hour:02d}:{minute:02d}\n"
            f"🔢 *ID:* {scheduled.id}\n\n"
            "Recibirás tu resumen diario a esa hora.",
            parse_mode="Markdown",
        )


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /list - Lista noticias programadas."""
    user = update.effective_user
    
    if AsyncSessionLocal is None:
        await init_database()
    
    async with AsyncSessionLocal() as session:
        db_user = await crud.get_user_by_telegram_id(session, str(user.id))
        
        if not db_user:
            await update.message.reply_text("No tienes noticias programadas.")
            return
        
        scheduled_list = await crud.get_user_scheduled_news(session, db_user.id)
        
        if not scheduled_list:
            await update.message.reply_text(
                "📭 No tienes noticias programadas.\n"
                "Usa `/schedule HH:MM tema` para crear una.",
                parse_mode="Markdown",
            )
            return
        
        message = "📋 *Tus noticias programadas:*\n\n"
        
        for scheduled in scheduled_list:
            status = "🟢" if scheduled.is_active else "🔴"
            last_sent = ""
            if scheduled.last_sent_at:
                last_sent = f"(Último: {scheduled.last_sent_at.strftime('%d/%m %H:%M')})"
            
            message += (
                f"{status} *ID {scheduled.id}*\n"
                f"   📰 {scheduled.topic}\n"
                f"   ⏰ {scheduled.hour:02d}:{scheduled.minute:02d} {last_sent}\n\n"
            )
        
        message += "\n_Para eliminar: /delete <id>_"
        
        await update.message.reply_text(message, parse_mode="Markdown")


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /delete - Elimina una noticia programada."""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "❌ Especifica el ID a eliminar.\n"
            "Ejemplo: `/delete 1`\n"
            "Usa `/list` para ver los IDs.",
            parse_mode="Markdown",
        )
        return
    
    try:
        scheduled_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID inválido. Debe ser un número.")
        return
    
    if AsyncSessionLocal is None:
        await init_database()
    
    async with AsyncSessionLocal() as session:
        db_user = await crud.get_user_by_telegram_id(session, str(user.id))
        
        if not db_user:
            await update.message.reply_text("❌ No se encontró tu usuario.")
            return
        
        deleted = await crud.delete_scheduled_news(session, scheduled_id, db_user.id)
        
        if deleted:
            await update.message.reply_text(f"✅ Noticia programada #{scheduled_id} eliminada.")
        else:
            await update.message.reply_text(
                f"❌ No se encontró la noticia #{scheduled_id} o no te pertenece."
            )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /stats - Muestra estadísticas del usuario."""
    user = update.effective_user
    config = get_config()
    
    if AsyncSessionLocal is None:
        await init_database()
    
    async with AsyncSessionLocal() as session:
        db_user = await crud.get_user_by_telegram_id(session, str(user.id))
        
        if not db_user:
            await update.message.reply_text("No hay estadísticas disponibles.")
            return
        
        # Obtener estadísticas
        scheduled_count = await crud.get_scheduled_news_count(session, db_user.id)
        requests = await crud.get_user_requests(session, db_user.id, limit=10)
        ondemand_today = await crud.get_ondemand_count_today(session, db_user.id)
        
        # Calcular estadísticas de peticiones
        total_requests = len(requests)
        completed = sum(1 for r in requests if r.status == "completed")
        
        message = f"""
📊 *Tus estadísticas*

👤 *Usuario:* {user.first_name}
📅 *Registrado:* {db_user.created_at.strftime('%d/%m/%Y')}

*📰 Hoy:*
• Peticiones on-demand: {ondemand_today}/{config.users.max_ondemand_per_day}
• Disponibles: {config.users.max_ondemand_per_day - ondemand_today}

*⏰ Programadas:*
• Activas: {scheduled_count}/{config.users.max_scheduled_news}

*📈 Últimas 10 peticiones:*
• Completadas: {completed}
• Total: {total_requests}
"""
        
        await update.message.reply_text(message, parse_mode="Markdown")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /status - Estado del sistema."""
    if AsyncSessionLocal is None:
        await init_database()
    
    async with AsyncSessionLocal() as session:
        stats = await crud.get_stats(session)
    
    message = f"""
🔧 *Estado del Sistema*

👥 Usuarios totales: {stats['total_users']}
📰 Peticiones totales: {stats['total_requests']}
✅ Completadas: {stats['completed_requests']}
⏰ Programadas activas: {stats['active_scheduled']}
📦 Artículos en caché: {stats['cached_articles']}

*Estado:* 🟢 Operativo
"""
    
    await update.message.reply_text(message, parse_mode="Markdown")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja mensajes de texto como peticiones on-demand."""
    user = update.effective_user
    topic = update.message.text.strip()
    
    # Ignorar mensajes muy cortos
    if len(topic) < 3:
        return
    
    await _process_news_request(update, str(user.id), topic)


async def _process_news_request(
    update: Update,
    telegram_id: str,
    topic: str,
) -> None:
    """Procesa una petición de noticias."""
    global _news_generator_callback
    config = get_config()
    
    if AsyncSessionLocal is None:
        await init_database()
    
    async with AsyncSessionLocal() as session:
        # Obtener/crear usuario
        db_user = await crud.get_or_create_user(
            session,
            telegram_id=telegram_id,
            username=update.effective_user.username,
        )
        
        # Verificar límite diario
        ondemand_today = await crud.get_ondemand_count_today(session, db_user.id)
        
        if ondemand_today >= config.users.max_ondemand_per_day:
            await update.message.reply_text(
                f"❌ Has alcanzado el límite de {config.users.max_ondemand_per_day} "
                "peticiones diarias.\n"
                "Vuelve mañana o programa noticias con `/schedule`.",
                parse_mode="Markdown",
            )
            return
        
        # Crear petición
        request = await crud.create_news_request(
            session,
            user_id=db_user.id,
            topic=topic,
            request_type="ondemand",
        )
    
    # Enviar mensaje de procesamiento
    processing_msg = await update.message.reply_text(
        f"🔄 Procesando tu petición...\n\n"
        f"📰 *Tema:* {topic}\n\n"
        "_Esto puede tardar 1-2 minutos._",
        parse_mode="Markdown",
    )
    
    try:
        if _news_generator_callback:
            # Generar noticias
            result = await _news_generator_callback(db_user.id, topic)
            
            if result:
                audio_path, script = result
                
                # Actualizar petición como completada
                async with AsyncSessionLocal() as session:
                    await crud.update_news_request(
                        session,
                        request_id=request.id,
                        status="completed",
                        audio_path=str(audio_path),
                        script_text=script,
                    )
                    await crud.increment_daily_usage(session, db_user.id, "ondemand")
                
                # Enviar audio
                await processing_msg.delete()
                
                with open(audio_path, "rb") as audio_file:
                    await update.message.reply_audio(
                        audio=audio_file,
                        title=f"Noticias: {topic[:50]}",
                        caption=f"📰 Tu resumen sobre: {topic}",
                    )
            else:
                raise Exception("No se pudo generar el audio")
        else:
            raise Exception("Generador de noticias no configurado")
            
    except Exception as e:
        logger.error(f"Error processing news request: {e}")
        
        # Actualizar petición como fallida
        async with AsyncSessionLocal() as session:
            await crud.update_news_request(
                session,
                request_id=request.id,
                status="failed",
                error_message=str(e),
            )
        
        await processing_msg.edit_text(
            "❌ Error al generar las noticias.\n"
            "Por favor, intenta de nuevo más tarde.",
        )


# ============== COMANDOS DE ADMINISTRADOR ==============

def is_admin(user_id: int) -> bool:
    """Verifica si un usuario es administrador."""
    config = get_config()
    admin_ids = config.telegram.admin_chat_ids
    # Si no hay admins configurados, todos pueden usar comandos de admin (desarrollo)
    return len(admin_ids) == 0 or user_id in admin_ids


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /admin - Panel de administrador."""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ No tienes permisos de administrador.")
        return
    
    if AsyncSessionLocal is None:
        await init_database()
    
    async with AsyncSessionLocal() as session:
        stats = await crud.get_admin_stats(session)
    
    users = stats["users"]
    requests = stats["requests"]
    tokens = stats["tokens"]
    
    message = f"""
🔐 *Panel de Administrador*

👥 *USUARIOS*
├ Total: {users['total']}
├ Activos: {users['active']}
└ Nuevos (7 días): {users['new_this_week']}

📰 *PETICIONES*
├ Total: {requests['total']}
├ Completadas: {requests['completed']}
├ Fallidas: {requests['failed']}
├ Hoy: {requests['today']}
├ Semana: {requests['this_week']}
└ Tasa éxito: {requests['success_rate']:.1f}%

⏰ *PROGRAMADAS*
└ Activas: {stats['scheduled']['active']}

⚡ *RENDIMIENTO*
└ Tiempo promedio: {stats['performance']['avg_processing_time_sec']}s

💰 *TOKENS (7 días)*
├ Total: {tokens['total_tokens']:,}
├ Requests: {tokens['total_requests']}
└ Costo est.: ${tokens['total_cost_usd']:.4f}

---
*Comandos admin:*
/admin\\_users - Detalle usuarios
/admin\\_tokens - Consumo de tokens
/admin\\_requests - Últimas peticiones
"""
    
    await update.message.reply_text(message, parse_mode="Markdown")


async def cmd_admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /admin_users - Detalle de usuarios."""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ No tienes permisos de administrador.")
        return
    
    if AsyncSessionLocal is None:
        await init_database()
    
    async with AsyncSessionLocal() as session:
        users = await crud.get_all_users(session)
    
    if not users:
        await update.message.reply_text("No hay usuarios registrados.")
        return
    
    message = "👥 *Lista de Usuarios*\n\n"
    
    for u in users[:20]:  # Limitar a 20 usuarios
        status = "🟢" if u.is_active else "🔴"
        username = f"@{u.username}" if u.username else "Sin username"
        message += (
            f"{status} *ID {u.id}* | TG: `{u.telegram_id}`\n"
            f"   └ {username} | {u.created_at.strftime('%d/%m/%Y')}\n"
        )
    
    if len(users) > 20:
        message += f"\n_... y {len(users) - 20} usuarios más_"
    
    await update.message.reply_text(message, parse_mode="Markdown")


async def cmd_admin_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /admin_tokens - Consumo de tokens por modelo."""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ No tienes permisos de administrador.")
        return
    
    # Parsear días del argumento
    days = 7
    if context.args:
        try:
            days = int(context.args[0])
            days = min(max(days, 1), 30)  # Limitar entre 1 y 30
        except ValueError:
            pass
    
    if AsyncSessionLocal is None:
        await init_database()
    
    async with AsyncSessionLocal() as session:
        summary = await crud.get_token_usage_summary(session, days=days)
    
    message = f"💰 *Consumo de Tokens ({days} días)*\n\n"
    
    if not summary["by_model"]:
        message += "_No hay datos de consumo de tokens._"
    else:
        for model, data in summary["by_model"].items():
            message += (
                f"🤖 *{model}*\n"
                f"├ Prompt: {data['prompt_tokens']:,}\n"
                f"├ Completion: {data['completion_tokens']:,}\n"
                f"├ Total: {data['total_tokens']:,}\n"
                f"├ Requests: {data['requests']}\n"
                f"└ Costo: ${data['cost_usd']:.4f}\n\n"
            )
        
        message += (
            f"━━━━━━━━━━━━━━━━\n"
            f"📊 *TOTALES*\n"
            f"├ Tokens: {summary['total_tokens']:,}\n"
            f"├ Requests: {summary['total_requests']}\n"
            f"└ Costo: ${summary['total_cost_usd']:.4f}\n"
        )
    
    message += f"\n_Uso: /admin\\_tokens \\[días\\]_"
    
    await update.message.reply_text(message, parse_mode="Markdown")


async def cmd_admin_requests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /admin_requests - Últimas peticiones."""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ No tienes permisos de administrador.")
        return
    
    # Parsear límite del argumento
    limit = 10
    if context.args:
        try:
            limit = int(context.args[0])
            limit = min(max(limit, 1), 25)  # Limitar entre 1 y 25
        except ValueError:
            pass
    
    if AsyncSessionLocal is None:
        await init_database()
    
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from src.database.models import NewsRequest
        
        result = await session.execute(
            select(NewsRequest)
            .order_by(NewsRequest.created_at.desc())
            .limit(limit)
        )
        requests = result.scalars().all()
    
    if not requests:
        await update.message.reply_text("No hay peticiones registradas.")
        return
    
    message = f"📋 *Últimas {limit} Peticiones*\n\n"
    
    status_icons = {
        "pending": "🟡",
        "processing": "🔵",
        "completed": "🟢",
        "failed": "🔴",
    }
    
    for req in requests:
        icon = status_icons.get(req.status, "⚪")
        topic_short = req.topic[:30] + "..." if len(req.topic) > 30 else req.topic
        time_str = req.created_at.strftime("%d/%m %H:%M")
        
        proc_time = ""
        if req.processing_time_seconds:
            proc_time = f" | {req.processing_time_seconds:.1f}s"
        
        tokens = ""
        if req.tokens_used:
            tokens = f" | {req.tokens_used:,}tok"
        
        message += (
            f"{icon} *{topic_short}*\n"
            f"   └ {time_str}{proc_time}{tokens} | User#{req.user_id}\n"
        )
    
    message += f"\n_Uso: /admin\\_requests \\[límite\\]_"
    
    await update.message.reply_text(message, parse_mode="Markdown")
