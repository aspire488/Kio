"""Desktop automation — window management, mouse, keyboard, multi-monitor, notifications.

Integrates with the ProviderRegistry as a desktop execution backend.
Extends app_operator.py with comprehensive desktop control capabilities.
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Any

from mini_kio.core.win_spawn import no_window

logger = logging.getLogger("mini_kio.desktop")


class WindowManager:
    """Window management — list, focus, move, resize, minimize, maximize, close."""

    @staticmethod
    def list_windows() -> list[dict[str, Any]]:
        if not WindowManager._is_windows():
            return []
        try:
            result = subprocess.run(
                ["powershell", "-Command", """
                    Get-Process | Where-Object { $_.MainWindowHandle -ne 0 } |
                    Select-Object Id, ProcessName, MainWindowTitle, @{N='Handle';E={$_.MainWindowHandle}} |
                    ConvertTo-Json
                """],
                capture_output=True, text=True, timeout=10,
                **no_window(),
            )
            import json
            data = json.loads(result.stdout or "[]")
            if isinstance(data, dict):
                data = [data]
            return [{
                "pid": w.get("Id"), "name": w.get("ProcessName", ""),
                "title": w.get("MainWindowTitle", ""), "handle": w.get("Handle"),
            } for w in data if w.get("MainWindowTitle")]
        except Exception as exc:
            logger.debug("list_windows failed: %s", exc)
            return []

    @staticmethod
    def focus_window(title: str) -> dict[str, Any]:
        if not WindowManager._is_windows():
            return {"success": False, "message": "Not supported on this platform"}
        try:
            import ctypes
            user32 = ctypes.windll.user32
            result = subprocess.run(
                ["powershell", "-Command", f"""
                    $h = (Get-Process | Where-Object {{ $_.MainWindowTitle -match '{title}' }} |
                           Select-Object -First 1).MainWindowHandle;
                    if ($h -and $h -ne 0) {{
                        [User32]::SetForegroundWindow($h) | Out-Null;
                        return $true
                    }}
                    return $false
                """],
                capture_output=True, text=True, timeout=5,
                **no_window(),
            )
            success = "True" in result.stdout
            return {"success": success, "message": f"{'Focused' if success else 'Could not find'} window: {title}"}
        except Exception as exc:
            return {"success": False, "message": f"focus_window failed: {exc}"}

    @staticmethod
    def _is_windows() -> bool:
        import platform
        return platform.system() == "Windows"


class MouseController:
    """Mouse automation — move, click, double-click, drag, scroll."""

    def __init__(self) -> None:
        self._x: int = 0
        self._y: int = 0

    def move(self, x: int, y: int, *, duration: float = 0.2) -> dict[str, Any]:
        try:
            import pyautogui
            pyautogui.moveTo(x, y, duration=duration)
            self._x, self._y = x, y
            return {"success": True, "message": f"Moved mouse to ({x}, {y})"}
        except ImportError:
            return self._move_fallback(x, y)
        except Exception as exc:
            return {"success": False, "message": f"Mouse move failed: {exc}"}

    def click(self, x: int | None = None, y: int | None = None, *,
              button: str = "left", clicks: int = 1) -> dict[str, Any]:
        try:
            import pyautogui
            pyautogui.click(x=x, y=y, button=button, clicks=clicks)
            if x is not None:
                self._x, self._y = x, y
            return {"success": True, "message": f"Mouse {button} click at ({x or self._x}, {y or self._y})"}
        except ImportError:
            return self._click_fallback(x, y, button)
        except Exception as exc:
            return {"success": False, "message": f"Mouse click failed: {exc}"}

    def double_click(self, x: int | None = None, y: int | None = None) -> dict[str, Any]:
        return self.click(x, y, clicks=2)

    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int, *,
             duration: float = 0.5) -> dict[str, Any]:
        try:
            import pyautogui
            pyautogui.drag(end_x - start_x, end_y - start_y, duration=duration)
            return {"success": True, "message": f"Dragged from ({start_x},{start_y}) to ({end_x},{end_y})"}
        except ImportError:
            pass
        return self._drag_fallback(start_x, start_y, end_x, end_y)

    def scroll(self, clicks: int, *, x: int | None = None, y: int | None = None) -> dict[str, Any]:
        try:
            import pyautogui
            pyautogui.scroll(clicks, x=x, y=y)
            return {"success": True, "message": f"Scrolled {clicks} clicks"}
        except ImportError:
            pass
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.mouse_event(0x0800, 0, 0, clicks * 120, 0)
            return {"success": True, "message": f"Scrolled {clicks} clicks"}
        except Exception as exc:
            return {"success": False, "message": f"Scroll failed: {exc}"}

    def position(self) -> dict[str, Any]:
        try:
            import pyautogui
            x, y = pyautogui.position()
            return {"success": True, "x": x, "y": y}
        except ImportError:
            pass
        try:
            import ctypes
            user32 = ctypes.windll.user32
            point = ctypes.wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            return {"success": True, "x": point.x, "y": point.y}
        except Exception as exc:
            return {"success": False, "message": f"Get position failed: {exc}"}

    def _move_fallback(self, x: int, y: int) -> dict[str, Any]:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetCursorPos(x, y)
            self._x, self._y = x, y
            return {"success": True, "message": f"Moved mouse to ({x}, {y})"}
        except Exception as exc:
            return {"success": False, "message": f"Mouse move failed: {exc}"}

    def _click_fallback(self, x: int | None, y: int | None, button: str) -> dict[str, Any]:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            if x is not None:
                user32.SetCursorPos(x, y)
                self._x, self._y = x, y
            flags = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}
            down, up = flags.get(button, (0x0002, 0x0004))
            user32.mouse_event(down, 0, 0, 0, 0)
            user32.mouse_event(up, 0, 0, 0, 0)
            return {"success": True, "message": f"Mouse {button} click at ({x or self._x}, {y or self._y})"}
        except Exception as exc:
            return {"success": False, "message": f"Mouse click failed: {exc}"}

    def _drag_fallback(self, sx: int, sy: int, ex: int, ey: int) -> dict[str, Any]:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetCursorPos(sx, sy)
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            user32.SetCursorPos(ex, ey)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
            return {"success": True, "message": f"Dragged from ({sx},{sy}) to ({ex},{ey})"}
        except Exception as exc:
            return {"success": False, "message": f"Drag failed: {exc}"}


class KeyboardController:
    """Keyboard automation — type, press hotkeys, shortcuts."""

    @staticmethod
    def type(text: str, *, interval: float = 0.05) -> dict[str, Any]:
        try:
            import pyautogui
            pyautogui.write(text, interval=interval)
            return {"success": True, "message": f"Typed {len(text)} characters"}
        except ImportError:
            pass
        try:
            import ctypes
            user32 = ctypes.windll.user32
            for char in text:
                user32.keybd_event(ord(char.upper()), 0, 0, 0)
                user32.keybd_event(ord(char.upper()), 0, 2, 0)
            return {"success": True, "message": f"Typed {len(text)} characters"}
        except Exception as exc:
            return {"success": False, "message": f"Type failed: {exc}"}

    @staticmethod
    def press(key: str) -> dict[str, Any]:
        try:
            import pyautogui
            pyautogui.press(key)
            return {"success": True, "message": f"Pressed key: {key}"}
        except ImportError:
            pass
        return {"success": False, "message": "Keyboard not available. Install pyautogui."}

    @staticmethod
    def hotkey(*keys: str) -> dict[str, Any]:
        try:
            import pyautogui
            pyautogui.hotkey(*keys)
            return {"success": True, "message": f"Hotkey: {'+'.join(keys)}"}
        except ImportError:
            pass
        try:
            import ctypes
            user32 = ctypes.windll.user32
            vk_map = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
                       "a": 0x41, "c": 0x43, "v": 0x56, "x": 0x58, "z": 0x5A,
                       "s": 0x53, "t": 0x54, "w": 0x57, "tab": 0x09, "escape": 0x1B,
                       "enter": 0x0D, "space": 0x20, "delete": 0x2E, "backspace": 0x08,
                       "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27}
            vks = [vk_map.get(k.lower(), ord(k.upper()[0])) if len(k) == 1 else vk_map.get(k.lower(), 0) for k in keys]
            for vk in vks:
                user32.keybd_event(vk, 0, 0, 0)
            for vk in reversed(vks):
                user32.keybd_event(vk, 0, 2, 0)
            return {"success": True, "message": f"Hotkey: {'+'.join(keys)}"}
        except Exception as exc:
            return {"success": False, "message": f"Hotkey failed: {exc}"}


class ClipboardController:
    """Desktop clipboard operations."""

    @staticmethod
    def get_text() -> dict[str, Any]:
        try:
            import pyperclip
            text = pyperclip.paste()
            return {"success": True, "text": text, "length": len(text)}
        except ImportError:
            pass
        try:
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            user32.OpenClipboard(0)
            handle = user32.GetClipboardData(13)
            text = ctypes.c_char_p(ctypes.windll.kernel32.GlobalLock(handle)).value
            user32.CloseClipboard()
            return {"success": True, "text": (text or b"").decode("utf-8", errors="replace")}
        except Exception as exc:
            return {"success": False, "message": f"Clipboard read failed: {exc}"}

    @staticmethod
    def set_text(text: str) -> dict[str, Any]:
        try:
            import pyperclip
            pyperclip.copy(text)
            return {"success": True, "message": f"Copied {len(text)} chars to clipboard"}
        except ImportError:
            pass
        return {"success": False, "message": "Clipboard not available. Install pyperclip."}


class NotificationController:
    """Desktop notifications."""

    @staticmethod
    def notify(title: str, message: str, *, duration_s: int = 5) -> dict[str, Any]:
        import platform
        system = platform.system()
        try:
            if system == "Windows":
                from plyer import notification
                notification.notify(title=title, message=message, timeout=duration_s)
            elif system == "Darwin":
                subprocess.run(["osascript", "-e",
                    f'display notification "{message}" with title "{title}"'], timeout=5)
            else:
                subprocess.run(["notify-send", title, message], timeout=5)
            return {"success": True, "message": f"Notification sent: {title}"}
        except ImportError:
            pass
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.MessageBoxW(0, message, title, 0)
            return {"success": True, "message": f"Notification shown: {title}"}
        except Exception as exc:
            return {"success": False, "message": f"Notification failed: {exc}"}


class ScreenController:
    """Screen / multi-monitor information."""

    @staticmethod
    def size() -> dict[str, Any]:
        try:
            import pyautogui
            w, h = pyautogui.size()
            return {"success": True, "width": w, "height": h}
        except ImportError:
            pass
        try:
            import ctypes
            user32 = ctypes.windll.user32
            return {"success": True, "width": user32.GetSystemMetrics(0),
                    "height": user32.GetSystemMetrics(1)}
        except Exception as exc:
            return {"success": False, "message": f"Screen size failed: {exc}"}

    @staticmethod
    def monitors() -> list[dict[str, Any]]:
        monitors = []
        try:
            import ctypes
            user32 = ctypes.windll.user32

            def _monitor_enum(hmonitor, hdc, rect, lparam):
                r = ctypes.wintypes.RECT()
                user32.GetMonitorInfoW(hmonitor, ctypes.byref(r))
                monitors.append({"left": r.left, "top": r.top,
                                 "right": r.right, "bottom": r.bottom})
                return 1

            MONITOR_ENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                                    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
            user32.EnumDisplayMonitors(None, None, MONITOR_ENUMPROC(_monitor_enum), 0)
        except Exception:
            pass
        if not monitors:
            size = ScreenController.size()
            monitors.append({"left": 0, "top": 0, "right": size.get("width", 1920),
                             "bottom": size.get("height", 1080)})
        return monitors

    @staticmethod
    def screenshot(save_path: str | None = None) -> dict[str, Any]:
        try:
            import pyautogui
            img = pyautogui.screenshot()
            if save_path:
                img.save(save_path)
                return {"success": True, "path": save_path, "size": img.size}
            import io
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return {"success": True, "data_length": len(buf.getvalue())}
        except ImportError:
            pass
        return {"success": False, "message": "Screenshot not available. Install pyautogui."}


class DesktopProvider:
    """Unified desktop automation provider.

    Registers with ProviderRegistry as the 'desktop' backend.
    """

    def __init__(self) -> None:
        self.windows = WindowManager()
        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        self.clipboard = ClipboardController()
        self.notifications = NotificationController()
        self.screen = ScreenController()

    def execute(self, action: str, target: str = "", **kwargs: Any) -> dict[str, Any]:
        dispatch = {
            "window_list": lambda: {"success": True, "windows": self.windows.list_windows()},
            "window_focus": lambda: self.windows.focus_window(target),
            "mouse_move": lambda: self.mouse.move(kwargs.get("x", 0), kwargs.get("y", 0)),
            "mouse_click": lambda: self.mouse.click(kwargs.get("x"), kwargs.get("y"),
                                                     button=kwargs.get("button", "left")),
            "mouse_double_click": lambda: self.mouse.double_click(kwargs.get("x"), kwargs.get("y")),
            "mouse_drag": lambda: self.mouse.drag(kwargs.get("start_x", 0), kwargs.get("start_y", 0),
                                                   kwargs.get("end_x", 0), kwargs.get("end_y", 0)),
            "mouse_scroll": lambda: self.mouse.scroll(kwargs.get("clicks", 1)),
            "mouse_position": lambda: self.mouse.position(),
            "keyboard_type": lambda: self.keyboard.type(target, interval=kwargs.get("interval", 0.05)),
            "keyboard_press": lambda: self.keyboard.press(target),
            "keyboard_hotkey": lambda: self.keyboard.hotkey(*target.split("+")),
            "clipboard_get": lambda: self.clipboard.get_text(),
            "clipboard_set": lambda: self.clipboard.set_text(target),
            "notification_send": lambda: self.notifications.notify(target, kwargs.get("message", "")),
            "screen_size": lambda: {"success": True, **self.screen.size()},
            "screen_monitors": lambda: {"success": True, "monitors": self.screen.monitors()},
            "screen_screenshot": lambda: self.screen.screenshot(target or None),
        }
        handler = dispatch.get(action)
        if handler:
            result = handler()
            result.setdefault("action", action)
            result.setdefault("target", target)
            return result
        return {"success": False, "message": f"Unknown desktop action: {action}", "action": action, "target": target}
