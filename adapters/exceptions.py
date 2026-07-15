# Adapter related exceptions – minimal hierarchy.

class AdapterError(Exception):
    """Base class for all adapter errors."""
    pass

class AdapterLoadError(AdapterError):
    """Raised when an adapter fails to load (import/instantiation)."""
    pass

class AdapterRegistrationError(AdapterError):
    """Raised when registering an adapter fails (duplicate id, invalid metadata)."""
    pass

class AdapterValidationError(AdapterError):
    """Raised when an adapter does not meet required interface."""
    pass

class AdapterHealthError(AdapterError):
    """Raised when an adapter's health check fails or is malformed."""
    pass