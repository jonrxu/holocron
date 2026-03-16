from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from holocron.extractor import ExtractedPaper
from holocron.service import HolocronService

from support import DeterministicEmbeddingProvider, SequenceExtractor, StructuredAnalyzer, make_settings


class HolocronMapTests(unittest.TestCase):
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
                    title="Retrieval Benchmark",
                    authors=["C. Ranker"],
                    year=2022,
                    abstract="Benchmark for retrieval systems.",
                    full_text="Retrieval benchmark with ArxivBench and ranking baselines.",
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
            paper = self.service.ingest_upload(f"graph-{index}.pdf", f"%PDF-g-{index}".encode("utf-8"))
            self.paper_ids.append(paper["id"])
            self.service.process_paper(paper["id"])

    def tearDown(self) -> None:
        self.service.stop()
        self.temp_dir.cleanup()

    def test_paper_detail_is_trimmed_to_basic_fields(self) -> None:
        detail = self.service.get_paper(self.paper_ids[0])
        self.assertEqual(detail["title"], "Transformer Retrieval")
        self.assertIn("tags", detail)
        self.assertIn("notes", detail)
        self.assertNotIn("graph", detail)
        self.assertNotIn("events", detail)

    def test_query_library_includes_corpus_graph(self) -> None:
        result = self.service.query_library()
        graph = result["graph"]

        self.assertEqual(len(graph["nodes"]), 3)
        self.assertNotIn("edges", graph)
        self.assertTrue(any(node["title"] == "Transformer Retrieval" for node in graph["nodes"]))
        self.assertTrue(all(node["x"] is not None for node in graph["nodes"]))
        self.assertTrue(all(node["y"] is not None for node in graph["nodes"]))
