"""OpenWork Adapter – placeholder implementation.

Provides the minimal interface required by AdapterRegistry.
No direct imports of the real OpenWork library are performed to satisfy
architecture constraints.
"""

__adapter_id__ = "openwork"
__version__ = "0.1.0"
CAPABILITIES = ["openwork"]

class Adapter:
    """Simple stub adapter exposing a health method.
    """

    def health(self):
        return {"status": True, "details": "OpenWork stub healthy"}

    def shutdown(self):
        pass
