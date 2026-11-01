# Local model tuning - 2026-11-01

The model remains `qwen2.5:14b-instruct`, Q4_K_M, on Ollama 0.40.0.
The observed system has an NVIDIA GeForce RTX 3060 with 12 GB of video memory.
No model, runtime dependency, database schema, interface layout, or button was
replaced for this calibration. All comparisons use real inference and the
existing schema/evidence decoder.

## Measured comparison

The anchor PDF is `attachment_07.pdf`, SHA-256
`d57248fcb16d2069f3837c180c508d77f2aa424b380526f43d145bf7433f44d0`.

| Measurement | Before | Final anchor run |
| --- | ---: | ---: |
| Inference duration | 409.963 s | 25.166 s |
| Input tokens | 4,289 | 1,263 |
| Output tokens | 2,136 | 782 |
| Context allocation | 32,768 | 8,192 |
| Model placement reported by Ollama | 34% CPU / 66% GPU | 100% GPU |

The baseline is the recorded earlier run of the same PDF, rather than a fresh
concurrent A/B test. Context allocation, prompt serialization, and verbosity
changed together; these measurements do not isolate their individual effects.
The first tuned cold/reload probe took 31.929 s, including 8.549 s of model
loading. Final warm probes were:

| PDF | Predicted class | Seconds | Validation retries |
| --- | --- | ---: | ---: |
| `attachment_07.pdf` | `supplier_receipt` | 23.750 | 0 |
| `attachment_081.pdf` | `invoice` | 24.328 | 0 |
| `attachment_094.pdf` | `purchase_order` | 24.182 | 0 |
| `attachment_162.pdf` | `supplier_receipt` | 24.956 | 0 |
| `attachment_07.pdf`, repeat | `supplier_receipt` | 25.560 | 0 |

Ollama reported 10,279,599,471 bytes allocated to the model, all on the GPU
(about 9.57 GiB). Total GPU memory use including the desktop and other allocations
was sampled at about 10.6 GiB. Allocating an exact amount of unused video memory
is not an application requirement; full GPU placement is the relevant observation.

## Changes and controls

- Ordinary inputs use an 8,192-token context. Larger inputs select the smallest
  sufficient tier, up to 32,768. Large contexts can still cause CPU offloading
  and slower execution; they are no longer imposed on every short PDF.
- The complete extracted evidence is serialized as compact rows with a separate
  page-label map. Every segment identifier, page index, label, and text is kept.
  The output schema is supplied through native structured output, without
  copying it again into the prompt.
- The model selects up to eight strong evidence segments and up to six metadata
  fields. Classification, references, contradictions, abstention, and review
  remain model-driven. Output is bounded at 2,048 tokens; truncation is a failure.
- The native schema now expresses the existing lowercase metadata-name rule
  and nonempty metadata evidence references. It does not rewrite invalid output.
  Initial compact probes failed on two cases; a captured response demonstrated
  names such as `Document ID` that violated the decoder's existing contract.
  The final probes above passed that unchanged decoder.
- Context sizing conservatively budgets UTF-8 bytes plus output and template
  space. Inputs beyond the maximum are rejected, never silently truncated.
- Prompt versions participate in analysis/proposal identity. New prompt results
  cannot silently reuse a previous prompt's stored proposal. Existing document
  identity and history are retained. Observed tokens, duration, retries, and
  prompt version are stored with new model runs.

An input-size check of all 100 synthetic PDFs found all 100 fit the 8,192-token
tier: serialized prompts ranged from 4,245 to 4,946 UTF-8 bytes, within the
5,632-byte conservative input allowance. This check did not classify 100 PDFs.

The actual desktop classification worker also processed a three-PDF batch
against an isolated local SQLite database. All three started, completed, and
persisted their document, model-run, and proposal rows. No files changed.

## Limits and reproducibility

These convenience samples do not establish representative classification
accuracy or worst-case latency. The corpus's `delivery_note` label is absent
from the current taxonomy; the anchor's `supplier_receipt` output remains a
known mismatch. No answer mapping was introduced to conceal it.

With DocWeave idle and Ollama running, reproduce an anchor measurement with:

```powershell
.\.venv\Scripts\python scripts/benchmark-local-model.py --authorized-root pdf_sintetici --output anchor-new.json pdf_sintetici/attachment_07.pdf
```

The report path must not already exist. This runs real inference and validation
without writing application memory or moving documents. Close and reopen the
desktop after updating code; an already running Python process retains the
previous configuration.

Evidence: [anchor report](benchmark-final-anchor.json) and
[tuning probes, input budgets, and batch proof](tuning-measurements.json).
