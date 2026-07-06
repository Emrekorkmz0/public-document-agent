from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def default_db_path(base_dir: Path) -> Path:
    raw = os.getenv("DATABASE_URL", "").strip()
    # MVP-14 yerel SQLite kullanır. DATABASE_URL ileride PostgreSQL'e geçiş için ayrılmıştır.
    if raw.startswith("sqlite:///"):
        return Path(raw.replace("sqlite:///", "", 1)).expanduser().resolve()
    return base_dir / "outputs" / "database" / "kamu_evrak_agent.sqlite3"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_database(base_dir: Path) -> Path:
    db_path = default_db_path(base_dir)
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                username TEXT,
                role TEXT,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT,
                payload_json TEXT
            );

            CREATE TABLE IF NOT EXISTS document_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                username TEXT,
                role TEXT,
                file_name TEXT,
                file_type TEXT,
                document_hash TEXT,
                document_type TEXT,
                confidence REAL,
                risk_level TEXT,
                recommended_unit TEXT,
                draft_type TEXT,
                llm_mode TEXT,
                llm_status TEXT,
                rag_backend TEXT,
                duration_ms INTEGER,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS archive_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                username TEXT,
                run_id TEXT,
                archive_path TEXT,
                document_type TEXT,
                recommended_unit TEXT,
                payload_json TEXT
            );

            CREATE TABLE IF NOT EXISTS feedback_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                username TEXT,
                role TEXT,
                run_id TEXT,
                classification_ok INTEGER,
                routing_ok INTEGER,
                draft_ok INTEGER,
                corrected_document_type TEXT,
                corrected_unit TEXT,
                draft_quality TEXT,
                notes TEXT,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS resource_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                username TEXT,
                action TEXT NOT NULL,
                category TEXT,
                title TEXT,
                path TEXT,
                detail TEXT,
                payload_json TEXT
            );

            CREATE TABLE IF NOT EXISTS system_kv (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO system_kv(key, value, updated_at) VALUES (?, ?, ?)",
            ("schema_version", "mvp14_sqlite_v1", now_iso()),
        )
        conn.commit()
    return db_path


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _run_id(username: str, document_text: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    short_hash = _hash_text(document_text)[:10]
    safe_user = (username or "anon").replace(" ", "_")[:24]
    return f"RUN-{stamp}-{safe_user}-{short_hash}"


def log_event(
    base_dir: Path,
    username: str,
    role: str,
    action: str,
    status: str = "success",
    detail: str = "",
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    db_path = init_database(base_dir)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO audit_events(created_at, username, role, action, status, detail, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (now_iso(), username, role, action, status, detail, _json_dumps(payload or {})),
        )
        conn.commit()


def save_analysis_run(
    base_dir: Path,
    username: str,
    role: str,
    document_text: str,
    file_meta: Dict[str, Any],
    analysis: Dict[str, Any],
    routing: Dict[str, Any],
    draft: Dict[str, Any],
    sources: List[Dict[str, Any]],
    llm_status: Dict[str, Any],
    agent_trace: List[Dict[str, Any]],
    pipeline_meta: Dict[str, Any],
    rag_info: Dict[str, Any],
) -> str:
    db_path = init_database(base_dir)
    run_id = _run_id(username, document_text)
    payload = {
        "run_id": run_id,
        "document_text": document_text,
        "file_meta": file_meta,
        "analysis": analysis,
        "routing": routing,
        "draft": draft,
        "sources": sources,
        "llm_status": llm_status,
        "agent_trace": agent_trace,
        "pipeline_meta": pipeline_meta,
        "rag_info": rag_info,
    }
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO document_runs(
                run_id, created_at, username, role, file_name, file_type, document_hash,
                document_type, confidence, risk_level, recommended_unit, draft_type,
                llm_mode, llm_status, rag_backend, duration_ms, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                now_iso(),
                username,
                role,
                file_meta.get("file_name"),
                file_meta.get("file_type"),
                _hash_text(document_text),
                analysis.get("document_type"),
                float(analysis.get("confidence", 0) or 0),
                analysis.get("risk_level"),
                routing.get("recommended_unit"),
                draft.get("draft_type"),
                llm_status.get("mode"),
                llm_status.get("status"),
                rag_info.get("backend"),
                int((pipeline_meta or {}).get("duration_ms", 0) or 0),
                _json_dumps(payload),
            ),
        )
        conn.execute(
            """
            INSERT INTO audit_events(created_at, username, role, action, status, detail, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (now_iso(), username, role, "analysis_run_saved", "success", run_id, _json_dumps({"run_id": run_id})),
        )
        conn.commit()
    return run_id


def save_archive_reference(
    base_dir: Path,
    username: str,
    run_id: str,
    archive_path: str,
    analysis: Dict[str, Any],
    routing: Dict[str, Any],
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    db_path = init_database(base_dir)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO archive_records(created_at, username, run_id, archive_path, document_type, recommended_unit, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                username,
                run_id,
                archive_path,
                analysis.get("document_type"),
                routing.get("recommended_unit"),
                _json_dumps(payload or {}),
            ),
        )
        conn.commit()


def save_feedback_record(
    base_dir: Path,
    username: str,
    role: str,
    run_id: str,
    feedback: Dict[str, Any],
    payload: Dict[str, Any],
) -> None:
    db_path = init_database(base_dir)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO feedback_records(
                created_at, username, role, run_id, classification_ok, routing_ok, draft_ok,
                corrected_document_type, corrected_unit, draft_quality, notes, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                username,
                role,
                run_id,
                1 if feedback.get("classification_ok") else 0,
                1 if feedback.get("routing_ok") else 0,
                1 if feedback.get("draft_ok") else 0,
                feedback.get("corrected_document_type"),
                feedback.get("corrected_unit"),
                feedback.get("draft_quality"),
                feedback.get("notes"),
                _json_dumps(payload),
            ),
        )
        conn.commit()


def save_resource_event(
    base_dir: Path,
    username: str,
    action: str,
    category: str = "",
    title: str = "",
    path: str = "",
    detail: str = "",
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    db_path = init_database(base_dir)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO resource_events(created_at, username, action, category, title, path, detail, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now_iso(), username, action, category, title, path, detail, _json_dumps(payload or {})),
        )
        conn.commit()


def db_stats(base_dir: Path) -> Dict[str, Any]:
    db_path = init_database(base_dir)
    stats: Dict[str, Any] = {"db_path": str(db_path)}
    with connect(db_path) as conn:
        for table in ["document_runs", "feedback_records", "archive_records", "resource_events", "audit_events"]:
            stats[table] = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
        latest = conn.execute("SELECT created_at FROM document_runs ORDER BY id DESC LIMIT 1").fetchone()
        stats["latest_analysis"] = latest["created_at"] if latest else "-"
    return stats


def list_analysis_runs(base_dir: Path, limit: int = 25) -> List[Dict[str, Any]]:
    db_path = init_database(base_dir)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, run_id, created_at, username, file_name, document_type, confidence,
                   risk_level, recommended_unit, llm_status, rag_backend, duration_ms
            FROM document_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    return [dict(row) for row in rows]


def list_feedback_records(base_dir: Path, limit: int = 25) -> List[Dict[str, Any]]:
    db_path = init_database(base_dir)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, username, run_id, classification_ok, routing_ok, draft_ok,
                   corrected_document_type, corrected_unit, draft_quality, notes
            FROM feedback_records
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    return [dict(row) for row in rows]


def list_audit_events(base_dir: Path, limit: int = 50) -> List[Dict[str, Any]]:
    db_path = init_database(base_dir)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, username, role, action, status, detail
            FROM audit_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    return [dict(row) for row in rows]


def build_table_csv(rows: Iterable[Dict[str, Any]]) -> bytes:
    rows = list(rows)
    if not rows:
        return b""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


def build_db_export_zip(base_dir: Path) -> bytes:
    db_path = init_database(base_dir)
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as zf:
        if db_path.exists():
            zf.write(db_path, arcname="kamu_evrak_agent.sqlite3")
        zf.writestr("analysis_runs.csv", build_table_csv(list_analysis_runs(base_dir, limit=10000)))
        zf.writestr("feedback_records.csv", build_table_csv(list_feedback_records(base_dir, limit=10000)))
        zf.writestr("audit_events.csv", build_table_csv(list_audit_events(base_dir, limit=10000)))
    memory.seek(0)
    return memory.getvalue()
