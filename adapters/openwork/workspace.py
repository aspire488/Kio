"""OpenWork workspace – simple in‑memory store.

Provides APIs to list, add, and retrieve workspace items.
"""

_items = []  # type: list[dict]

def list_items():
    """Return a list of all workspace items.
    """
    return list(_items)

def add_item(item: dict):
    """Add a new item to the workspace.
    """
    _items.append(item)
    return item

def get_item(index: int):
    """Retrieve an item by its index.
    """
    try:
        return _items[index]
    except IndexError:
        return None
