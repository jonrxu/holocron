from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from holocron.service import HolocronService

from support import DeterministicEmbeddingProvider, FakeAnalyzer, FakeExtractor, make_settings


class HolocronServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.service = HolocronService(
            make_settings(root),
            extractor=FakeExtractor(),
            analyzer=FakeAnalyzer(),
            embedding_provider=DeterministicEmbeddingProvider(),
            worker_enabled=False,
        )
        self.service.start()

    def tearDown(self) -> None:
        self.service.stop()
        self.temp_dir.cleanup()

    def test_ingest_process_and_note_flow(self) -> None:
        paper = self.service.ingest_upload("sample.pdf", b"%PDF-1.4 sample")
        self.service.process_paper(paper["id"])

        detail = self.service.get_paper(paper["id"])
        self.assertEqual(detail["status"], "ready")
        self.assertEqual(detail["title"], "Holocron Research Memory")
        self.assertIn("lightweight system", detail["summary_short"])
        self.assertIn("status:important", detail["tags"])

        updated = self.service.add_note(paper["id"], "Useful architecture sketch.", page_number=2)
        self.assertEqual(updated["note_count"], 1)
        self.assertEqual(updated["notes"][0]["page_number"], 2)

    def test_duplicate_upload_reuses_existing_paper(self) -> None:
        first = self.service.ingest_upload("sample.pdf", b"%PDF-1.4 sample")
        second = self.service.ingest_upload("copy.pdf", b"%PDF-1.4 sample")

        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(len(self.service.list_papers()), 1)

    def test_list_papers_returns_minimal_records(self) -> None:
        paper = self.service.ingest_upload("sample.pdf", b"%PDF-1.4 sample")
        self.service.process_paper(paper["id"])
        record = self.service.list_papers()[0]

        self.assertEqual(record["title"], "Holocron Research Memory")
        self.assertIn("summary_short", record)
        self.assertNotIn("tags", record)
