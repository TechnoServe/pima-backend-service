from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DomainError(Exception):
    """Base domain-level exception translated by routers into HTTP errors."""

    message: str
    status_code: int = 400
    code: str = "domain_error"
    details: dict[str, Any] = field(default_factory=dict)


class ValidationError(DomainError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message=message, status_code=400, code="validation_error", details=details or {})


class NotFoundError(DomainError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message=message, status_code=404, code="not_found", details=details or {})


class ConflictError(DomainError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message=message, status_code=409, code="conflict", details=details or {})


class ExternalServiceError(DomainError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message=message, status_code=502, code="external_service_error", details=details or {})
