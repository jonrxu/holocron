# holocron

Holocron is now a memory architecture project for LLMs.

The new goal is to build a model-facing memory system that can:
- inspect and grep its real prior chat logs
- distinguish fast working memory from slower persistent storage
- decide what should stay live in context vs what should be committed to disk
- recall prior interactions as first-class evidence instead of relying on a lossy summary alone

## Pivot

The old paper-library application is preserved on the `v1` branch.

`main` is now reserved for the new direction: an LLM memory runtime with explicit storage tiers and self-reference over logs.

## Core idea

Current chat systems mostly treat memory as one of three weak approximations:
- a fixed context window
- a rolling summary
- a vector search layer detached from the real transcript

Holocron should instead treat memory more like a computer system:
- `working memory`: small, fast, transient context currently loaded for reasoning
- `persistent memory`: slower, durable records written to disk
- `logs`: the authoritative event stream of what actually happened
- `indexes`: retrieval structures that help the model find the right prior state without replacing the source of truth

The model should be able to decide:
- when to keep something in working memory
- when to summarize
- when to commit a fact, plan, preference, or artifact to durable storage
- when to reopen raw logs instead of trusting a summary

## Design principles

1. Logs are primary.
   The system should preserve raw interaction history and let the model inspect it directly.

2. Memory is tiered.
   Not everything belongs in the prompt. Not everything belongs on disk either.

3. Persistence is selective.
   Durable memory should be written intentionally, with a policy for what is worth storing.

4. Retrieval must stay inspectable.
   If the model recalls something, it should be able to show where it came from.

5. Summaries are cached views, not truth.
   Summaries help with speed, but logs remain the canonical record.

## Early architecture sketch

- append-only chat/event log
- grepable local transcript store
- memory objects for facts, preferences, plans, artifacts, and open loops
- a commit policy that promotes selected working-memory items into persistent storage
- retrieval that can mix:
  - exact text search
  - structural filters
  - semantic ranking
  - direct log replay
- a controller that decides whether to:
  - answer from working memory
  - search recent context
  - grep historical logs
  - load durable memory objects
  - write a new persistent memory

## Immediate questions

- What should the memory unit be: message, span, fact, plan, artifact, or session?
- Which items should be persisted automatically vs only on explicit commit?
- How should the model inspect prior logs without wasting context window budget?
- How should memory decay, invalidation, contradiction, and correction work?
- What is the minimum viable system that proves better recall than plain chat history plus RAG?

## Status

This branch is intentionally reset to the project definition. Implementation will be rebuilt around the new memory-system thesis.
