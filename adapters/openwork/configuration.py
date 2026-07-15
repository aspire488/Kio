"""OpenWork configuration – simple key/value store.

Provides ``get_config`` and ``set_config`` helpers used by the adapter.
"""

_config_store = {}  # type: dict[str, any]

def get_config(key: str, default=None):
    """Retrieve a configuration value.
    Returns ``default`` if the key is missing.
    """
    return _config_store.get(key, default)

def set_config(key: str, value):
    """Set a configuration value.
    """
    _config_store[key] = value
    return value
