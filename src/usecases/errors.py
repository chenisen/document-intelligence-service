from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    UNSUPPORTED_DOCUMENT_TYPE = "unsupported_document_type"
    DOCUMENT_QUALITY_TOO_LOW = "document_quality_too_low"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    UPSTREAM_TIMEOUT = "upstream_timeout"
    RATE_LIMITED = "rate_limited"
    INTERNAL_ERROR = "internal_error"


STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.INVALID_INPUT: 400,
    ErrorCode.UNSUPPORTED_DOCUMENT_TYPE: 422,
    ErrorCode.DOCUMENT_QUALITY_TOO_LOW: 422,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.UPSTREAM_UNAVAILABLE: 503,
    ErrorCode.UPSTREAM_TIMEOUT: 504,
}

TITLE_BY_CODE: dict[ErrorCode, str] = {
    ErrorCode.INVALID_INPUT: "Invalid input",
    ErrorCode.UNSUPPORTED_DOCUMENT_TYPE: "Unsupported document type",
    ErrorCode.DOCUMENT_QUALITY_TOO_LOW: "Document quality too low",
    ErrorCode.RATE_LIMITED: "Rate limited",
    ErrorCode.INTERNAL_ERROR: "Internal error",
    ErrorCode.UPSTREAM_UNAVAILABLE: "Upstream unavailable",
    ErrorCode.UPSTREAM_TIMEOUT: "Upstream timeout",
}


class ServiceError(Exception):
    def __init__(self, code: ErrorCode, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.extra = extra

    @property
    def status(self) -> int:
        return STATUS_BY_CODE[self.code]

    @property
    def title(self) -> str:
        return TITLE_BY_CODE[self.code]
