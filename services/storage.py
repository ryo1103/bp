from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "app.db"
UPLOAD_DIR = ROOT / "uploads"


def now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@contextmanager
def connect():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def fetch_all(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
    return [row_to_dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def fetch_one(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> Optional[Dict[str, Any]]:
    row = conn.execute(sql, tuple(params)).fetchone()
    return row_to_dict(row) if row else None


def init_db() -> None:
    UPLOAD_DIR.mkdir(exist_ok=True)
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
              id TEXT PRIMARY KEY,
              company_name TEXT NOT NULL,
              industry TEXT NOT NULL,
              financing_stage TEXT NOT NULL,
              one_liner TEXT NOT NULL,
              current_recommendation TEXT NOT NULL,
              risk_level TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS documents (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              document_type TEXT NOT NULL,
              file_name TEXT NOT NULL,
              file_path TEXT NOT NULL,
              parser TEXT NOT NULL,
              parse_status TEXT NOT NULL,
              summary TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS document_chunks (
              id TEXT PRIMARY KEY,
              document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              chunk_index INTEGER NOT NULL,
              page_number INTEGER NOT NULL,
              section_label TEXT NOT NULL,
              text TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bp_claims (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              claim_text TEXT NOT NULL,
              claim_type TEXT NOT NULL,
              topic TEXT NOT NULL,
              source_chunk_id TEXT NOT NULL,
              source_page INTEGER NOT NULL,
              source_quote TEXT NOT NULL,
              verification_status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS key_highlights (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              title TEXT NOT NULL,
              linked_claim_text TEXT NOT NULL,
              source_chunk_id TEXT NOT NULL,
              source_page INTEGER NOT NULL,
              why_important TEXT NOT NULL,
              evidence_level TEXT NOT NULL,
              verification_direction TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS investment_assumptions (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              assumption_text TEXT NOT NULL,
              importance TEXT NOT NULL,
              risk_level TEXT NOT NULL,
              current_status TEXT NOT NULL,
              why_it_matters TEXT NOT NULL,
              failure_impact TEXT NOT NULL,
              verification_method TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS verification_tasks (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              title TEXT NOT NULL,
              task_type TEXT NOT NULL,
              linked_claim_id TEXT,
              linked_assumption_id TEXT,
              risk_level TEXT NOT NULL,
              status TEXT NOT NULL,
              existing_evidence TEXT NOT NULL,
              missing_evidence TEXT NOT NULL,
              suggested_materials TEXT NOT NULL,
              suggested_interviewees TEXT NOT NULL,
              founder_questions TEXT NOT NULL,
              customer_questions TEXT NOT NULL,
              user_notes TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS evidence_links (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              task_id TEXT NOT NULL REFERENCES verification_tasks(id) ON DELETE CASCADE,
              claim_id TEXT,
              document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              chunk_id TEXT NOT NULL,
              evidence_text TEXT NOT NULL,
              judgment TEXT NOT NULL,
              confidence REAL NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS investment_memos (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              memo_type TEXT NOT NULL,
              content_markdown TEXT NOT NULL,
              source_snapshot_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )


def create_project(company_name: str, industry: str = "待识别", financing_stage: str = "待确认", one_liner: str = "待 BP 分析后生成") -> str:
    init_db()
    project_id = new_id("proj")
    ts = now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                company_name.strip() or "未命名项目",
                industry.strip() or "待识别",
                financing_stage.strip() or "待确认",
                one_liner.strip() or "待 BP 分析后生成",
                "等待补充信息",
                "medium",
                ts,
                ts,
            ),
        )
    return project_id


def list_projects() -> List[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        projects = fetch_all(conn, "SELECT * FROM projects ORDER BY updated_at DESC")
        for project in projects:
            project.update(project_counts(conn, project["id"]))
        return projects


def project_counts(conn: sqlite3.Connection, project_id: str) -> Dict[str, int]:
    tasks = fetch_all(conn, "SELECT risk_level, status FROM verification_tasks WHERE project_id = ?", (project_id,))
    return {
        "task_count": len(tasks),
        "unverified_high_risk_count": sum(
            1 for task in tasks if task["risk_level"] == "high" and task["status"] != "verified"
        ),
        "verified_count": sum(1 for task in tasks if task["status"] == "verified"),
    }


def delete_project(project_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))


def get_project_bundle(project_id: str) -> Dict[str, Any]:
    init_db()
    with connect() as conn:
        project = fetch_one(conn, "SELECT * FROM projects WHERE id = ?", (project_id,))
        if not project:
            raise ValueError("项目不存在")
        project.update(project_counts(conn, project_id))
        return {
            "project": project,
            "documents": fetch_all(conn, "SELECT * FROM documents WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "chunks": fetch_all(conn, "SELECT * FROM document_chunks WHERE project_id = ? ORDER BY chunk_index", (project_id,)),
            "claims": fetch_all(conn, "SELECT * FROM bp_claims WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "highlights": fetch_all(conn, "SELECT * FROM key_highlights WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "assumptions": fetch_all(conn, "SELECT * FROM investment_assumptions WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "tasks": fetch_all(conn, "SELECT * FROM verification_tasks WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "evidence": fetch_all(conn, "SELECT * FROM evidence_links WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "memos": fetch_all(conn, "SELECT * FROM investment_memos WHERE project_id = ? ORDER BY created_at", (project_id,)),
        }


def save_uploaded_file(project_id: str, file_name: str, content: bytes) -> Path:
    project_dir = UPLOAD_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file_name).name or "uploaded.txt"
    target = project_dir / f"{new_id('file')}_{safe_name}"
    target.write_bytes(content)
    return target


def replace_bp_analysis(
    project_id: str,
    documents: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    all_analysis_chunks: List[Dict[str, Any]],
    analysis: Dict[str, Any],
) -> None:
    ts = now()
    chunk_document_ids = {
        str(chunk["id"]): str(chunk.get("document_id") or "")
        for chunk in all_analysis_chunks
        if chunk.get("id")
    }
    fallback_document_id = documents[0]["id"] if documents else next(
        (chunk["document_id"] for chunk in all_analysis_chunks if chunk.get("document_id")),
        "",
    )
    with connect() as conn:
        conn.execute(
            """
            DELETE FROM evidence_links
            WHERE project_id = ?
              AND task_id IN (
                SELECT id FROM verification_tasks
                WHERE project_id = ?
                  AND (COALESCE(linked_claim_id, '') != '' OR COALESCE(linked_assumption_id, '') != '')
              )
            """,
            (project_id, project_id),
        )
        conn.execute(
            """
            DELETE FROM verification_tasks
            WHERE project_id = ?
              AND (COALESCE(linked_claim_id, '') != '' OR COALESCE(linked_assumption_id, '') != '')
            """,
            (project_id,),
        )
        conn.execute("DELETE FROM bp_claims WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM key_highlights WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM investment_assumptions WHERE project_id = ?", (project_id,))

        for document in documents:
            conn.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    document["id"],
                    project_id,
                    document["document_type"],
                    document["file_name"],
                    document["file_path"],
                    document["parser"],
                    "completed",
                    analysis["document_summary"],
                    ts,
                    ts,
                ),
            )
        for chunk in chunks:
            conn.execute(
                "INSERT INTO document_chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk["id"],
                    chunk["document_id"],
                    project_id,
                    chunk["chunk_index"],
                    chunk["page_number"],
                    chunk["section_label"],
                    chunk["text"],
                    ts,
                ),
            )

        claim_ids: List[str] = []
        for claim in analysis["bp_claims"]:
            claim_id = new_id("claim")
            claim_ids.append(claim_id)
            document_id = chunk_document_ids.get(claim["source_chunk_id"]) or fallback_document_id
            conn.execute(
                "INSERT INTO bp_claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    claim_id,
                    project_id,
                    document_id,
                    claim["claim_text"],
                    claim["claim_type"],
                    claim["topic"],
                    claim["source_chunk_id"],
                    claim["source_page"],
                    claim["source_quote"],
                    "unverified",
                    ts,
                    ts,
                ),
            )

        for highlight in analysis["key_highlights"]:
            document_id = chunk_document_ids.get(highlight["source_chunk_id"]) or fallback_document_id
            conn.execute(
                "INSERT INTO key_highlights VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("highlight"),
                    project_id,
                    document_id,
                    highlight["title"],
                    highlight["linked_claim_text"],
                    highlight["source_chunk_id"],
                    highlight["source_page"],
                    highlight["why_important"],
                    highlight["evidence_level"],
                    highlight["verification_direction"],
                    ts,
                    ts,
                ),
            )

        assumption_ids: List[str] = []
        for assumption in analysis["assumptions"]:
            assumption_id = new_id("assumption")
            assumption_ids.append(assumption_id)
            conn.execute(
                "INSERT INTO investment_assumptions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    assumption_id,
                    project_id,
                    assumption["assumption_text"],
                    assumption["importance"],
                    assumption["risk_level"],
                    "unverified",
                    assumption["why_it_matters"],
                    assumption["failure_impact"],
                    assumption["verification_method"],
                    ts,
                    ts,
                ),
            )

        for index, task in enumerate(analysis["verification_tasks"]):
            conn.execute(
                "INSERT INTO verification_tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("task"),
                    project_id,
                    task["title"],
                    task["task_type"],
                    claim_ids[index % len(claim_ids)] if claim_ids else "",
                    assumption_ids[index % len(assumption_ids)] if assumption_ids else "",
                    task["risk_level"],
                    "unverified",
                    task["existing_evidence"],
                    task["missing_evidence"],
                    task["suggested_materials"],
                    task["suggested_interviewees"],
                    task["founder_questions"],
                    task["customer_questions"],
                    "",
                    ts,
                    ts,
                ),
            )

        company = analysis["company_summary"]
        conn.execute(
            """
            UPDATE projects
            SET company_name = ?, industry = ?, financing_stage = ?, one_liner = ?,
                current_recommendation = ?, risk_level = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                company["company_name"],
                company["industry"],
                company["financing_stage"],
                company["one_liner"],
                analysis["stage_recommendation"],
                analysis["risk_level"],
                ts,
                project_id,
            ),
        )


def insert_bp_analysis(project_id: str, document: Dict[str, Any], chunks: List[Dict[str, Any]], analysis: Dict[str, Any]) -> None:
    prepared_chunks = [{**chunk, "document_id": document["id"]} for chunk in chunks]
    replace_bp_analysis(project_id, [document], prepared_chunks, prepared_chunks, analysis)


def insert_supplementary_verification(project_id: str, document: Dict[str, Any], chunks: List[Dict[str, Any]], result: Dict[str, Any]) -> None:
    ts = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                document["id"],
                project_id,
                document["document_type"],
                document["file_name"],
                document["file_path"],
                document["parser"],
                "completed",
                result["material_summary"],
                ts,
                ts,
            ),
        )
        for chunk in chunks:
            conn.execute(
                "INSERT INTO document_chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk["id"],
                    document["id"],
                    project_id,
                    chunk["chunk_index"],
                    chunk["page_number"],
                    chunk["section_label"],
                    chunk["text"],
                    ts,
                ),
            )
        for update in result["task_updates"]:
            task = fetch_one(conn, "SELECT * FROM verification_tasks WHERE id = ? AND project_id = ?", (update["task_id"], project_id))
            if not task:
                continue
            conn.execute(
                "UPDATE verification_tasks SET status = ?, missing_evidence = ?, user_notes = ?, updated_at = ? WHERE id = ?",
                (
                    update["new_status"],
                    update.get("still_missing", task["missing_evidence"]),
                    update.get("new_questions", task["user_notes"]),
                    ts,
                    task["id"],
                ),
            )
            if task["linked_claim_id"]:
                conn.execute(
                    "UPDATE bp_claims SET verification_status = ?, updated_at = ? WHERE id = ?",
                    (update["new_status"], ts, task["linked_claim_id"]),
                )
            if task["linked_assumption_id"]:
                conn.execute(
                    "UPDATE investment_assumptions SET current_status = ?, updated_at = ? WHERE id = ?",
                    (update["new_status"], ts, task["linked_assumption_id"]),
                )
            conn.execute(
                "INSERT INTO evidence_links VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("evidence"),
                    project_id,
                    task["id"],
                    task["linked_claim_id"] or "",
                    document["id"],
                    update["chunk_id"],
                    update["evidence_text"],
                    update["judgment"],
                    float(update["confidence"]),
                    ts,
                ),
            )
        conn.execute(
            "UPDATE projects SET current_recommendation = ?, risk_level = ?, updated_at = ? WHERE id = ?",
            (result["stage_recommendation"], result["risk_level"], ts, project_id),
        )


def update_task(task_id: str, status: str, risk_level: str, user_notes: str) -> None:
    ts = now()
    with connect() as conn:
        task = fetch_one(conn, "SELECT * FROM verification_tasks WHERE id = ?", (task_id,))
        if not task:
            return
        conn.execute(
            "UPDATE verification_tasks SET status = ?, risk_level = ?, user_notes = ?, updated_at = ? WHERE id = ?",
            (status, risk_level, user_notes, ts, task_id),
        )
        if task["linked_claim_id"]:
            conn.execute("UPDATE bp_claims SET verification_status = ?, updated_at = ? WHERE id = ?", (status, ts, task["linked_claim_id"]))
        if task["linked_assumption_id"]:
            conn.execute("UPDATE investment_assumptions SET current_status = ?, updated_at = ? WHERE id = ?", (status, ts, task["linked_assumption_id"]))
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (ts, task["project_id"]))


def create_manual_task(
    project_id: str,
    title: str,
    task_type: str,
    risk_level: str,
    existing_evidence: str,
    missing_evidence: str,
    suggested_materials: str,
    suggested_interviewees: str,
    founder_questions: str,
    customer_questions: str,
    user_notes: str = "",
) -> str:
    task_id = new_id("task")
    ts = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO verification_tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task_id,
                project_id,
                title.strip(),
                task_type,
                "",
                "",
                risk_level,
                "unverified",
                existing_evidence.strip() or "用户手动添加，暂无已有证据。",
                missing_evidence.strip(),
                suggested_materials.strip(),
                suggested_interviewees.strip(),
                founder_questions.strip(),
                customer_questions.strip(),
                user_notes.strip(),
                ts,
                ts,
            ),
        )
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (ts, project_id))
    return task_id


def delete_task(task_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM verification_tasks WHERE id = ?", (task_id,))


def insert_memo(project_id: str, content_markdown: str, snapshot: Dict[str, Any]) -> str:
    memo_id = new_id("memo")
    ts = now()
    with connect() as conn:
        existing = fetch_all(conn, "SELECT id FROM investment_memos WHERE project_id = ?", (project_id,))
        conn.execute(
            "INSERT INTO investment_memos VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                memo_id,
                project_id,
                "updated" if existing else "initial",
                content_markdown,
                json.dumps(snapshot, ensure_ascii=False),
                ts,
                ts,
            ),
        )
    return memo_id
