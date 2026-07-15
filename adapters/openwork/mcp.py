"""OpenWork MCP (Management Control Point).

Provides a thin wrapper to coordinate runtime, configuration, and sessions.
"""

from .runtime import start as runtime_start, stop as runtime_stop, status as runtime_status
from .configuration import get_config, set_config
from .session import create_session, get_session, close_session

class MCP:
    """Simple orchestrator for OpenWork components.
    """

    def start(self):
        """Start the OpenWork runtime and return its status."""
        return runtime_start()

    def stop(self):
        """Stop the runtime."""
        return runtime_stop()

    def status(self):
        """Return runtime status together with config snapshot."""
        return {
            "runtime": runtime_status(),
            "config": {k: get_config(k) for k in []},  # empty snapshot for now
        }

    # Configuration shortcuts
    def set_config(self, key: str, value):
        return set_config(key, value)

    def get_config(self, key: str, default=None):
        return get_config(key, default)

    # Session shortcuts
    def create_session(self, name: str):
        return create_session(name)

    def get_session(self, name: str):
        return get_session(name)

    def close_session(self, name: str):
        return close_session(name)
