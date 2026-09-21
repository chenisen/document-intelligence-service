"""Composition root. The only module that reads `DIS_PROFILE` and the only one that builds adapters.

Everything else receives what it needs. That is what keeps the domain testable without AWS, and it
is enforced by a test that scans the source for anyone else reading the variable.
"""

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from adapters.aws.bedrock import BedrockLlm
from adapters.aws.kendra import KendraRetriever
from adapters.aws.metrics import EmfMetrics
from adapters.aws.textract import TextractOcr
from adapters.catalog import load_catalog
from adapters.clock import SystemClock
from adapters.documents import normalize, pages_of, read_pdf
from adapters.fakes.clock import FixedClock
from adapters.fakes.knowledge import FakeKnowledgeRetriever
from adapters.fakes.llm import StubLlm
from adapters.fakes.metrics import InMemoryMetrics
from adapters.fakes.ocr import StubOcr
from core.catalog import Catalog
from core.document import MAX_FILE_BYTES, ReadingRoute
from usecases.analyze import Analysis, AnalyzeDocument
from usecases.errors import ErrorCode, ServiceError
from usecases.ports import Clock, KnowledgeRetriever, LlmPort, MetricsPort, OcrPort

PROFILE_VARIABLE = "DIS_PROFILE"
FAKE = "fake"
AWS = "aws"
PROFILES = (FAKE, AWS)
DEFAULT_PROFILE = FAKE


class UnknownProfile(RuntimeError):
    """Raised when `DIS_PROFILE` holds something that is not a profile.

    Failing to start is the point: a typo must never quietly fall back to `aws` and start spending.
    """


class MissingConfiguration(RuntimeError):
    """Raised when the `aws` profile is asked for without the settings it needs.

    Failing to start is the point. A knowledge index id that is absent would otherwise surface as
    an analysis that silently stops being grounded.
    """


@dataclass(frozen=True)
class Dependencies:
    """Everything the pipeline needs, resolved once, at the edge.

    There is no storage here, and that absence is intentional: the service keeps nothing.
    """

    ocr: OcrPort
    llm: LlmPort
    knowledge: KnowledgeRetriever
    metrics: MetricsPort
    clock: Clock
    catalog: Catalog
    # Vem da configuração do modelo, nunca de uma constante no código: é ela que viaja na
    # proveniência, e duas fontes de verdade fariam a proveniência mentir sobre o prompt que rodou.
    prompt_version: str
    # Same rule for the model and the OCR engine: the profile names what actually runs.
    model_id: str
    ocr_engine: str


# Both identify a resource inside one AWS account, so neither belongs in a file that travels in
# the image: they arrive from the deployment. What stays in configuration is the governance around
# them — the guardrail version, the retrieval filter — which is the same in every account.
KENDRA_INDEX_VARIABLE = "DIS_KENDRA_INDEX_ID"
GUARDRAIL_VARIABLE = "DIS_BEDROCK_GUARDRAIL_ID"
CONFIG = Path(__file__).resolve().parents[2] / "config"
BEDROCK_CONFIG = CONFIG / "bedrock.json"
KENDRA_CONFIG = CONFIG / "kendra.json"
TEXTRACT_ENGINE = "amazon-textract/detect-document-text"
STUB_ENGINE = "stub/reference-set"


def current_profile(environment: Mapping[str, str] | None = None) -> str:
    """Resolve the active profile. Defaults to `fake`: the safe one costs nothing."""
    source = os.environ if environment is None else environment
    name = source.get(PROFILE_VARIABLE, DEFAULT_PROFILE).strip().lower()
    if name not in PROFILES:
        raise UnknownProfile(
            f"{PROFILE_VARIABLE}={name!r} is not a profile. Use one of {', '.join(PROFILES)}."
        )
    return name


def build_metrics(profile: str) -> MetricsPort:
    return InMemoryMetrics() if profile == FAKE else EmfMetrics()


def build_clock(profile: str) -> Clock:
    return FixedClock() if profile == FAKE else SystemClock()


def build_dependencies(profile: str | None = None) -> Dependencies:
    name = profile if profile is not None else current_profile()
    if name not in PROFILES:
        raise UnknownProfile(f"{name!r} is not a profile. Use one of {', '.join(PROFILES)}.")

    catalog = load_catalog()
    config = json.loads(BEDROCK_CONFIG.read_text(encoding="utf-8"))
    if name == AWS:
        index_id = os.environ.get(KENDRA_INDEX_VARIABLE, "").strip()
        if not index_id:
            raise MissingConfiguration(
                f"profile {AWS!r} needs {KENDRA_INDEX_VARIABLE}: without a knowledge index the "
                "analysis would quietly stop being grounded in the internal norm."
            )
        guardrail_id = os.environ.get(GUARDRAIL_VARIABLE, "").strip()
        if not guardrail_id:
            raise MissingConfiguration(
                f"profile {AWS!r} needs {GUARDRAIL_VARIABLE}: reading health documents with no "
                "policy in front of the model is worse than being unavailable."
            )
        config["guardrail"] = {**config["guardrail"], "identifier": guardrail_id}
        retrieval = json.loads(KENDRA_CONFIG.read_text(encoding="utf-8"))["retrieve"]
        return Dependencies(
            ocr=TextractOcr(),
            llm=BedrockLlm(config, catalog),
            knowledge=KendraRetriever(index_id, retrieval.get("AttributeFilter")),
            metrics=build_metrics(name),
            clock=build_clock(name),
            catalog=catalog,
            prompt_version=config["prompt_version"],
            model_id=config["model_id"],
            ocr_engine=TEXTRACT_ENGINE,
        )

    return Dependencies(
        ocr=StubOcr(),
        llm=StubLlm(),
        knowledge=FakeKnowledgeRetriever(),
        metrics=build_metrics(name),
        clock=build_clock(name),
        catalog=catalog,
        prompt_version=config["prompt_version"],
        model_id=STUB_ENGINE,
        ocr_engine=STUB_ENGINE,
    )


def build_analyzer(
    profile: str | None = None,
    dependencies: Dependencies | None = None,
) -> Callable[[bytes], Analysis]:
    dependencies = dependencies or build_dependencies(profile)
    pipeline = AnalyzeDocument(
        dependencies.ocr,
        dependencies.llm,
        dependencies.knowledge,
        dependencies.metrics,
        dependencies.clock,
        dependencies.catalog,
        prompt_version=dependencies.prompt_version,
        model_id=dependencies.model_id,
        ocr_engine=dependencies.ocr_engine,
    )

    def analyze(content: bytes) -> Analysis:
        if len(content) > MAX_FILE_BYTES:
            raise ServiceError(
                ErrorCode.INVALID_INPUT, "file exceeds the limit", limit_bytes=MAX_FILE_BYTES
            )
        if not content:
            raise ServiceError(ErrorCode.INVALID_INPUT, "the file is empty")
        try:
            document = normalize(content)
            if document.route is ReadingRoute.REJECT:
                raise ServiceError(
                    ErrorCode.DOCUMENT_QUALITY_TOO_LOW,
                    "the document is below the minimum reading quality",
                )
            pages = pages_of(content)
            direct_text = read_pdf(content)[1] if document.has_reliable_text_layer else []
        except ServiceError:
            raise
        except Exception:
            raise ServiceError(
                ErrorCode.INVALID_INPUT, "unsupported or malformed document"
            ) from None
        return pipeline(content, document, pages, direct_text)

    return analyze
