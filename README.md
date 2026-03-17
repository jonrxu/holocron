# holocron

Holocron is a lightweight personal research memory for scientific papers.

The product goal is simple:
- get PDFs out of `Downloads`
- preserve them in cheap cloud storage
- turn each paper into a structured brief with tags, notes, and dated reading history
- connect related papers in a sparse semantic graph that stays useful instead of noisy

The v1 product and system design lives in [docs/holocron-v1-spec.md](/Users/jonathanxu/Documents/Code/holocron/docs/holocron-v1-spec.md).
The next implementation plan lives in [docs/next-steps.md](/Users/jonathanxu/Documents/Code/holocron/docs/next-steps.md).

## Current shape

Holocron is currently a small single-user Python app with:
- SQLite for metadata, search, and paper chat retrieval
- filesystem-backed blob storage for PDFs
- background analysis for structured paper cards, embeddings, and chunk indexing
- a minimal web UI for upload, search, map, list, and a split paper view with chat + PDF

By default PDFs are stored under `./data/blobs`. If you want the library on a synced drive, set `HOLOCRON_BLOB_DIR` to a folder in Dropbox, Google Drive, iCloud Drive, OneDrive, a NAS mount, or any shared disk you already trust.

## Run

```bash
python3 -m holocron
```

Then open [http://127.0.0.1:8420](http://127.0.0.1:8420).

Holocron auto-loads a local `.env` file from the project root on startup.

Most useful settings:
- `HOLOCRON_BLOB_DIR=/path/to/synced-or-shared-folder`
- `HOLOCRON_DATA_DIR=/path/to/local-app-data`
- `HOLOCRON_PORT=8420`
- `OPENAI_API_KEY=...` for model-backed paper analysis
- `GEMINI_API_KEY=...` or `GOOGLE_API_KEY=...` for embeddings and paper chat answers
- `HOLOCRON_GEMINI_ANALYSIS_MODEL=gemini-2.5-flash`
- `HOLOCRON_GEMINI_EMBEDDING_MODEL=gemini-embedding-001`
- `HOLOCRON_GEMINI_GENERATION_MODEL=gemini-2.5-flash-lite`

Behavior is simple:
- analysis uses OpenAI if configured, otherwise Gemini if configured, otherwise a built-in heuristic fallback
- analysis produces a structured paper card that is used for paper-level embeddings
- paper-level and chunk-level embeddings use Gemini if configured, otherwise a local hashed fallback
- paper chat uses Gemini if configured, otherwise an extractive fallback

## Verify

```bash
python3 -m unittest discover -s tests -v
```

## Future ideas

- Holocron could grow into a lightweight note-taking companion, not just a paper archive.
- While you write notes, a small background model could wait for a pause in typing and then suggest related papers, adjacent ideas, or missing questions.
- The constraint is restraint: suggestions should appear only occasionally, not continuously.
