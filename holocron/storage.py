from __future__ import annotations

from pathlib import Path


class FileSystemBlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def build_key(self, checksum: str) -> str:
        return f"papers/raw/sha256/{checksum}.pdf"

    def put_pdf(self, checksum: str, pdf_bytes: bytes) -> str:
        key = self.build_key(checksum)
        destination = self.root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            temp_path = destination.with_suffix(".tmp")
            temp_path.write_bytes(pdf_bytes)
            temp_path.replace(destination)
        return key

    def path_for_key(self, key: str) -> Path:
        return self.root / key
