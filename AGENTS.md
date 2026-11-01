# Project rules

- Preserve genuine model inference, retrieval, evidence validation, and failure reporting.
- Follow the user's explicit scope. Do not change interface layout or remove buttons.
- Keep application runtime local: Ollama on loopback and SQLite on local disk.
- Never introduce remote inference or canned-result fallbacks.
- Require human approval for document file mutations and retain restore history.
- Keep source and repository documentation in English; explain work in Italian.
- Do not publish credentials, user documents, or runtime databases.
- Preserve the original source project until the user completes manual acceptance.
- Report test failures and limitations honestly. Do not claim readiness without evidence.
