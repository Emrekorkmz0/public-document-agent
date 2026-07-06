from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

WORKFLOW_STATUSES = [
    "Yeni Evrak",
    "Analiz Edildi",
    "Yönlendirme Bekliyor",
    "Birimde İncelemede",
    "Taslak Hazırlandı",
    "Onay Bekliyor",
    "Revizyon Gerekli",
    "Onaylandı",
    "Arşivlendi",
    "Reddedildi",
]

STATUS_TRANSITIONS = {
    "Yeni Evrak": ["Analiz Edildi", "Yönlendirme Bekliyor", "Reddedildi"],
    "Analiz Edildi": ["Yönlendirme Bekliyor", "Birimde İncelemede", "Taslak Hazırlandı", "Reddedildi"],
    "Yönlendirme Bekliyor": ["Birimde İncelemede", "Revizyon Gerekli", "Reddedildi"],
    "Birimde İncelemede": ["Taslak Hazırlandı", "Revizyon Gerekli", "Reddedildi"],
    "Taslak Hazırlandı": ["Onay Bekliyor", "Revizyon Gerekli", "Reddedildi"],
    "Onay Bekliyor": ["Onaylandı", "Revizyon Gerekli", "Reddedildi"],
    "Revizyon Gerekli": ["Birimde İncelemede", "Taslak Hazırlandı", "Onay Bekliyor", "Reddedildi"],
    "Onaylandı": ["Arşivlendi"],
    "Arşivlendi": [],
    "Reddedildi": ["Revizyon Gerekli"],
}

ROLE_ALLOWED_STATUSES = {
    "admin": WORKFLOW_STATUSES,
    "yazi_isleri": ["Yeni Evrak", "Analiz Edildi", "Yönlendirme Bekliyor", "Birimde İncelemede", "Taslak Hazırlandı", "Onay Bekliyor", "Revizyon Gerekli", "Arşivlendi", "Reddedildi"],
    "birim_yetkilisi": ["Birimde İncelemede", "Taslak Hazırlandı", "Revizyon Gerekli"],
    "onayci": ["Onay Bekliyor", "Onaylandı", "Revizyon Gerekli", "Reddedildi", "Arşivlendi"],
    "viewer": [],
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def workflow_dir(outputs_dir: Path) -> Path:
    path = outputs_dir / "workflows"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_slug(text: str, fallback: str = "evrak") -> str:
    text = (text or fallback).strip().lower()
    table = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    text = text.translate(table)
    text = re.sub(r"[^a-z0-9_-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:60] or fallback


def _workflow_id(username: str, subject: str = "") -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return f"WF-{stamp}-{_safe_slug(username, 'user')}-{_safe_slug(subject, 'evrak')}"


def _path(outputs_dir: Path, workflow_id: str) -> Path:
    return workflow_dir(outputs_dir) / f"{workflow_id}.json"


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _visible_for_role(item: Dict[str, Any], role: str, username: str) -> bool:
    if role == "admin":
        return True
    if role == "viewer":
        return True
    status = item.get("status", "")
    assigned_unit = (item.get("assigned_unit") or "").lower()
    if role == "yazi_isleri":
        return True
    if role == "birim_yetkilisi":
        return status in {"Birimde İncelemede", "Taslak Hazırlandı", "Revizyon Gerekli"}
    if role == "onayci":
        return status in {"Onay Bekliyor", "Onaylandı", "Revizyon Gerekli", "Reddedildi", "Arşivlendi"}
    return False


def create_workflow_case(
    outputs_dir: Path,
    username: str,
    role: str,
    document_text: str,
    file_meta: Dict[str, Any],
    analysis: Dict[str, Any],
    routing: Dict[str, Any],
    draft: Dict[str, Any],
    sources: List[Dict[str, Any]],
    run_id: str = "",
    note: str = "",
) -> Dict[str, Any]:
    subject = draft.get("subject") or analysis.get("extracted_fields", {}).get("subject") or analysis.get("document_type") or "evrak"
    workflow_id = _workflow_id(username, subject)
    created_at = now_iso()
    payload = {
        "workflow_id": workflow_id,
        "run_id": run_id,
        "created_at": created_at,
        "updated_at": created_at,
        "created_by": username,
        "created_by_role": role,
        "status": "Onay Bekliyor" if draft.get("body") else "Analiz Edildi",
        "assigned_unit": routing.get("recommended_unit") or "Yazı İşleri Müdürlüğü",
        "priority": "Normal",
        "document_type": analysis.get("document_type", "Belirsiz"),
        "risk_level": analysis.get("risk_level", "Orta"),
        "summary": analysis.get("summary", ""),
        "subject": subject,
        "file_meta": file_meta,
        "document_text": document_text,
        "analysis": analysis,
        "routing": routing,
        "draft": draft,
        "sources": sources,
        "history": [
            {
                "timestamp": created_at,
                "user": username,
                "role": role,
                "action": "workflow_created",
                "from_status": None,
                "to_status": "Onay Bekliyor" if draft.get("body") else "Analiz Edildi",
                "note": note or "Analiz sonucu iş akışına aktarıldı.",
            }
        ],
        "unit_notes": [],
        "approval_notes": [],
    }
    _save(_path(outputs_dir, workflow_id), payload)
    return payload


def list_workflow_cases(outputs_dir: Path, role: str = "admin", username: str = "") -> List[Dict[str, Any]]:
    items = []
    for path in sorted(workflow_dir(outputs_dir).glob("*.json"), reverse=True):
        try:
            payload = _load(path)
            if _visible_for_role(payload, role, username):
                items.append(payload)
        except Exception:
            continue
    return items


def get_workflow_case(outputs_dir: Path, workflow_id: str) -> Optional[Dict[str, Any]]:
    path = _path(outputs_dir, workflow_id)
    if not path.exists():
        return None
    return _load(path)


def allowed_next_statuses(current_status: str, role: str) -> List[str]:
    possible = STATUS_TRANSITIONS.get(current_status, [])
    role_allowed = ROLE_ALLOWED_STATUSES.get(role, [])
    if role == "admin":
        return possible
    return [s for s in possible if s in role_allowed]


def update_workflow_status(
    outputs_dir: Path,
    workflow_id: str,
    new_status: str,
    username: str,
    role: str,
    note: str = "",
    assigned_unit: str = "",
    priority: str = "",
) -> Dict[str, Any]:
    payload = get_workflow_case(outputs_dir, workflow_id)
    if not payload:
        raise FileNotFoundError(f"Workflow kaydı bulunamadı: {workflow_id}")

    old_status = payload.get("status", "")
    next_allowed = allowed_next_statuses(old_status, role)
    if role != "admin" and new_status not in next_allowed:
        raise PermissionError(f"Bu rol '{old_status}' durumundan '{new_status}' durumuna geçiş yapamaz.")

    payload["status"] = new_status
    payload["updated_at"] = now_iso()
    if assigned_unit:
        payload["assigned_unit"] = assigned_unit
    if priority:
        payload["priority"] = priority
    event = {
        "timestamp": payload["updated_at"],
        "user": username,
        "role": role,
        "action": "status_changed",
        "from_status": old_status,
        "to_status": new_status,
        "note": note,
    }
    payload.setdefault("history", []).append(event)
    if role == "birim_yetkilisi" and note:
        payload.setdefault("unit_notes", []).append(event)
    if role in {"onayci", "admin"} and note:
        payload.setdefault("approval_notes", []).append(event)
    _save(_path(outputs_dir, workflow_id), payload)
    return payload


def update_workflow_draft(outputs_dir: Path, workflow_id: str, draft_body: str, username: str, role: str, note: str = "") -> Dict[str, Any]:
    payload = get_workflow_case(outputs_dir, workflow_id)
    if not payload:
        raise FileNotFoundError(f"Workflow kaydı bulunamadı: {workflow_id}")
    payload.setdefault("draft", {})["body"] = draft_body
    payload["updated_at"] = now_iso()
    payload.setdefault("history", []).append(
        {
            "timestamp": payload["updated_at"],
            "user": username,
            "role": role,
            "action": "draft_updated",
            "from_status": payload.get("status"),
            "to_status": payload.get("status"),
            "note": note or "Taslak metni güncellendi.",
        }
    )
    _save(_path(outputs_dir, workflow_id), payload)
    return payload


def delete_workflow_case(outputs_dir: Path, workflow_id: str, username: str, role: str) -> Path:
    path = _path(outputs_dir, workflow_id)
    if not path.exists():
        raise FileNotFoundError(workflow_id)
    trash = outputs_dir / "deleted_workflows"
    trash.mkdir(parents=True, exist_ok=True)
    target = trash / f"{workflow_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    payload = _load(path)
    payload.setdefault("history", []).append(
        {
            "timestamp": now_iso(),
            "user": username,
            "role": role,
            "action": "workflow_deleted",
            "from_status": payload.get("status"),
            "to_status": "deleted_backup",
            "note": "Kayıt yedeğe taşındı.",
        }
    )
    _save(target, payload)
    path.unlink()
    return target


def filter_workflow_cases(
    items: List[Dict[str, Any]],
    query: str = "",
    statuses: Optional[List[str]] = None,
    units: Optional[List[str]] = None,
    priorities: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    q = (query or "").strip().lower()
    statuses = statuses or []
    units = units or []
    priorities = priorities or []
    out = []
    for item in items:
        if statuses and item.get("status") not in statuses:
            continue
        if units and item.get("assigned_unit") not in units:
            continue
        if priorities and item.get("priority") not in priorities:
            continue
        if q:
            hay = " ".join(
                str(item.get(k, "")) for k in ["workflow_id", "subject", "summary", "document_type", "assigned_unit", "status", "created_by"]
            ).lower()
            if q not in hay:
                continue
        out.append(item)
    return out


def workflow_stats(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_status: Dict[str, int] = {}
    by_unit: Dict[str, int] = {}
    for item in items:
        by_status[item.get("status", "-")] = by_status.get(item.get("status", "-"), 0) + 1
        by_unit[item.get("assigned_unit", "-")] = by_unit.get(item.get("assigned_unit", "-"), 0) + 1
    return {
        "total": len(items),
        "waiting_approval": by_status.get("Onay Bekliyor", 0),
        "in_unit_review": by_status.get("Birimde İncelemede", 0),
        "approved": by_status.get("Onaylandı", 0),
        "archived": by_status.get("Arşivlendi", 0),
        "by_status": by_status,
        "by_unit": by_unit,
    }


def build_workflow_csv_bytes(items: List[Dict[str, Any]]) -> bytes:
    output = io.StringIO()
    fieldnames = ["workflow_id", "created_at", "updated_at", "status", "priority", "assigned_unit", "document_type", "subject", "created_by", "risk_level"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for item in items:
        writer.writerow({k: item.get(k, "") for k in fieldnames})
    return output.getvalue().encode("utf-8-sig")


def build_workflow_zip(outputs_dir: Path, items: List[Dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("workflow_index.csv", build_workflow_csv_bytes(items))
        for item in items:
            workflow_id = item.get("workflow_id")
            if workflow_id:
                zf.writestr(f"workflows/{workflow_id}.json", json.dumps(item, ensure_ascii=False, indent=2, default=str))
    buffer.seek(0)
    return buffer.getvalue()
