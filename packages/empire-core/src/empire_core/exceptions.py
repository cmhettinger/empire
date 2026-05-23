"""Exceptions raised by empire-core."""


class EmpireCoreError(Exception):
    """Base exception for empire-core."""


class ConfigurationError(EmpireCoreError):
    """Raised when required configuration is missing or invalid."""


class NotFoundError(EmpireCoreError):
    """Raised when a requested resource cannot be found."""


class StorageRootNotFoundError(NotFoundError):
    """Raised when a storage root does not exist or is inactive."""


class ValidationError(EmpireCoreError):
    """Raised when caller input is invalid."""


class StorageError(EmpireCoreError):
    """Raised when object storage cannot complete an operation."""
