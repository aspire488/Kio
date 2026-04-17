"""
Activity Monitor - Monitor user activity and send alerts when idle.
"""

import threading
import time
import logging

logger = logging.getLogger(__name__)

IDLE_THRESHOLD_MINUTES = 5
_last_activity_time = time.time()
_monitor_thread = None
_running = False


def reset_activity():
    """Reset the idle timer on user activity."""
    global _last_activity_time
    _last_activity_time = time.time()


def check_idle() -> bool:
    """Check if user has been idle beyond threshold."""
    global _last_activity_time
    idle_seconds = time.time() - _last_activity_time
    return idle_seconds > (IDLE_THRESHOLD_MINUTES * 60)


def send_telegram_alert(message: str):
    """Send alert via Telegram if configured."""
    try:
        from .config import TELEGRAM_TOKEN, ALLOWED_USER_IDS

        if not TELEGRAM_TOKEN or not ALLOWED_USER_IDS:
            return

        import requests

        user_id = ALLOWED_USER_IDS[0]
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": user_id, "text": message}, timeout=10)
    except Exception as e:
        logger.warning(f"Failed to send alert: {e}")


def monitor_loop():
    """Background monitoring loop."""
    global _running
    while _running:
        if check_idle():
            alert_msg = "⚠️ KIO ALERT\nActivity detected on your laptop."
            send_telegram_alert(alert_msg)
            logger.info("Activity alert sent")
        time.sleep(60)


def start_monitor():
    """Start the activity monitor."""
    global _monitor_thread, _running
    _running = True
    _monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    _monitor_thread.start()
    print("[MONITOR] Activity monitor started")


def stop_monitor():
    """Stop the activity monitor."""
    global _running
    _running = False


def record_activity():
    """Record user activity (call from any input handler)."""
    reset_activity()


__all__ = ["start_monitor", "stop_monitor", "record_activity", "check_idle"]
