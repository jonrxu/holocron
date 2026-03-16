from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from holocron.analysis import AnalysisResult
from holocron.config import Settings
from holocron.extractor import ExtractedPaper, PdfExtractor
from holocron.service import HolocronService


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


class HolocronServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        settings = Settings(
            data_dir=root / "data",
            database_path=root / "data" / "holocron.db",
            blob_dir=root / "blob-store",
            analyzer_command=None,
        )
        self.service = HolocronService(
            settings,
            extractor=FakeExtractor(),
            analyzer=FakeAnalyzer(),
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
        self.assertIn("Background analysis improves recall", detail["claims"][0])
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

    def test_review_queue_flags_low_confidence_items(self) -> None:
        paper = self.service.ingest_upload("sample.pdf", b"%PDF-1.4 sample")
        self.service.process_paper(paper["id"])
        queue_items = self.service.list_review_queue()
        self.assertEqual(len(queue_items), 1)
        self.assertIn("Marked important but still has no notes.", queue_items[0]["reasons"])


class PdfExtractorTests(unittest.TestCase):
    def test_extractor_reads_text_from_generated_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "sample.txt"
            pdf_path = root / "sample.pdf"
            source.write_text(
                "Holocron Sample Paper\n\n"
                "Abstract\n"
                "This paper presents a lightweight archive for scientific papers.\n\n"
                "Introduction\n"
                "We show that storing summaries with notes improves recall.\n",
                encoding="utf-8",
            )
            with pdf_path.open("wb") as output_file:
                subprocess.run(
                    ["cupsfilter", "-m", "application/pdf", str(source)],
                    check=True,
                    stdout=output_file,
                    stderr=subprocess.DEVNULL,
                )

            result = PdfExtractor().extract(pdf_path)

            self.assertIn("lightweight archive", result.full_text.lower())
            self.assertTrue(result.title)
            self.assertGreaterEqual(result.page_count or 0, 1)


if __name__ == "__main__":
    unittest.main()
