# Next steps

The current app does three useful things well:
- stores PDFs cleanly
- gives each paper a searchable record
- lets you chat against grounded excerpts while reading the PDF

The biggest remaining gap is representation quality. Right now the paper-level embedding is only as strong as the current analyzer output, and the analyzer is still heuristic unless an OpenAI key is configured.

## Priority 1: Gemini structured paper card

Status: in progress.

The app now has a Gemini-backed structured analyzer path and stores one canonical paper card per paper.
The next refinement is to improve the schema quality and prompt quality so the card better captures the paper's essence.

Each card should stay focused on:
- problem
- core idea
- method
- findings
- limitations
- prerequisites
- concepts
- datasets
- tasks
- why it matters

The remaining work here is:
- embed the paper card for library search, map placement, and related-paper retrieval
- tune the card prompt so embeddings reflect the paper's high-level meaning better
- keep chunk embeddings only for grounded paper chat

## Priority 2: Memory layer

Persist understanding beyond one session:
- chat history per paper
- user-authored notes and takeaways
- a rolling "what I learned" summary
- recurring questions across papers

This becomes the personal layer of the holocron rather than a stateless Q&A surface.

## Priority 3: Lineage layer

Use the structured paper cards plus memory layer to build sparse knowledge edges:
- builds on
- contradicts
- uses method
- shares benchmark
- prerequisite for

The graph should represent lineages of ideas, not just geometric embedding proximity.

## Priority 4: Retrieval cleanup

After the structured analyzer is in:
- switch library semantic ranking to use the paper card embedding
- prefilter with lexical search, then rerank semantically
- keep the current chunk retrieval only for paper chat

## Priority 5: UI polish

Keep the product minimal:
- library page: search, upload, list, map
- paper page: chat + PDF

Avoid reintroducing dashboard-style surfaces unless they directly improve teaching, memory, or lineage.
