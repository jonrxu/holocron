from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExtractedPaper:
    title: str | None
    authors: list[str]
    year: int | None
    abstract: str | None
    full_text: str
    page_count: int | None
    metadata: dict[str, str]


class PdfExtractor:
    def extract(self, pdf_path: Path) -> ExtractedPaper:
        metadata = self._read_pdfinfo(pdf_path)
        full_text = self._read_text(pdf_path)
        title = self._clean_title(metadata.get("Title")) or self._guess_title(full_text)
        authors = self._parse_authors(metadata.get("Author")) or self._guess_authors(full_text)
        year = self._extract_year(metadata)
        abstract = self._extract_abstract(full_text)
        page_count = self._parse_page_count(metadata.get("Pages"))
        return ExtractedPaper(
            title=title,
            authors=authors,
            year=year,
            abstract=abstract,
            full_text=full_text,
            page_count=page_count,
            metadata=metadata,
        )

    def _read_pdfinfo(self, pdf_path: Path) -> dict[str, str]:
        result = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        metadata: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
        return metadata

    def _read_text(self, pdf_path: Path) -> str:
        result = subprocess.run(
            ["pdftotext", "-layout", "-nopgbrk", "-q", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            check=True,
        )
        text = result.stdout.replace("\x0c", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _clean_title(self, title: str | None) -> str | None:
        if not title:
            return None
        cleaned = " ".join(title.split())
        if not cleaned or cleaned.lower() == "untitled":
            return None
        return cleaned

    def _guess_title(self, full_text: str) -> str | None:
        for line in full_text.splitlines():
            candidate = " ".join(line.split())
            if 12 <= len(candidate) <= 180:
                return candidate
        return None

    def _parse_authors(self, author_value: str | None) -> list[str]:
        if not author_value:
            return []
        cleaned = author_value.replace(";", ",")
        parts = re.split(r",| and ", cleaned)
        authors = [part.strip() for part in parts if part.strip()]
        return authors[:12]

    def _guess_authors(self, full_text: str) -> list[str]:
        lines = [line.strip() for line in full_text.splitlines() if line.strip()]
        if len(lines) < 2:
            return []
        for candidate in lines[1:4]:
            if "@" in candidate:
                continue
            if len(candidate) > 120:
                continue
            if re.search(r"[A-Z][a-z]+ [A-Z][a-z]+", candidate):
                pieces = re.split(r",| and ", candidate)
                authors = [piece.strip() for piece in pieces if piece.strip()]
                if authors:
                    return authors[:8]
        return []

    def _extract_year(self, metadata: dict[str, str]) -> int | None:
        for key in ("CreationDate", "ModDate"):
            value = metadata.get(key)
            if not value:
                continue
            match = re.search(r"(19|20)\d{2}", value)
            if match:
                return int(match.group(0))
        return None

    def _parse_page_count(self, page_value: str | None) -> int | None:
        if not page_value:
            return None
        try:
            return int(page_value)
        except ValueError:
            return None

    def _extract_abstract(self, full_text: str) -> str | None:
        match = re.search(
            r"\babstract\b[\s:.-]*(.+?)(?:\n\s*\n|\b1\s+introduction\b|\bintroduction\b)",
            full_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return None
        abstract = " ".join(match.group(1).split())
        return abstract[:2000] if abstract else None
