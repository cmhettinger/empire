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


class OHLCVWorkflowError(EmpireStonksOHLCVError):
    """Secret-safe failure at one acquisition-to-import workflow stage."""

    def __init__(self, stage: str) -> None:
        if stage not in {"acquisition", "parsing", "persistence"}:
            raise ValueError("stage must be acquisition, parsing, or persistence.")
        self.stage = stage
        super().__init__(f"OHLCV provider workflow failed during {stage}.")
