import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

_is_dotenv_loaded = False

def _ensure_env_loaded():
    global _is_dotenv_loaded
    if not _is_dotenv_loaded:
        if load_dotenv is not None:
            load_dotenv()
        _is_dotenv_loaded = True

def _reset_env_loaded():
    global _is_dotenv_loaded
    _is_dotenv_loaded = False

_ensure_env_loaded()

# ── Discord Configuration ────────────────────────────────────────
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
DISCORD_APPLICATION_ID = os.getenv("DISCORD_APPLICATION_ID", "").strip()
DISCORD_ENABLED = bool(DISCORD_BOT_TOKEN)

# ── Telegram Configuration ────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
# Proxy for Telegram Bot API. Supports socks5://, http://, https://
# Falls back to HTTPS_PROXY / https_proxy env var if not set.
_raw_tg_proxy = os.getenv("TELEGRAM_PROXY", "").strip() or os.getenv("HTTPS_PROXY", "").strip() or os.getenv("https_proxy", "").strip()
TELEGRAM_PROXY = _raw_tg_proxy if _raw_tg_proxy else None

allowed_users = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS = [
    int(x.strip())
    for x in allowed_users.split(",")
    if x.strip().isdigit()
]

_camera_device = os.getenv("CAMERA_DEVICE_INDEX", "0")
CAMERA_DEVICE_INDEX = int(_camera_device) if _camera_device.strip().isdigit() else 0

_camera_poll = os.getenv("CAMERA_MAX_FRAMES_PER_POLL", "1")
CAMERA_MAX_FRAMES_PER_POLL = max(1, min(3, int(_camera_poll))) if _camera_poll.strip().isdigit() else 1

_activation_timeout = os.getenv("ACTIVATION_SESSION_TIMEOUT_S", "300")
ACTIVATION_SESSION_TIMEOUT_S = (
    max(5, int(_activation_timeout)) if _activation_timeout.strip().isdigit() else 300
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_ENABLED = bool(GEMINI_API_KEY.strip())
GEMINI_TIMEOUT_S = float(os.getenv("GEMINI_TIMEOUT_S", "15.0"))
GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "1024"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.0-flash")

FREELLMAPI_BASE_URL = os.getenv("FREELLMAPI_BASE_URL", "http://127.0.0.1:3001/v1/chat/completions")
FREELLMAPI_API_KEY = os.getenv("FREELLMAPI_API_KEY", "")
FREELLMAPI_ENABLED = bool(FREELLMAPI_API_KEY.strip())
FREELLMAPI_MODEL = os.getenv("FREELLMAPI_MODEL", "auto")
FREELLMAPI_TIMEOUT_S = float(os.getenv("FREELLMAPI_TIMEOUT_S", "15.0"))
FREELLMAPI_MAX_TOKENS = int(os.getenv("FREELLMAPI_MAX_TOKENS", "1024"))

# ── Together AI Configuration ─────────────────────────────────────
TOGETHER_AI_API_KEY = os.getenv("TOGETHER_AI_API_KEY", "")
TOGETHER_AI_ENABLED = bool(TOGETHER_AI_API_KEY.strip())
TOGETHER_AI_BASE_URL = os.getenv("TOGETHER_AI_BASE_URL", "https://api.together.xyz")
TOGETHER_AI_MODEL = os.getenv("TOGETHER_AI_MODEL", "mistralai/Mixtral-8x7B-Instruct-v0.1")
TOGETHER_AI_TIMEOUT_S = float(os.getenv("TOGETHER_AI_TIMEOUT_S", "12.0"))
TOGETHER_AI_MAX_TOKENS = int(os.getenv("TOGETHER_AI_MAX_TOKENS", "1024"))

# ── Cerebras Configuration ────────────────────────────────────────
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
CEREBRAS_ENABLED = bool(CEREBRAS_API_KEY.strip())
CEREBRAS_BASE_URL = os.getenv("CEREBRAS_BASE_URL", "https://api.cerebras.ai")
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")
CEREBRAS_TIMEOUT_S = float(os.getenv("CEREBRAS_TIMEOUT_S", "12.0"))
CEREBRAS_MAX_TOKENS = int(os.getenv("CEREBRAS_MAX_TOKENS", "1024"))

# ── Groq Configuration ────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_ENABLED = bool(GROQ_API_KEY.strip())
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai")
GROQ_MODEL = os.getenv("GROQ_MODEL", "mixtral-8x7b-32768")
GROQ_TIMEOUT_S = float(os.getenv("GROQ_TIMEOUT_S", "12.0"))
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "1024"))

# ── SambaNova Configuration ───────────────────────────────────────
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY", "")
SAMBANOVA_ENABLED = bool(SAMBANOVA_API_KEY.strip())
SAMBANOVA_MODEL = os.getenv("SAMBANOVA_MODEL", "Llama-2-7b-chat-hf")
SAMBANOVA_TIMEOUT_S = float(os.getenv("SAMBANOVA_TIMEOUT_S", "15.0"))
SAMBANOVA_MAX_TOKENS = int(os.getenv("SAMBANOVA_MAX_TOKENS", "1024"))
SAMBANOVA_BASE_URL = os.getenv("SAMBANOVA_BASE_URL", "https://api.sambanova.ai")

# ── Fireworks Configuration ───────────────────────────────────────
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "")
FIREWORKS_ENABLED = bool(FIREWORKS_API_KEY.strip())
FIREWORKS_MODEL = os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/llama-v2-7b")
FIREWORKS_TIMEOUT_S = float(os.getenv("FIREWORKS_TIMEOUT_S", "15.0"))
FIREWORKS_MAX_TOKENS = int(os.getenv("FIREWORKS_MAX_TOKENS", "1024"))
FIREWORKS_BASE_URL = os.getenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference")

# ── Hugging Face Configuration ────────────────────────────────────
HUGGINGFACE_API_KEY = os.getenv("HF_TOKEN", "")  # Use HF_TOKEN as specified in the prompt
HUGGINGFACE_ENABLED = bool(HUGGINGFACE_API_KEY.strip())
HUGGINGFACE_MODEL = os.getenv("HUGGINGFACE_MODEL", "Qwen/Qwen3-32B")
HUGGINGFACE_TIMEOUT_S = float(os.getenv("HUGGINGFACE_TIMEOUT_S", "15.0"))
HUGGINGFACE_MAX_TOKENS = int(os.getenv("HUGGINGFACE_MAX_TOKENS", "1024"))

# ── OpenRouter Configuration ──────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_ENABLED = bool(OPENROUTER_API_KEY.strip())
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324:free")
OPENROUTER_TIMEOUT_S = float(os.getenv("OPENROUTER_TIMEOUT_S", "12.0"))
OPENROUTER_MAX_TOKENS = int(os.getenv("OPENROUTER_MAX_TOKENS", "1024"))

# ── Exa Search Configuration ──────────────────────────────────────
EXA_API_KEY = os.getenv("EXA_API_KEY", "")
EXA_ENABLED = bool(EXA_API_KEY.strip())
EXA_TIMEOUT_S = float(os.getenv("EXA_TIMEOUT_S", "5.0"))
EXA_MAX_RESULTS = int(os.getenv("EXA_MAX_RESULTS", "3"))

# ── Tavily Search Configuration ───────────────────────────────────
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
TAVILY_ENABLED = bool(TAVILY_API_KEY.strip())
TAVILY_TIMEOUT_S = float(os.getenv("TAVILY_TIMEOUT_S", "5.0"))
TAVILY_MAX_RESULTS = int(os.getenv("TAVILY_MAX_RESULTS", "3"))

# ── Jina Reader Configuration ─────────────────────────────────────
JINA_READER_ENABLED = bool(os.getenv("JINA_READER_ENABLED", "false").lower() == "true")
JINA_READER_TIMEOUT_S = float(os.getenv("JINA_READER_TIMEOUT_S", "10.0"))

# ── Failover Chain Configuration ──────────────────────────────────
PROVIDER_FAILOVER_ENABLED = bool(os.getenv("PROVIDER_FAILOVER_ENABLED", "true").strip().lower() == "true")

# ── Spotify API Configuration (for track resolution) ──────────────
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_API_ENABLED = bool(SPOTIFY_CLIENT_ID.strip() and SPOTIFY_CLIENT_SECRET.strip())

# ── Browser Connector V1 ───────────────────────────────────────────
BROWSER_CONNECTOR_ENABLED = os.getenv("BROWSER_CONNECTOR_ENABLED", "").strip().lower() == "true"
BROWSER_CONNECTOR_PORT = int(os.getenv("BROWSER_CONNECTOR_PORT", "9877"))
BROWSER_CONNECTOR_MOCK = os.getenv("BROWSER_CONNECTOR_MOCK", "").strip().lower() == "true"

# ── Browser Configuration ─────────────────────────────────────────
DEFAULT_BROWSER = os.getenv("DEFAULT_BROWSER", "chrome").lower()
