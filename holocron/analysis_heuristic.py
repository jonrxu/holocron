from __future__ import annotations

import re

from .analysis_common import AnalysisInput, AnalysisResult, dedupe, split_sentences, trim_sentence


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
        sentences = split_sentences(source_text)
        full_sentences = split_sentences(payload.full_text)
        summary_candidates = sentences or full_sentences

        summary_short = trim_sentence(
            summary_candidates[0]
            if summary_candidates
            else f"{payload.title or 'This paper'} was ingested into Holocron."
        )
        summary_long = " ".join(trim_sentence(sentence) for sentence in summary_candidates[:3]) or summary_short

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
            trim_sentence(sentence)
            for sentence in sentences
            if any(marker in sentence.lower() for marker in claim_markers)
        ]
        if not candidates:
            candidates = [trim_sentence(sentence) for sentence in sentences[:2]]
        return dedupe(candidates[:3])

    def _select_method_summary(self, text: str, fallback: str) -> str:
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        keywords = ("method", "approach", "framework", "model", "architecture", "we use", "we train")
        for paragraph in paragraphs:
            lower = paragraph.lower()
            if any(keyword in lower for keyword in keywords):
                return trim_sentence(paragraph.replace("\n", " "), 320)
        return fallback

    def _select_limitations(self, sentences: list[str]) -> list[str]:
        markers = ("limitation", "however", "future work", "we do not", "remains challenging")
        candidates = [
            trim_sentence(sentence)
            for sentence in sentences
            if any(marker in sentence.lower() for marker in markers)
        ]
        if not candidates:
            candidates = [
                "The extraction did not surface an explicit limitations section; verify assumptions manually."
            ]
        return dedupe(candidates[:3])

    def _extract_datasets(self, text: str) -> list[str]:
        matches = re.findall(
            r"(?:dataset|benchmark|corpus)\s+(?:called\s+)?([A-Z][A-Za-z0-9-]{2,})",
            text,
            flags=re.IGNORECASE,
        )
        return dedupe(matches[:5])

    def _detect_tasks(self, text: str) -> list[str]:
        lower = text.lower()
        tasks = [
            task
            for task, keywords in self.TASK_KEYWORDS.items()
            if any(keyword in lower for keyword in keywords)
        ]
        return dedupe(tasks[:5])

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
        return dedupe(tags)

    def _build_why_it_matters(
        self,
        payload: AnalysisInput,
        claims: list[str],
        summary_short: str,
    ) -> str:
        if claims:
            return trim_sentence(claims[0], 300)
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
        return dedupe(questions[:4])

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
