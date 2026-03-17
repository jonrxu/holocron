from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from .embedding import cosine_similarity, project_embeddings


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def dumps_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def loads_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def tag_family(tag: str) -> str:
    if ":" not in tag:
        return "misc"
    return tag.split(":", 1)[0]


def get_library_graph(rows: list[Any]) -> dict[str, Any]:
    nodes = []
    for row in rows:
        nodes.append(
            {
                "id": int(row["id"]),
                "title": row["title"] or row["original_filename"] or "Untitled paper",
                "x": float(row["map_x"] or 0.0),
                "y": float(row["map_y"] or 0.0),
                "semantic_score": float(row.get("semantic_score", 0.0)) if isinstance(row, dict) else 0.0,
            }
        )
    return {"nodes": nodes}


def build_match_query(query: str) -> str | None:
    tokens = re.findall(r"[A-Za-z0-9_]+", query.lower())
    if not tokens:
        return None
    return " ".join(f"{token}*" for token in tokens[:8])


def search_rows(connection: Any, query: str, limit: int) -> list[Any]:
    where_params: list[Any] = []
    order_params: list[Any] = []
    where_clauses = ["1 = 1"]
    score_select = "0.0 AS lexical_rank"
    fts_join = ""
    order_by = "papers.added_at DESC"

    if query:
        match_query = build_match_query(query)
        if match_query:
            fts_join = "JOIN paper_search ON paper_search.paper_id = papers.id"
            where_clauses.append("paper_search MATCH ?")
            where_params.append(match_query)
            score_select = (
                "bm25(paper_search, 10.0, 4.0, 3.0, 4.0, 2.0, 2.0, 2.0, 1.6, 1.4, 0.3) "
                "AS lexical_rank"
            )
            where_clauses.append("papers.id = paper_search.paper_id")
            order_by = (
                "CASE WHEN lower(COALESCE(papers.title, '')) LIKE ? THEN 0 ELSE 1 END, "
                "lexical_rank ASC, papers.added_at DESC"
            )
            order_params.append(f"%{query.lower()}%")

    sql = f"""
        SELECT
            papers.*,
            paper_artifacts.summary_short,
            paper_artifacts.embedding_json,
            paper_artifacts.map_x,
            paper_artifacts.map_y,
            {score_select}
        FROM papers
        LEFT JOIN paper_artifacts ON paper_artifacts.paper_id = papers.id
        {fts_join}
        WHERE {' AND '.join(where_clauses)}
        ORDER BY {order_by}
        LIMIT ?
    """
    params = [*where_params, *order_params, limit]
    return connection.execute(sql, params).fetchall()


def rank_rows_by_embedding(
    rows: list[Any],
    query: str,
    embedding_provider: Any,
    limit: int,
) -> list[dict[str, Any]]:
    query_embedding = embedding_provider.embed_query(query)
    ranked: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        embedding = loads_json(record.get("embedding_json"), [])
        score = cosine_similarity(query_embedding, embedding) if embedding else 0.0
        record["semantic_score"] = score
        ranked.append(record)
    ranked.sort(key=lambda item: (item["semantic_score"], item["added_at"]), reverse=True)
    return ranked[:limit]


def reindex_paper(connection: Any, paper_id: int) -> None:
    row = connection.execute(
        """
        SELECT
            papers.*,
            paper_artifacts.extracted_text,
            paper_artifacts.summary_short,
            paper_artifacts.summary_long,
            paper_artifacts.why_it_matters,
            paper_artifacts.method_summary,
            paper_artifacts.limitations_json,
            paper_artifacts.claims_json,
            paper_artifacts.datasets_json,
            paper_artifacts.tasks_json,
            paper_artifacts.tags_json,
            paper_artifacts.followup_questions_json,
            COALESCE(
                (
                    SELECT GROUP_CONCAT(body, '\n')
                    FROM notes
                    WHERE notes.paper_id = papers.id
                ),
                ''
            ) AS notes_text
        FROM papers
        LEFT JOIN paper_artifacts ON paper_artifacts.paper_id = papers.id
        WHERE papers.id = ?
        """,
        (paper_id,),
    ).fetchone()

    if not row:
        return

    tags = loads_json(row["tags_json"], [])
    tasks = loads_json(row["tasks_json"], [])
    datasets = loads_json(row["datasets_json"], [])
    claims = loads_json(row["claims_json"], [])
    limitations = loads_json(row["limitations_json"], [])
    followups = loads_json(row["followup_questions_json"], [])
    authors = loads_json(row["authors_json"], [])

    connection.execute("DELETE FROM paper_search WHERE paper_id = ?", (paper_id,))
    connection.execute("DELETE FROM paper_tags WHERE paper_id = ?", (paper_id,))

    for tag in tags:
        connection.execute(
            """
            INSERT INTO paper_tags (paper_id, tag, family, source)
            VALUES (?, ?, ?, 'artifact')
            """,
            (paper_id, tag, tag_family(tag)),
        )

    connection.execute(
        """
        INSERT INTO paper_search (
            paper_id, title, authors, abstract, summary, tags, tasks,
            datasets, claims, notes, body
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            paper_id,
            row["title"] or row["original_filename"] or "",
            " ".join(authors),
            row["abstract"] or "",
            " ".join(
                part
                for part in [
                    row["summary_short"] or "",
                    row["summary_long"] or "",
                    row["why_it_matters"] or "",
                    row["method_summary"] or "",
                ]
                if part
            ),
            " ".join(tags),
            " ".join(tasks),
            " ".join(datasets),
            " ".join(claims + limitations + followups),
            row["notes_text"] or "",
            row["extracted_text"] or "",
        ),
    )


def build_paper_card(title: str | None, authors: list[str], year: int | None, analysis: Any) -> dict[str, Any]:
    return {
        "title": title or "",
        "authors": authors[:8],
        "year": year,
        "problem": analysis.problem,
        "core_idea": analysis.core_idea,
        "summary_short": analysis.summary_short,
        "summary_long": analysis.summary_long,
        "why_it_matters": analysis.why_it_matters,
        "method_summary": analysis.method_summary,
        "prerequisites": analysis.prerequisites,
        "concepts": analysis.concepts,
        "claims": analysis.claims,
        "limitations": analysis.limitations,
        "datasets": analysis.datasets,
        "tasks": analysis.tasks,
        "tags": analysis.tags,
    }


def build_paper_card_text(paper_card: dict[str, Any], full_text: str) -> str:
    # The paper card is the high-level representation used for map placement and library retrieval.
    parts = [
        paper_card.get("title", ""),
        f"Problem: {paper_card.get('problem', '')}".strip(),
        f"Core idea: {paper_card.get('core_idea', '')}".strip(),
        f"Summary: {paper_card.get('summary_short', '')}".strip(),
        paper_card.get("summary_long", ""),
        f"Why it matters: {paper_card.get('why_it_matters', '')}".strip(),
        f"Method: {paper_card.get('method_summary', '')}".strip(),
        "Concepts: " + ", ".join(paper_card.get("concepts", [])),
        "Prerequisites: " + ", ".join(paper_card.get("prerequisites", [])),
        "Tasks: " + ", ".join(paper_card.get("tasks", [])),
        "Datasets: " + ", ".join(paper_card.get("datasets", [])),
        "Claims: " + " ".join(paper_card.get("claims", [])[:3]),
        "Limitations: " + " ".join(paper_card.get("limitations", [])[:2]),
        "Tags: " + ", ".join(paper_card.get("tags", [])),
    ]
    source = "\n\n".join(part.strip() for part in parts if part and part.strip())
    if source:
        return source[:4000]
    return full_text[:4000]


def rebuild_embedding_map(connection: Any) -> None:
    rows = connection.execute(
        """
        SELECT paper_id, embedding_json
        FROM paper_artifacts
        ORDER BY paper_id ASC
        """
    ).fetchall()

    paper_ids: list[int] = []
    vectors: list[list[float]] = []
    for row in rows:
        embedding = loads_json(row["embedding_json"], [])
        if not embedding:
            continue
        paper_ids.append(int(row["paper_id"]))
        vectors.append([float(value) for value in embedding])

    positions = project_embeddings(vectors)
    connection.execute("UPDATE paper_artifacts SET map_x = NULL, map_y = NULL")
    for paper_id, (map_x, map_y) in zip(paper_ids, positions):
        connection.execute(
            "UPDATE paper_artifacts SET map_x = ?, map_y = ? WHERE paper_id = ?",
            (map_x, map_y, paper_id),
        )


def serialize_paper_list_item(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "original_filename": row["original_filename"],
        "status": row["status"],
        "added_at": row["added_at"],
        "summary_short": row["summary_short"],
        "semantic_score": float(row.get("semantic_score", 0.0)) if isinstance(row, dict) else 0.0,
    }


def serialize_paper_detail(row: Any, notes: list[Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "original_filename": row["original_filename"],
        "status": row["status"],
        "analysis_error": row["analysis_error"],
        "added_at": row["added_at"],
        "authors": loads_json(row["authors_json"], []),
        "year": row["year"],
        "abstract": row["abstract"],
        "summary_short": row["summary_short"],
        "summary_long": row["summary_long"],
        "tags": loads_json(row["tags_json"], []),
        "chunk_count": int(row["chunk_count"] or 0),
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
    }
