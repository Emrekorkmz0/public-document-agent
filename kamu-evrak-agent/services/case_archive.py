from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def save_case_json(
    outputs_dir: Path,
    document_text: str,
    file_meta: Dict[str, Any],
    analysis: Dict[str, Any],
    routing: Dict[str, Any],
    draft: Dict[str, Any],
    sources: Optional[List[Dict[str, Any]]] = None,
    llm_status: Optional[Dict[str, Any]] = None,
) -> Path:
    """Analiz sonucunu outputs/cases altına JSON olarak kaydeder."""
    cases_dir = outputs_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"case_{stamp}.json"
    path = cases_dir / file_name

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "file_meta": file_meta or {},
        "document_text": document_text,
        "analysis": analysis,
        "routing": routing,
        "draft": draft,
        "sources": sources or [],
        "llm_status": llm_status or {},
        "human_approval_required": True,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_case_json_bytes(
    document_text: str,
    file_meta: Dict[str, Any],
    analysis: Dict[str, Any],
    routing: Dict[str, Any],
    draft: Dict[str, Any],
    sources: Optional[List[Dict[str, Any]]] = None,
    llm_status: Optional[Dict[str, Any]] = None,
) -> bytes:
    payload = {
        "file_meta": file_meta or {},
        "document_text": document_text,
        "analysis": analysis,
        "routing": routing,
        "draft": draft,
        "sources": sources or [],
        "llm_status": llm_status or {},
        "human_approval_required": True,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
