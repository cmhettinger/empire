"""Package-specific exceptions for Empire stonks OHLCV ingestion."""


class EmpireStonksOHLCVError(Exception):
    """Base exception for Empire stonks OHLCV failures."""


class OHLCVConfigError(EmpireStonksOHLCVError):
    """Raised when OHLCV configuration is missing or invalid."""


class OHLCVAcquisitionError(EmpireStonksOHLCVError):
    """Raised when provider source acquisition fails."""

    def __init__(
        self,
        message: str,
        *,
        market: str | None = None,
        source_code: str | None = None,
    ) -> None:
        self.market = market
        self.source_code = source_code
        super().__init__(message)


class OHLCVParseError(EmpireStonksOHLCVError):
    """Raised when provider source data cannot be parsed."""


class OHLCVPersistenceError(EmpireStonksOHLCVError):
    """Raised when provider-native OHLCV data cannot be persisted."""


class OHLCVWorkflowError(EmpireStonksOHLCVError):
    """Secret-safe failure at one acquisition-to-import workflow stage."""

    def __init__(
        self,
        stage: str,
        *,
        market: str | None = None,
        source_code: str | None = None,
    ) -> None:
        if stage not in {
            "acquisition",
            "parsing",
            "persistence",
            "reporting",
        }:
            raise ValueError(
                "stage must be acquisition, parsing, persistence, or reporting."
            )
        self.stage = stage
        self.market = market
        self.source_code = source_code
        super().__init__(f"OHLCV provider workflow failed during {stage}.")
