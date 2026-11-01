# Local architecture

The PySide6 desktop selects an authorized folder and scans supported PDFs.
Extraction runs in a bounded disposable process. The application builds
evidence segments and requests native structured JSON from local Ollama.
The validated classification produces a proposed filename and destination.

SQLite stores documents, agent runs, proposals, human decisions, file history,
and optional document relationships. Connections enforce foreign keys. Review
transactions use `BEGIN IMMEDIATE` and bounded retries for locked or busy
databases. The local schema is version 1; a newer unknown version is rejected.

The application records human decisions before reporting their durable result.
File moves and SQLite writes are separate operations, not a single atomic
transaction. An interrupted or failed write after a move requires investigation
and recovery from the local audit evidence and backups. Manual acceptance must
include the approve, close, reopen, and restore sequence.

The LLM control checks the installed local model. It never starts a browser,
performs login, downloads a model, or switches inference providers. Unavailable
inference and invalid output produce visible failure states.

The application has no required remote runtime service. Dependency installation,
model provisioning, repository hosting, and automated build checks are separate
development/distribution activities.
