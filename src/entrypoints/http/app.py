import hashlib
import logging
from typing import Annotated, BinaryIO

from fastapi import Depends, FastAPI, Form
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.formparsers import MultiPartParser
from starlette.requests import Request

from core.document import MAX_FILE_BYTES
from entrypoints.bootstrap import Dependencies, build_analyzer, build_dependencies
from entrypoints.http import models
from usecases.errors import ErrorCode, ServiceError

CHUNK_BYTES = 64 * 1024
PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_TYPE_PREFIX = "https://itau.example/document-intelligence/errors/"

logger = logging.getLogger("document_intelligence")

MultiPartParser.spool_max_size = 0

app = FastAPI(
    title="Document Intelligence Service",
    version="1.1.0",
    description=(
        "Interpreta um documento médico e devolve os campos daquele tipo, cada um com o trecho de "
        "texto que o originou e um grau de confiança. Não decide nada de negócio e não guarda nada."
    ),
)


def read_within_limit(stream: BinaryIO, limit: int = MAX_FILE_BYTES) -> bytes:
    file_chunks: list[bytes] = []
    total_bytes = 0
    while file_chunk := stream.read(CHUNK_BYTES):
        total_bytes += len(file_chunk)
        if total_bytes > limit:
            raise ServiceError(
                ErrorCode.INVALID_INPUT,
                "the file is larger than the accepted limit; shrink it before calling",
                limit_bytes=limit,
            )
        file_chunks.append(file_chunk)
    if total_bytes == 0:
        raise ServiceError(ErrorCode.INVALID_INPUT, "the file is empty")
    return b"".join(file_chunks)


def get_dependencies() -> Dependencies:
    return build_dependencies()


@app.post("/v1/documents:analyze", response_model=models.AnalysisResult, tags=["analysis"])
def analyze_document(
    request: Request,
    upload: Annotated[models.DocumentUpload, Form(media_type="multipart/form-data")],
    dependencies: Annotated[Dependencies, Depends(get_dependencies)],
) -> models.AnalysisResult:
    content = read_within_limit(upload.file.file)
    file_sha256 = hashlib.sha256(content).hexdigest()
    request.state.file_sha256 = file_sha256

    try:
        analysis = build_analyzer(dependencies=dependencies)(content)
        confidence_by_field = {item.name: item.confidence.value for item in analysis.fields}
        logger.info(
            "document_analysis",
            extra={
                "file_sha256": file_sha256,
                "caller": "local",
                "route": analysis.route.value,
                "outcome": "success",
                "confidence_by_field": confidence_by_field,
                "model_id": analysis.provenance.get("model_id"),
                "prompt_version": analysis.provenance.get("prompt_version"),
                "review_required": analysis.review.required,
                "review_reasons": analysis.review.reasons,
            },
        )
        return models.from_analysis(analysis)
    except TimeoutError:
        logger.info(
            "document_analysis",
            extra={
                "file_sha256": file_sha256,
                "caller": "local",
                "outcome": ErrorCode.UPSTREAM_TIMEOUT.value,
            },
            exc_info=None,
        )
        raise ServiceError(
            ErrorCode.UPSTREAM_TIMEOUT, "an upstream service timed out during analysis"
        ) from None
    except ConnectionError:
        logger.info(
            "document_analysis",
            extra={
                "file_sha256": file_sha256,
                "caller": "local",
                "outcome": ErrorCode.UPSTREAM_UNAVAILABLE.value,
            },
            exc_info=None,
        )
        raise ServiceError(
            ErrorCode.UPSTREAM_UNAVAILABLE, "an upstream service was unavailable during analysis"
        ) from None
    except ServiceError:
        raise
    except Exception:
        logger.info(
            "document_analysis",
            extra={
                "file_sha256": file_sha256,
                "caller": "local",
                "outcome": "internal_error",
            },
            exc_info=None,
        )
        raise ServiceError(ErrorCode.INTERNAL_ERROR, "the analysis could not complete") from None


def problem_response(error: ServiceError) -> JSONResponse:
    body = {
        "type": f"{PROBLEM_TYPE_PREFIX}{error.code.value}",
        "title": error.title,
        "status": error.status,
        "detail": error.detail,
        "code": error.code.value,
        **error.extra,
    }
    return JSONResponse(status_code=error.status, content=body, media_type=PROBLEM_MEDIA_TYPE)


@app.exception_handler(ServiceError)
def handle_service_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, ServiceError)
    return problem_response(error)


@app.exception_handler(RequestValidationError)
def handle_validation_error(request: Request, error: Exception) -> JSONResponse:
    return problem_response(
        ServiceError(ErrorCode.INVALID_INPUT, "the request does not match the published contract")
    )


@app.exception_handler(Exception)
def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    return problem_response(
        ServiceError(ErrorCode.INTERNAL_ERROR, "the analysis could not complete")
    )
