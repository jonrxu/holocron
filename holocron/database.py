from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checksum TEXT NOT NULL UNIQUE,
    storage_key TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_value TEXT,
    original_filename TEXT,
    title TEXT,
    authors_json TEXT NOT NULL DEFAULT '[]',
    year INTEGER,
    doi TEXT,
    arxiv_id TEXT,
    abstract TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    analysis_error TEXT,
    added_at TEXT NOT NULL,
    last_opened_at TEXT,
    last_reviewed_at TEXT
);

CREATE TABLE IF NOT EXISTS paper_artifacts (
    paper_id INTEGER PRIMARY KEY,
    extracted_text TEXT,
    text_excerpt TEXT,
    summary_short TEXT,
    summary_long TEXT,
    why_it_matters TEXT,
    method_summary TEXT,
    limitations_json TEXT NOT NULL DEFAULT '[]',
    claims_json TEXT NOT NULL DEFAULT '[]',
    datasets_json TEXT NOT NULL DEFAULT '[]',
    tasks_json TEXT NOT NULL DEFAULT '[]',
    tags_json TEXT NOT NULL DEFAULT '[]',
    followup_questions_json TEXT NOT NULL DEFAULT '[]',
    embedding_json TEXT NOT NULL DEFAULT '[]',
    embedding_model TEXT,
    map_x REAL,
    map_y REAL,
    analysis_version TEXT,
    analysis_confidence REAL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS paper_tags (
    paper_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    family TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'artifact',
    PRIMARY KEY (paper_id, tag),
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS paper_search USING fts5(
    paper_id UNINDEXED,
    title,
    authors,
    abstract,
    summary,
    tags,
    tasks,
    datasets,
    claims,
    notes,
    body,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS paper_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE (paper_id, chunk_index),
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER NOT NULL,
    author_type TEXT NOT NULL,
    body TEXT NOT NULL,
    page_number INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_paper_id INTEGER NOT NULL,
    target_paper_id INTEGER NOT NULL,
    edge_type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 0.0,
    rationale TEXT,
    source TEXT NOT NULL DEFAULT 'agent',
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    FOREIGN KEY (target_paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_papers_added_at ON papers(added_at DESC);
CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(status);
CREATE INDEX IF NOT EXISTS idx_paper_chunks_paper_id ON paper_chunks(paper_id, chunk_index ASC);
CREATE INDEX IF NOT EXISTS idx_paper_tags_tag ON paper_tags(tag);
CREATE INDEX IF NOT EXISTS idx_paper_tags_family ON paper_tags(family, tag);
CREATE INDEX IF NOT EXISTS idx_notes_paper_id ON notes(paper_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_paper_id ON events(paper_id, created_at DESC);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._migrate(connection)

    def _migrate(self, connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(paper_artifacts)").fetchall()
        }
        if "embedding_json" not in columns:
            connection.execute(
                "ALTER TABLE paper_artifacts ADD COLUMN embedding_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "embedding_model" not in columns:
            connection.execute("ALTER TABLE paper_artifacts ADD COLUMN embedding_model TEXT")
        if "map_x" not in columns:
            connection.execute("ALTER TABLE paper_artifacts ADD COLUMN map_x REAL")
        if "map_y" not in columns:
            connection.execute("ALTER TABLE paper_artifacts ADD COLUMN map_y REAL")

        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        if "paper_chunks" not in tables:
            connection.execute(
                """
                CREATE TABLE paper_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    embedding_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    UNIQUE (paper_id, chunk_index),
                    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_paper_chunks_paper_id
                ON paper_chunks(paper_id, chunk_index ASC)
                """
            )

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
