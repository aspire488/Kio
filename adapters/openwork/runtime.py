"""OpenWork runtime – minimal in‑memory implementation.

Provides start/stop control and status tracking used by the adapter.
"""

# Simple global state for the runtime
_state = {
    "running": False,
    "info": "OpenWork runtime not started",
}

def start():
    """Start the OpenWork runtime.
    Returns a dict with the current status.
    """
    _state["running"] = True
    _state["info"] = "runtime started"
    return {"status": "started", "running": True}

def stop():
    """Stop the OpenWork runtime.
    Returns a dict indicating the runtime has stopped.
    """
    _state["running"] = False
    _state["info"] = "runtime stopped"
    return {"status": "stopped", "running": False}

def status():
    """Return current runtime status dictionary.
    """
    return {"running": _state["running"], "info": _state["info"]}
