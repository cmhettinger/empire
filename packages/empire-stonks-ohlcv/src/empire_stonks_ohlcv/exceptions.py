"""Package-specific exceptions for Empire stonks OHLCV ingestion."""


class EmpireStonksOHLCVError(Exception):
    """Base exception for Empire stonks OHLCV failures."""


class OHLCVConfigError(EmpireStonksOHLCVError):
    """Raised when OHLCV configuration is missing or invalid."""


class OHLCVAcquisitionError(EmpireStonksOHLCVError):
    """Raised when provider source acquisition fails."""


class OHLCVParseError(EmpireStonksOHLCVError):
    """Raised when provider source data cannot be parsed."""


class OHLCVPersistenceError(EmpireStonksOHLCVError):
    """Raised when provider-native OHLCV data cannot be persisted."""
