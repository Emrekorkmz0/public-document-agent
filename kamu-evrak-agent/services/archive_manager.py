from __future__ import annotations

import csv
import io
import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class CaseRecord:
    file_name: str
    path: Path
    created_at: str
    source_file: str
    document_type: str
    summary: str
    recommended_unit: str
    risk_level: str
    draft_type: str
    subject: str
    size_bytes: int
    modified_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "created_at": self.created_at,
            "archive_file": self.file_name,
            "source_file": self.source_file,
            "document_type": self.document_type,
            "recommended_unit": self.recommended_unit,
            "risk_level": self.risk_level,
            "draft_type": self.draft_type,
            "subject": self.subject,
            "summary": self.summary,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
        }


def _cases_dir(outputs_dir: Path) -> Path:
    path = outputs_dir / "cases"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_case_path(outputs_dir: Path, file_name: str) -> Path:
    name = Path(file_name).name
    if not name.endswith(".json"):
        raise ValueError("Arşiv dosyası JSON olmalıdır.")
    path = _cases_dir(outputs_dir) / name
    resolved_cases = _cases_dir(outputs_dir).resolve()
    resolved_path = path.resolve()
    if resolved_cases not in resolved_path.parents and resolved_path != resolved_cases:
        raise ValueError("Geçersiz arşiv dosyası yolu.")
    return path


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _first_nonempty(*values: Any, default: str = "-") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def case_payload_to_record(path: Path, payload: Dict[str, Any]) -> CaseRecord:
    stat = path.stat()
    analysis = payload.get("analysis") or {}
    routing = payload.get("routing") or {}
    draft = payload.get("draft") or {}
    file_meta = payload.get("file_meta") or {}
    extracted = analysis.get("extracted_fields") or {}

    created_at = _first_nonempty(payload.get("created_at"), datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"))
    return CaseRecord(
        file_name=path.name,
        path=path,
        created_at=created_at,
        source_file=_first_nonempty(file_meta.get("file_name"), default="manuel_giris"),
        document_type=_first_nonempty(analysis.get("document_type"), default="Belirsiz"),
        summary=_first_nonempty(analysis.get("summary"), default="Özet yok"),
        recommended_unit=_first_nonempty(routing.get("recommended_unit"), default="Belirsiz"),
        risk_level=_first_nonempty(analysis.get("risk_level"), default="Belirsiz"),
        draft_type=_first_nonempty(draft.get("draft_type"), default="Belirsiz"),
        subject=_first_nonempty(draft.get("subject"), extracted.get("subject"), default="Konu yok"),
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    )


def list_case_records(outputs_dir: Path) -> List[CaseRecord]:
    records: List[CaseRecord] = []
    for path in _cases_dir(outputs_dir).glob("*.json"):
        payload = _load_json(path)
        records.append(case_payload_to_record(path, payload))
    records.sort(key=lambda r: r.created_at, reverse=True)
    return records


def read_case_payload(outputs_dir: Path, file_name: str) -> Dict[str, Any]:
    path = _safe_case_path(outputs_dir, file_name)
    if not path.exists():
        raise FileNotFoundError(f"Arşiv kaydı bulunamadı: {file_name}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_case_json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _payload_search_text(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False).lower()


def filter_case_records(
    outputs_dir: Path,
    records: Iterable[CaseRecord],
    query: str = "",
    document_types: Optional[List[str]] = None,
    units: Optional[List[str]] = None,
    risk_levels: Optional[List[str]] = None,
) -> List[CaseRecord]:
    q = (query or "").strip().lower()
    document_types = [x for x in (document_types or []) if x]
    units = [x for x in (units or []) if x]
    risk_levels = [x for x in (risk_levels or []) if x]

    filtered: List[CaseRecord] = []
    for record in records:
        if document_types and record.document_type not in document_types:
            continue
        if units and record.recommended_unit not in units:
            continue
        if risk_levels and record.risk_level not in risk_levels:
            continue
        if q:
            payload = _load_json(record.path)
            haystack = " ".join([
                record.file_name,
                record.source_file,
                record.document_type,
                record.summary,
                record.recommended_unit,
                record.subject,
                _payload_search_text(payload),
            ]).lower()
            if q not in haystack:
                continue
        filtered.append(record)
    return filtered


def archive_stats(records: List[CaseRecord]) -> Dict[str, Any]:
    type_counts: Dict[str, int] = {}
    unit_counts: Dict[str, int] = {}
    for r in records:
        type_counts[r.document_type] = type_counts.get(r.document_type, 0) + 1
        unit_counts[r.recommended_unit] = unit_counts.get(r.recommended_unit, 0) + 1
    return {
        "total": len(records),
        "document_type_count": len(type_counts),
        "unit_count": len(unit_counts),
        "last_created_at": records[0].created_at if records else "-",
        "type_counts": type_counts,
        "unit_counts": unit_counts,
    }


def build_cases_csv_bytes(records: List[CaseRecord]) -> bytes:
    buffer = io.StringIO()
    fieldnames = [
        "created_at",
        "archive_file",
        "source_file",
        "document_type",
        "recommended_unit",
        "risk_level",
        "draft_type",
        "subject",
        "summary",
        "size_bytes",
        "modified_at",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for r in records:
        writer.writerow(r.to_dict())
    return buffer.getvalue().encode("utf-8-sig")


def build_cases_zip(outputs_dir: Path, records: Optional[List[CaseRecord]] = None) -> bytes:
    records = records if records is not None else list_case_records(outputs_dir)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for record in records:
            if record.path.exists():
                zf.write(record.path, arcname=f"cases/{record.file_name}")
        zf.writestr("archive_index.csv", build_cases_csv_bytes(records).decode("utf-8-sig"))
    buffer.seek(0)
    return buffer.getvalue()


def delete_case_record(outputs_dir: Path, file_name: str) -> Path:
    path = _safe_case_path(outputs_dir, file_name)
    if not path.exists():
        raise FileNotFoundError(file_name)
    deleted_dir = outputs_dir / "deleted_cases"
    deleted_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = deleted_dir / f"{path.stem}_deleted_{stamp}.json"
    shutil.move(str(path), str(target))
    return target
