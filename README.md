# holocron

Holocron is a lightweight personal research memory for scientific papers.

The product goal is simple:
- get PDFs out of `Downloads`
- preserve them in cheap cloud storage
- turn each paper into a structured brief with tags, notes, and dated reading history
- connect related papers in a sparse semantic graph that stays useful instead of noisy

The concrete v1 product and system design lives in [docs/holocron-v1-spec.md](/Users/jonathanxu/Documents/Code/holocron/docs/holocron-v1-spec.md).

## Phase 1

Phase 1 is now implemented as a zero-dependency Python app:
- SQLite for metadata, notes, artifacts, and events
- a filesystem-backed blob store for PDFs
- PDF extraction through the installed `pdftotext` and `pdfinfo` tools
- a background worker that generates a first-pass brief and tags
- a minimal web UI for upload, inbox, paper detail, notes, and review queue

By default PDFs are stored under `./data/blobs`, but the important knob is `HOLOCRON_BLOB_DIR`.
Point that at a synced folder or mounted shared drive to keep papers out of local `Downloads`, for example:
- Dropbox, Google Drive, iCloud Drive, OneDrive
- a mounted NAS share
- any external disk or shared folder you already trust

## Run

```bash
python3 -m holocron
```

Then open [http://127.0.0.1:8420](http://127.0.0.1:8420).

Holocron also auto-loads a local `.env` file from the project root on startup.

Useful environment variables:
- `HOLOCRON_BLOB_DIR=/path/to/synced-or-shared-folder`
- `HOLOCRON_DATA_DIR=/path/to/local-app-data`
- `HOLOCRON_PORT=8420`
- `HOLOCRON_ANALYZER_COMMAND=/path/to/custom-analyzer`
- `OPENAI_API_KEY=...`
- `HOLOCRON_OPENAI_MODEL=gpt-5`
- `HOLOCRON_OPENAI_REASONING_EFFORT=low`
- `GEMINI_API_KEY=...` or `GOOGLE_API_KEY=...`
- `HOLOCRON_GEMINI_EMBEDDING_MODEL=gemini-embedding-001`
- `HOLOCRON_GEMINI_EMBEDDING_DIMENSIONS=768`

Analyzer selection works like this:
- if `HOLOCRON_ANALYZER_COMMAND` is set, Holocron pipes JSON paper payloads to that command and expects structured JSON back
- otherwise, if `OPENAI_API_KEY` or `HOLOCRON_OPENAI_API_KEY` is set, Holocron uses the built-in OpenAI Responses API analyzer
- otherwise it falls back to the built-in heuristic analyzer

The OpenAI path still falls back to the heuristic analyzer if the model call fails, so ingestion remains usable even when the remote analysis path is unavailable.

Embeddings work similarly:
- if `GEMINI_API_KEY`, `GOOGLE_API_KEY`, or `HOLOCRON_GEMINI_API_KEY` is set, Holocron uses Gemini embeddings for semantic ranking and the 2D paper map
- otherwise it falls back to a local hashed embedding so the map and search still work without a remote dependency

## Verify

```bash
python3 -m unittest discover -s tests -v
```

## Future ideas

- Holocron could grow into a lightweight note-taking companion, not just a paper archive.
- While you write notes on a paper, a small background model could watch the note stream and wait for a pause in typing before doing anything.
- On each pause, it could suggest related papers, adjacent ideas, missing questions, or links to concepts already in your library.
- The important constraint is restraint: suggestions should appear only at quiet intervals, not continuously while you type.
