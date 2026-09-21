import base64
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from functions.analyze.handler import handler

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "contracts" / "v1"
SAMPLES = ROOT / "samples"
ROUTE = "/v1/documents:analyze"
BOUNDARY = "----document-intelligence"

analysis_schema = Draft202012Validator(json.loads((V1 / "analysis_result.schema.json").read_text()))
problem_schema = Draft202012Validator(json.loads((V1 / "problem.schema.json").read_text()))


class LambdaContext:
    function_name = "document-intelligence-hml-analyze"
    memory_limit_in_mb = 2048
    invoked_function_arn = "arn:aws:lambda:us-east-1:000000000000:function:document-intelligence"
    aws_request_id = "1d8f0b3e-0000-4000-8000-000000000000"

    def get_remaining_time_in_millis(self) -> int:
        return 29_000


def multipart(content: bytes, filename: str = "atestado.pdf") -> bytes:
    head = (
        f"--{BOUNDARY}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode()
    return head + content + f"\r\n--{BOUNDARY}--\r\n".encode()


def gateway_event(body: bytes) -> dict:
    return {
        "version": "2.0",
        "routeKey": f"POST {ROUTE}",
        "rawPath": ROUTE,
        "rawQueryString": "",
        "headers": {
            "content-type": f"multipart/form-data; boundary={BOUNDARY}",
            "content-length": str(len(body)),
            "host": "api.example.com",
        },
        "requestContext": {
            "accountId": "000000000000",
            "apiId": "abc123",
            "domainName": "api.example.com",
            "http": {
                "method": "POST",
                "path": ROUTE,
                "protocol": "HTTP/1.1",
                "sourceIp": "203.0.113.1",
                "userAgent": "integration-test",
            },
            "requestId": "1d8f0b3e",
            "stage": "$default",
            "time": "21/Sep/2026:12:00:00 +0000",
            "timeEpoch": 1790000000000,
        },
        "body": base64.b64encode(body).decode(),
        "isBase64Encoded": True,
    }


def invoke(content: bytes, filename: str = "atestado.pdf") -> dict:
    return handler(gateway_event(multipart(content, filename)), LambdaContext())


CERTIFICATE = (SAMPLES / "atestado_01_pdf_nativo.pdf").read_bytes()


def test_the_lambda_handler_answers_a_gateway_event_in_contract_format() -> None:
    response = invoke(CERTIFICATE)

    assert response["statusCode"] == 200
    assert response["isBase64Encoded"] is False
    analysis_schema.validate(json.loads(response["body"]))


def test_the_lambda_handler_returns_a_problem_the_gateway_can_deliver() -> None:
    response = invoke(b"")

    assert response["statusCode"] == 400
    assert response["isBase64Encoded"] is False
    problem_schema.validate(json.loads(response["body"]))
