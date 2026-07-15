"""OpenWork session management – in‑memory implementation.

Creates, stores, and retrieves simple session objects.
"""

_sessions = {}  # type: dict[str, dict]

def create_session(name: str):
    """Create a new session with the given name.
    Returns the session dict.
    """
    sess = {"name": name, "active": True}
    _sessions[name] = sess
    return sess

def get_session(name: str):
    """Retrieve a session by name, or ``None`` if not exists.
    """
    return _sessions.get(name)

def close_session(name: str):
    """Mark a session as inactive and remove it.
    """
    sess = _sessions.pop(name, None)
    if sess:
        sess["active"] = False
    return sess
