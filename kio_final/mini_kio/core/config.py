import os

try:
    from dotenv import load_dotenv
except ImportError:  # Optional during Gate 0 bootstrap
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

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
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
