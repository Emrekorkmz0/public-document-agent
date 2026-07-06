from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Tuple

REQUIRED_ANALYSIS_KEYS = {
    "document_type": "Belirsiz",
    "confidence": 0.5,
    "risk_level": "Orta",
    "summary": "Özet üretilemedi.",
    "extracted_fields": {},
    "missing_information": [],
    "user_recommendation": "Yetkili personel tarafından kontrol edilmesi önerilir.",
}

REQUIRED_EXTRACTED_FIELDS = {
    "sender": None,
    "receiver": None,
    "date": None,
    "subject": None,
    "document_number": None,
    "request_or_action": None,
    "signature_present": False,
    "contact_info_present": False,
    "address_present": False,
}

REQUIRED_DRAFT_KEYS = {
    "draft_type": "Ön inceleme yazısı",
    "subject": "Evrak Hakkında",
    "body": "Taslak metin üretilemedi. Evrakın yetkili personel tarafından incelenmesi önerilir.",
    "closing": "Bilgilerinize rica ederim.",
    "requires_human_approval": True,
}


def _safe_float(value: Any, default: float = 0.5) -> float:
    try:
        value = float(value)
    except Exception:
        return default
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


def validate_analysis(analysis: Dict[str, Any] | None) -> Tuple[Dict[str, Any], List[str]]:
    """Analiz çıktısını uygulamanın beklediği şemaya normalize eder."""
    warnings: List[str] = []
    normalized = deepcopy(REQUIRED_ANALYSIS_KEYS)

    if not isinstance(analysis, dict):
        warnings.append("Analiz çıktısı sözlük formatında değildi; varsayılan şema kullanıldı.")
        analysis = {}

    for key, default in REQUIRED_ANALYSIS_KEYS.items():
        value = analysis.get(key, default)
        if value in [None, "", "null", "None"]:
            warnings.append(f"Analiz alanı boş geldi: {key}")
            value = default
        normalized[key] = value

    normalized["confidence"] = _safe_float(normalized.get("confidence"), 0.5)

    extracted = normalized.get("extracted_fields")
    if not isinstance(extracted, dict):
        warnings.append("extracted_fields sözlük formatında değildi; sıfırlandı.")
        extracted = {}

    fixed_extracted = deepcopy(REQUIRED_EXTRACTED_FIELDS)
    fixed_extracted.update({k: v for k, v in extracted.items() if k in REQUIRED_EXTRACTED_FIELDS or isinstance(k, str)})
    for bool_key in ["signature_present", "contact_info_present", "address_present"]:
        fixed_extracted[bool_key] = bool(fixed_extracted.get(bool_key))
    normalized["extracted_fields"] = fixed_extracted

    if not isinstance(normalized.get("missing_information"), list):
        warnings.append("missing_information liste formatında değildi; listeye çevrildi.")
        normalized["missing_information"] = [str(normalized.get("missing_information"))]

    # Özet hâlâ boş/varsayılan ise alanlardan basit bir özet üretmeye çalış.
    if normalized.get("summary") == "Özet üretilemedi.":
        subject = fixed_extracted.get("subject")
        action = fixed_extracted.get("request_or_action")
        if subject or action:
            normalized["summary"] = f"Evrak, {subject or 'belirtilen konu'} hakkında {action or 'işlem talebi'} içermektedir."

    return normalized, warnings


def validate_draft(draft: Dict[str, Any] | None, analysis: Dict[str, Any] | None = None) -> Tuple[Dict[str, Any], List[str]]:
    """Taslak çıktısını normalize eder ve her zaman insan onayını zorunlu işaretler."""
    warnings: List[str] = []
    normalized = deepcopy(REQUIRED_DRAFT_KEYS)

    if not isinstance(draft, dict):
        warnings.append("Taslak çıktısı sözlük formatında değildi; varsayılan taslak kullanıldı.")
        draft = {}

    for key, default in REQUIRED_DRAFT_KEYS.items():
        value = draft.get(key, default)
        if value in [None, "", "null", "None"]:
            warnings.append(f"Taslak alanı boş geldi: {key}")
            value = default
        normalized[key] = value

    analysis = analysis or {}
    extracted = analysis.get("extracted_fields") or {}
    if normalized.get("subject") == "Evrak Hakkında" and extracted.get("subject"):
        normalized["subject"] = extracted.get("subject")

    body = str(normalized.get("body", "")).strip()
    if len(body) < 40:
        warnings.append("Taslak gövdesi kısa görünüyor.")
    normalized["body"] = body or REQUIRED_DRAFT_KEYS["body"]
    normalized["requires_human_approval"] = True
    return normalized, warnings
