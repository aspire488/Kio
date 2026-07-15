"""OpenWork plugins registry.

Allows registration of plugin callables that can extend OpenWork behavior.
"""

_plugins: dict[str, any] = {}

def register_plugin(name: str, plugin):
    """Register a plugin under the given name.
    Overwrites any existing plugin with the same name.
    """
    _plugins[name] = plugin
    return plugin

def get_plugin(name: str):
    """Retrieve a plugin by name, or ``None`` if not registered.
    """
    return _plugins.get(name)

def list_plugins():
    """List all registered plugin names.
    """
    return list(_plugins.keys())
