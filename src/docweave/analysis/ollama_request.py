"""Compact, evidence-preserving requests for the local model."""

import json
from typing import Any

from docweave.analysis.compact_response import WIRE_INSTRUCTION, compact_response_schema
from docweave.analysis.taxonomy import TAXONOMY_DEFINITIONS

LOCAL_CONTEXT_TOKENS = 8_192
LOCAL_OUTPUT_TOKENS = 2_048
LOCAL_TEMPLATE_RESERVE = 512
LOCAL_MAXIMUM_EVIDENCE = 8
LOCAL_PROMPT_VERSION = "classification.ollama.rows.v2"
_CONTEXT_TIERS = (8_192, 12_288, 16_384, 24_576, 32_768)


class LocalContextLimitError(ValueError):
    """Refuse a prompt that cannot fit without dropping evidence."""


def build_local_request(model_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """Preserve every evidence segment while removing repeated wire-field names."""
    definitions = "\n".join(
        f"{item.class_code.value}: {item.definition}" for item in TAXONOMY_DEFINITIONS
    )
    system = "\n".join(item["text"] for item in request["system"])
    messages = [
        {
            "role": "system",
            "content": system + "\nClasses:\n" + definitions + "\n" + WIRE_INSTRUCTION,
        }
    ]
    for message in request["messages"]:
        payload = json.loads(message["content"][0]["text"])
        segments = payload["evidence_segments"]
        compact = {
            "document_data_trust": "untrusted",
            "columns": ["segment_id", "page_index", "text"],
            "page_labels": {
                str(segment["page_index"]): segment["page_label"]
                for segment in segments
            },
            "segments": [
                [segment["segment_id"], segment["page_index"], segment["text"]]
                for segment in segments
            ],
        }
        messages.append(
            {
                "role": message["role"],
                "content": json.dumps(
                    compact, ensure_ascii=False, separators=(",", ":")
                ),
            }
        )
    schema = compact_response_schema()
    # Qwen's byte-level tokenizer needs at most one token per UTF-8 byte.
    # Reserve output and chat-template space without ever slicing document text.
    required = (
        sum(len(message["content"].encode("utf-8")) for message in messages)
        + LOCAL_OUTPUT_TOKENS
        + LOCAL_TEMPLATE_RESERVE
    )
    context = next((size for size in _CONTEXT_TIERS if size >= required), None)
    if context is None:
        raise LocalContextLimitError("Document exceeds the local context budget.")
    return {
        "model": model_id,
        "messages": messages,
        "stream": False,
        "format": schema,
        "options": {
            "temperature": 0,
            "num_predict": LOCAL_OUTPUT_TOKENS,
            "num_ctx": context,
        },
    }
