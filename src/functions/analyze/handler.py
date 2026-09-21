"""Lambda entry point. Two lines of adaptation and the structured logger, nothing else."""

from typing import Any

from aws_lambda_powertools import Logger
from mangum import Mangum
from mangum.adapter import DEFAULT_TEXT_MIME_TYPES

from entrypoints.http.app import app

logger = Logger(service="document-intelligence")

# lifespan off: there is nothing to start up or tear down, and the invocation is one request long.
# The problem type is declared because Mangum only knows `application/json`, and would ship every
# error response base64 encoded while every success went out as text.
_asgi = Mangum(
    app,
    lifespan="off",
    text_mime_types=[*DEFAULT_TEXT_MIME_TYPES, "application/problem+json"],
)


@logger.inject_lambda_context
def handler(event: dict[str, Any], context: Any) -> Any:
    return _asgi(event, context)
