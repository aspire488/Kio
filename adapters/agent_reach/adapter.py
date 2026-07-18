"""Agent Reach Adapter – thin wrapper around the Agent Reach library.

Provides web‑read, semantic search and remote‑execution capabilities as a
plain Python adaptor. No direct network logic is implemented here – all heavy
lifting is delegated to the upstream `agent_reach` package.
"""

__adapter_id__ = "agent_reach"
__version__ = "0.1.0"
CAPABILITIES = ["web_read", "semantic_search", "remote_execution"]

class Adapter:
    """Adapter exposing a minimal subset of Agent Reach functionality.

    The methods lazily import `agent_reach.core` to avoid import‑time failures
    when the optional dependency is not installed. This keeps the core KIO
    runtime lightweight.
    """

    def __init__(self):
        self.id = __adapter_id__
        self.version = __version__
        self._capabilities = CAPABILITIES
        self._last_error = None

    # ------- health -----------------------------------------------------
    def health(self):
        return {
            "status": True,
            "version": self.version,
            "capabilities": self._capabilities,
            "details": "Agent Reach stub healthy",
        }

    # ------- web read ---------------------------------------------------
    def read_url(self, url: str):
        """Return the textual content of a URL using Agent Reach's reader.

        Returns a dict with `status` (bool) and `content` (str) on success.
        """
        try:
            from agent_reach.core import read as ar_read
        except Exception as exc:
            self._last_error = str(exc)
            return {"status": False, "error": "agent_reach not available", "details": self._last_error}
        try:
            content = ar_read(url)
            return {"status": True, "content": content}
        except Exception as exc:
            self._last_error = str(exc)
            return {"status": False, "error": "read failed", "details": self._last_error}

    # ------- semantic search --------------------------------------------
    def search(self, query: str):
        """Perform a semantic search via Agent Reach.

        Returns a dict with `status` and `results` (list) on success.
        """
        try:
            from agent_reach.core import search as ar_search
        except Exception as exc:
            self._last_error = str(exc)
            return {"status": False, "error": "agent_reach not available", "details": self._last_error}
        try:
            results = ar_search(query)
            return {"status": True, "results": results}
        except Exception as exc:
            self._last_error = str(exc)
            return {"status": False, "error": "search failed", "details": self._last_error}

    # ------- shutdown ---------------------------------------------------
    def shutdown(self):
        # No persistent resources to clean up.
        pass
