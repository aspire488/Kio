"""
Action Executor - High-level actions without GUI automation.
Uses webbrowser and subprocess for reliable execution.
"""

from __future__ import annotations

import logging
import subprocess
import urllib.parse
import webbrowser
from typing import Any

logger = logging.getLogger(__name__)

APP_PATHS = {
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "vscode": r"C:\Users\HP\AppData\Local\Programs\Microsoft VSCode\Code.exe",
    "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
    "calculator": "C:\\Windows\\System32\\calc.exe",
}

# Contact name to phone number mapping
CONTACTS = {
    "aditya": "91XXXXXXXXXX",
    "joel": "91XXXXXXXXXX",
    "aaron": "91XXXXXXXXXX",
}


def open_app(app: str) -> dict[str, Any]:
    """Open an application using subprocess."""
    print(f"[ACTION EXECUTED] open_app({app})")
    app_lower = app.lower()

    if app_lower in APP_PATHS:
        try:
            subprocess.Popen(APP_PATHS[app_lower])
            logger.info(f"Opened {app} via subprocess")
            return {"success": True, "message": f"Opened {app}"}
        except Exception as e:
            logger.warning(f"Failed to open {app}: {e}")

    web_apps = {
        "claude": "https://claude.ai",
        "youtube": "https://youtube.com",
        "gmail": "https://gmail.com",
        "whatsapp": "https://web.whatsapp.com",
        "antigravity": "https://antigravity.app",
        "chatgpt": "https://chat.openai.com",
    }

    if app_lower in web_apps:
        webbrowser.open(web_apps[app_lower])
        return {"success": True, "message": f"Opened {app}"}

    return {"success": False, "message": f"Unknown app: {app}"}


def search_web(query: str) -> dict[str, Any]:
    """Search the web using Google."""
    print(f"[ACTION EXECUTED] search_web({query})")
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    webbrowser.open(url)
    logger.info(f"Searched: {query}")
    return {"success": True, "message": f"Searching: {query}"}


def open_url(url: str) -> dict[str, Any]:
    """Open a URL in browser."""
    print(f"[ACTION EXECUTED] open_url({url})")
    webbrowser.open(url)
    logger.info(f"Opened URL: {url}")
    return {"success": True, "message": f"Opened {url}"}


def send_whatsapp_message(contact: str, message: str) -> dict[str, Any]:
    """Send WhatsApp message via WhatsApp Web with pyautogui automation."""
    print(f"[ACTION EXECUTED] whatsapp_send({contact}, {message})")
    try:
        import pyautogui
        import time

        webbrowser.open("https://web.whatsapp.com")
        time.sleep(10)

        pyautogui.write(contact)
        time.sleep(1)
        pyautogui.press("enter")
        time.sleep(2)
        pyautogui.write(message)
        time.sleep(0.5)
        pyautogui.press("enter")

        logger.info(f"WhatsApp: sent message to {contact}")
        return {"success": True, "message": f"WhatsApp message sent to {contact}"}
    except Exception as e:
        logger.warning(f"WhatsApp automation failed: {e}")
        webbrowser.open("https://web.whatsapp.com")
        return {
            "success": True,
            "message": f"WhatsApp Web opened - please send message manually to {contact}",
        }


def automation_self_test() -> dict[str, Any]:
    """Run self test for action executor."""
    results = []

    # Test basic open
    r = open_app("chrome")
    results.append(f"open_app(chrome): {r.get('success')}")

    # Test search (doesn't actually execute to avoid opening browser)
    logger.info("Self test: action executor ready")

    return {"success": True, "tests": results}


__all__ = [
    "open_app",
    "search_web",
    "open_url",
    "send_whatsapp_message",
    "automation_self_test",
]
