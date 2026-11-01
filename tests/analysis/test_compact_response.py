import copy
import json
from typing import Any

import pytest

from docweave.analysis.compact_response import (
    compact_response_schema,
    expand_compact_response,
)
from docweave.analysis.validation import (
    ClassificationValidationError,
    decode_classification_v1,
)
from docweave.extraction import ExtractedPage

PAGES = (ExtractedPage(0, "1", "INVOICE INV-7"), ExtractedPage(1, "2", "Supplier ACME"))


def canonical() -> dict[str, Any]:
    return {
        "contract_version": "classification.v1",
        "taxonomy_version": "docweave_mvp_v0_1",
        "proposed_class": "invoice",
        "document_language": "en",
        "rationale": "The invoice heading is explicit.",
        "rationale_evidence_ids": ["ev_1"],
        "evidence": [
            {
                "evidence_id": "ev_1",
                "segment_id": "p0_s1",
                "supports": ["classification"],
            },
            {"evidence_id": "ev_2", "segment_id": "p1_s1", "supports": ["metadata"]},
        ],
        "candidate_metadata": [
            {"name": "supplier", "value": "ACME", "evidence_ids": ["ev_2"]}
        ],
        "alternative_classes": [
            {
                "class_code": "contract",
                "reason": "Possible agreement.",
                "evidence_ids": ["ev_2"],
            }
        ],
        "contradictions": [
            {"description": "The amount is disputed.", "evidence_ids": ["ev_1", "ev_2"]}
        ],
        "missing_expected_evidence": ["tax amount"],
        "raw_signals": {
            "classification_strength": "strong",
            "evidence_coverage": "moderate",
            "ambiguity": "weak",
        },
        "abstention_reason": None,
    }


def wire() -> dict[str, Any]:
    payload = copy.deepcopy(canonical())
    payload.update(
        evidence=[
            ["ev_1", "p0_s1", ["classification"]],
            ["ev_2", "p1_s1", ["metadata"]],
        ],
        candidate_metadata=[["supplier", "ACME", ["ev_2"]]],
        alternative_classes=[["contract", "Possible agreement.", ["ev_2"]]],
        contradictions=[["The amount is disputed.", ["ev_1", "ev_2"]]],
    )
    return payload


def test_every_model_authored_value_survives_exactly_without_defaults_or_repairs() -> (
    None
):
    expanded = json.loads(expand_compact_response(json.dumps(wire())))
    assert expanded == canonical()
    proposal = decode_classification_v1(json.dumps(expanded), extracted_pages=PAGES)
    assert proposal.evidence[1].quote == "Supplier ACME"
    assert proposal.candidate_metadata[0].evidence_ids == ("ev_2",)
    assert proposal.alternative_classes[0].reason == "Possible agreement."
    assert proposal.contradictions[0].evidence_ids == ("ev_1", "ev_2")


@pytest.mark.parametrize("reference", [True, False, 0, -1, 9, "1", 1.0, None, "ev_3"])
def test_invalid_references_are_not_coerced_or_replaced(reference: Any) -> None:
    payload = wire()
    payload["rationale_evidence_ids"] = [reference]
    with pytest.raises(ClassificationValidationError):
        decode_classification_v1(
            expand_compact_response(json.dumps(payload)), extracted_pages=PAGES
        )


@pytest.mark.parametrize("references", [["ev_1", "ev_1"], []])
def test_duplicate_or_missing_references_remain_invalid(references: list[str]) -> None:
    payload = wire()
    payload["rationale_evidence_ids"] = references
    with pytest.raises(ClassificationValidationError):
        decode_classification_v1(
            expand_compact_response(json.dumps(payload)), extracted_pages=PAGES
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("candidate_metadata", [["supplier", "ACME"]]),
        ("evidence", [["ev_1", "p0_s1"]]),
        ("alternative_classes", [["contract"]]),
        ("contradictions", [["conflict"]]),
    ],
)
def test_malformed_rows_fail_closed(field: str, value: Any) -> None:
    payload = wire()
    payload[field] = value
    with pytest.raises(ClassificationValidationError):
        expand_compact_response(json.dumps(payload))


@pytest.mark.parametrize("text", ['{"c":"invoice","c":"contract"}', "NaN", "{"])
def test_ambiguous_or_invalid_json_is_rejected(text: str) -> None:
    with pytest.raises(ClassificationValidationError):
        expand_compact_response(text)


def test_missing_versions_are_not_supplied_by_the_codec() -> None:
    payload = wire()
    del payload["contract_version"]
    with pytest.raises(ClassificationValidationError):
        decode_classification_v1(
            expand_compact_response(json.dumps(payload)), extracted_pages=PAGES
        )


def test_extra_properties_are_not_silently_discarded() -> None:
    payload = wire()
    payload["unexpected"] = "must remain visible to validation"
    with pytest.raises(ClassificationValidationError):
        decode_classification_v1(
            expand_compact_response(json.dumps(payload)), extracted_pages=PAGES
        )


def test_abstention_still_comes_from_the_model() -> None:
    payload = wire()
    payload.update(
        proposed_class="unclassified",
        abstention_reason="The source is ambiguous.",
        alternative_classes=[],
        contradictions=[],
    )
    result = decode_classification_v1(
        expand_compact_response(json.dumps(payload)), extracted_pages=PAGES
    )
    assert result.proposed_class.value == "unclassified"
    assert result.abstention_reason == "The source is ambiguous."


def test_wire_schema_requires_every_canonical_field_and_same_evidence_cap() -> None:
    schema = compact_response_schema()
    assert set(schema["required"]) == set(canonical())
    assert schema["additionalProperties"] is False
    assert schema["properties"]["evidence"]["maxItems"] == 8
    assert schema["properties"]["candidate_metadata"]["maxItems"] == 6
