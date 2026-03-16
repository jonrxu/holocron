from __future__ import annotations

import json
import re
import shlex
import subprocess
from dataclasses import asdict, dataclass


def _dedupe(items: list[str]) -> list[str]:
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


def _trim_sentence(sentence: str, max_length: int = 260) -> str:
    collapsed = " ".join(sentence.split())
    if len(collapsed) <= max_length:
        return collapsed
    return collapsed[: max_length - 1].rstrip() + "…"


def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
        if sentence.strip()
    ]


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


class HeuristicAnalyzer:
    version = "heuristic-v1"

    DOMAIN_KEYWORDS = {
        "domain:ml": ["transformer", "neural", "language model", "benchmark", "training"],
        "domain:biology": ["protein", "cell", "genome", "biology", "biological"],
        "domain:neuroscience": ["neural recording", "brain", "cortex", "neuron", "neuroscience"],
        "domain:robotics": ["robot", "control", "manipulation", "planner", "simulator"],
    }

    TASK_KEYWORDS = {
        "question answering": ["question answering", "qa"],
        "classification": ["classification", "classifier"],
        "generation": ["generation", "generate", "synthesis"],
        "retrieval": ["retrieval", "search", "rank"],
        "segmentation": ["segmentation"],
        "translation": ["translation", "translate"],
    }

    PAPER_TYPE_KEYWORDS = {
        "paper_type:survey": ["survey", "review of"],
        "paper_type:benchmark": ["benchmark", "leaderboard"],
        "paper_type:theory": ["theorem", "proof", "theoretical"],
        "paper_type:methods": ["method", "approach", "framework", "architecture"],
        "paper_type:empirical": ["experiment", "empirical", "evaluation"],
    }

    def analyze(self, payload: AnalysisInput) -> AnalysisResult:
        source_text = payload.abstract or payload.full_text
        sentences = _split_sentences(source_text)
        full_sentences = _split_sentences(payload.full_text)
        summary_candidates = sentences or full_sentences

        summary_short = _trim_sentence(
            summary_candidates[0]
            if summary_candidates
            else f"{payload.title or 'This paper'} was ingested into Holocron."
        )
        summary_long = " ".join(_trim_sentence(sentence) for sentence in summary_candidates[:3]) or summary_short

        claims = self._select_claims(full_sentences)
        method_summary = self._select_method_summary(payload.full_text, summary_short)
        limitations = self._select_limitations(full_sentences)
        datasets = self._extract_datasets(payload.full_text)
        tasks = self._detect_tasks(payload.full_text)
        tags = self._build_tags(payload, tasks, datasets, limitations)
        why_it_matters = self._build_why_it_matters(payload, claims, summary_short)
        followup_questions = self._build_followups(payload, tasks, datasets, limitations)
        confidence = self._estimate_confidence(payload, claims, summary_candidates)

        return AnalysisResult(
            summary_short=summary_short,
            summary_long=summary_long,
            why_it_matters=why_it_matters,
            method_summary=method_summary,
            limitations=limitations,
            claims=claims,
            datasets=datasets,
            tasks=tasks,
            tags=tags,
            followup_questions=followup_questions,
            confidence=confidence,
            version=self.version,
        )

    def _select_claims(self, sentences: list[str]) -> list[str]:
        claim_markers = ("show", "demonstrate", "propose", "present", "find", "achieve", "improve")
        candidates = [
            _trim_sentence(sentence)
            for sentence in sentences
            if any(marker in sentence.lower() for marker in claim_markers)
        ]
        if not candidates:
            candidates = [_trim_sentence(sentence) for sentence in sentences[:2]]
        return _dedupe(candidates[:3])

    def _select_method_summary(self, text: str, fallback: str) -> str:
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        keywords = ("method", "approach", "framework", "model", "architecture", "we use", "we train")
        for paragraph in paragraphs:
            lower = paragraph.lower()
            if any(keyword in lower for keyword in keywords):
                return _trim_sentence(paragraph.replace("\n", " "), 320)
        return fallback

    def _select_limitations(self, sentences: list[str]) -> list[str]:
        markers = ("limitation", "however", "future work", "we do not", "remains challenging")
        candidates = [
            _trim_sentence(sentence)
            for sentence in sentences
            if any(marker in sentence.lower() for marker in markers)
        ]
        if not candidates:
            candidates = [
                "The extraction did not surface an explicit limitations section; verify assumptions manually."
            ]
        return _dedupe(candidates[:3])

    def _extract_datasets(self, text: str) -> list[str]:
        matches = re.findall(
            r"(?:dataset|benchmark|corpus)\s+(?:called\s+)?([A-Z][A-Za-z0-9-]{2,})",
            text,
            flags=re.IGNORECASE,
        )
        return _dedupe(matches[:5])

    def _detect_tasks(self, text: str) -> list[str]:
        lower = text.lower()
        tasks = [
            task
            for task, keywords in self.TASK_KEYWORDS.items()
            if any(keyword in lower for keyword in keywords)
        ]
        return _dedupe(tasks[:5])

    def _build_tags(
        self,
        payload: AnalysisInput,
        tasks: list[str],
        datasets: list[str],
        limitations: list[str],
    ) -> list[str]:
        lower = f"{payload.title or ''}\n{payload.abstract or ''}\n{payload.full_text[:8000]}".lower()
        tags = ["status:unread"]
        for tag, keywords in self.DOMAIN_KEYWORDS.items():
            if any(keyword in lower for keyword in keywords):
                tags.append(tag)
        for tag, keywords in self.PAPER_TYPE_KEYWORDS.items():
            if any(keyword in lower for keyword in keywords):
                tags.append(tag)
        if datasets:
            tags.append("has:dataset")
        if tasks:
            tags.extend(f"task:{task.replace(' ', '_')}" for task in tasks[:3])
        tags.append("quality:high_confidence" if len(lower) > 2000 else "quality:low_confidence_extraction")
        if limitations and "explicit limitations section" in limitations[0].lower():
            tags.append("needs:manual_limitations_review")
        return _dedupe(tags)

    def _build_why_it_matters(
        self,
        payload: AnalysisInput,
        claims: list[str],
        summary_short: str,
    ) -> str:
        if claims:
            return _trim_sentence(claims[0], 300)
        if payload.title:
            return f"{payload.title} matters because it captures a specific research problem in a reusable, searchable form."
        return summary_short

    def _build_followups(
        self,
        payload: AnalysisInput,
        tasks: list[str],
        datasets: list[str],
        limitations: list[str],
    ) -> list[str]:
        questions = []
        if tasks:
            questions.append(f"Which baseline or prior work should this be compared against for {tasks[0]}?")
        else:
            questions.append("What exact problem formulation should this paper be grouped under?")
        if datasets:
            questions.append(f"Is performance on {datasets[0]} representative, or is there a better benchmark?")
        else:
            questions.append("Which datasets or benchmarks are missing from this paper record?")
        if limitations:
            questions.append("Which limitation here most affects whether this paper is worth revisiting?")
        if payload.year:
            questions.append(f"What newer work since {payload.year} extends or contradicts this paper?")
        return _dedupe(questions[:4])

    def _estimate_confidence(
        self,
        payload: AnalysisInput,
        claims: list[str],
        summary_candidates: list[str],
    ) -> float:
        score = 0.25
        if payload.title:
            score += 0.15
        if payload.abstract:
            score += 0.2
        if len(payload.full_text) > 4000:
            score += 0.2
        if claims:
            score += 0.1
        if len(summary_candidates) >= 2:
            score += 0.1
        return min(score, 0.95)


class ExternalCommandAnalyzer:
    def __init__(self, command: str) -> None:
        self.command = command

    def analyze(self, payload: AnalysisInput) -> AnalysisResult:
        result = subprocess.run(
            shlex.split(self.command),
            input=json.dumps(asdict(payload)),
            text=True,
            capture_output=True,
            check=True,
        )
        parsed = json.loads(result.stdout)
        return AnalysisResult(
            summary_short=str(parsed["summary_short"]).strip(),
            summary_long=str(parsed["summary_long"]).strip(),
            why_it_matters=str(parsed["why_it_matters"]).strip(),
            method_summary=str(parsed["method_summary"]).strip(),
            limitations=_dedupe([str(item) for item in parsed.get("limitations", [])]),
            claims=_dedupe([str(item) for item in parsed.get("claims", [])]),
            datasets=_dedupe([str(item) for item in parsed.get("datasets", [])]),
            tasks=_dedupe([str(item) for item in parsed.get("tasks", [])]),
            tags=_dedupe([str(item) for item in parsed.get("tags", [])]),
            followup_questions=_dedupe(
                [str(item) for item in parsed.get("followup_questions", [])]
            ),
            confidence=float(parsed.get("confidence", 0.7)),
            version=str(parsed.get("version", "external-command")),
        )
