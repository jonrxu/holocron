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

Useful environment variables:
- `HOLOCRON_BLOB_DIR=/path/to/synced-or-shared-folder`
- `HOLOCRON_DATA_DIR=/path/to/local-app-data`
- `HOLOCRON_PORT=8420`
- `HOLOCRON_ANALYZER_COMMAND=/path/to/custom-analyzer`

`HOLOCRON_ANALYZER_COMMAND` is optional. If set, Holocron will pipe JSON paper payloads to that command and expect structured JSON back. Otherwise it falls back to the built-in heuristic analyzer.

## Verify

```bash
python3 -m unittest discover -s tests -v
```
