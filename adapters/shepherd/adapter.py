"""Shepherd Adapter – placeholder implementation.

Provides minimal governance, audit, and recovery capabilities required by the
AdapterRegistry. No real Shepherd library is imported to keep the architecture
constraint that external code is only accessed via adapters.
"""

__adapter_id__ = "shepherd"
__version__ = "0.1.0"
CAPABILITIES = ["governance", "audit", "recovery"]

class Adapter:
    """Simple stub exposing health and shutdown methods.
    """

    def __init__(self):
        self.id = __adapter_id__
        self.version = __version__
        self._capabilities = CAPABILITIES
        self._last_error = None

    def health(self):
        return {
            "status": True,
            "version": self.version,
            "capabilities": self._capabilities,
            "details": "Shepherd stub healthy",
        }

    def shutdown(self):
        pass
