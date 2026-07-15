"""OpenWork tool registry – maps tool names to callables.
"""

_tools: dict[str, any] = {}

def register_tool(name: str, func):
    """Register a tool callable under the given name.
    Overwrites any existing entry with the same name.
    """
    _tools[name] = func
    return func

def get_tool(name: str):
    """Retrieve a registered tool, or ``None`` if not found.
    """
    return _tools.get(name)

def list_tools():
    """Return a list of registered tool names.
    """
    return list(_tools.keys())
