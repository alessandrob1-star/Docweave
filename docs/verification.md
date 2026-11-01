# Verification - 2026-11-01

## Automated checks

- Python 3.14 on Windows; isolated local virtual environment.
- Ruff lint and formatting checks passed.
- MyPy strict checking passed for application and test modules.
- `pip check` found no broken dependency requirements.
- The automated suite covers document discovery, extraction, validation,
  file-operation approval, restore, desktop controls, and local persistence.
- SQLite integration tests verify six tables, foreign-key enforcement,
  durable path history after reopening, idempotent writes, and rejected
  proposals leaving stored file paths unchanged.
- Search of the new repository's source, tests, and documentation found no
  references to retired providers or event material.

Final local result: **474 passed in 78.18 seconds**, with **86% aggregate
coverage** (statements and branches). No warnings were reported in this final
run. MyPy passed for all 101 application and test modules. No manual acceptance
or security certification is implied.

## Live local inference

Input: synthetic `attachment_07.pdf`, two pages.
Model: installed `qwen2.5:14b-instruct` through loopback Ollama.
Observed hardware: NVIDIA GeForce RTX 3060, 12 GB video memory.

- Native structured output passed schema and evidence-reference validation.
- Document, model run, and proposal were written to the local SQLite database.
- Observed usage: 4,289 input tokens and 2,136 output tokens; 6,425 total.
- Inference duration recorded by the application: 409.963 seconds.
- No file was renamed or moved by this inference check.

The corpus label is `delivery_note`. That class does not exist in the current
application taxonomy. The model returned `supplier_receipt`, with a rationale
describing a delivery note. This is a taxonomy/label mismatch, not a validated
correct classification. One sample cannot establish model accuracy.

The latency is too high to claim practical bulk-processing performance on
the tested configuration. Context size, hardware use, taxonomy alignment,
and representative quality evaluation remain follow-up work. No model switch,
hardcoded correction, or remote inference fallback was introduced.

## Interface and manual acceptance

Analysis-status follow-up: the existing upper analysis panel now displays
`ANALYZING`, the current document name and batch position as each document
starts. It changes to `AI PROPOSAL` when a validated result arrives, or
`ANALYSIS FAILED` on error. No layout or button was removed. A controlled
waiting-worker test verifies that the status appears before completion.
The follow-up suite passed **475 tests in 102.73 seconds**, with **86% aggregate
coverage**; all 31 desktop cockpit tests and strict type/lint checks passed.

The first hosted build failed because editable installation without build
isolation lacked a build helper. Hosted checks now install the normal wheel;
local wheel construction, installation, and SQLite initialization passed.
Hosted verification of this follow-up is tracked separately on GitHub Actions.

A native Windows render confirmed the retained layout and controls, with the
model button labeled LLM and the memory status labeled SQLite. The screenshot
in the README is from this local application, not a previous deployment.

Manual approval, close/reopen, restore, and disconnected-internet acceptance
remain pending. Follow `manual-testing.md`. Preserve the original source
project until the owner completes those checks.
