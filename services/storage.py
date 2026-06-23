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


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row["name"] == column for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


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

            CREATE TABLE IF NOT EXISTS sector_analyses (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              primary_industry TEXT NOT NULL,
              sub_sector TEXT NOT NULL,
              target_customer TEXT NOT NULL,
              value_chain_position TEXT NOT NULL,
              replacement_target TEXT NOT NULL,
              profit_pool_logic TEXT NOT NULL,
              summary TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS industry_map_nodes (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              node_type TEXT NOT NULL,
              label TEXT NOT NULL,
              description TEXT NOT NULL,
              is_company_position INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS industry_terms (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              term TEXT NOT NULL,
              explanation TEXT NOT NULL,
              relevance TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS red_flags (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              title TEXT NOT NULL,
              flag_type TEXT NOT NULL,
              severity TEXT NOT NULL,
              status TEXT NOT NULL,
              evidence TEXT NOT NULL,
              source_chunk_id TEXT NOT NULL,
              source_page INTEGER NOT NULL,
              why_it_matters TEXT NOT NULL,
              suggested_verification TEXT NOT NULL,
              resolved_by_document_id TEXT NOT NULL,
              resolution_note TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS supplementary_resolutions (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              target_type TEXT NOT NULL,
              target_id TEXT NOT NULL,
              target_title TEXT NOT NULL,
              resolution_status TEXT NOT NULL,
              evidence_text TEXT NOT NULL,
              impact_summary TEXT NOT NULL,
              remaining_gap TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS financial_analyses (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              summary TEXT NOT NULL,
              revenue_quality TEXT NOT NULL,
              margin_costs TEXT NOT NULL,
              cashflow_quality TEXT NOT NULL,
              customer_concentration TEXT NOT NULL,
              anomalies TEXT NOT NULL,
              bp_conflicts TEXT NOT NULL,
              follow_up_materials TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS funding_analyses (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              stated_round TEXT NOT NULL,
              inferred_round TEXT NOT NULL,
              round_confidence TEXT NOT NULL,
              material_sufficiency TEXT NOT NULL,
              risk_return_profile TEXT NOT NULL,
              stability_assessment TEXT NOT NULL,
              payback_cycle_view TEXT NOT NULL,
              investor_signal TEXT NOT NULL,
              existing_investors TEXT NOT NULL,
              missing_round_evidence TEXT NOT NULL,
              valuation_fit TEXT NOT NULL,
              suggested_checks TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_suggestions (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              suggestion_type TEXT NOT NULL,
              target_object_type TEXT,
              target_object_id TEXT,
              suggested_change_json TEXT NOT NULL,
              ai_reason TEXT,
              status TEXT NOT NULL DEFAULT 'pending',
              created_at TEXT NOT NULL,
              reviewed_at TEXT,
              reviewed_by TEXT,
              human_action TEXT,
              human_note TEXT
            );

            CREATE TABLE IF NOT EXISTS human_decision_logs (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              previous_status TEXT,
              new_status TEXT NOT NULL,
              decision_reason TEXT,
              decision_reason_category TEXT,
              decided_by TEXT,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS evidence_items (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              document_id TEXT,
              source_chunk_id TEXT,
              source_page INTEGER,
              evidence_text TEXT NOT NULL,
              evidence_type TEXT NOT NULL,
              evidence_level TEXT NOT NULL,
              related_object_type TEXT,
              related_object_id TEXT,
              created_by TEXT NOT NULL DEFAULT 'ai',
              ai_confidence TEXT DEFAULT 'medium',
              human_verified INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS risk_items (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              risk_title TEXT NOT NULL,
              risk_description TEXT NOT NULL,
              risk_category TEXT NOT NULL,
              risk_status TEXT NOT NULL,
              severity_candidate TEXT NOT NULL DEFAULT 'medium',
              evidence_level TEXT NOT NULL DEFAULT 'company_claim_only',
              source_chunk_id TEXT,
              source_page INTEGER,
              suggested_verification_method TEXT,
              ai_confidence TEXT NOT NULL DEFAULT 'medium',
              created_by TEXT NOT NULL DEFAULT 'ai',
              human_note TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS investment_hypotheses (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              parent_hypothesis_id TEXT,
              hypothesis_text TEXT NOT NULL,
              hypothesis_category TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'unverified',
              evidence_level TEXT NOT NULL DEFAULT 'company_claim_only',
              ai_confidence TEXT NOT NULL DEFAULT 'medium',
              why_it_matters TEXT,
              created_by TEXT NOT NULL DEFAULT 'ai',
              human_note TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS research_actions (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              title TEXT NOT NULL,
              description TEXT NOT NULL,
              action_type TEXT NOT NULL,
              action_status TEXT NOT NULL DEFAULT 'ai_suggested',
              priority TEXT NOT NULL DEFAULT 'medium',
              cost_level TEXT NOT NULL DEFAULT 'low',
              linked_hypothesis_id TEXT,
              linked_risk_id TEXT,
              requested_materials TEXT,
              owner TEXT,
              due_date TEXT,
              ai_reason TEXT,
              human_note TEXT,
              created_by TEXT NOT NULL DEFAULT 'ai',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS readiness_scorecards (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              dimension TEXT NOT NULL,
              level TEXT NOT NULL,
              explanation TEXT NOT NULL,
              evidence_level TEXT,
              source_chunk_id TEXT,
              source_page INTEGER,
              created_by TEXT NOT NULL DEFAULT 'ai',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fund_strategies (
              id TEXT PRIMARY KEY,
              strategy_name TEXT NOT NULL,
              focus_sectors TEXT,
              excluded_sectors TEXT,
              preferred_stages TEXT,
              excluded_stages TEXT,
              ticket_size_min REAL,
              ticket_size_max REAL,
              target_ownership_min REAL,
              target_ownership_max REAL,
              geography_preference TEXT,
              revenue_requirement TEXT,
              gross_margin_requirement TEXT,
              customer_type_preference TEXT,
              long_rd_cycle_allowed INTEGER DEFAULT 1,
              industrial_synergy_preferred INTEGER DEFAULT 0,
              requires_existing_investor INTEGER DEFAULT 0,
              hard_redlines TEXT,
              soft_preferences TEXT,
              created_by TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS project_strategy_matches (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              strategy_id TEXT NOT NULL,
              match_status TEXT NOT NULL,
              matched_items_json TEXT,
              unknown_items_json TEXT,
              outside_scope_items_json TEXT,
              source_summary TEXT,
              created_by TEXT NOT NULL DEFAULT 'ai',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS material_requests (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              material_name TEXT NOT NULL,
              why_needed TEXT NOT NULL,
              linked_hypothesis_id TEXT,
              linked_risk_id TEXT,
              priority TEXT NOT NULL DEFAULT 'medium',
              required_or_optional TEXT NOT NULL DEFAULT 'required',
              status TEXT NOT NULL DEFAULT 'ai_suggested',
              received_document_id TEXT,
              created_by TEXT NOT NULL DEFAULT 'ai',
              human_note TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS interview_notes (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              interview_type TEXT NOT NULL,
              interviewee_name TEXT,
              interviewee_role TEXT,
              organization TEXT,
              interview_date TEXT,
              raw_note TEXT NOT NULL,
              summary TEXT,
              created_by TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memo_sections (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              memo_id TEXT NOT NULL,
              section_key TEXT NOT NULL,
              section_title TEXT NOT NULL,
              ai_draft TEXT,
              human_edited_text TEXT,
              source_refs_json TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS project_events (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              event_type TEXT NOT NULL,
              event_summary TEXT NOT NULL,
              actor_type TEXT NOT NULL,
              actor_name TEXT,
              object_type TEXT,
              object_id TEXT,
              diff_json TEXT,
              created_at TEXT NOT NULL
            );
            """
        )
        _add_column_if_missing(conn, "projects", "ai_research_state", "TEXT DEFAULT 'material_insufficient'")
        _add_column_if_missing(conn, "projects", "human_project_status", "TEXT DEFAULT 'inbox'")
        _add_column_if_missing(conn, "projects", "material_stage", "TEXT DEFAULT 'only_bp'")
        _add_column_if_missing(conn, "projects", "judgement_readiness", "TEXT DEFAULT 'very_limited'")
        _add_column_if_missing(conn, "projects", "strategy_match_status", "TEXT DEFAULT 'unknown_due_to_missing_materials'")
        _add_column_if_missing(conn, "projects", "evidence_sufficiency", "TEXT DEFAULT 'low'")
        _add_column_if_missing(conn, "projects", "owner", "TEXT")
        _add_column_if_missing(conn, "projects", "last_ai_summary", "TEXT")
        _add_column_if_missing(conn, "projects", "last_human_decision_reason", "TEXT")
        _add_column_if_missing(conn, "projects", "pending_ai_updates_count", "INTEGER DEFAULT 0")


def create_project(company_name: str, industry: str = "待识别", financing_stage: str = "待确认", one_liner: str = "待 BP 分析后生成") -> str:
    init_db()
    project_id = new_id("proj")
    ts = now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO projects (
              id, company_name, industry, financing_stage, one_liner,
              current_recommendation, risk_level, created_at, updated_at,
              ai_research_state, human_project_status, material_stage,
              judgement_readiness, strategy_match_status, evidence_sufficiency,
              owner, last_ai_summary, last_human_decision_reason, pending_ai_updates_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                company_name.strip() or "未命名项目",
                industry.strip() or "待识别",
                financing_stage.strip() or "待确认",
                one_liner.strip() or "待 BP 分析后生成",
                "当前材料不足以支持进一步判断",
                "medium",
                ts,
                ts,
                "material_insufficient",
                "inbox",
                "only_bp",
                "very_limited",
                "unknown_due_to_missing_materials",
                "low",
                "",
                "",
                "",
                0,
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
    risk_count = fetch_one(conn, "SELECT COUNT(*) AS count FROM red_flags WHERE project_id = ? AND status != 'resolved'", (project_id,))
    pending_ai = fetch_one(conn, "SELECT COUNT(*) AS count FROM ai_suggestions WHERE project_id = ? AND status = 'pending'", (project_id,))
    return {
        "task_count": len(tasks),
        "unverified_high_risk_count": sum(
            1 for task in tasks if task["risk_level"] == "high" and task["status"] != "verified"
        ),
        "verified_count": sum(1 for task in tasks if task["status"] == "verified"),
        "pending_risk_count": int(risk_count["count"] if risk_count else 0),
        "pending_ai_suggestion_count": int(pending_ai["count"] if pending_ai else 0),
    }


def _task_type_to_hypothesis_category(value: str) -> str:
    text = value.lower()
    if "financial" in text or "收入" in value or "回款" in value:
        return "financial_quality"
    if "team" in text or "团队" in value:
        return "team_capability"
    if "market" in text or "市场" in value:
        return "market_size"
    if "business" in text or "商业" in value:
        return "business_model"
    if "technology" in text or "技术" in value:
        return "product_technology"
    if "fund" in text or "融资" in value:
        return "funding_round_fit"
    return "customer_validation"


def _task_type_to_action_type(value: str) -> str:
    if value == "financial_quality":
        return "financial_check"
    if value == "team":
        return "founder_interview"
    if value == "market":
        return "expert_interview"
    if value == "financing_use":
        return "legal_check"
    return "material_request"


def delete_project(project_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))


def list_deal_pipeline_projects(status: str | None = None, owner: str | None = None) -> List[Dict[str, Any]]:
    init_db()
    clauses = []
    params: List[Any] = []
    if status:
        clauses.append("human_project_status = ?")
        params.append(status)
    if owner:
        clauses.append("owner = ?")
        params.append(owner)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as conn:
        projects = fetch_all(conn, f"SELECT * FROM projects {where} ORDER BY updated_at DESC", params)
        for project in projects:
            project.update(project_counts(conn, project["id"]))
        return projects


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
            "sector_analyses": fetch_all(conn, "SELECT * FROM sector_analyses WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "industry_map_nodes": fetch_all(conn, "SELECT * FROM industry_map_nodes WHERE project_id = ? ORDER BY node_type, created_at", (project_id,)),
            "industry_terms": fetch_all(conn, "SELECT * FROM industry_terms WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "red_flags": fetch_all(conn, "SELECT * FROM red_flags WHERE project_id = ? ORDER BY severity, created_at", (project_id,)),
            "supplementary_resolutions": fetch_all(conn, "SELECT * FROM supplementary_resolutions WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "financial_analyses": fetch_all(conn, "SELECT * FROM financial_analyses WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "funding_analyses": fetch_all(conn, "SELECT * FROM funding_analyses WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "ai_suggestions": fetch_all(conn, "SELECT * FROM ai_suggestions WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "human_decision_logs": fetch_all(conn, "SELECT * FROM human_decision_logs WHERE project_id = ? ORDER BY created_at DESC", (project_id,)),
            "evidence_items": fetch_all(conn, "SELECT * FROM evidence_items WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "risk_items": fetch_all(conn, "SELECT * FROM risk_items WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "investment_hypotheses": fetch_all(conn, "SELECT * FROM investment_hypotheses WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "research_actions": fetch_all(conn, "SELECT * FROM research_actions WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "readiness_scorecards": fetch_all(conn, "SELECT * FROM readiness_scorecards WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "fund_strategies": fetch_all(conn, "SELECT * FROM fund_strategies ORDER BY updated_at DESC"),
            "project_strategy_matches": fetch_all(conn, "SELECT * FROM project_strategy_matches WHERE project_id = ? ORDER BY created_at DESC", (project_id,)),
            "material_requests": fetch_all(conn, "SELECT * FROM material_requests WHERE project_id = ? ORDER BY created_at", (project_id,)),
            "interview_notes": fetch_all(conn, "SELECT * FROM interview_notes WHERE project_id = ? ORDER BY created_at DESC", (project_id,)),
            "memo_sections": fetch_all(conn, "SELECT * FROM memo_sections WHERE project_id = ? ORDER BY section_key", (project_id,)),
            "project_events": fetch_all(conn, "SELECT * FROM project_events WHERE project_id = ? ORDER BY created_at DESC", (project_id,)),
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
        conn.execute("DELETE FROM supplementary_resolutions WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM sector_analyses WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM industry_map_nodes WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM industry_terms WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM red_flags WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM funding_analyses WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM evidence_items WHERE project_id = ? AND created_by = 'ai'", (project_id,))
        conn.execute("DELETE FROM risk_items WHERE project_id = ? AND created_by = 'ai'", (project_id,))
        conn.execute("DELETE FROM investment_hypotheses WHERE project_id = ? AND created_by = 'ai'", (project_id,))
        conn.execute("DELETE FROM research_actions WHERE project_id = ? AND created_by = 'ai'", (project_id,))
        conn.execute("DELETE FROM readiness_scorecards WHERE project_id = ? AND created_by = 'ai'", (project_id,))
        conn.execute("DELETE FROM material_requests WHERE project_id = ? AND created_by = 'ai'", (project_id,))

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
            conn.execute(
                "INSERT INTO evidence_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("evitem"),
                    project_id,
                    document_id,
                    claim["source_chunk_id"],
                    claim["source_page"],
                    claim["claim_text"],
                    claim["claim_type"],
                    "company_claim_only",
                    "bp_claim",
                    claim_id,
                    "ai",
                    "high",
                    0,
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
            conn.execute(
                "INSERT INTO investment_hypotheses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("hyp"),
                    project_id,
                    "",
                    assumption["assumption_text"],
                    _task_type_to_hypothesis_category(assumption.get("verification_method", "")),
                    "unverified",
                    "company_claim_only",
                    "medium",
                    assumption["why_it_matters"],
                    "ai",
                    "",
                    ts,
                    ts,
                ),
            )

        for index, task in enumerate(analysis["verification_tasks"]):
            action_id = new_id("action")
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
            conn.execute(
                "INSERT INTO research_actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    action_id,
                    project_id,
                    task["title"],
                    task["missing_evidence"],
                    _task_type_to_action_type(task.get("task_type", "")),
                    "ai_suggested",
                    task["risk_level"],
                    "low",
                    "",
                    "",
                    task["suggested_materials"],
                    "",
                    "",
                    task["existing_evidence"],
                    "",
                    "ai",
                    ts,
                    ts,
                ),
            )
            if task.get("suggested_materials"):
                conn.execute(
                    "INSERT INTO material_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        new_id("matreq"),
                        project_id,
                        task["suggested_materials"],
                        task["missing_evidence"],
                        "",
                        "",
                        task["risk_level"],
                        "required",
                        "ai_suggested",
                        "",
                        "ai",
                        "",
                        ts,
                        ts,
                    ),
                )

        sector = analysis.get("sector_analysis", {})
        conn.execute(
            "INSERT INTO sector_analyses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_id("sector"),
                project_id,
                sector.get("primary_industry", ""),
                sector.get("sub_sector", ""),
                sector.get("target_customer", ""),
                sector.get("value_chain_position", ""),
                sector.get("replacement_target", ""),
                sector.get("profit_pool_logic", ""),
                sector.get("summary", ""),
                ts,
                ts,
            ),
        )

        for node in analysis.get("industry_map", []):
            conn.execute(
                "INSERT INTO industry_map_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("imap"),
                    project_id,
                    node.get("node_type", ""),
                    node.get("label", ""),
                    node.get("description", ""),
                    1 if node.get("is_company_position") else 0,
                    ts,
                    ts,
                ),
            )

        for term in analysis.get("industry_terms", []):
            conn.execute(
                "INSERT INTO industry_terms VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("term"),
                    project_id,
                    term.get("term", ""),
                    term.get("explanation", ""),
                    term.get("relevance", ""),
                    ts,
                    ts,
                ),
            )

        for flag in analysis.get("red_flags", []):
            _normalize_flag = {
                "source_chunk_id": flag.get("source_chunk_id") or "",
                "source_page": int(flag.get("source_page") or 1),
            }
            conn.execute(
                "INSERT INTO red_flags VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("flag"),
                    project_id,
                    flag.get("title", ""),
                    flag.get("flag_type", ""),
                    flag.get("severity", "medium"),
                    flag.get("status", "open"),
                    flag.get("evidence", ""),
                    _normalize_flag["source_chunk_id"],
                    _normalize_flag["source_page"],
                    flag.get("why_it_matters", ""),
                    flag.get("suggested_verification", ""),
                    "",
                    "",
                    ts,
                    ts,
                ),
            )
            conn.execute(
                "INSERT INTO risk_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("risk"),
                    project_id,
                    flag.get("title", ""),
                    flag.get("why_it_matters", ""),
                    flag.get("flag_type", "other"),
                    "needs_verification",
                    flag.get("severity", "medium"),
                    "company_claim_only",
                    _normalize_flag["source_chunk_id"],
                    _normalize_flag["source_page"],
                    flag.get("suggested_verification", ""),
                    "medium",
                    "ai",
                    "",
                    ts,
                    ts,
                ),
            )

        funding = analysis.get("funding_analysis", {})
        conn.execute(
            "INSERT INTO funding_analyses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_id("funding"),
                project_id,
                funding.get("stated_round", ""),
                funding.get("inferred_round", ""),
                funding.get("round_confidence", "medium"),
                funding.get("material_sufficiency", ""),
                funding.get("risk_return_profile", ""),
                funding.get("stability_assessment", ""),
                funding.get("payback_cycle_view", ""),
                funding.get("investor_signal", ""),
                json.dumps(funding.get("existing_investors", []), ensure_ascii=False),
                funding.get("missing_round_evidence", ""),
                funding.get("valuation_fit", ""),
                funding.get("suggested_checks", ""),
                ts,
                ts,
            ),
        )

        scorecards = [
            ("material_completeness", "low", "当前主要依赖上传材料，仍需补充原始证据。"),
            ("source_traceability", "medium" if analysis.get("bp_claims") else "not_assessable", "材料陈述和初步亮点已绑定来源页和原文摘录。"),
            ("hypothesis_coverage", "medium" if analysis.get("assumptions") else "low", "已形成关键假设和待验证动作。"),
            ("evidence_strength", "low", "多数关键信息仍停留在材料陈述（未核验）层面。"),
            ("risk_clarity", "medium" if analysis.get("red_flags") else "low", "疑似异常和信息缺口已初步列出，仍需人工复核。"),
            ("strategy_context_completeness", "not_assessable", "基金策略匹配需要研究员配置策略后再判断。"),
        ]
        for dimension, level, explanation in scorecards:
            conn.execute(
                "INSERT INTO readiness_scorecards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id("score"), project_id, dimension, level, explanation, "company_claim_only", "", None, "ai", ts, ts),
            )

        company = analysis["company_summary"]
        conn.execute(
            """
            UPDATE projects
            SET company_name = ?, industry = ?, financing_stage = ?, one_liner = ?,
                current_recommendation = ?, risk_level = ?, updated_at = ?,
                ai_research_state = ?, material_stage = ?, judgement_readiness = ?,
                evidence_sufficiency = ?, last_ai_summary = ?, pending_ai_updates_count = ?
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
                "key_gaps_identified",
                "only_bp" if len({chunk.get("document_id") for chunk in all_analysis_chunks}) <= 1 else "bp_plus_basic_docs",
                "limited" if analysis.get("bp_claims") else "very_limited",
                "low" if not analysis.get("evidence_links") else "medium",
                analysis.get("document_summary", ""),
                0,
                project_id,
            ),
        )
        conn.execute(
            "INSERT INTO project_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_id("event"),
                project_id,
                "ai_analysis_generated",
                "AI 生成低权限结构化研究底稿",
                "ai",
                "LLM",
                "project",
                project_id,
                json.dumps({"claim_count": len(analysis.get("bp_claims", [])), "task_count": len(analysis.get("verification_tasks", []))}, ensure_ascii=False),
                ts,
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
        for update in result.get("red_flag_updates", []):
            flag = fetch_one(conn, "SELECT * FROM red_flags WHERE id = ? AND project_id = ?", (update.get("red_flag_id"), project_id))
            if not flag:
                continue
            status = update.get("new_status") or flag["status"]
            conn.execute(
                "INSERT INTO supplementary_resolutions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("resolution"),
                    project_id,
                    document["id"],
                    "red_flag",
                    flag["id"],
                    flag["title"],
                    status,
                    update.get("evidence_text", ""),
                    update.get("impact_summary", ""),
                    update.get("remaining_gap", ""),
                    ts,
                ),
            )
        for resolution in result.get("material_resolutions", []):
            target_id = resolution.get("target_id", "")
            target_type = resolution.get("target_type", "material")
            target_title = resolution.get("target_title", "")
            if target_type == "task" and target_id:
                task = fetch_one(conn, "SELECT title FROM verification_tasks WHERE id = ? AND project_id = ?", (target_id, project_id))
                target_title = target_title or (task["title"] if task else "")
            conn.execute(
                "INSERT INTO supplementary_resolutions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("resolution"),
                    project_id,
                    document["id"],
                    target_type,
                    target_id,
                    target_title,
                    resolution.get("resolution_status", "new_information"),
                    resolution.get("evidence_text", ""),
                    resolution.get("impact_summary", ""),
                    resolution.get("remaining_gap", ""),
                    ts,
                ),
            )
        financial = result.get("financial_analysis")
        has_financial_analysis = isinstance(financial, dict) and any(str(value).strip() for value in financial.values())
        if has_financial_analysis:
            conn.execute(
                "INSERT INTO financial_analyses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("fin"),
                    project_id,
                    document["id"],
                    financial.get("summary", ""),
                    financial.get("revenue_quality", ""),
                    financial.get("margin_costs", ""),
                    financial.get("cashflow_quality", ""),
                    financial.get("customer_concentration", ""),
                    financial.get("anomalies", ""),
                    financial.get("bp_conflicts", ""),
                    financial.get("follow_up_materials", ""),
                    ts,
                    ts,
                ),
            )
        conn.execute(
            """
            UPDATE projects
            SET current_recommendation = ?, risk_level = ?, ai_research_state = ?,
                material_stage = ?, evidence_sufficiency = ?, last_ai_summary = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                result["stage_recommendation"],
                result["risk_level"],
                "evidence_partially_collected",
                "bp_plus_financials" if has_financial_analysis else "bp_plus_basic_docs",
                "medium" if result.get("task_updates") or result.get("red_flag_updates") else "low",
                result.get("material_summary", ""),
                ts,
                project_id,
            ),
        )


def create_ai_suggestion(
    project_id: str,
    suggestion_type: str,
    target_object_type: str | None,
    target_object_id: str | None,
    suggested_change_json: Dict[str, Any],
    ai_reason: str = "",
) -> str:
    suggestion_id = new_id("suggestion")
    ts = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO ai_suggestions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                suggestion_id,
                project_id,
                suggestion_type,
                target_object_type or "",
                target_object_id or "",
                json.dumps(suggested_change_json, ensure_ascii=False),
                ai_reason,
                "pending",
                ts,
                "",
                "",
                "",
                "",
            ),
        )
        conn.execute(
            """
            UPDATE projects
            SET pending_ai_updates_count = (
                SELECT COUNT(*) FROM ai_suggestions WHERE project_id = ? AND status = 'pending'
            ), updated_at = ?
            WHERE id = ?
            """,
            (project_id, ts, project_id),
        )
    return suggestion_id


def list_pending_ai_suggestions(project_id: str) -> List[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        return fetch_all(conn, "SELECT * FROM ai_suggestions WHERE project_id = ? AND status = 'pending' ORDER BY created_at", (project_id,))


def review_ai_suggestion(suggestion_id: str, human_action: str, human_note: str = "", reviewed_by: str = "") -> None:
    ts = now()
    with connect() as conn:
        suggestion = fetch_one(conn, "SELECT * FROM ai_suggestions WHERE id = ?", (suggestion_id,))
        if not suggestion:
            return
        status = "accepted" if human_action == "accept" else "ignored" if human_action == "ignore" else "needs_review"
        suggested_change = json.loads(suggestion["suggested_change_json"] or "{}")
        applied_summary = ""
        if human_action == "accept":
            if suggestion["target_object_type"] == "verification_task":
                task = fetch_one(conn, "SELECT * FROM verification_tasks WHERE id = ?", (suggestion["target_object_id"],))
                if task:
                    new_status = suggested_change.get("new_status") or task["status"]
                    user_notes = "\n".join(
                        part
                        for part in [
                            task.get("user_notes", ""),
                            f"AI 建议已由 {reviewed_by or '研究员'} 接受：{suggested_change.get('evidence_text', '')}",
                            f"仍缺：{suggested_change.get('still_missing', '')}" if suggested_change.get("still_missing") else "",
                            f"新问题：{suggested_change.get('new_questions', '')}" if suggested_change.get("new_questions") else "",
                            human_note,
                        ]
                        if part
                    )
                    conn.execute(
                        "UPDATE verification_tasks SET status = ?, user_notes = ?, updated_at = ? WHERE id = ?",
                        (new_status, user_notes, ts, task["id"]),
                    )
                    action_status = "done" if new_status == "verified" else "in_progress" if new_status == "partially_verified" else "open"
                    conn.execute(
                        """
                        UPDATE research_actions
                        SET action_status = ?, human_note = ?, updated_at = ?
                        WHERE project_id = ? AND title = ?
                        """,
                        (action_status, user_notes, ts, task["project_id"], task["title"]),
                    )
                    if task["linked_claim_id"]:
                        conn.execute("UPDATE bp_claims SET verification_status = ?, updated_at = ? WHERE id = ?", (new_status, ts, task["linked_claim_id"]))
                    if task["linked_assumption_id"]:
                        conn.execute("UPDATE investment_assumptions SET current_status = ?, updated_at = ? WHERE id = ?", (new_status, ts, task["linked_assumption_id"]))
                    applied_summary = f"已应用到验证任务：{task['title']}"
            elif suggestion["target_object_type"] == "red_flag":
                flag = fetch_one(conn, "SELECT * FROM red_flags WHERE id = ?", (suggestion["target_object_id"],))
                if flag:
                    new_status = suggested_change.get("new_status") or flag["status"]
                    resolution_note = "\n".join(
                        part
                        for part in [
                            flag.get("resolution_note", ""),
                            suggested_change.get("resolution_note", ""),
                            suggested_change.get("impact_summary", ""),
                            f"仍缺：{suggested_change.get('remaining_gap', '')}" if suggested_change.get("remaining_gap") else "",
                            human_note,
                        ]
                        if part
                    )
                    conn.execute(
                        "UPDATE red_flags SET status = ?, resolution_note = ?, updated_at = ? WHERE id = ?",
                        (new_status, resolution_note, ts, flag["id"]),
                    )
                    risk_status = "needs_verification" if new_status == "open" else new_status
                    conn.execute(
                        """
                        UPDATE risk_items
                        SET risk_status = ?, human_note = ?, updated_at = ?
                        WHERE project_id = ? AND risk_title = ?
                        """,
                        (risk_status, resolution_note, ts, flag["project_id"], flag["title"]),
                    )
                    applied_summary = f"已应用到待核验风险：{flag['title']}"
        conn.execute(
            """
            UPDATE ai_suggestions
            SET status = ?, reviewed_at = ?, reviewed_by = ?, human_action = ?, human_note = ?
            WHERE id = ?
            """,
            (status, ts, reviewed_by, human_action, human_note, suggestion_id),
        )
        conn.execute(
            """
            UPDATE projects
            SET pending_ai_updates_count = (
                SELECT COUNT(*) FROM ai_suggestions WHERE project_id = ? AND status = 'pending'
            ), updated_at = ?
            WHERE id = ?
            """,
            (suggestion["project_id"], ts, suggestion["project_id"]),
        )
        conn.execute(
            "INSERT INTO project_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_id("event"),
                suggestion["project_id"],
                "ai_suggestion_reviewed",
                applied_summary or f"研究员处理 AI 建议：{human_action}",
                "human",
                reviewed_by,
                "ai_suggestion",
                suggestion_id,
                json.dumps({"human_note": human_note}, ensure_ascii=False),
                ts,
            ),
        )


def update_human_project_status(
    project_id: str,
    new_status: str,
    reason: str = "",
    reason_category: str = "",
    decided_by: str = "",
) -> None:
    ts = now()
    with connect() as conn:
        project = fetch_one(conn, "SELECT human_project_status FROM projects WHERE id = ?", (project_id,))
        if not project:
            return
        previous = project["human_project_status"]
        conn.execute(
            """
            UPDATE projects
            SET human_project_status = ?, last_human_decision_reason = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_status, reason, ts, project_id),
        )
        conn.execute(
            "INSERT INTO human_decision_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (new_id("decision"), project_id, previous, new_status, reason, reason_category, decided_by, ts),
        )
        conn.execute(
            "INSERT INTO project_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_id("event"),
                project_id,
                "human_status_changed",
                f"人工状态从 {previous} 变更为 {new_status}",
                "human",
                decided_by,
                "project",
                project_id,
                json.dumps({"reason": reason, "reason_category": reason_category}, ensure_ascii=False),
                ts,
            ),
        )


def create_fund_strategy(data: Dict[str, Any]) -> str:
    init_db()
    strategy_id = new_id("strategy")
    ts = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO fund_strategies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                strategy_id,
                data.get("strategy_name", "").strip() or "默认基金策略",
                data.get("focus_sectors", ""),
                data.get("excluded_sectors", ""),
                data.get("preferred_stages", ""),
                data.get("excluded_stages", ""),
                data.get("ticket_size_min"),
                data.get("ticket_size_max"),
                data.get("target_ownership_min"),
                data.get("target_ownership_max"),
                data.get("geography_preference", ""),
                data.get("revenue_requirement", ""),
                data.get("gross_margin_requirement", ""),
                data.get("customer_type_preference", ""),
                1 if data.get("long_rd_cycle_allowed", True) else 0,
                1 if data.get("industrial_synergy_preferred") else 0,
                1 if data.get("requires_existing_investor") else 0,
                data.get("hard_redlines", ""),
                data.get("soft_preferences", ""),
                data.get("created_by", ""),
                ts,
                ts,
            ),
        )
    return strategy_id


def list_fund_strategies() -> List[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        return fetch_all(conn, "SELECT * FROM fund_strategies ORDER BY updated_at DESC")


def create_strategy_match(project_id: str, strategy_id: str, match_status: str, matched: list[str], unknown: list[str], outside: list[str], summary: str) -> str:
    match_id = new_id("match")
    ts = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO project_strategy_matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                match_id,
                project_id,
                strategy_id,
                match_status,
                json.dumps(matched, ensure_ascii=False),
                json.dumps(unknown, ensure_ascii=False),
                json.dumps(outside, ensure_ascii=False),
                summary,
                "ai",
                ts,
                ts,
            ),
        )
        conn.execute("UPDATE projects SET strategy_match_status = ?, updated_at = ? WHERE id = ?", (match_status, ts, project_id))
    return match_id


def create_material_request(project_id: str, material_name: str, why_needed: str, priority: str = "medium", created_by: str = "human") -> str:
    request_id = new_id("matreq")
    ts = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO material_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (request_id, project_id, material_name.strip(), why_needed.strip(), "", "", priority, "required", "accepted_by_human" if created_by == "human" else "ai_suggested", "", created_by, "", ts, ts),
        )
    return request_id


def update_material_request_status(request_id: str, status: str, human_note: str = "") -> None:
    ts = now()
    with connect() as conn:
        conn.execute("UPDATE material_requests SET status = ?, human_note = ?, updated_at = ? WHERE id = ?", (status, human_note, ts, request_id))


def insert_interview_note(project_id: str, interview_type: str, raw_note: str, interviewee_name: str = "", interviewee_role: str = "", organization: str = "", interview_date: str = "", created_by: str = "") -> str:
    note_id = new_id("interview")
    ts = now()
    summary = raw_note.strip()[:300]
    with connect() as conn:
        conn.execute(
            "INSERT INTO interview_notes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (note_id, project_id, interview_type, interviewee_name, interviewee_role, organization, interview_date, raw_note.strip(), summary, created_by, ts, ts),
        )
        conn.execute(
            "INSERT INTO project_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (new_id("event"), project_id, "interview_note_added", f"新增{interview_type}纪要", "human", created_by, "interview_note", note_id, "{}", ts),
        )
    return note_id


def upsert_memo_sections(project_id: str, memo_id: str, sections: List[Dict[str, str]]) -> None:
    ts = now()
    with connect() as conn:
        conn.execute("DELETE FROM memo_sections WHERE project_id = ? AND memo_id = ?", (project_id, memo_id))
        for section in sections:
            conn.execute(
                "INSERT INTO memo_sections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("msection"),
                    project_id,
                    memo_id,
                    section["section_key"],
                    section["section_title"],
                    section.get("ai_draft", ""),
                    section.get("human_edited_text", ""),
                    section.get("source_refs_json", "[]"),
                    ts,
                    ts,
                ),
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


def create_manual_research_question(
    project_id: str,
    assumption_text: str,
    importance: str,
    risk_level: str,
    why_it_matters: str,
    failure_impact: str,
    verification_method: str,
    source_note: str = "",
    human_note: str = "",
    created_by: str = "human",
) -> str:
    assumption_id = new_id("manual_assumption")
    ts = now()
    context_parts = [why_it_matters.strip()]
    if source_note.strip():
        context_parts.append(f"当前材料线索：{source_note.strip()}")
    if human_note.strip():
        context_parts.append(f"人工备注：{human_note.strip()}")
    if created_by.strip():
        context_parts.append(f"创建人：{created_by.strip()}")
    with connect() as conn:
        conn.execute(
            "INSERT INTO investment_assumptions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                assumption_id,
                project_id,
                assumption_text.strip(),
                importance.strip(),
                risk_level,
                "unverified",
                "\n".join([part for part in context_parts if part]),
                failure_impact.strip(),
                verification_method.strip(),
                ts,
                ts,
            ),
        )
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (ts, project_id))
    return assumption_id


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
    linked_assumption_id: str = "",
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
                linked_assumption_id,
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
