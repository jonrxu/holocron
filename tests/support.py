from __future__ import annotations

from pathlib import Path

from holocron.analysis import AnalysisResult
from holocron.config import Settings
from holocron.extractor import ExtractedPaper


def make_settings(root: Path, **overrides: object) -> Settings:
    values = {
        "data_dir": root / "data",
        "database_path": root / "data" / "holocron.db",
        "blob_dir": root / "blob-store",
        "analyzer_command": None,
    }
    values.update(overrides)
    return Settings(**values)


class FakeExtractor:
    def extract(self, pdf_path: Path) -> ExtractedPaper:
        del pdf_path
        text = (
            "Holocron Research Memory\n\n"
            "Abstract This paper presents a lightweight system for storing scientific papers. "
            "We show that background analysis improves recall and note taking. "
            "Our method uses a shared drive dataset called LabCorpus."
        )
        return ExtractedPaper(
            title="Holocron Research Memory",
            authors=["J. Xu", "A. Researcher"],
            year=2026,
            abstract=(
                "This paper presents a lightweight system for storing scientific papers and "
                "shows that background analysis improves recall."
            ),
            full_text=text,
            page_count=1,
            metadata={"Pages": "1"},
        )


class FakeAnalyzer:
    def analyze(self, payload):  # noqa: ANN001
        del payload
        return AnalysisResult(
            summary_short="A lightweight system for storing and revisiting scientific papers.",
            summary_long=(
                "The paper proposes a lightweight personal research memory. "
                "It stores PDFs, generates briefs, and supports notes."
            ),
            why_it_matters="It helps prevent papers from disappearing into Downloads.",
            method_summary="Store the PDF, extract text, generate a brief, then keep notes and events.",
            limitations=["The prototype focuses on a single-user workflow."],
            claims=["Background analysis improves recall and note-taking."],
            datasets=["LabCorpus"],
            tasks=["retrieval"],
            tags=["status:unread", "domain:ml", "status:important"],
            followup_questions=["What prior work should this system be compared against?"],
            confidence=0.88,
            version="fake-analyzer-v1",
        )


class SequenceExtractor:
    def __init__(self, papers: list[ExtractedPaper]) -> None:
        self.papers = list(papers)

    def extract(self, pdf_path: Path) -> ExtractedPaper:
        del pdf_path
        return self.papers.pop(0)


class StructuredAnalyzer:
    def analyze(self, payload):  # noqa: ANN001
        title = (payload.title or "").lower()
        if "transformer" in title:
            return AnalysisResult(
                summary_short="Transformer retrieval model for scientific ranking.",
                summary_long="A machine learning paper about transformer-based retrieval.",
                why_it_matters="Useful for search-heavy workflows.",
                method_summary="Train a transformer encoder for document ranking.",
                limitations=["Focused on one benchmark."],
                claims=["Transformer retrieval improves ranking quality."],
                datasets=["ArxivBench"],
                tasks=["retrieval"],
                tags=["status:unread", "domain:ml", "paper_type:methods", "task:retrieval"],
                followup_questions=["How does it compare to dense retrieval baselines?"],
                confidence=0.9,
                version="structured-v1",
            )
        if "benchmark" in title:
            return AnalysisResult(
                summary_short="Benchmark paper for retrieval systems.",
                summary_long="A retrieval benchmark paper evaluated on ArxivBench.",
                why_it_matters="Useful for comparing search models.",
                method_summary="Benchmark multiple retrieval systems on a shared dataset.",
                limitations=["Benchmark scope is narrow."],
                claims=["The benchmark exposes meaningful gaps between retrieval systems."],
                datasets=["ArxivBench"],
                tasks=["retrieval"],
                tags=["status:unread", "domain:ml", "paper_type:benchmark", "task:retrieval"],
                followup_questions=["Which newer retrieval benchmarks should be added?"],
                confidence=0.91,
                version="structured-v1",
            )
        if "protein" in title:
            return AnalysisResult(
                summary_short="Survey of protein modeling systems.",
                summary_long="A biology survey covering recent protein modeling methods.",
                why_it_matters="Good overview paper for the space.",
                method_summary="Survey and taxonomy of protein models.",
                limitations=["Not an empirical benchmark paper."],
                claims=["The survey organizes the field into useful categories."],
                datasets=["ProteinSet"],
                tasks=["classification"],
                tags=["status:unread", "domain:biology", "paper_type:survey"],
                followup_questions=["Which newer protein benchmarks are missing?"],
                confidence=0.92,
                version="structured-v1",
            )
        return AnalysisResult(
            summary_short="Robotics control system with notes-friendly writeup.",
            summary_long="A robotics paper focused on controller design and evaluation.",
            why_it_matters="Useful for control and deployment workflows.",
            method_summary="Evaluate a learned controller in simulation.",
            limitations=["Only tested in a narrow environment."],
            claims=["The controller improves stability under shift."],
            datasets=["RoboArena"],
            tasks=["classification"],
            tags=["status:unread", "domain:robotics", "paper_type:empirical"],
            followup_questions=["Does it transfer out of simulation?"],
            confidence=0.85,
            version="structured-v1",
        )


class DeterministicEmbeddingProvider:
    version = "deterministic-test-v1"

    def _embed(self, text: str) -> list[float]:
        lower = text.lower()
        vector = [
            1.0 if any(keyword in lower for keyword in ["transformer", "retrieval", "rank"]) else 0.0,
            1.0 if any(keyword in lower for keyword in ["protein", "biology"]) else 0.0,
            1.0 if any(keyword in lower for keyword in ["benchmark", "arxivbench"]) else 0.0,
            1.0 if "robot" in lower else 0.0,
        ]
        norm = sum(value * value for value in vector) ** 0.5
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def embed_document(self, document):  # noqa: ANN001
        return self._embed(f"{document.title or ''} {document.text}")

    def embed_query(self, query: str) -> list[float]:
        return self._embed(query)


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read(self) -> bytes:
        import json

        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001, ANN204
        del exc_type, exc, tb
        return False
