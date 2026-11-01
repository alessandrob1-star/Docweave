import json
from typing import Any

import pytest

from docweave.analysis import (
    LlmClassificationGateway,
    LlmGatewayConfig,
    LlmGatewayError,
)
from docweave.analysis.compact_response import WIRE_VERSION
from docweave.analysis.llm_gateway import OllamaClient
from docweave.extraction import ExtractedPage

PAGES = (
    ExtractedPage(
        page_index=0,
        page_label="1",
        text="INVOICE INV-17 Total EUR 42.00",
    ),
)


def _proposal_json(*, segment_id: str = "p0_s1") -> str:
    return json.dumps(
        {
            "contract_version": "classification.v1",
            "taxonomy_version": "docweave_mvp_v0_1",
            "proposed_class": "invoice",
            "document_language": "en",
            "rationale": "The document identifies itself as an invoice.",
            "rationale_evidence_ids": ["ev_1"],
            "evidence": [
                {
                    "evidence_id": "ev_1",
                    "segment_id": segment_id,
                    "supports": ["classification"],
                }
            ],
            "candidate_metadata": [],
            "alternative_classes": [],
            "contradictions": [],
            "missing_expected_evidence": ["supplier"],
            "raw_signals": {
                "classification_strength": "strong",
                "evidence_coverage": "moderate",
                "ambiguity": "weak",
            },
            "abstention_reason": None,
        }
    )


class FakeClient:
    def __init__(self, content: str, *, reason: str = "stop") -> None:
        self.content = content
        self.reason = reason
        self.calls = 0

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return {
            "model": "qwen2.5:14b-instruct",
            "done": True,
            "done_reason": self.reason,
            "message": {"role": "assistant", "content": self.content},
            "prompt_eval_count": 31,
            "eval_count": 17,
            "total_duration": 1000000,
        }


def test_native_response_is_validated_and_usage_is_observed() -> None:
    client = FakeClient(_proposal_json())
    result = LlmClassificationGateway(client).classify(PAGES)
    assert result.proposal.proposed_class.value == "invoice"
    assert result.provenance.usage.total_tokens == 48
    assert result.provenance.model_id == "qwen2.5:14b-instruct"
    assert client.calls == 1


def test_fabricated_evidence_is_rejected_after_bounded_retry() -> None:
    client = FakeClient(_proposal_json(segment_id="fabricated"))
    with pytest.raises(LlmGatewayError):
        LlmClassificationGateway(client).classify(PAGES)
    assert client.calls <= 3


def test_truncated_output_is_not_success() -> None:
    with pytest.raises(LlmGatewayError):
        LlmClassificationGateway(
            FakeClient(_proposal_json(), reason="length")
        ).classify(PAGES)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://192.168.1.2:11434",
        "http://user:pass@localhost:11434",
        "http://localhost:11434/remote",
    ],
)
def test_remote_or_ambiguous_model_addresses_are_rejected(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("DOCWEAVE_OLLAMA_URL", url)
    with pytest.raises(ValueError, match="local loopback"):
        OllamaClient(LlmGatewayConfig())


def test_model_identity_mismatch_is_rejected() -> None:
    class WrongModel(FakeClient):
        def converse(self, **kwargs: Any) -> dict[str, Any]:
            response = super().converse(**kwargs)
            response["model"] = "unexpected-model"
            return response

    with pytest.raises(LlmGatewayError):
        LlmClassificationGateway(WrongModel(_proposal_json())).classify(PAGES)


def test_oversized_prompt_is_rejected_before_transport() -> None:
    class NoTransport(OllamaClient):
        def request(
            self, endpoint: str, payload: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            raise AssertionError("Oversized evidence must not reach the transport.")

    with pytest.raises(LlmGatewayError):
        NoTransport(LlmGatewayConfig()).converse(
            system=[{"text": "x" * 32_768}], messages=[]
        )


def test_invalid_wire_row_is_retried_without_repairing_model_output() -> None:
    class RowClient(FakeClient):
        def converse(self, **kwargs: Any) -> dict[str, Any]:
            response = super().converse(**kwargs)
            payload = json.loads(_proposal_json())
            rows: list[list[Any]] = (
                [["ev_1", "p0_s1"]]
                if self.calls == 1
                else [["ev_1", "p0_s1", ["classification"]]]
            )
            payload["evidence"] = rows
            response["message"]["content"] = json.dumps(payload)
            response["_docweave_response_format"] = WIRE_VERSION
            return response

    client = RowClient(_proposal_json())
    result = LlmClassificationGateway(client).classify(PAGES)
    assert client.calls == 2
    assert result.provenance.retry_attempts == 1
    assert result.proposal.proposed_class.value == "invoice"


def test_unknown_wire_format_is_rejected_without_a_format_fallback() -> None:
    class UnknownFormat(FakeClient):
        def converse(self, **kwargs: Any) -> dict[str, Any]:
            response = super().converse(**kwargs)
            response["_docweave_response_format"] = "unknown"
            return response

    with pytest.raises(LlmGatewayError):
        LlmClassificationGateway(UnknownFormat(_proposal_json())).classify(PAGES)
