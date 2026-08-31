class SystematicFuturesError(Exception):
    """Base exception for this project."""


class TimeSemanticsError(SystematicFuturesError):
    """Raised when a timestamp is naive, inconsistent, or unavailable."""


class DataTimingInvariantError(SystematicFuturesError):
    """Raised when usable-from or delivery ordering is invalid."""


class DataQualityError(SystematicFuturesError):
    """Raised when a datum violates its dataset policy."""


class DuplicateIdentifierError(SystematicFuturesError):
    """Raised when an immutable identifier is reused."""


class MarketConfigurationError(SystematicFuturesError):
    """Raised when a market definition is incomplete or inconsistent."""


class SessionBoundaryError(SystematicFuturesError):
    """Raised when a timestamp cannot be classified under a valid session policy."""


class ContractBoundaryError(SystematicFuturesError):
    """Raised when contract identity changes without an explicit transition."""


class UnverifiedQuantConnectApiError(SystematicFuturesError):
    """Raised when code depends on an unverified QuantConnect API."""


__all__ = (
    "ContractBoundaryError",
    "DataQualityError",
    "DataTimingInvariantError",
    "DuplicateIdentifierError",
    "MarketConfigurationError",
    "SessionBoundaryError",
    "SystematicFuturesError",
    "TimeSemanticsError",
    "UnverifiedQuantConnectApiError",
)
