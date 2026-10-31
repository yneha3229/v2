"""Exception hierarchy. Every error Proofroom raises on purpose derives from ProofroomError."""
from __future__ import annotations


class ProofroomError(Exception):
    """Base class for expected, reportable failures."""


class ConfigError(ProofroomError):
    """A required setting (such as an API key) is missing or invalid."""


class CrustError(ProofroomError):
    """A normalized Crustdata failure: {status, type, message, denied_fields} (plan v2 §6.3).

    `status` is the HTTP status, or 0 for failures before a response (network, deadline,
    missing fixture). `type` is the API's error type or a local one such as `network`.
    """

    def __init__(self, status: int, type: str, message: str,
                 denied_fields: list[str] | None = None):
        self.status = status
        self.type = type
        self.message = message
        self.denied_fields = list(denied_fields or [])
        super().__init__(f"{status} {type}: {message}")

    def as_dict(self) -> dict:
        return {"status": self.status, "type": self.type, "message": self.message,
                "denied_fields": list(self.denied_fields)}

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CrustError) and self.as_dict() == other.as_dict()

    __hash__ = Exception.__hash__

    @property
    def fatal(self) -> bool:
        """401 stops the run; 402 stops retrieval (the brief is narrowed, not failed)."""
        return self.status == 401


class StoreError(ProofroomError):
    """A run could not be written, read back or verified, so it is not DELIVERED."""


class ModelError(ProofroomError):
    """A model call failed: refusal, max_tokens stop, timeout or invalid output."""
