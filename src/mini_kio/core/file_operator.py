"""
File Operator - Open folders and handle file operations.

Key improvements:
1. Folder aliases: downloads, desktop, documents, pictures, etc.
2. shell: paths for Windows standard folders (work regardless of username)
3. Proper error handling with subprocess.run()
4. Platform detection (Windows vs Unix)
5. Strips trailing "folder" keyword from commands
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == "Windows"

# ─────────────────────────────────────────────────────────────────────────────
# Folder aliases for Windows (using shell: paths for reliability)
# ─────────────────────────────────────────────────────────────────────────────

FOLDER_ALIASES: dict[str, str] = {
    "downloads": "shell:Downloads",
    "desktop": "shell:Desktop",
    "documents": "shell:Documents",
    "pictures": "shell:Pictures",
    "music": "shell:Music",
    "videos": "shell:Videos",
    "home": str(Path.home()),
    "appdata": str(Path(os.environ.get("APPDATA", Path.home()))),
}

# For compatibility
WINDOWS_FOLDERS = FOLDER_ALIASES


def open_folder(name: str) -> dict:
    """
    Open a folder by name or path.
    
    Args:
        name: Folder name (downloads, desktop, etc.) or absolute path
        
    Returns:
        {"success": bool, "message": str}
    """
    name_clean = name.lower().strip()
    
    # Strip trailing "folder" keyword
    if name_clean.endswith(" folder"):
        name_clean = name_clean[:-7].strip()
    
    # Also handle if someone says just "folder"
    if name_clean == "folder":
        name_clean = name.lower().strip()

    logger.info(f"[FILE] open_folder({name_clean!r})")

    # 1. Check folder aliases
    if name_clean in FOLDER_ALIASES:
        folder_path = FOLDER_ALIASES[name_clean]
        return _open_path(folder_path, name_clean)

    # 2. Try as absolute or home-relative path
    try:
        path = Path(name_clean).expanduser()
        if path.exists() and path.is_dir():
            return _open_path(str(path), name_clean)
    except Exception as e:
        logger.debug(f"[FILE] path check failed: {e}")

    logger.warning(f"[FILE] folder not found: {name!r}")
    return {"success": False, "message": f"Folder not found: {name}"}


def _open_path(path: str, label: str) -> dict:
    """
    Open a file path or Windows shell: path.
    
    Args:
        path: Filesystem path or shell: path
        label: Display label for messages
        
    Returns:
        {"success": bool, "message": str}
    """
    try:
        if _IS_WINDOWS:
            # On Windows, use explorer
            result = subprocess.run(
                ["explorer", path],
                timeout=5,
                creationflags=0x00000008,  # DETACHED_PROCESS
                capture_output=True,
            )
            # explorer often returns non-zero even on success
            logger.info(f"[FILE] opened: {path}")
            return {"success": True, "message": f"Opened {label}"}
        else:
            # On Unix, use xdg-open
            subprocess.Popen(["xdg-open", path])
            logger.info(f"[FILE] opened: {path}")
            return {"success": True, "message": f"Opened {label}"}

    except subprocess.TimeoutExpired:
        # Timeout is normal — explorer is running
        logger.info(f"[FILE] explorer timeout (normal): {path}")
        return {"success": True, "message": f"Opened {label}"}

    except FileNotFoundError:
        logger.error(f"[FILE] explorer not found")
        return {"success": False, "message": f"File explorer not found"}

    except Exception as e:
        logger.error(f"[FILE] _open_path error for {path}: {e}")
        return {"success": False, "message": f"Failed to open {label}: {str(e)[:80]}"}


def create_file(filename: str, content: str = "") -> dict:
    """
    Create a new file with optional content.
    
    Args:
        filename: Filename or path (~ is expanded)
        content: File content
        
    Returns:
        {"success": bool, "message": str}
    """
    try:
        path = Path(filename).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info(f"[FILE] created: {path}")
        return {"success": True, "message": f"Created {filename}"}
    except Exception as e:
        logger.error(f"[FILE] create_file error: {e}")
        return {"success": False, "message": f"Failed to create file: {str(e)[:80]}"}


def list_directory(path: str = ".") -> dict:
    """
    List contents of a directory.
    
    Args:
        path: Directory path
        
    Returns:
        {"success": bool, "message": str, "items": [{"name": str, "type": str}]}
    """
    try:
        dir_path = Path(path).expanduser()
        if not dir_path.exists():
            return {"success": False, "message": f"Path does not exist: {path}"}
        if not dir_path.is_dir():
            return {"success": False, "message": f"Not a directory: {path}"}

        items = [
            {"name": item.name, "type": "folder" if item.is_dir() else "file"}
            for item in sorted(dir_path.iterdir())
        ]
        return {
            "success": True,
            "message": f"Found {len(items)} items",
            "items": items
        }
    except PermissionError:
        return {"success": False, "message": f"Permission denied: {path}"}
    except Exception as e:
        logger.error(f"[FILE] list_directory error: {e}")
        return {"success": False, "message": f"Failed to list: {str(e)[:80]}"}


__all__ = ["open_folder", "create_file", "list_directory", "FOLDER_ALIASES", "WINDOWS_FOLDERS"]
