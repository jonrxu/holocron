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
    summary_short: str
    summary_long: str
    why_it_matters: str
    method_summary: str
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
        summary_short=str(parsed.get("summary_short", "")).strip(),
        summary_long=str(parsed.get("summary_long", "")).strip(),
        why_it_matters=str(parsed.get("why_it_matters", "")).strip(),
        method_summary=str(parsed.get("method_summary", "")).strip(),
        limitations=coerce_strings(list(parsed.get("limitations", [])), limit=5),
        claims=coerce_strings(list(parsed.get("claims", [])), limit=5),
        datasets=coerce_strings(list(parsed.get("datasets", [])), limit=8),
        tasks=tasks,
        tags=tags,
        followup_questions=coerce_strings(list(parsed.get("followup_questions", [])), limit=5),
        confidence=float(parsed.get("confidence", 0.7)),
        version=version,
    )
