"""Lossless positional-row transport; every model-authored value is preserved."""

import json
from typing import Any

from docweave.analysis.schema import classification_v1_json_schema
from docweave.analysis.validation import (
    MAXIMUM_RESPONSE_BYTES,
    ClassificationValidationCode,
    ClassificationValidationError,
)

WIRE_VERSION = "classification.rows.v2"
_ROWS = {
    "evidence": ("evidence_id", "segment_id", "supports"),
    "candidate_metadata": ("name", "value", "evidence_ids"),
    "alternative_classes": ("class_code", "reason", "evidence_ids"),
    "contradictions": ("description", "evidence_ids"),
}

WIRE_INSTRUCTION = """Return minified JSON, without indentation or extra whitespace.
Keep the standard field names. Only these arrays use positional rows:
evidence: [evidence_id,segment_id,[supports]];
candidate_metadata: [name,value,[evidence_ids]];
alternative_classes: [class_code,reason,[evidence_ids]];
contradictions: [description,[evidence_ids]].
Use ev_N evidence identifiers exactly as usual. All references must be unique.
Cite only the minimal evidence actually supporting each field, not unrelated rows.
Alternative classes must differ from the primary class. Report contradictions
only for conflicting factual claims supported by document evidence."""


def compact_response_schema() -> dict[str, Any]:
    """Replace repeated row-property names with fixed-position arrays."""
    schema = classification_v1_json_schema()
    properties = schema["properties"]
    properties["evidence"]["maxItems"] = 8
    metadata = properties["candidate_metadata"]["items"]["properties"]
    metadata["name"]["pattern"] = "^[a-z][a-z0-9_]{0,63}$"
    metadata["evidence_ids"]["minItems"] = 1
    _compact_evidence_enums(schema)
    for field, names in _ROWS.items():
        row = properties[field]["items"]["properties"]
        properties[field]["items"] = {
            "type": "array",
            "prefixItems": [row[name] for name in names],
            "minItems": len(names),
            "maxItems": len(names),
        }
    return schema


def _compact_evidence_enums(node: Any) -> None:
    if isinstance(node, dict):
        values = node.get("enum")
        if isinstance(values, list) and values and values[0] == "ev_1":
            node["enum"] = [f"ev_{index}" for index in range(1, 9)]
        for value in node.values():
            _compact_evidence_enums(value)
    elif isinstance(node, list):
        for value in node:
            _compact_evidence_enums(value)


def expand_compact_response(text: str) -> str:
    """Restore object keys, without selecting, correcting, or supplying any value."""
    if len(text.encode("utf-8")) > MAXIMUM_RESPONSE_BYTES:
        raise ClassificationValidationError(
            ClassificationValidationCode.RESPONSE_TOO_LARGE
        )
    try:
        payload = json.loads(
            text, object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
    except ClassificationValidationError:
        raise
    except (json.JSONDecodeError, ValueError) as error:
        raise ClassificationValidationError(
            ClassificationValidationCode.INVALID_JSON
        ) from error
    if not isinstance(payload, dict):
        raise ClassificationValidationError(ClassificationValidationCode.SCHEMA_INVALID)
    for field, names in _ROWS.items():
        rows = payload.get(field)
        if not isinstance(rows, list):
            raise ClassificationValidationError(
                ClassificationValidationCode.SCHEMA_INVALID
            )
        expanded = []
        for row in rows:
            if not isinstance(row, list) or len(row) != len(names):
                raise ClassificationValidationError(
                    ClassificationValidationCode.SCHEMA_INVALID
                )
            expanded.append(dict(zip(names, row, strict=True)))
        payload[field] = expanded
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClassificationValidationError(
                ClassificationValidationCode.DUPLICATE_JSON_KEY
            )
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ClassificationValidationError(ClassificationValidationCode.SCHEMA_INVALID)
