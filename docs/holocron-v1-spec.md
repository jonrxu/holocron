# Holocron v1

## Product thesis

Holocron is not a general reference manager. It is a personal research memory.

Each paper should become a durable record with three layers:
- artifact: the canonical PDF and extracted text
- essence: the machine-generated brief, tags, and your notes
- lineage: dated reading events and links to related papers, methods, datasets, and questions

The system should feel lightweight:
- dropping in a paper should take seconds
- local disk should not accumulate cold PDFs
- the graph should stay sparse and legible
- the user should never be forced to fill in metadata by hand

## Design principles

1. Single-user first.
   Build for one person and one corpus. Do not pay the complexity tax for multi-user collaboration in v1.

2. Cheap blob storage for PDFs.
   PDFs are immutable files. Store them in object storage and keep only a small local cache.

3. One database for metadata.
   Do not introduce a dedicated graph database or vector database in v1. Store metadata, notes, edges, events, FTS, and embeddings in one database.

4. Async analysis.
   Ingestion should be fast. Deep analysis can run in the background and progressively enrich the paper record.

5. Structured outputs over free text.
   The agent should emit JSON-like fields for claims, methods, limitations, tags, and follow-up questions so they can be searched and reused.

6. Sparse typed graph.
   A small number of high-confidence edges is more useful than an automatic hairball.

7. Human correction is cheap.
   The agent proposes tags and links; the user can edit them, but manual work is optional.

## User experience

### 1. Intake

The user adds a paper in one of two ways:
- preferred: drag-and-drop into a small web or desktop inbox that uploads directly to object storage
- fallback: save into a watched local folder that is emptied after successful upload

The system immediately creates a paper card with:
- title if detectable
- upload date
- status: `queued`, `processing`, `ready`, or `needs_review`

### 2. First-pass brief

Within a short time, Holocron generates:
- one-sentence summary
- why it matters
- key claims
- method summary
- limitations
- datasets, tasks, and domains
- auto-tags
- related concepts and candidate links
- suggested next actions such as `read later`, `revisit`, or `discard`

The user can read this before opening the full PDF.

### 3. Notes

The user can add:
- freeform notes
- page-anchored notes
- a short verdict such as `important`, `unclear`, `replication-worthy`, or `ignore`

User notes are always kept separate from machine-generated fields.

### 4. Recall

Holocron keeps a dated history:
- saved
- analyzed
- opened
- annotated
- revisited

It also nudges recall with a minimal review queue:
- unread papers older than 7 days
- papers marked important but not revisited
- papers with weak understanding signals such as no notes or low-confidence summary

### 5. Explore

The user can navigate by:
- keyword search
- semantic search
- tags
- timeline
- graph view

The graph view should focus on local neighborhoods, not a full-corpus galaxy map by default.

## Non-goals for v1

- full citation management
- collaborative workspaces
- perfect OCR for scanned PDFs
- automatic import of every paper from browser history or email
- a full-featured PDF editor
- giant recommendation feeds
- a dedicated graph database

## Recommended architecture

### Core components

1. Ingest service
   Accepts a PDF or URL, computes a checksum, uploads the file, creates a paper record, and emits analysis jobs.

2. Storage layer
   Stores canonical PDFs in object storage using content-addressed keys.

3. Analysis worker
   Extracts text, resolves metadata, runs LLM synthesis, generates tags and candidate edges, and writes structured artifacts.

4. Metadata database
   Stores papers, notes, events, edges, and search indexes.

5. API + UI
   Shows inbox, paper detail, search, timeline, and graph.

### Recommended stack

For the lightest practical v1:
- object storage: Cloudflare R2, Backblaze B2, or S3
- metadata DB: SQLite with FTS5 and vector support such as `sqlite-vec` or `libsql`
- backend: one small API service plus one worker process
- text extraction: `PyMuPDF` first, OCR only as a fallback
- frontend: a small React app or server-rendered app with fast list/detail views

Why this stack:
- SQLite keeps operations, backup, and local development simple
- object storage keeps PDFs off the main machine
- one worker is enough for background enrichment
- no extra graph or vector service reduces operational drag

If hosted multi-device sync becomes important later, the first upgrade should be `SQLite -> Postgres`, not adding more specialized databases.

## Storage design

### Canonical PDF storage

Store each PDF by checksum:

```text
papers/raw/sha256/<hash>.pdf
```

Benefits:
- dedupe is trivial
- the same paper saved twice does not create two blobs
- metadata can be corrected without moving the file

### Local cache

Keep a small LRU cache for recently opened PDFs:
- target size: 1 to 5 GB
- evict automatically
- never depend on the cache for correctness

If a watched local folder is used for intake, delete the local source file after upload succeeds and the hash is recorded.

## Data model

Use one database with plain tables.

### `papers`

- `id`
- `checksum`
- `storage_key`
- `source_type` (`upload`, `url`, `arxiv`, `doi`)
- `source_value`
- `title`
- `authors_json`
- `year`
- `doi`
- `arxiv_id`
- `abstract`
- `status`
- `added_at`
- `last_opened_at`
- `last_reviewed_at`

### `paper_artifacts`

- `paper_id`
- `extracted_text`
- `summary_short`
- `summary_long`
- `why_it_matters`
- `method_summary`
- `limitations_json`
- `claims_json`
- `datasets_json`
- `tasks_json`
- `tags_json`
- `followup_questions_json`
- `embedding`
- `analysis_version`
- `updated_at`

### `notes`

- `id`
- `paper_id`
- `author_type` (`user`, `agent`)
- `body`
- `page_number`
- `created_at`

### `edges`

- `id`
- `source_paper_id`
- `target_paper_id`
- `edge_type`
- `weight`
- `rationale`
- `source` (`agent`, `user`, `rule`)
- `created_at`

Recommended `edge_type` values:
- `same_topic`
- `uses_method`
- `extends`
- `contradicts`
- `uses_dataset`
- `motivates`

### `events`

- `id`
- `paper_id`
- `event_type`
- `payload_json`
- `created_at`

Recommended `event_type` values:
- `ingested`
- `analyzed`
- `opened`
- `annotated`
- `tag_corrected`
- `edge_confirmed`
- `revisited`

## Ingestion pipeline

The pipeline should be staged so the user sees progress quickly.

### Stage 1: intake

- receive PDF or URL
- compute checksum
- detect duplicates
- upload PDF to object storage
- create `papers` row
- emit `ingested` event

### Stage 2: extraction

- extract text with `PyMuPDF`
- capture first-page heuristics for title and authors
- if available, resolve DOI, arXiv ID, or Crossref metadata

This stage should avoid heavyweight academic parsing services in v1.

### Stage 3: synthesis

Run an LLM over extracted text and require structured output:
- summary
- claims
- methods
- limitations
- tasks
- datasets
- tags
- follow-up questions
- confidence notes when extraction quality is poor

### Stage 4: indexing

- write FTS text
- write embedding
- create candidate graph edges
- emit `analyzed` event

### Stage 5: review queue

Mark papers for follow-up when:
- summary confidence is low
- extraction is incomplete
- the user has not opened the paper after several days
- the paper is tagged important but has no notes

## Search and graph

### Search

Use hybrid retrieval:
- keyword search for exact terms, authors, and datasets
- semantic search for concept-level recall

The simplest useful ranking is:
- recent activity boost
- exact title/author matches first
- then FTS score
- then embedding similarity

### Graph generation

Do not create edges from raw embedding similarity alone.

Prefer edges from:
- shared explicit entities such as dataset, task, or method
- LLM-generated relation proposals with rationale
- user-confirmed links

Practical graph rules:
- limit auto-created edges per paper
- store a reason for every edge
- visualize only 1 to 2 hops from the current paper by default

## Tagging strategy

Use a constrained typed taxonomy instead of loose freeform labels.

Recommended tag families:
- domain: `biology`, `ml`, `neuroscience`, `robotics`
- paper type: `survey`, `benchmark`, `theory`, `empirical`, `methods`
- modality: `text`, `image`, `multimodal`, `genomics`
- status: `unread`, `reading`, `understood`, `revisit`, `important`
- quality signal: `high_confidence`, `low_confidence_extraction`

Freeform tags can exist, but typed tags should drive the main navigation.

## Minimal UI surfaces

Only build five screens in v1.

### Inbox

Shows:
- newly ingested papers
- processing state
- quick actions: archive, mark important, open brief

### Paper detail

Shows:
- metadata
- structured brief
- your notes
- related papers
- event history

### Search

Shows:
- hybrid search results
- faceted filtering by typed tags

### Graph

Shows:
- current paper at center
- sparse neighboring papers and concepts

### Review queue

Shows:
- unread papers
- stale important papers
- papers needing metadata cleanup

## Efficiency constraints

These constraints keep the project lightweight.

1. No dedicated graph service in v1.
2. No dedicated vector service in v1.
3. No OCR unless extraction fails.
4. No full-library re-embedding unless the prompt or schema changes materially.
5. No giant generated markdown files per paper unless the user explicitly exports them.
6. No automatic graph edges without a stored rationale.
7. No local permanent copy once upload succeeds.

## Suggested implementation order

### Phase 1: prove the loop

Build:
- file/URL intake
- object storage upload
- checksum dedupe
- SQLite schema
- text extraction
- AI brief
- notes
- inbox and paper detail

This is the minimum version that already beats `Downloads`.

### Phase 2: retrieval

Add:
- FTS search
- embeddings
- hybrid ranking
- typed tags and filters

### Phase 3: connections

Add:
- candidate edges
- graph view
- rationale display
- edge confirmation/editing

### Phase 4: memory

Add:
- review queue
- reminders
- weekly digest
- revisit scoring

## What success looks like

Holocron v1 succeeds if:
- adding a paper takes less than 10 seconds of user effort
- the user can recover any previously saved paper in under 30 seconds
- every saved paper has a readable brief and auto-tags
- the graph helps find related work without becoming clutter
- the user no longer relies on `Downloads` as a research archive

## Sharp recommendation

If there is only one thing to protect, protect simplicity:
- store PDFs as blobs
- store metadata in one database
- generate structured briefs
- keep the graph sparse
- make recall a first-class feature

That is enough for Holocron to feel like a real research memory instead of another document folder.
