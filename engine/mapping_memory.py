"""Mapping matching and SQLite templates, independent of Streamlit.

``apply_template`` is pure: neither its DataFrame nor its template is mutated.
Database helpers accept an explicit connection and never open the application DB.
"""

from __future__ import annotations

from collections import defaultdict
import json
import re
import sqlite3

import pandas as pd

from .persistence import DB_TO_SECTION


def normalize_column_name(name: str) -> str:
    """Fold case, bracket widths and whitespace without removing punctuation."""
    name = str(name).translate(str.maketrans("（）［］｛｝", "()[]{}"))
    name = re.sub(r"\s+", " ", name).strip().casefold()
    # Exporters differ in spacing around option brackets as well as their width.
    return re.sub(r"\s*([()\[\]{}])\s*", r"\1", name)


def apply_template(current_mapping_df: pd.DataFrame, template_rows: list[dict]) -> tuple[pd.DataFrame, dict]:
    """Apply unambiguous name matches, preserving shape, index and source names.

    Exact names win over normalized names. Ambiguous normalized names are left
    alone. Multi-select and ranking groups use (q_type, section, q_no), as in the app.
    Only complete current groups mapping to one template group receive its key.
    Other rows retain their key; newly recognized grouped rows form singleton
    current groups and may join the corresponding template group.
    """
    result = current_mapping_df.copy(deep=True)
    exact: dict[str, list[int]] = defaultdict(list)
    normalized: dict[str, list[int]] = defaultdict(list)
    for pos, row in enumerate(template_rows):
        exact[row["column"]].append(pos)
        normalized[normalize_column_name(row["column"])].append(pos)

    current = current_mapping_df.to_dict("records")
    matches: dict[int, int] = {}
    for pos, row in enumerate(current):
        candidates = exact.get(row["column"]) or normalized.get(normalize_column_name(row["column"]), [])
        if len(candidates) == 1:
            matches[pos] = candidates[0]
            for field in ("q_type", "section", "title"):
                result.iat[pos, result.columns.get_loc(field)] = template_rows[candidates[0]][field]

    groups: dict[tuple, list[int]] = defaultdict(list)
    for pos, row in enumerate(current):
        key = (row["q_type"], row["section"], row["q_no"]) if row["q_type"] in {"multi", "ranking"} else ("row", pos)
        groups[key].append(pos)

    proposals: dict[int, str] = {}
    for members in groups.values():
        if not all(pos in matches for pos in members):
            continue
        targets = [template_rows[matches[pos]] for pos in members]
        if targets[0]["q_type"] in {"multi", "ranking"} and len({(row["q_type"], row["section"], row["q_no"]) for row in targets}) == 1:
            for pos in members:
                proposals[pos] = targets[0]["q_no"]

    # A template key must not accidentally merge with a group whose automatic
    # key is being retained. Recheck after rejecting proposals (chains can collide).
    while proposals:
        retained = {
            (result.iloc[pos]["q_type"], result.iloc[pos]["section"], row["q_no"])
            for pos, row in enumerate(current)
            if pos not in proposals and result.iloc[pos]["q_type"] in {"multi", "ranking"}
        }
        blocked = {
            pos for pos, key in proposals.items()
            if (result.iloc[pos]["q_type"], result.iloc[pos]["section"], key) in retained
        }
        if not blocked:
            break
        for members in groups.values():
            if blocked.intersection(members):
                for pos in members:
                    proposals.pop(pos, None)
    for pos, key in proposals.items():
        result.iat[pos, result.columns.get_loc("q_no")] = key

    current_names = {row["column"] for row in current}
    current_normalized = {normalize_column_name(name) for name in current_names}
    report = {
        "matched_count": len(matches),
        "total_count": len(current),
        "unmatched_columns": [row["column"] for pos, row in enumerate(current) if pos not in matches],
        "missing_columns": [
            row["column"] for row in template_rows
            if row["column"] not in current_names
            and normalize_column_name(row["column"]) not in current_normalized
        ],
    }
    return result, report


def save_template(conn: sqlite3.Connection, name: str, rows: list[dict]) -> int:
    """Create a named template; names need not be unique (IDs disambiguate)."""
    if not name.strip():
        raise ValueError("Template name must not be empty")
    with conn:
        cursor = conn.execute(
            "INSERT INTO mapping_templates (name, rows_json) VALUES (?, ?)",
            (name.strip(), json.dumps(rows, ensure_ascii=False)),
        )
    return cursor.lastrowid


def list_templates(conn: sqlite3.Connection) -> list[dict]:
    """List template metadata across all projects, newest first."""
    return [dict(row) for row in conn.execute(
        "SELECT id, name, created_at FROM mapping_templates ORDER BY id DESC"
    )]


def load_template(conn: sqlite3.Connection, template_id: int) -> list[dict] | None:
    row = conn.execute("SELECT rows_json FROM mapping_templates WHERE id = ?", (template_id,)).fetchone()
    return json.loads(row["rows_json"]) if row is not None else None


def delete_template(conn: sqlite3.Connection, template_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM mapping_templates WHERE id = ?", (template_id,))


def mapping_from_questions(questions: list[dict]) -> list[dict]:
    """Restore mapping rows without fetching respondents or autosaved drafts.

    Legacy non-multi questions did not store original columns. Their source text
    is the best available fallback; edited legacy titles cannot be reversed.
    Saved question numbers serve as equivalent multi-select grouping keys.
    """
    rows = []
    for question in questions:
        meta = json.loads(question["meta_json"] or "{}")
        columns = meta.get("columns") or [question["source_text_en"] or question["q_no"]]
        for column in columns:
            rows.append({
                "column": column,
                "q_type": question["q_type"],
                "section": DB_TO_SECTION[question["section"]],
                "q_no": question["q_no"],
                "title": question["source_text_en"],
            })
    return rows


def latest_project_mapping(
    conn: sqlite3.Connection, project_id: int | None, exclude_document_id: int | None = None,
) -> dict | None:
    """Find the other document most recently written to the formal questions table.

    Question IDs are AUTOINCREMENT; update_analysis replaces all its questions.
    MAX(id) therefore orders formal saves, even within one timestamp second and
    when renaming/AI updates touch documents.updated_at. Draft-only docs have no
    questions and cannot be selected.
    """
    document = conn.execute(
        """SELECT d.id, COALESCE(d.title, d.filename) AS name
           FROM documents d JOIN questions q ON q.document_id = d.id
           WHERE d.project_id = ? AND (? IS NULL OR d.id != ?)
           GROUP BY d.id ORDER BY MAX(q.id) DESC LIMIT 1""",
        (project_id, exclude_document_id, exclude_document_id),
    ).fetchone()
    if document is None:
        return None
    questions = conn.execute(
        "SELECT * FROM questions WHERE document_id = ? ORDER BY order_index, id",
        (document["id"],),
    ).fetchall()
    return {**dict(document), "rows": mapping_from_questions(questions)}
