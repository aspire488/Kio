"""
Mini-KIO Core - Fixed and Enhanced Modules

This package contains the core automation engine with:
- Reliable multi-step command execution
- App registry and process verification
- Folder routing with shortcuts
- Safe subprocess management
- Comprehensive diagnostics
"""

__version__ = "1.0"
__author__ = "KIO Team"

# Core modules (will be imported on demand)
__all__ = [
    "command_parser",
    "command_router",
    "app_operator",
    "file_operator",
    "system_operator",
    "task_engine",
    "kio_diagnostics",
]
