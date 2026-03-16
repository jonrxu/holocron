from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from holocron.extractor import PdfExtractor


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
