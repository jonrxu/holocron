from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .analysis_common import split_sentences, trim_sentence


@dataclass
class PaperChunk:
    chunk_index: int
    text: str
    score: float = 0.0


@dataclass
class AnswerResult:
    answer: str
    model: str


def split_text_into_chunks(text: str, max_chars: int = 1400, overlap_chars: int = 220) -> list[str]:
    # Preserve paragraph boundaries when possible so retrieved chunks stay readable in chat.
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(_split_long_paragraph(paragraph, max_chars=max_chars, overlap_chars=overlap_chars))
            continue
        if not current:
            current = paragraph
            continue
        candidate = f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current.strip())
            overlap = current[-overlap_chars:].strip()
            current = f"{overlap}\n\n{paragraph}".strip() if overlap else paragraph
            if len(current) > max_chars:
                chunks.extend(_split_long_paragraph(current, max_chars=max_chars, overlap_chars=overlap_chars))
                current = ""

    if current:
        chunks.append(current.strip())
    return [chunk for chunk in chunks if chunk]


def _split_long_paragraph(paragraph: str, max_chars: int, overlap_chars: int) -> list[str]:
    sentences = split_sentences(paragraph) or [paragraph.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current.strip())
            overlap = current[-overlap_chars:].strip()
            current = f"{overlap} {sentence}".strip() if overlap else sentence
        else:
            chunks.append(sentence[:max_chars].strip())
            current = sentence[max_chars - overlap_chars:].strip()
    if current:
        chunks.append(current.strip())
    return [chunk for chunk in chunks if chunk]


class HeuristicAnswerer:
    model = "extractive-v1"

    def answer_question(self, paper_title: str, question: str, contexts: list[PaperChunk]) -> AnswerResult:
        del paper_title
        query_tokens = {
            token.lower()
            for token in re.findall(r"[A-Za-z0-9_]+", question)
            if len(token) >= 4
        }

        ranked_sentences: list[tuple[int, int, str]] = []
        for chunk in contexts:
            for sentence in split_sentences(chunk.text)[:8]:
                sentence_lower = sentence.lower()
                score = sum(1 for token in query_tokens if token in sentence_lower)
                ranked_sentences.append((score, chunk.chunk_index, sentence))

        ranked_sentences.sort(key=lambda item: (item[0], -item[1], len(item[2])), reverse=True)
        picked: list[tuple[int, str]] = []
        seen: set[str] = set()
        for score, index, sentence in ranked_sentences:
            if score <= 0 and picked:
                continue
            normalized = sentence.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            picked.append((index, trim_sentence(sentence)))
            if len(picked) == 3:
                break

        if not picked and contexts:
            picked.append((contexts[0].chunk_index, trim_sentence(contexts[0].text)))

        if not picked:
            answer = "I could not find enough extracted text to answer that question yet."
        else:
            lines = [f"{sentence} [{index}]" for index, sentence in picked]
            answer = " ".join(lines)

        return AnswerResult(answer=answer, model=self.model)


class GeminiAnswerer:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash-lite",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds: int = 30,
        opener: Callable[..., object] = urllib.request.urlopen,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.opener = opener

    def answer_question(self, paper_title: str, question: str, contexts: list[PaperChunk]) -> AnswerResult:
        excerpts = []
        for chunk in contexts:
            excerpts.append(f"[{chunk.chunk_index}] {chunk.text.strip()}")

        prompt = "\n\n".join(
            [
                "Answer the question using only the excerpts below from one scientific paper.",
                "Be concise and specific. If the excerpts are insufficient, say so.",
                "When you rely on an excerpt, cite it with bracketed numbers like [1] or [2].",
                f"Paper title: {paper_title or 'Untitled paper'}",
                f"Question: {question.strip()}",
                "Excerpts:",
                "\n\n".join(excerpts),
            ]
        )
        request = urllib.request.Request(
            f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}",
            data=json.dumps(
                {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": prompt}],
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.2,
                    },
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.opener(request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))

        candidates = body.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned no candidates.")
        parts = candidates[0].get("content", {}).get("parts", [])
        answer = "\n".join(str(part.get("text", "")).strip() for part in parts if part.get("text")).strip()
        if not answer:
            raise ValueError("Gemini returned an empty answer.")
        return AnswerResult(answer=answer, model=self.model)


class FallbackAnswerer:
    def __init__(self, primary: object, fallback: object) -> None:
        self.primary = primary
        self.fallback = fallback

    def answer_question(self, paper_title: str, question: str, contexts: list[PaperChunk]) -> AnswerResult:
        try:
            return self.primary.answer_question(paper_title, question, contexts)
        except Exception:
            return self.fallback.answer_question(paper_title, question, contexts)
