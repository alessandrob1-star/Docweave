"""Measure real local inference without writing application memory or moving PDFs."""

import argparse
import json
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.request import Request

from docweave.analysis.llm_gateway import (
    LlmClassificationGateway,
    LlmGatewayConfig,
    OllamaClient,
)
from docweave.extraction import PdfExtractionRequest, extract_pdf_text


class RecordingClient(OllamaClient):
    def __init__(self) -> None:
        super().__init__(LlmGatewayConfig())
        self.calls: list[dict[str, Any]] = []

    def request(
        self, endpoint: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        started = perf_counter()
        response = super().request(endpoint, payload)
        if endpoint == "/api/chat":
            self.calls.append(
                {
                    "wall_seconds": round(perf_counter() - started, 3),
                    "input_tokens": response.get("prompt_eval_count"),
                    "output_tokens": response.get("eval_count"),
                    "load_duration_ns": response.get("load_duration"),
                    "prompt_eval_duration_ns": response.get("prompt_eval_duration"),
                    "eval_duration_ns": response.get("eval_duration"),
                    "done_reason": response.get("done_reason"),
                }
            )
        return response

    def model_memory(self) -> dict[str, Any] | None:
        request = Request(self.base_url + "/api/ps")  # noqa: S310 - validated loopback
        with self.opener.open(request, timeout=5) as response:
            payload = json.load(response)
        for model in payload.get("models", []):
            if model.get("name") == self.config.model_id:
                return {
                    "bytes": model.get("size"),
                    "gpu_bytes": model.get("size_vram"),
                    "context": model.get("context_length"),
                }
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorized-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("pdfs", type=Path, nargs="+")
    args = parser.parse_args()
    root = args.authorized_root.resolve(strict=True)
    # Reserve the report path before inference; never overwrite previous evidence.
    with args.output.open("x", encoding="utf-8") as report:
        records = []
        for path in args.pdfs:
            client = RecordingClient()
            record: dict[str, Any] = {
                "file": path.name,
                "model": client.config.model_id,
            }
            try:
                started = perf_counter()
                extraction = extract_pdf_text(PdfExtractionRequest(path, root))
                record["extraction_seconds"] = round(perf_counter() - started, 3)
                record["source_sha256"] = extraction.source_sha256
                run = LlmClassificationGateway(client).classify(extraction.pages)
                record.update(
                    validated=True,
                    predicted_class=run.proposal.proposed_class.value,
                    evidence_count=len(run.proposal.evidence),
                    inference_seconds=run.provenance.observed_duration_ms / 1000,
                    retry_attempts=run.provenance.retry_attempts,
                )
            except Exception as error:
                record.update(validated=False, error=type(error).__name__)
                code = getattr(error, "validation_code", None)
                record["validation_code"] = getattr(code, "value", None)
            record["requests"] = client.calls
            record["memory"] = client.model_memory()
            records.append(record)
            print(json.dumps(record), flush=True)
        json.dump(records, report, indent=2)
    return 0 if all(row["validated"] for row in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
