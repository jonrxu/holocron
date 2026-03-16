from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from holocron.extractor import ExtractedPaper
from holocron.service import HolocronService

from support import DeterministicEmbeddingProvider, SequenceExtractor, StructuredAnalyzer, make_settings


class HolocronSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        extractor = SequenceExtractor(
            [
                ExtractedPaper(
                    title="Transformer Retrieval",
                    authors=["A. Ranker"],
                    year=2024,
                    abstract="Transformer retrieval for scientific search.",
                    full_text="Transformer retrieval improves ranking on ArxivBench.",
                    page_count=1,
                    metadata={},
                ),
                ExtractedPaper(
                    title="Protein Modeling Survey",
                    authors=["B. Biologist"],
                    year=2023,
                    abstract="Survey of protein modeling methods.",
                    full_text="Protein modeling survey across datasets and methods.",
                    page_count=1,
                    metadata={},
                ),
                ExtractedPaper(
                    title="Retrieval Benchmark",
                    authors=["C. Ranker"],
                    year=2022,
                    abstract="Benchmark for retrieval systems.",
                    full_text="Retrieval benchmark with ArxivBench and ranking baselines.",
                    page_count=1,
                    metadata={},
                ),
            ]
        )
        self.service = HolocronService(
            make_settings(root),
            extractor=extractor,
            analyzer=StructuredAnalyzer(),
            embedding_provider=DeterministicEmbeddingProvider(),
            worker_enabled=False,
        )
        self.service.start()

        self.paper_ids = []
        for index in range(3):
            paper = self.service.ingest_upload(f"paper-{index}.pdf", f"%PDF-{index}".encode("utf-8"))
            self.paper_ids.append(paper["id"])
            self.service.process_paper(paper["id"])

    def tearDown(self) -> None:
        self.service.stop()
        self.temp_dir.cleanup()

    def test_query_library_matches_title_and_summary(self) -> None:
        result = self.service.query_library(query="transformer")
        self.assertEqual(result["papers"][0]["title"], "Transformer Retrieval")
        self.assertGreater(result["papers"][0]["semantic_score"], 0.0)

    def test_query_library_indexes_notes(self) -> None:
        self.service.add_note(self.paper_ids[2], "Contains a strong policy gradient sketch.", page_number=4)
        result = self.service.query_library(query="gradient")
        self.assertEqual(len(result["papers"]), 1)
        self.assertEqual(result["papers"][0]["title"], "Retrieval Benchmark")
