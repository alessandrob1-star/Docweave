"""Real local Ollama inference with schema and evidence validation."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from time import monotonic
from typing import Any, Protocol, cast
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from docweave.analysis.contracts import (
    CLASSIFICATION_CONTRACT_VERSION,
    ClassificationProposal,
)
from docweave.analysis.ollama_request import (
    LocalContextLimitError,
    build_local_request,
)
from docweave.analysis.request import classification_v1_converse_fields
from docweave.analysis.taxonomy import TAXONOMY_VERSION
from docweave.analysis.validation import (
    ClassificationValidationCode,
    ClassificationValidationError,
    decode_classification_v1,
)
from docweave.extraction import ExtractedPage

APPROVED_LLM_REGION = "local"
APPROVED_LLM_MODEL_ID = "qwen2.5:14b-instruct"
LLM_CONNECT_TIMEOUT_SECONDS = 5
LLM_READ_TIMEOUT_SECONDS = 600
LLM_TOTAL_MAX_ATTEMPTS = 5
_MAXIMUM_TRANSPORT_BYTES = 2_000_000
_MAXIMUM_REQUEST_ID_CHARACTERS = 128
_MAXIMUM_VALIDATION_RETRY_ATTEMPTS = 2
_VALIDATION_RETRY_CODES = {
    ClassificationValidationCode.ABSTENTION_INVALID,
    ClassificationValidationCode.ALTERNATIVE_INVALID,
    ClassificationValidationCode.EVIDENCE_REFERENCE_INVALID,
    ClassificationValidationCode.METADATA_INVALID,
    ClassificationValidationCode.SCHEMA_INVALID,
}


class ConverseClient(Protocol):
    """Narrow Llm client surface required by the gateway."""

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        """Invoke the Llm Runtime Converse operation."""


class SessionLike(Protocol):
    """Optional local client injection for tests."""

    def client(self, service_name: str, **kwargs: Any) -> ConverseClient:
        """Create one service client."""


@dataclass(frozen=True, slots=True)
class LlmGatewayConfig:
    """Approved immutable runtime settings for the primary classifier."""

    region_name: str = APPROVED_LLM_REGION
    model_id: str = APPROVED_LLM_MODEL_ID
    connect_timeout_seconds: int = LLM_CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: int = LLM_READ_TIMEOUT_SECONDS
    total_max_attempts: int = LLM_TOTAL_MAX_ATTEMPTS

    def __post_init__(self) -> None:
        if self.region_name != APPROVED_LLM_REGION:
            raise ValueError("Unapproved Llm region.")
        if self.model_id != APPROVED_LLM_MODEL_ID:
            raise ValueError("Unapproved Llm model.")
        if (
            self.connect_timeout_seconds <= 0
            or self.read_timeout_seconds <= 0
            or self.total_max_attempts <= 0
        ):
            raise ValueError("Llm runtime limits must be positive.")


@dataclass(frozen=True, slots=True)
class LlmUsage:
    """Token counts observed in the actual Converse response."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    cache_read_input_tokens: int = 0
    cache_write_input_tokens: int = 0


@dataclass(frozen=True, slots=True)
class LlmTokenPricing:
    """Externally supplied on-demand prices in US dollars per million tokens."""

    input_per_million_usd: Decimal
    output_per_million_usd: Decimal

    def __post_init__(self) -> None:
        if self.input_per_million_usd < 0 or self.output_per_million_usd < 0:
            raise ValueError("Llm token prices cannot be negative.")

    def estimate_usd(self, usage: LlmUsage) -> Decimal:
        """Estimate uncached token cost without claiming billing authority."""
        million = Decimal(1_000_000)
        return (
            Decimal(usage.input_tokens) * self.input_per_million_usd
            + Decimal(usage.output_tokens) * self.output_per_million_usd
        ) / million


@dataclass(frozen=True, slots=True)
class LlmRunProvenance:
    """Observed runtime provenance, never copied from model-authored JSON."""

    region_name: str
    model_id: str
    contract_version: str
    taxonomy_version: str
    stop_reason: str
    usage: LlmUsage
    service_latency_ms: int
    observed_duration_ms: int
    request_id: str | None
    retry_attempts: int
    estimated_cost_usd: Decimal | None


@dataclass(frozen=True, slots=True)
class LlmClassificationRun:
    """One validated proposal and its observed Llm provenance."""

    proposal: ClassificationProposal
    provenance: LlmRunProvenance


class LlmGatewayErrorCode(StrEnum):
    """Content-free terminal category for a failed gateway attempt."""

    ACCESS_DENIED = "access_denied"
    AUTHENTICATION_FAILED = "authentication_failed"
    CONTENT_FILTERED = "content_filtered"
    GUARDRAIL_INTERVENED = "guardrail_intervened"
    INVALID_MODEL_OUTPUT = "invalid_model_output"
    MODEL_TIMEOUT = "model_timeout"
    REQUEST_INVALID = "request_invalid"
    RESPONSE_INVALID = "response_invalid"
    RESPONSE_TRUNCATED = "response_truncated"
    SERVICE_UNAVAILABLE = "service_unavailable"
    THROTTLED = "throttled"
    TRANSPORT_FAILED = "transport_failed"
    UNEXPECTED_LOCAL_ERROR = "unexpected_local_error"
    UNEXPECTED_STOP_REASON = "unexpected_stop_reason"


class LlmGatewayError(RuntimeError):
    """Sanitized gateway failure that retains no document or local message."""

    def __init__(
        self,
        code: LlmGatewayErrorCode,
        *,
        validation_code: ClassificationValidationCode | None = None,
        service_error_code: str | None = None,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.validation_code = validation_code
        self.service_error_code = service_error_code


class NoRedirect(HTTPRedirectHandler):
    """Never follow redirects from the local model service."""

    def redirect_request(  # noqa: PLR0913 - standard library override
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


class OllamaClient:
    """Loopback-only JSON transport; no proxy, login, or remote model fallback."""

    def __init__(self, config: LlmGatewayConfig) -> None:
        self.config = config
        self.base_url = os.environ.get(
            "DOCWEAVE_OLLAMA_URL", "http://127.0.0.1:11434"
        ).rstrip("/")
        parsed = urlparse(self.base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Ollama must use a local loopback HTTP address.")
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(
        self, endpoint: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if endpoint not in {"/api/chat", "/api/tags"}:
            raise ValueError("Unsupported local model endpoint.")
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(  # noqa: S310 - validated loopback HTTP only
            self.base_url + endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with self.opener.open(
            request,
            timeout=3 if endpoint == "/api/tags" else self.config.read_timeout_seconds,
        ) as response:
            raw = response.read(_MAXIMUM_TRANSPORT_BYTES + 1)
        if len(raw) > _MAXIMUM_TRANSPORT_BYTES:
            raise ValueError("Ollama response exceeded the size limit.")
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get("error"):
            raise ValueError("Ollama returned an invalid response.")
        return result

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        try:
            payload = build_local_request(self.config.model_id, kwargs)
        except LocalContextLimitError as error:
            raise LlmGatewayError(LlmGatewayErrorCode.REQUEST_INVALID) from error
        return self.request("/api/chat", payload)


def model_available() -> bool:
    """Check actual installed model names without triggering a download."""
    client = OllamaClient(LlmGatewayConfig())
    try:
        payload = client.request("/api/tags")
        return any(
            item.get("name") == client.config.model_id
            for item in payload.get("models", [])
        )
    except (OSError, ValueError, URLError):
        return False


def create_llm_runtime_client(
    *, config: LlmGatewayConfig | None = None, session: SessionLike | None = None
) -> ConverseClient:
    """Create the local Ollama transport without making a request."""
    if session is not None:
        raise ValueError(
            "Use direct local client injection instead of service sessions."
        )
    return OllamaClient(config or LlmGatewayConfig())


class LlmClassificationGateway:
    """Invoke Converse and validate one classification proposal."""

    def __init__(
        self,
        client: ConverseClient,
        *,
        config: LlmGatewayConfig | None = None,
        pricing: LlmTokenPricing | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._client = client
        self._config = config or LlmGatewayConfig()
        self._pricing = pricing
        self._clock = clock

    def classify(
        self,
        pages: tuple[ExtractedPage, ...],
    ) -> LlmClassificationRun:
        """Perform one bounded real model call through the injected client."""
        request = classification_v1_converse_fields(pages)
        responses: list[dict[str, Any]] = []
        validation_retry_attempts = 0
        started_at = self._clock()
        while True:
            response = self._converse(request)
            responses.append(response)

            stop_reason = _required_string(response, "done_reason")
            _validate_stop_reason(stop_reason)
            response_text = _response_text(response)
            try:
                proposal = decode_classification_v1(
                    response_text,
                    extracted_pages=pages,
                )
                break
            except ClassificationValidationError as error:
                if (
                    validation_retry_attempts < _MAXIMUM_VALIDATION_RETRY_ATTEMPTS
                    and error.code in _VALIDATION_RETRY_CODES
                ):
                    validation_retry_attempts += 1
                    request = _with_validation_retry_instruction(
                        request,
                        validation_code=error.code,
                    )
                    continue
                raise LlmGatewayError(
                    LlmGatewayErrorCode.INVALID_MODEL_OUTPUT,
                    validation_code=error.code,
                ) from error
        observed_duration_ms = max(
            0,
            round((self._clock() - started_at) * 1_000),
        )

        usage = _aggregate_usage(
            _decode_usage(
                {
                    "inputTokens": item.get("prompt_eval_count"),
                    "outputTokens": item.get("eval_count"),
                    "totalTokens": item.get("prompt_eval_count", 0)
                    + item.get("eval_count", 0),
                }
            )
            for item in responses
        )
        service_latency_ms = sum(
            _service_latency({"latencyMs": item.get("total_duration", 0) // 1_000_000})
            for item in responses
        )
        request_id, retry_attempts = _response_metadata({})
        retry_attempts += validation_retry_attempts + sum(
            _response_metadata({})[1] for item in responses[:-1]
        )
        estimated_cost = (
            self._pricing.estimate_usd(usage) if self._pricing is not None else None
        )
        return LlmClassificationRun(
            proposal=proposal,
            provenance=LlmRunProvenance(
                region_name=self._config.region_name,
                model_id=self._config.model_id,
                contract_version=CLASSIFICATION_CONTRACT_VERSION,
                taxonomy_version=TAXONOMY_VERSION,
                stop_reason=stop_reason,
                usage=usage,
                service_latency_ms=service_latency_ms,
                observed_duration_ms=observed_duration_ms,
                request_id=request_id,
                retry_attempts=retry_attempts,
                estimated_cost_usd=estimated_cost,
            ),
        )

    def _converse(self, request: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.converse(modelId=self._config.model_id, **request)
            if response.get("model") != self._config.model_id:
                raise LlmGatewayError(LlmGatewayErrorCode.RESPONSE_INVALID)
            return response
        except (TimeoutError, URLError, OSError) as error:
            raise LlmGatewayError(LlmGatewayErrorCode.TRANSPORT_FAILED) from error
        except (ValueError, KeyError, TypeError) as error:
            raise LlmGatewayError(LlmGatewayErrorCode.RESPONSE_INVALID) from error


def _with_validation_retry_instruction(
    request: dict[str, Any],
    *,
    validation_code: ClassificationValidationCode,
) -> dict[str, Any]:
    retry_request = dict(request)
    retry_request["system"] = [
        *request["system"],
        {
            "text": (
                "The previous classification JSON failed DocWeave "
                f"validation with code {validation_code.value}. Re-read the "
                "same untrusted document data and approved taxonomy, then emit "
                "a fresh classification.v1 JSON object. Do not reuse invalid "
                "evidence references. Every evidence_id used in rationale, "
                "metadata, alternatives, or contradictions must exist in the "
                "evidence array you emit. Use a compact evidence array and "
                "prefer only ev_1 through ev_8 for rationale_evidence_ids. If "
                "proposed_class is not unclassified, abstention_reason must be "
                "null."
            )
        },
    ]
    return retry_request


def _aggregate_usage(usages: Any) -> LlmUsage:
    items = tuple(usages)
    if not items:
        raise LlmGatewayError(LlmGatewayErrorCode.RESPONSE_INVALID)
    return LlmUsage(
        input_tokens=sum(item.input_tokens for item in items),
        output_tokens=sum(item.output_tokens for item in items),
        total_tokens=sum(item.total_tokens for item in items),
        cache_read_input_tokens=sum(item.cache_read_input_tokens for item in items),
        cache_write_input_tokens=sum(item.cache_write_input_tokens for item in items),
    )


def _validate_stop_reason(stop_reason: str) -> None:
    error_codes = {
        "length": LlmGatewayErrorCode.RESPONSE_TRUNCATED,
        "max_tokens": LlmGatewayErrorCode.RESPONSE_TRUNCATED,
        "guardrail_intervened": LlmGatewayErrorCode.GUARDRAIL_INTERVENED,
        "content_filtered": LlmGatewayErrorCode.CONTENT_FILTERED,
        "model_context_window_exceeded": LlmGatewayErrorCode.RESPONSE_TRUNCATED,
        "malformed_model_output": LlmGatewayErrorCode.INVALID_MODEL_OUTPUT,
    }
    if stop_reason == "stop":
        return
    raise LlmGatewayError(
        error_codes.get(
            stop_reason,
            LlmGatewayErrorCode.UNEXPECTED_STOP_REASON,
        )
    )


def _response_text(response: dict[str, Any]) -> str:
    message = response.get("message")
    if (
        response.get("done") is not True
        or not isinstance(message, dict)
        or message.get("role") != "assistant"
        or not isinstance(message.get("content"), str)
    ):
        raise LlmGatewayError(LlmGatewayErrorCode.RESPONSE_INVALID)
    return cast(str, message["content"])


def _decode_usage(value: Any) -> LlmUsage:
    if not isinstance(value, dict):
        raise LlmGatewayError(LlmGatewayErrorCode.RESPONSE_INVALID)
    usage = LlmUsage(
        input_tokens=_nonnegative_int(value, "inputTokens"),
        output_tokens=_nonnegative_int(value, "outputTokens"),
        total_tokens=_nonnegative_int(value, "totalTokens"),
        cache_read_input_tokens=_optional_nonnegative_int(
            value,
            "cacheReadInputTokens",
        ),
        cache_write_input_tokens=_optional_nonnegative_int(
            value,
            "cacheWriteInputTokens",
        ),
    )
    if usage.total_tokens < usage.input_tokens + usage.output_tokens:
        raise LlmGatewayError(LlmGatewayErrorCode.RESPONSE_INVALID)
    return usage


def _service_latency(value: Any) -> int:
    if not isinstance(value, dict):
        raise LlmGatewayError(LlmGatewayErrorCode.RESPONSE_INVALID)
    return _nonnegative_int(value, "latencyMs")


def _response_metadata(value: Any) -> tuple[str | None, int]:
    if not isinstance(value, dict):
        raise LlmGatewayError(LlmGatewayErrorCode.RESPONSE_INVALID)
    request_id = value.get("RequestId")
    if request_id is not None and (
        not isinstance(request_id, str)
        or len(request_id) > _MAXIMUM_REQUEST_ID_CHARACTERS
    ):
        raise LlmGatewayError(LlmGatewayErrorCode.RESPONSE_INVALID)
    retry_attempts = _optional_nonnegative_int(value, "RetryAttempts")
    return request_id, retry_attempts


def _required_string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise LlmGatewayError(LlmGatewayErrorCode.RESPONSE_INVALID)
    return item


def _nonnegative_int(value: dict[str, Any], key: str) -> int:
    item = value.get(key)
    if type(item) is not int or item < 0:
        raise LlmGatewayError(LlmGatewayErrorCode.RESPONSE_INVALID)
    return item


def _optional_nonnegative_int(value: dict[str, Any], key: str) -> int:
    item = value.get(key, 0)
    if type(item) is not int or item < 0:
        raise LlmGatewayError(LlmGatewayErrorCode.RESPONSE_INVALID)
    return item
