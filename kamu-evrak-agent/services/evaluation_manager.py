from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_TEST_CASES = [
    {
        "case_id": "TC-001",
        "title": "Yol bakım talebi dilekçesi",
        "document_text": """T.C. ÖRNEK BELEDİYESİ BAŞKANLIĞINA\n\nKonu: Yol bakım ve onarım talebi\n\nBelediyeniz sınırları içinde bulunan Cumhuriyet Mahallesi 145. Sokak üzerinde yol zemininin bozuk olması nedeniyle araç ve yaya ulaşımında sorun yaşanmaktadır. Gerekli bakım ve onarım çalışmalarının yapılmasını arz ederim.\n\nAd Soyad: Ahmet Yılmaz\nAdres: Cumhuriyet Mahallesi 145. Sokak No: 12\nTelefon: 05xx xxx xx xx\nTarih: 04.07.2026\nİmza\n""",
        "expected_document_type": "Şikâyet / talep",
        "expected_unit": "Fen İşleri Müdürlüğü",
        "expected_draft_keywords": ["inceleme", "ilgili birim", "bilgi"],
    },
    {
        "case_id": "TC-002",
        "title": "Personel izin talebi",
        "document_text": """T.C. ÖRNEK BELEDİYESİ\nİnsan Kaynakları Müdürlüğüne\n\nKonu: Yıllık izin talebi\n\n15.08.2026 - 22.08.2026 tarihleri arasında yıllık izin kullanmak istiyorum. Gereğini arz ederim.\n\nAd Soyad: Ayşe Demir\nBirim: Bilgi İşlem Müdürlüğü\nTarih: 04.07.2026\nİmza\n""",
        "expected_document_type": "Personel izin / görevlendirme",
        "expected_unit": "İnsan Kaynakları Müdürlüğü",
        "expected_draft_keywords": ["izin", "personel", "değerlendirme"],
    },
    {
        "case_id": "TC-003",
        "title": "Malzeme satın alma talebi",
        "document_text": """T.C. ÖRNEK BELEDİYESİ BAŞKANLIĞINA\n\nKonu: Malzeme temini talebi\n\nMüdürlüğümüzde kullanılmak üzere 10 adet dizüstü bilgisayar, 5 adet yazıcı ve gerekli sarf malzemelerinin temin edilmesi hususunda gereğini arz ederim.\n\nBirim: Bilgi İşlem Müdürlüğü\nTarih: 04.07.2026\n""",
        "expected_document_type": "Satın alma / malzeme talebi",
        "expected_unit": "Destek Hizmetleri Müdürlüğü",
        "expected_draft_keywords": ["malzeme", "temin", "ilgili birim"],
    },
    {
        "case_id": "TC-004",
        "title": "Bilgi edinme başvurusu",
        "document_text": """T.C. ÖRNEK BELEDİYESİ BAŞKANLIĞINA\n\nKonu: Bilgi edinme başvurusu\n\n4982 sayılı Bilgi Edinme Hakkı Kanunu kapsamında, 2025 yılında mahallemizde yapılan park bakım ve yenileme çalışmalarına ilişkin bilgi verilmesini arz ederim.\n\nAd Soyad: Mehmet Kaya\nE-posta: mehmet@example.com\nTarih: 04.07.2026\n""",
        "expected_document_type": "Bilgi edinme başvurusu",
        "expected_unit": "Yazı İşleri Müdürlüğü",
        "expected_draft_keywords": ["bilgi edinme", "başvuru", "ilgili"],
    },
]


def normalize_text(value: Any) -> str:
    return str(value or "").strip().lower().replace("ı", "i")


def is_match(predicted: Any, expected: Any) -> bool:
    p = normalize_text(predicted)
    e = normalize_text(expected)
    if not p or not e:
        return False
    return p == e or e in p or p in e


def ensure_default_test_cases(test_cases_dir: Path) -> Path:
    test_cases_dir.mkdir(parents=True, exist_ok=True)
    path = test_cases_dir / "test_cases.json"
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_TEST_CASES, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_test_cases(test_cases_dir: Path) -> List[Dict[str, Any]]:
    path = ensure_default_test_cases(test_cases_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("cases"), list):
            return data["cases"]
    except Exception:
        pass
    return DEFAULT_TEST_CASES


def save_test_case(test_cases_dir: Path, case: Dict[str, Any]) -> Path:
    path = ensure_default_test_cases(test_cases_dir)
    cases = load_test_cases(test_cases_dir)
    case_id = str(case.get("case_id") or f"TC-{len(cases)+1:03d}")
    case["case_id"] = case_id
    updated = False
    for idx, existing in enumerate(cases):
        if str(existing.get("case_id")) == case_id:
            cases[idx] = case
            updated = True
            break
    if not updated:
        cases.append(case)
    path.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def delete_test_case(test_cases_dir: Path, case_id: str) -> int:
    path = ensure_default_test_cases(test_cases_dir)
    cases = load_test_cases(test_cases_dir)
    remaining = [c for c in cases if str(c.get("case_id")) != str(case_id)]
    path.write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(cases) - len(remaining)


def evaluate_single_result(case: Dict[str, Any], pipeline_output: Dict[str, Any]) -> Dict[str, Any]:
    analysis = pipeline_output.get("analysis") or {}
    routing = pipeline_output.get("routing") or {}
    draft = pipeline_output.get("draft") or {}
    llm_status = pipeline_output.get("llm_status") or {}
    meta = pipeline_output.get("pipeline_meta") or {}

    predicted_type = analysis.get("document_type", "")
    expected_type = case.get("expected_document_type", "")
    predicted_unit = routing.get("recommended_unit", "")
    expected_unit = case.get("expected_unit", "")
    draft_body = draft.get("body", "")
    expected_keywords = case.get("expected_draft_keywords") or []

    keyword_hits = 0
    for kw in expected_keywords:
        if normalize_text(kw) in normalize_text(draft_body):
            keyword_hits += 1

    draft_keyword_score = keyword_hits / len(expected_keywords) if expected_keywords else 1.0

    return {
        "case_id": case.get("case_id"),
        "title": case.get("title"),
        "expected_document_type": expected_type,
        "predicted_document_type": predicted_type,
        "document_type_ok": is_match(predicted_type, expected_type),
        "expected_unit": expected_unit,
        "predicted_unit": predicted_unit,
        "routing_ok": is_match(predicted_unit, expected_unit),
        "draft_generated": bool(str(draft_body).strip()),
        "expected_draft_keywords": expected_keywords,
        "draft_keyword_hits": keyword_hits,
        "draft_keyword_score": round(draft_keyword_score, 3),
        "confidence": analysis.get("confidence", 0),
        "risk_level": analysis.get("risk_level", ""),
        "llm_status": llm_status.get("status", ""),
        "llm_detail": llm_status.get("detail", ""),
        "duration_ms": meta.get("duration_ms", 0),
    }


def aggregate_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    if total == 0:
        return {
            "total": 0,
            "classification_accuracy": 0,
            "routing_accuracy": 0,
            "draft_generation_rate": 0,
            "avg_draft_keyword_score": 0,
            "avg_confidence": 0,
            "avg_duration_ms": 0,
            "passed_cases": 0,
            "failed_cases": 0,
        }
    classification_ok = sum(1 for r in results if r.get("document_type_ok"))
    routing_ok = sum(1 for r in results if r.get("routing_ok"))
    draft_generated = sum(1 for r in results if r.get("draft_generated"))
    passed_cases = sum(1 for r in results if r.get("document_type_ok") and r.get("routing_ok") and r.get("draft_generated"))
    avg_draft_keyword_score = sum(float(r.get("draft_keyword_score", 0)) for r in results) / total
    avg_confidence = sum(float(r.get("confidence", 0) or 0) for r in results) / total
    avg_duration_ms = sum(int(r.get("duration_ms", 0) or 0) for r in results) / total
    return {
        "total": total,
        "classification_accuracy": round(classification_ok / total, 3),
        "routing_accuracy": round(routing_ok / total, 3),
        "draft_generation_rate": round(draft_generated / total, 3),
        "avg_draft_keyword_score": round(avg_draft_keyword_score, 3),
        "avg_confidence": round(avg_confidence, 3),
        "avg_duration_ms": int(avg_duration_ms),
        "passed_cases": passed_cases,
        "failed_cases": total - passed_cases,
    }


def build_evaluation_payload(results: List[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "settings": settings or {},
        "metrics": aggregate_metrics(results),
        "results": results,
    }


def save_evaluation_report(outputs_dir: Path, payload: Dict[str, Any]) -> Path:
    report_dir = outputs_dir / "evaluation_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = report_dir / f"evaluation_report_{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_evaluation_json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def build_evaluation_csv_bytes(results: List[Dict[str, Any]]) -> bytes:
    output = io.StringIO()
    fieldnames = [
        "case_id", "title", "expected_document_type", "predicted_document_type", "document_type_ok",
        "expected_unit", "predicted_unit", "routing_ok", "draft_generated", "draft_keyword_score",
        "confidence", "risk_level", "llm_status", "duration_ms"
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in results:
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    return output.getvalue().encode("utf-8-sig")


def build_evaluation_markdown(payload: Dict[str, Any]) -> str:
    metrics = payload.get("metrics") or {}
    lines = [
        "# Kamu Evrak Agent Sistemi Değerlendirme Raporu",
        "",
        f"Oluşturma zamanı: {payload.get('created_at', '-')}",
        "",
        "## Özet Metrikler",
        "",
        f"- Toplam test: {metrics.get('total', 0)}",
        f"- Evrak sınıflandırma doğruluğu: %{int(float(metrics.get('classification_accuracy', 0)) * 100)}",
        f"- Birim yönlendirme doğruluğu: %{int(float(metrics.get('routing_accuracy', 0)) * 100)}",
        f"- Taslak üretim oranı: %{int(float(metrics.get('draft_generation_rate', 0)) * 100)}",
        f"- Ortalama taslak anahtar kelime skoru: %{int(float(metrics.get('avg_draft_keyword_score', 0)) * 100)}",
        f"- Ortalama güven: %{int(float(metrics.get('avg_confidence', 0)) * 100)}",
        f"- Ortalama süre: {metrics.get('avg_duration_ms', 0)} ms",
        f"- Geçen test: {metrics.get('passed_cases', 0)}",
        f"- Kalan/iyileştirilecek test: {metrics.get('failed_cases', 0)}",
        "",
        "## Test Sonuçları",
        "",
    ]
    for row in payload.get("results") or []:
        status = "BAŞARILI" if row.get("document_type_ok") and row.get("routing_ok") and row.get("draft_generated") else "İYİLEŞTİRİLECEK"
        lines.extend([
            f"### {row.get('case_id')} — {row.get('title')}",
            f"- Durum: {status}",
            f"- Evrak türü: beklenen `{row.get('expected_document_type')}`, çıkan `{row.get('predicted_document_type')}`",
            f"- Birim: beklenen `{row.get('expected_unit')}`, çıkan `{row.get('predicted_unit')}`",
            f"- Taslak anahtar kelime skoru: {row.get('draft_keyword_score')}",
            f"- LLM durumu: {row.get('llm_status')} — {row.get('llm_detail')}",
            "",
        ])
    return "\n".join(lines)
