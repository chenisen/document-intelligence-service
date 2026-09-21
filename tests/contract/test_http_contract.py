import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from core.document import MAX_FILE_BYTES
from entrypoints.http.app import app
from usecases.errors import STATUS_BY_CODE, TITLE_BY_CODE, ErrorCode

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "contracts" / "v1"
ROUTE = "/v1/documents:analyze"

client = TestClient(app)


def oversized_bytes() -> bytes:
    return b"\xff\xd8\xff" + b"\0" * (MAX_FILE_BYTES - 2)


ANALYSIS_SCHEMA = json.loads((V1 / "analysis_result.schema.json").read_text())
CONTRACT_VERSION = ANALYSIS_SCHEMA["properties"]["schema_version"]["const"]
problem_schema = Draft202012Validator(json.loads((V1 / "problem.schema.json").read_text()))


def post(content: bytes, filename: str = "atestado.pdf") -> object:
    return client.post(ROUTE, files={"file": (filename, content, "application/pdf")})


def test_rejects_request_without_file_field() -> None:
    response = client.post(ROUTE)

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    problem_schema.validate(response.json())
    assert response.json()["code"] == ErrorCode.INVALID_INPUT


def test_rejects_file_above_the_limit_with_the_limit_in_the_body() -> None:
    response = post(oversized_bytes(), filename="foto_acima_do_limite.jpg")

    assert response.status_code == 400
    problem_schema.validate(response.json())
    assert response.json()["code"] == ErrorCode.INVALID_INPUT
    assert response.json()["limit_bytes"] == MAX_FILE_BYTES


def test_rejects_an_empty_file() -> None:
    response = post(b"")

    assert response.status_code == 400
    assert response.json()["code"] == ErrorCode.INVALID_INPUT


def test_the_python_error_taxonomy_matches_the_published_catalogue() -> None:
    catalogue = yaml.safe_load((V1 / "errors.yaml").read_text(encoding="utf-8"))["errors"]

    assert {entry["code"] for entry in catalogue} == {code.value for code in ErrorCode}
    for entry in catalogue:
        code = ErrorCode(entry["code"])
        assert STATUS_BY_CODE[code] == entry["status"]
        assert TITLE_BY_CODE[code]


@pytest.mark.parametrize("code", list(ErrorCode))
def test_every_code_produces_a_body_that_validates_as_a_problem(code: ErrorCode) -> None:
    from entrypoints.http.app import problem_response
    from usecases.errors import ServiceError

    response = problem_response(ServiceError(code, "detail without document content"))

    assert response.status_code == STATUS_BY_CODE[code]
    problem_schema.validate(json.loads(response.body))


def test_the_published_openapi_is_served_for_the_demo() -> None:
    assert client.get("/docs").status_code == 200

    served = client.get("/openapi.json").json()
    assert served["info"]["version"] == CONTRACT_VERSION
    assert ROUTE in served["paths"]
