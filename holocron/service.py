from __future__ import annotations

import hashlib
import json
import queue
import threading
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .analysis import AnalysisInput, ExternalCommandAnalyzer, HeuristicAnalyzer
from .config import Settings
from .database import Database
from .extractor import PdfExtractor
from .storage import FileSystemBlobStore


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def dumps_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def loads_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


class HolocronService:
    def __init__(
        self,
        settings: Settings,
        database: Database | None = None,
        storage: FileSystemBlobStore | None = None,
        extractor: PdfExtractor | None = None,
        analyzer: Any | None = None,
        worker_enabled: bool = True,
    ) -> None:
        self.settings = settings
        self.database = database or Database(settings.database_path)
        self.storage = storage or FileSystemBlobStore(settings.blob_dir)
        self.extractor = extractor or PdfExtractor()
        self.analyzer = analyzer or self._build_analyzer()
        self.worker_enabled = worker_enabled
        self._queue: queue.Queue[int | None] = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None

    def _build_analyzer(self) -> Any:
        if self.settings.analyzer_command:
            return ExternalCommandAnalyzer(self.settings.analyzer_command)
        return HeuristicAnalyzer()

    def start(self) -> None:
        self.database.initialize()
        self.storage.initialize()
        if not self.worker_enabled:
            return
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        self.recover_pending_jobs()

    def stop(self) -> None:
        if not self.worker_enabled:
            return
        self._stop_event.set()
        self._queue.put(None)
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=2.0)

    def recover_pending_jobs(self) -> None:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id FROM papers WHERE status IN ('queued', 'processing') ORDER BY added_at ASC"
            ).fetchall()
        for row in rows:
            self.enqueue_analysis(int(row["id"]))

    def enqueue_analysis(self, paper_id: int) -> None:
        if self.worker_enabled:
            self._queue.put(paper_id)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            paper_id = self._queue.get()
            if paper_id is None:
                self._queue.task_done()
                return
            try:
                self.process_paper(paper_id)
            finally:
                self._queue.task_done()

    def ingest_upload(
        self,
        filename: str,
        payload: bytes,
        source_type: str = "upload",
        source_value: str | None = None,
    ) -> dict[str, Any]:
        checksum = hashlib.sha256(payload).hexdigest()
        storage_key = self.storage.put_pdf(checksum, payload)
        now = utc_now()

        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM papers WHERE checksum = ?",
                (checksum,),
            ).fetchone()
            if existing:
                paper_id = int(existing["id"])
                self._insert_event(
                    connection,
                    paper_id,
                    "ingested",
                    {
                        "duplicate": True,
                        "source_type": source_type,
                        "source_value": source_value or filename,
                    },
                )
                connection.commit()
                paper = self.get_paper(paper_id)
                paper["duplicate"] = True
                return paper

            cursor = connection.execute(
                """
                INSERT INTO papers (
                    checksum, storage_key, source_type, source_value, original_filename,
                    status, added_at
                ) VALUES (?, ?, ?, ?, ?, 'queued', ?)
                """,
                (
                    checksum,
                    storage_key,
                    source_type,
                    source_value,
                    filename,
                    now,
                ),
            )
            paper_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO paper_artifacts (
                    paper_id, extracted_text, text_excerpt, summary_short, summary_long,
                    why_it_matters, method_summary, limitations_json, claims_json,
                    datasets_json, tasks_json, tags_json, followup_questions_json,
                    analysis_version, analysis_confidence, updated_at
                ) VALUES (?, '', '', '', '', '', '', '[]', '[]', '[]', '[]', '[]', '[]', '', 0.0, ?)
                """,
                (paper_id, now),
            )
            self._insert_event(
                connection,
                paper_id,
                "ingested",
                {
                    "duplicate": False,
                    "filename": filename,
                    "source_type": source_type,
                    "source_value": source_value or filename,
                },
            )
            connection.commit()

        self.enqueue_analysis(paper_id)
        return self.get_paper(paper_id)

    def ingest_url(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": "Holocron/0.1"})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
        filename = Path(urlparse(url).path).name or "downloaded-paper.pdf"
        return self.ingest_upload(
            filename=filename,
            payload=payload,
            source_type="url",
            source_value=url,
        )

    def process_paper(self, paper_id: int) -> None:
        with self.database.connect() as connection:
            paper = connection.execute(
                "SELECT * FROM papers WHERE id = ?",
                (paper_id,),
            ).fetchone()
            if not paper:
                return
            connection.execute(
                "UPDATE papers SET status = 'processing', analysis_error = NULL WHERE id = ?",
                (paper_id,),
            )
            connection.commit()

        try:
            extracted = self.extractor.extract(self.storage.path_for_key(paper["storage_key"]))
            analysis = self.analyzer.analyze(
                AnalysisInput(
                    title=extracted.title or paper["title"],
                    authors=extracted.authors,
                    year=extracted.year,
                    abstract=extracted.abstract,
                    full_text=extracted.full_text[: self.settings.max_text_chars],
                )
            )
            status = "ready" if analysis.confidence >= 0.6 else "needs_review"
            now = utc_now()

            with self.database.connect() as connection:
                connection.execute(
                    """
                    UPDATE papers
                    SET title = COALESCE(NULLIF(title, ''), ?),
                        authors_json = CASE
                            WHEN authors_json = '[]' THEN ?
                            ELSE authors_json
                        END,
                        year = COALESCE(year, ?),
                        abstract = COALESCE(NULLIF(abstract, ''), ?),
                        status = ?,
                        analysis_error = NULL
                    WHERE id = ?
                    """,
                    (
                        extracted.title,
                        dumps_json(extracted.authors),
                        extracted.year,
                        extracted.abstract,
                        status,
                        paper_id,
                    ),
                )
                connection.execute(
                    """
                    UPDATE paper_artifacts
                    SET extracted_text = ?,
                        text_excerpt = ?,
                        summary_short = ?,
                        summary_long = ?,
                        why_it_matters = ?,
                        method_summary = ?,
                        limitations_json = ?,
                        claims_json = ?,
                        datasets_json = ?,
                        tasks_json = ?,
                        tags_json = ?,
                        followup_questions_json = ?,
                        analysis_version = ?,
                        analysis_confidence = ?,
                        updated_at = ?
                    WHERE paper_id = ?
                    """,
                    (
                        extracted.full_text,
                        extracted.full_text[:2000],
                        analysis.summary_short,
                        analysis.summary_long,
                        analysis.why_it_matters,
                        analysis.method_summary,
                        dumps_json(analysis.limitations),
                        dumps_json(analysis.claims),
                        dumps_json(analysis.datasets),
                        dumps_json(analysis.tasks),
                        dumps_json(analysis.tags),
                        dumps_json(analysis.followup_questions),
                        analysis.version,
                        analysis.confidence,
                        now,
                        paper_id,
                    ),
                )
                self._insert_event(
                    connection,
                    paper_id,
                    "analyzed",
                    {
                        "analysis_version": analysis.version,
                        "confidence": analysis.confidence,
                        "status": status,
                    },
                )
                connection.commit()
        except Exception as error:
            with self.database.connect() as connection:
                connection.execute(
                    "UPDATE papers SET status = 'needs_review', analysis_error = ? WHERE id = ?",
                    (str(error), paper_id),
                )
                self._insert_event(
                    connection,
                    paper_id,
                    "analysis_failed",
                    {"error": str(error)},
                )
                connection.commit()

    def list_papers(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    papers.*,
                    paper_artifacts.summary_short,
                    paper_artifacts.tags_json,
                    paper_artifacts.analysis_confidence,
                    COUNT(notes.id) AS note_count
                FROM papers
                LEFT JOIN paper_artifacts ON paper_artifacts.paper_id = papers.id
                LEFT JOIN notes ON notes.paper_id = papers.id
                GROUP BY papers.id
                ORDER BY papers.added_at DESC
                """
            ).fetchall()
        return [self._serialize_paper_list_item(row) for row in rows]

    def get_paper(self, paper_id: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            paper_row = connection.execute(
                """
                SELECT papers.*, paper_artifacts.*
                FROM papers
                LEFT JOIN paper_artifacts ON paper_artifacts.paper_id = papers.id
                WHERE papers.id = ?
                """,
                (paper_id,),
            ).fetchone()
            if not paper_row:
                raise KeyError(f"Paper {paper_id} not found")
            notes = connection.execute(
                "SELECT * FROM notes WHERE paper_id = ? ORDER BY created_at DESC",
                (paper_id,),
            ).fetchall()
            events = connection.execute(
                "SELECT * FROM events WHERE paper_id = ? ORDER BY created_at DESC",
                (paper_id,),
            ).fetchall()

        return self._serialize_paper_detail(paper_row, notes, events)

    def add_note(self, paper_id: int, body: str, page_number: int | None = None) -> dict[str, Any]:
        body = body.strip()
        if not body:
            raise ValueError("Note body cannot be empty.")
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO notes (paper_id, author_type, body, page_number, created_at)
                VALUES (?, 'user', ?, ?, ?)
                """,
                (paper_id, body, page_number, now),
            )
            connection.execute(
                "UPDATE papers SET last_reviewed_at = ? WHERE id = ?",
                (now, paper_id),
            )
            self._insert_event(
                connection,
                paper_id,
                "annotated",
                {"page_number": page_number},
            )
            connection.commit()
        return self.get_paper(paper_id)

    def mark_opened(self, paper_id: int) -> dict[str, Any]:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE papers SET last_opened_at = ? WHERE id = ?",
                (now, paper_id),
            )
            self._insert_event(connection, paper_id, "opened", {})
            connection.commit()
        return self.get_paper(paper_id)

    def toggle_tag(self, paper_id: int, tag: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT tags_json FROM paper_artifacts WHERE paper_id = ?",
                (paper_id,),
            ).fetchone()
            if not row:
                raise KeyError(f"Paper {paper_id} not found")
            tags = loads_json(row["tags_json"], [])
            if tag in tags:
                tags = [item for item in tags if item != tag]
            else:
                tags.append(tag)
            connection.execute(
                "UPDATE paper_artifacts SET tags_json = ?, updated_at = ? WHERE paper_id = ?",
                (dumps_json(tags), utc_now(), paper_id),
            )
            self._insert_event(connection, paper_id, "tag_corrected", {"tag": tag})
            connection.commit()
        return self.get_paper(paper_id)

    def list_review_queue(self) -> list[dict[str, Any]]:
        papers = self.list_papers()
        review_cutoff = datetime.now(UTC) - timedelta(days=self.settings.review_after_days)
        queue_items: list[dict[str, Any]] = []
        for paper in papers:
            reasons: list[str] = []
            added_at = datetime.fromisoformat(paper["added_at"])
            tags = paper["tags"]
            if paper["status"] == "needs_review":
                reasons.append("Analysis confidence was low or extraction failed.")
            if paper["last_opened_at"] is None and added_at <= review_cutoff:
                reasons.append(
                    f"Paper has been unread for more than {self.settings.review_after_days} days."
                )
            if "status:important" in tags and paper["note_count"] == 0:
                reasons.append("Marked important but still has no notes.")
            if reasons:
                queue_items.append(
                    {
                        "paper_id": paper["id"],
                        "title": paper["title"] or paper["original_filename"] or "Untitled paper",
                        "status": paper["status"],
                        "reasons": reasons,
                        "tags": tags,
                    }
                )
        return queue_items

    def open_pdf(self, paper_id: int) -> tuple[Path, str]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT storage_key, original_filename FROM papers WHERE id = ?",
                (paper_id,),
            ).fetchone()
        if not row:
            raise KeyError(f"Paper {paper_id} not found")
        filename = row["original_filename"] or f"paper-{paper_id}.pdf"
        return self.storage.path_for_key(row["storage_key"]), filename

    def _insert_event(
        self,
        connection: Any,
        paper_id: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO events (paper_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (paper_id, event_type, dumps_json(payload), utc_now()),
        )

    def _serialize_paper_list_item(self, row: Any) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "title": row["title"],
            "original_filename": row["original_filename"],
            "status": row["status"],
            "added_at": row["added_at"],
            "last_opened_at": row["last_opened_at"],
            "summary_short": row["summary_short"],
            "analysis_confidence": row["analysis_confidence"],
            "tags": loads_json(row["tags_json"], []),
            "note_count": int(row["note_count"] or 0),
        }

    def _serialize_paper_detail(
        self,
        row: Any,
        notes: list[Any],
        events: list[Any],
    ) -> dict[str, Any]:
        tags = loads_json(row["tags_json"], [])
        return {
            "id": int(row["id"]),
            "title": row["title"],
            "original_filename": row["original_filename"],
            "source_type": row["source_type"],
            "source_value": row["source_value"],
            "status": row["status"],
            "analysis_error": row["analysis_error"],
            "added_at": row["added_at"],
            "last_opened_at": row["last_opened_at"],
            "last_reviewed_at": row["last_reviewed_at"],
            "authors": loads_json(row["authors_json"], []),
            "year": row["year"],
            "abstract": row["abstract"],
            "summary_short": row["summary_short"],
            "summary_long": row["summary_long"],
            "why_it_matters": row["why_it_matters"],
            "method_summary": row["method_summary"],
            "limitations": loads_json(row["limitations_json"], []),
            "claims": loads_json(row["claims_json"], []),
            "datasets": loads_json(row["datasets_json"], []),
            "tasks": loads_json(row["tasks_json"], []),
            "tags": tags,
            "followup_questions": loads_json(row["followup_questions_json"], []),
            "analysis_version": row["analysis_version"],
            "analysis_confidence": row["analysis_confidence"],
            "text_excerpt": row["text_excerpt"],
            "file_url": f"/api/papers/{int(row['id'])}/file",
            "note_count": len(notes),
            "notes": [
                {
                    "id": int(note["id"]),
                    "body": note["body"],
                    "page_number": note["page_number"],
                    "created_at": note["created_at"],
                }
                for note in notes
            ],
            "events": [
                {
                    "id": int(event["id"]),
                    "event_type": event["event_type"],
                    "payload": loads_json(event["payload_json"], {}),
                    "created_at": event["created_at"],
                }
                for event in events
            ],
        }
