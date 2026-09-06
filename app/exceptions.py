"""Expected application failures safe to present to the user."""


class JarvisError(Exception):
    """Base class for recoverable application errors."""


class ServiceUnavailable(JarvisError):
    """An external dependency is temporarily unavailable."""


class BusyError(JarvisError):
    """Capacity is occupied; the caller should try again later."""


class ActionError(JarvisError):
    """An action is invalid, expired or has an uncertain outcome."""
