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

# ── Telegram Configuration ────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()

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
GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "200"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-1.5-flash-8b")

FREELLMAPI_BASE_URL = os.getenv("FREELLMAPI_BASE_URL", "http://127.0.0.1:3001/v1/chat/completions")
FREELLMAPI_API_KEY = os.getenv("FREELLMAPI_API_KEY", "")
FREELLMAPI_ENABLED = bool(FREELLMAPI_API_KEY.strip())
FREELLMAPI_MODEL = os.getenv("FREELLMAPI_MODEL", "auto")
FREELLMAPI_TIMEOUT_S = float(os.getenv("FREELLMAPI_TIMEOUT_S", "15.0"))
FREELLMAPI_MAX_TOKENS = int(os.getenv("FREELLMAPI_MAX_TOKENS", "200"))

# ── Together AI Configuration ─────────────────────────────────────
TOGETHER_AI_API_KEY = os.getenv("TOGETHER_AI_API_KEY", "")
TOGETHER_AI_ENABLED = bool(TOGETHER_AI_API_KEY.strip())
TOGETHER_AI_BASE_URL = os.getenv("TOGETHER_AI_BASE_URL", "https://api.together.xyz")
TOGETHER_AI_MODEL = os.getenv("TOGETHER_AI_MODEL", "mistralai/Mixtral-8x7B-Instruct-v0.1")
TOGETHER_AI_TIMEOUT_S = float(os.getenv("TOGETHER_AI_TIMEOUT_S", "12.0"))
TOGETHER_AI_MAX_TOKENS = int(os.getenv("TOGETHER_AI_MAX_TOKENS", "200"))

# ── Cerebras Configuration ────────────────────────────────────────
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
CEREBRAS_ENABLED = bool(CEREBRAS_API_KEY.strip())
CEREBRAS_BASE_URL = os.getenv("CEREBRAS_BASE_URL", "https://api.cerebras.ai")
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "llama3.1-8b")
CEREBRAS_TIMEOUT_S = float(os.getenv("CEREBRAS_TIMEOUT_S", "12.0"))
CEREBRAS_MAX_TOKENS = int(os.getenv("CEREBRAS_MAX_TOKENS", "200"))

# ── Groq Configuration ────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_ENABLED = bool(GROQ_API_KEY.strip())
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai")
GROQ_MODEL = os.getenv("GROQ_MODEL", "mixtral-8x7b-32768")
GROQ_TIMEOUT_S = float(os.getenv("GROQ_TIMEOUT_S", "12.0"))
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "200"))

# ── OpenRouter Configuration ──────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_ENABLED = bool(OPENROUTER_API_KEY.strip())
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324:free")
OPENROUTER_TIMEOUT_S = float(os.getenv("OPENROUTER_TIMEOUT_S", "12.0"))
OPENROUTER_MAX_TOKENS = int(os.getenv("OPENROUTER_MAX_TOKENS", "200"))

# ── Failover Chain Configuration ──────────────────────────────────
PROVIDER_FAILOVER_ENABLED = bool(os.getenv("PROVIDER_FAILOVER_ENABLED", "true").strip().lower() == "true")

# ── Browser Configuration ─────────────────────────────────────────
DEFAULT_BROWSER = os.getenv("DEFAULT_BROWSER", "chrome").lower()
