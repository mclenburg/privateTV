class PrivateTvError(Exception):
    """Base exception for PrivateTV."""


class ConfigurationError(PrivateTvError):
    """Raised when configuration is invalid."""


class NoCurrentProgrammeError(PrivateTvError):
    """Raised when no schedule entry exists for the requested time."""


class StreamLimitExceededError(PrivateTvError):
    """Raised when the configured maximum parallel stream count is reached."""
