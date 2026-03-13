# Custom News 📰

Aplicación de noticias personalizadas con audio generado por IA. Genera resúmenes de noticias en audio de ~5 minutos basados en tus intereses.

## Características

- 🎙️ **Resúmenes en audio**: Genera podcasts de ~5 minutos con las noticias más relevantes
- 🤖 **Selección inteligente**: Usa LLM para seleccionar y filtrar las noticias más relevantes
- ⏰ **Noticias programadas**: Configura hasta 3 resúmenes diarios a la hora que prefieras
- 📱 **Telegram Bot**: Interactúa con la app vía comandos de Telegram
- 🌐 **Dashboard Web**: Panel de control con Streamlit
- 💾 **Sistema de caché**: Ahorra tokens y tiempo reutilizando contenido reciente
- 📊 **Monitoreo**: Estadísticas de uso y consumo

## Requisitos

- Python 3.10+
- UV (gestor de paquetes)
- API Key de OpenAI
- Token de Bot de Telegram

## Instalación

### 1. Clonar e instalar dependencias

```bash
# Instalar UV si no lo tienes
pip install uv

# Crear entorno virtual e instalar dependencias
uv venv
uv pip install -e .
```

### 2. Configurar variables de entorno

```bash
# Copiar archivo de ejemplo
cp .env.example .env

# Editar .env con tus claves
# OPENAI_API_KEY=sk-...
# TELEGRAM_BOT_TOKEN=...
```

### 3. Configurar la aplicación (opcional)

Edita `config.yaml` para personalizar:
- Modelo de LLM
- Voz del TTS
- Duración del audio
- Límites de usuarios
- etc.

## Uso

### Ejecutar todo (Telegram + Web)

```bash
uv run python -m src.main
```

### Solo Telegram

```bash
uv run python -m src.main --mode telegram
```

### Solo Web (Streamlit)

```bash
uv run python -m src.main --mode web
```

O directamente:

```bash
uv run streamlit run src/web/streamlit_app.py
```

## Comandos de Telegram

| Comando | Descripción |
|---------|-------------|
| `/start` | Registrarse y ver bienvenida |
| `/help` | Ver ayuda detallada |
| `/news <tema>` | Generar noticias sobre un tema |
| `/schedule HH:MM <tema>` | Programar noticias diarias |
| `/list` | Ver noticias programadas |
| `/delete <id>` | Eliminar una programada |
| `/stats` | Ver estadísticas de uso |
| `/status` | Estado del sistema |

**Ejemplos:**
```
/news inteligencia artificial
/news mercados financieros europeos
/schedule 07:30 noticias del día
/schedule 18:00 tecnología y startups
```

## Estructura del Proyecto

```
Custom_news/
├── config.yaml           # Configuración principal
├── .env                  # Variables de entorno (API keys)
├── pyproject.toml        # Dependencias del proyecto
├── data/
│   ├── rss_feeds.yaml    # Fuentes RSS por categoría
│   └── prompts/          # Prompts del LLM
│       ├── select_categories_*.txt
│       ├── filter_news_*.txt
│       └── generate_script_*.txt
├── src/
│   ├── main.py           # Punto de entrada
│   ├── config.py         # Gestión de configuración
│   ├── pipeline.py       # Pipeline principal
│   ├── database/         # Modelos y CRUD
│   ├── rss/              # Parser y caché RSS
│   ├── llm/              # Clientes LLM
│   ├── tts/              # Text-to-Speech
│   ├── scraper/          # Extracción de artículos
│   ├── scheduler/        # Tareas programadas
│   ├── telegram_bot/     # Bot de Telegram
│   └── web/              # Interfaz Streamlit
├── audio_output/         # Audios generados
└── logs/                 # Logs de la aplicación
```

## Configuración de RSS

Edita `data/rss_feeds.yaml` para añadir o modificar fuentes:

```yaml
categories:
  mi_categoria:
    name: "Mi Categoría"
    description: "Descripción de la categoría"
    feeds:
      - name: "Nombre del Feed"
        url: "https://ejemplo.com/rss"
```

## Personalización de Prompts

Los prompts del LLM están en `data/prompts/`:

- `select_categories_*.txt`: Para seleccionar categorías RSS
- `filter_news_*.txt`: Para filtrar noticias relevantes
- `generate_script_*.txt`: Para generar el guion de radio

## Cambiar Proveedor de LLM

En `config.yaml`:

```yaml
llm:
  provider: "openai"  # openai, anthropic, groq, ollama
  model: "gpt-4o"
```

Para añadir un nuevo proveedor, crea una clase en `src/llm/` que herede de `BaseLLMClient`.

## Cambiar Voz del TTS

En `config.yaml`:

```yaml
tts:
  voice: "nova"  # alloy, echo, fable, onyx, nova, shimmer
```

## Límites y Caché

```yaml
users:
  max_scheduled_news: 3
  max_ondemand_per_day: 3

cache:
  news_cache_hours: 3
  
audio:
  retention_days: 2
```

## Desarrollo

```bash
# Instalar dependencias de desarrollo
uv pip install -e ".[dev]"

# Ejecutar tests
uv run pytest

# Formatear código
uv run black src/
uv run ruff check src/
```

## Troubleshooting

### Error de API Key
Verifica que `.env` contiene las claves correctas:
```
OPENAI_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=...
```

### Error de base de datos
Elimina `data/news_app.db` y reinicia la aplicación.

### Feeds RSS no funcionan
Algunos feeds pueden estar bloqueados o caídos. Verifica la URL manualmente.

### Audio muy largo/corto
Ajusta en `config.yaml`:
```yaml
audio:
  target_duration_minutes: 5
  words_per_minute: 150
```

## Licencia

MIT
