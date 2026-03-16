from __future__ import annotations

import hashlib
import queue
import threading
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .analysis import (
    AnalysisInput,
    ExternalCommandAnalyzer,
    FallbackAnalyzer,
    HeuristicAnalyzer,
    OpenAIAnalyzer,
)
from .config import Settings
from .database import Database
from .embedding import (
    DocumentEmbeddingInput,
    FallbackEmbeddingProvider,
    GeminiEmbeddingProvider,
    LocalEmbeddingProvider,
)
from .extractor import PdfExtractor
from .library import (
    build_embedding_text,
    dumps_json,
    get_library_graph,
    rank_rows_by_embedding,
    rebuild_embedding_map,
    reindex_paper,
    search_rows,
    serialize_paper_detail,
    serialize_paper_list_item,
    utc_now,
)
from .storage import FileSystemBlobStore


class HolocronService:
    def __init__(
        self,
        settings: Settings,
        database: Database | None = None,
        storage: FileSystemBlobStore | None = None,
        extractor: PdfExtractor | None = None,
        analyzer: Any | None = None,
        embedding_provider: Any | None = None,
        worker_enabled: bool = True,
    ) -> None:
        self.settings = settings
        self.database = database or Database(settings.database_path)
        self.storage = storage or FileSystemBlobStore(settings.blob_dir)
        self.extractor = extractor or PdfExtractor()
        self.analyzer = analyzer or self._build_analyzer()
        self.embedding_provider = embedding_provider or self._build_embedding_provider()
        self.worker_enabled = worker_enabled
        self._queue: queue.Queue[int | None] = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None

    def _build_analyzer(self) -> Any:
        if self.settings.analyzer_command:
            return ExternalCommandAnalyzer(self.settings.analyzer_command)
        heuristic = HeuristicAnalyzer()
        if self.settings.openai_api_key:
            return FallbackAnalyzer(
                OpenAIAnalyzer(
                    api_key=self.settings.openai_api_key,
                    model=self.settings.openai_model,
                    base_url=self.settings.openai_base_url,
                    timeout_seconds=self.settings.openai_timeout_seconds,
                    reasoning_effort=self.settings.openai_reasoning_effort,
                ),
                heuristic,
                label="openai",
            )
        return heuristic

    def _build_embedding_provider(self) -> Any:
        local_provider = LocalEmbeddingProvider()
        if self.settings.gemini_api_key:
            return FallbackEmbeddingProvider(
                GeminiEmbeddingProvider(
                    api_key=self.settings.gemini_api_key,
                    model=self.settings.gemini_embedding_model,
                    base_url=self.settings.gemini_embedding_base_url,
                    output_dimensionality=self.settings.gemini_embedding_dimensions,
                    timeout_seconds=self.settings.gemini_timeout_seconds,
                ),
                local_provider,
            )
        return local_provider

    def start(self) -> None:
        self.database.initialize()
        self.storage.initialize()
        self.rebuild_search_indexes()
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
            reindex_paper(connection, paper_id)
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
            embedding_input = DocumentEmbeddingInput(
                title=extracted.title or paper["title"],
                text=build_embedding_text(extracted.abstract, analysis, extracted.full_text),
            )
            embedding = self.embedding_provider.embed_document(embedding_input)
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
                        embedding_json = ?,
                        embedding_model = ?,
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
                        dumps_json(embedding),
                        getattr(self.embedding_provider, "version", "embedding"),
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
                reindex_paper(connection, paper_id)
                rebuild_embedding_map(connection)
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

    def rebuild_search_indexes(self) -> None:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT id FROM papers ORDER BY id ASC").fetchall()
            connection.execute("DELETE FROM paper_search")
            connection.execute("DELETE FROM paper_tags")
            for row in rows:
                reindex_paper(connection, int(row["id"]))
            rebuild_embedding_map(connection)
            connection.commit()

    def query_library(
        self,
        query: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        normalized_query = " ".join((query or "").split())
        safe_limit = max(1, min(limit, 200))

        with self.database.connect() as connection:
            if normalized_query:
                candidate_rows = search_rows(
                    connection,
                    query="",
                    limit=200,
                )
                rows = rank_rows_by_embedding(candidate_rows, normalized_query, self.embedding_provider, safe_limit)
                if not rows or rows[0]["semantic_score"] <= 0.05:
                    rows = search_rows(
                        connection,
                        query=normalized_query,
                        limit=safe_limit,
                    )
            else:
                rows = search_rows(
                    connection,
                    query="",
                    limit=safe_limit,
                )
            graph = get_library_graph(rows)

        return {
            "papers": [serialize_paper_list_item(row) for row in rows],
            "graph": graph,
        }

    def list_papers(self) -> list[dict[str, Any]]:
        return self.query_library()["papers"]

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
        return serialize_paper_detail(paper_row, notes)

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
            reindex_paper(connection, paper_id)
            connection.commit()
        return self.get_paper(paper_id)

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
