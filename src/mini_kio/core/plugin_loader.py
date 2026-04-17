import os
import sys
import importlib.util
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def load_plugins() -> None:
    core_dir = Path(__file__).resolve().parent
    if str(core_dir) not in sys.path:
        sys.path.insert(0, str(core_dir))

    from . import command_router, event_bus
    from .event_bus import subscribe

    plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
    if not plugins_dir.exists():
        plugins_dir.mkdir(parents=True, exist_ok=True)

    loaded_count = 0
    for file in plugins_dir.glob("*.py"):
        if file.name == "__init__.py":
            continue
        try:
            module_name = f"plugins.{file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if hasattr(module, "register_plugin"):
                    handlers = {}
                    patterns = []
                    module.register_plugin(handlers, patterns)

                    for event_name, handler in handlers.items():
                        subscribe(event_name, handler)

                    for k, v in handlers.items():
                        command_router.INTENT_HANDLERS[k] = v
                    for p, n in patterns:
                        command_router._COMPILED_INTENTS.insert(
                            0, (re.compile(p, re.IGNORECASE | re.MULTILINE), n)
                        )

                    loaded_count += 1
                    logger.info(
                        f"Loaded plugin {file.name} with {len(handlers)} handlers."
                    )
        except Exception as e:
            logger.error(f"Failed to load plugin {file.name}: {e}")

    logger.info(f"Finished loading {loaded_count} plugins.")
