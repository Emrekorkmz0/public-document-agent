from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def save_feedback(
    *,
    outputs_dir: Path,
    document_text: str,
    analysis: Dict[str, Any],
    routing: Dict[str, Any],
    draft: Dict[str, Any],
    feedback: Dict[str, Any],
    file_meta: Optional[Dict[str, Any]] = None,
) -> Path:
    """Kullanıcı geri bildirimlerini JSONL formatında saklar.

    Bu dosya ileride sınıflandırma, yönlendirme ve taslak kalitesi için fine-tuning/evaluation veri setine dönüştürülebilir.
    """
    feedback_dir = outputs_dir / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    path = feedback_dir / "feedback_dataset.jsonl"

    record = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "file_meta": file_meta or {},
        "document_text": document_text,
        "system_output": {
            "analysis": analysis,
            "routing": routing,
            "draft": draft,
        },
        "human_feedback": feedback,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def build_feedback_jsonl_bytes(outputs_dir: Path) -> bytes:
    path = outputs_dir / "feedback" / "feedback_dataset.jsonl"
    if not path.exists():
        return b""
    return path.read_bytes()
