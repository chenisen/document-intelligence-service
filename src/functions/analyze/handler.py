from typing import Any

from aws_lambda_powertools import Logger
from mangum import Mangum
from mangum.adapter import DEFAULT_TEXT_MIME_TYPES

from entrypoints.http.app import app

logger = Logger(service="document-intelligence")

lambda_http_adapter = Mangum(
    app,
    lifespan="off",
    text_mime_types=[*DEFAULT_TEXT_MIME_TYPES, "application/problem+json"],
)


@logger.inject_lambda_context
def handler(event: dict[str, Any], context: Any) -> Any:
    return lambda_http_adapter(event, context)
