"""Public exceptions for Empire stonks technical indicators."""


class EmpireStonksTechIndicatorsError(Exception):
    """Base exception for technical-indicator package failures."""


class TechIndicatorsConfigError(EmpireStonksTechIndicatorsError):
    """Raised when technical-indicator configuration is missing or invalid."""


class TechIndicatorsCalculationError(EmpireStonksTechIndicatorsError):
    """Raised when technical-indicator calculation cannot complete safely."""


class TechIndicatorsValidationError(EmpireStonksTechIndicatorsError):
    """Raised when technical-indicator input or output validation fails."""


class TechIndicatorsPersistenceError(EmpireStonksTechIndicatorsError):
    """Raised when technical-indicator state cannot be persisted safely."""


class TechIndicatorsWorkflowError(EmpireStonksTechIndicatorsError):
    """Raised when a technical-indicator workflow cannot complete safely."""


class TechIndicatorsWriterLockLostError(TechIndicatorsWorkflowError):
    """Raised when an acquired writer-lock transaction becomes unusable."""


__all__ = [
    "EmpireStonksTechIndicatorsError",
    "TechIndicatorsCalculationError",
    "TechIndicatorsConfigError",
    "TechIndicatorsPersistenceError",
    "TechIndicatorsValidationError",
    "TechIndicatorsWorkflowError",
    "TechIndicatorsWriterLockLostError",
]
