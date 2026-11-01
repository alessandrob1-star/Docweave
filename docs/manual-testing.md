# Manual acceptance

Use copies of synthetic PDFs, not original business documents.

- Start Ollama with the installed `qwen2.5:14b-instruct` model.
- Launch DocWeave and check that the existing layout, styling, and all buttons remain.
- Verify the LLM control and SQLite memory status.
- Choose a folder, scan, preview, and analyze several PDFs.
- Check proposed names, folders, evidence references, and displayed failures.
- Reject one proposal: its file must remain unchanged.
- Approve one proposal: verify the resulting file and stored original path.
- Close and reopen DocWeave: review history must persist.
- Restore the approved file and verify its original bytes, name, and location.
- Stop Ollama: analysis must report failure without a fabricated result.
- Repeat analysis with internet disconnected but Ollama running.
- Check cancel, individual review, batch review, and side-screen controls.

Record observations and failures in `verification.md`. Manual acceptance must
be completed before removing the preserved original source project.
