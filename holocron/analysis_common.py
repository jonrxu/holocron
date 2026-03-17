from __future__ import annotations

from dataclasses import dataclass


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        cleaned = item.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def trim_sentence(sentence: str, max_length: int = 260) -> str:
    collapsed = " ".join(sentence.split())
    if len(collapsed) <= max_length:
        return collapsed
    return collapsed[: max_length - 1].rstrip() + "…"


def split_sentences(text: str) -> list[str]:
    import re

    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
        if sentence.strip()
    ]


def coerce_strings(items: list[object], limit: int = 6) -> list[str]:
    return dedupe([str(item).strip() for item in items[:limit]])


def normalize_task_tags(tasks: list[str]) -> list[str]:
    return [f"task:{task.replace(' ', '_')}" for task in tasks]


@dataclass
class AnalysisInput:
    title: str | None
    authors: list[str]
    year: int | None
    abstract: str | None
    full_text: str


@dataclass
class AnalysisResult:
    problem: str
    core_idea: str
    summary_short: str
    summary_long: str
    why_it_matters: str
    method_summary: str
    prerequisites: list[str]
    concepts: list[str]
    limitations: list[str]
    claims: list[str]
    datasets: list[str]
    tasks: list[str]
    tags: list[str]
    followup_questions: list[str]
    confidence: float
    version: str


def coerce_analysis_result(parsed: dict[str, object], version: str) -> AnalysisResult:
    tasks = coerce_strings(list(parsed.get("tasks", [])), limit=6)
    tags = coerce_strings(list(parsed.get("tags", [])), limit=16)
    for task_tag in normalize_task_tags(tasks[:4]):
        if task_tag not in tags:
            tags.append(task_tag)
    if "status:unread" not in tags:
        tags.insert(0, "status:unread")

    return AnalysisResult(
        problem=str(parsed.get("problem", "")).strip(),
        core_idea=str(parsed.get("core_idea", "")).strip(),
        summary_short=str(parsed.get("summary_short", "")).strip(),
        summary_long=str(parsed.get("summary_long", "")).strip(),
        why_it_matters=str(parsed.get("why_it_matters", "")).strip(),
        method_summary=str(parsed.get("method_summary", "")).strip(),
        prerequisites=coerce_strings(list(parsed.get("prerequisites", [])), limit=6),
        concepts=coerce_strings(list(parsed.get("concepts", [])), limit=8),
        limitations=coerce_strings(list(parsed.get("limitations", [])), limit=5),
        claims=coerce_strings(list(parsed.get("claims", [])), limit=5),
        datasets=coerce_strings(list(parsed.get("datasets", [])), limit=8),
        tasks=tasks,
        tags=tags,
        followup_questions=coerce_strings(list(parsed.get("followup_questions", [])), limit=5),
        confidence=float(parsed.get("confidence", 0.7)),
        version=version,
    )


def paper_analysis_system_prompt() -> str:
    return (
        "You analyze scientific papers for a personal research memory. "
        "Return concise, factual structured JSON only. "
        "Focus on the paper's problem, core idea, method, findings, limitations, "
        "prerequisites, concepts, datasets, tasks, and why it matters. "
        "Infer fields only when the text supports them. "
        "Always include status:unread in tags. "
        "Allowed tag families: domain:*, paper_type:*, status:*, quality:*, needs:*, has:*, task:*."
    )


def paper_analysis_user_prompt(payload: AnalysisInput) -> str:
    title = payload.title or "Unknown title"
    authors = ", ".join(payload.authors) if payload.authors else "Unknown authors"
    year = str(payload.year) if payload.year else "Unknown year"
    abstract = payload.abstract or "No abstract extracted."
    return (
        f"Title: {title}\n"
        f"Authors: {authors}\n"
        f"Year: {year}\n"
        f"Abstract:\n{abstract}\n\n"
        "Paper text:\n"
        f"{payload.full_text}\n\n"
        "Return a compact structured paper card that is useful for library search, "
        "knowledge lineage, and revisiting the paper later."
    )


def paper_analysis_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "problem",
            "core_idea",
            "summary_short",
            "summary_long",
            "why_it_matters",
            "method_summary",
            "prerequisites",
            "concepts",
            "limitations",
            "claims",
            "datasets",
            "tasks",
            "tags",
            "followup_questions",
            "confidence",
        ],
        "properties": {
            "problem": {"type": "string"},
            "core_idea": {"type": "string"},
            "summary_short": {"type": "string"},
            "summary_long": {"type": "string"},
            "why_it_matters": {"type": "string"},
            "method_summary": {"type": "string"},
            "prerequisites": {
                "type": "array",
                "items": {"type": "string"},
            },
            "concepts": {
                "type": "array",
                "items": {"type": "string"},
            },
            "limitations": {
                "type": "array",
                "items": {"type": "string"},
            },
            "claims": {
                "type": "array",
                "items": {"type": "string"},
            },
            "datasets": {
                "type": "array",
                "items": {"type": "string"},
            },
            "tasks": {
                "type": "array",
                "items": {"type": "string"},
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
            },
            "followup_questions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
        },
    }
