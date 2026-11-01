# Lossless response-row tuning - 2026-11-01

This follow-up keeps Qwen 14B, its quantization, full document input, existing
classification fields, evidence validation, metadata limit, and desktop layout.
The model still authors every classification value and evidence reference.

## Warm measurements on the same selected PDFs

| PDF | Previous seconds | New seconds | Previous output tokens | New output tokens |
| --- | ---: | ---: | ---: | ---: |
| `attachment_07.pdf` | 25.166 | 9.784 | 782 | 270 |
| `attachment_081.pdf` | 24.328 | 14.288 | 732 | 398 |
| `attachment_094.pdf` | 24.182 | 12.774 | 719 | 350 |
| `attachment_162.pdf` | 24.956 | 11.660 | 750 | 320 |
| `attachment_07.pdf`, repeat | 25.560 | 9.507 | 782 | 270 |

All five requests passed the existing classification decoder without a retry.
Ollama reported the same 8,192-token allocation, all model memory on the GPU.
These are five warm requests on four selected synthetic PDFs, not a general
accuracy or worst-case performance benchmark. The earlier anchor report and
the v1 tuning probes supply the comparison measurements.

## What changed

Previously the model generated repeated property names for every evidence and
metadata item. The native response now uses positional rows in four arrays:

- `evidence`: `[evidence_id, segment_id, supports]`;
- `candidate_metadata`: `[name, value, evidence_ids]`;
- `alternative_classes`: `[class_code, reason, evidence_ids]`;
- `contradictions`: `[description, evidence_ids]`.

All top-level field names, version constants, signal fields, and other values
remain model-authored. A deterministic codec restores only the object keys for
these rows. It neither selects evidence nor supplies missing values, generates
identifiers, repairs references, changes classes, or removes invalid properties.
The expanded response must pass the same strict classification and evidence
decoder as before. Malformed rows trigger bounded model retry, not local repair.

The prompt also requests minified JSON and minimal relevant citations. The
available metadata and evidence limits are unchanged: six and eight. Actual
model selections vary; fewer selected items are not an assertion of equal
semantic coverage. New results use prompt version `classification.ollama.rows.v2`.

An earlier experimental format with opaque short keys and integer references
was rejected after reference/alternative validation failures and a worse
classification. That format was not adopted. The accepted format retains the
standard meaningful field names and normal `ev_N` identifiers.

## Integration and limits

The production desktop worker processed three PDFs sequentially against an
isolated SQLite database: all three model runs and proposals persisted, no
retries or errors occurred, and source files remained unchanged. Inference
durations were 13.733, 12.197, and 10.987 seconds.

A full-input budget check found all 100 synthetic PDFs still fit the small
context tier: 4,885-5,586 UTF-8 input bytes within the conservative 5,632-byte
allowance. That is an input-size check, not 100 live inference evaluations.
Larger inputs continue to receive a larger bounded context or an explicit
over-budget failure; no document text is silently truncated.

The delivery-note class remains absent from the application taxonomy. Its
`supplier_receipt` prediction is still a known mismatch, not a correct-class
claim. Broader metadata accuracy and representative customer documents remain
unvalidated. No output mapping was added to conceal these limitations.

Evidence:

- [Live model requests and timings](rows-v2/live-results.json)
- [Three-file worker and SQLite proof](rows-v2/batch-proof.json)
- [Input-budget check](rows-v2/input-budget.json)
- [Recorded model-selected fields](rows-v2/model-fields-probe.json)

The same `scripts/benchmark-local-model.py` command can reproduce the timing
check with a new output path. Restart the desktop to load the new prompt and
transport code. No database migration or document operation is needed.
