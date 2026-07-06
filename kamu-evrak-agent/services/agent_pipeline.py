from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional

from services.rag_service import LocalRAGService
from services.vector_rag_service import VectorRAGService
from services.document_analyzer import analyze_document
from services.analysis_utils import merge_llm_with_rule_analysis, document_debug_info
from services.routing_service import recommend_unit
from services.draft_generator import generate_official_draft
from services.llm_agent import analyze_and_draft_with_openai, analyze_and_draft_with_openrouter
from services.validation_service import validate_analysis, validate_draft


@dataclass
class AgentStep:
    """Arayüzde gösterilebilir agent işlem kaydı."""

    agent: str
    status: str
    summary: str
    duration_ms: int = 0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "status": self.status,
            "summary": self.summary,
            "duration_ms": self.duration_ms,
            "details": self.details,
        }


class AgentTrace:
    def __init__(self) -> None:
        self.steps: List[AgentStep] = []

    def add(self, agent: str, status: str, summary: str, start_time: float, details: Optional[Dict[str, Any]] = None) -> None:
        self.steps.append(
            AgentStep(
                agent=agent,
                status=status,
                summary=summary,
                duration_ms=int((perf_counter() - start_time) * 1000),
                details=details or {},
            )
        )

    def as_list(self) -> List[Dict[str, Any]]:
        return [step.to_dict() for step in self.steps]


def _build_review(analysis: Dict[str, Any], draft: Dict[str, Any], llm_review: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Son güvenlik kontrolü.

    İnsan onayı gerekliliği kamu evrak sistemi için normal bir durumdur; tek başına hata/warning değildir.
    Gerçek uyarı sadece eksik bilgi, zayıf taslak veya yüksek risk varsa üretilir.
    """
    missing = analysis.get("missing_information") or []
    issues: List[str] = []
    blocking_issues: List[str] = []

    if missing:
        issues.extend(missing[:6])
    if not draft.get("body") or len(str(draft.get("body", "")).strip()) < 40:
        blocking_issues.append("Taslak metin çok kısa veya boş görünüyor.")
    if draft.get("requires_human_approval") is not True:
        blocking_issues.append("Taslakta insan onayı zorunluluğu açık şekilde işaretlenmemiş.")
    if analysis.get("risk_level") == "Yüksek":
        blocking_issues.append("Evrak yüksek riskli görünüyor; manuel kontrol gereklidir.")

    if llm_review and isinstance(llm_review.get("issues"), list):
        for item in llm_review.get("issues", []):
            if item and item not in issues and item not in blocking_issues:
                issues.append(item)

    if blocking_issues:
        status = "warning"
        label = "Uyarı Var"
        severity = "warning"
    elif issues:
        status = "needs_info"
        label = "Eksik Bilgi / Kontrol Bekliyor"
        severity = "info"
    else:
        status = "human_review"
        label = "İnsan Onayı Gerekli"
        severity = "info"

    return {
        "status": status,
        "label": label,
        "severity": severity,
        "issues": issues,
        "blocking_issues": blocking_issues,
        "safety_note": "Bu sistem karar vermez; öneri ve taslak üretir. Nihai karar ve onay yetkili personele aittir.",
        "requires_human_approval": True,
    }


def run_multi_agent_pipeline(
    *,
    document_text: str,
    source_dirs: List[Path],
    vector_store_dir: Path,
    rag_mode: str,
    force_rebuild_index: bool,
    top_k: int,
    scenario: str,
    llm_mode: str,
    openai_model: str,
    openrouter_model: str,
    draft_type_preference: str,
) -> Dict[str, Any]:
    """Kamu evrak analizi için kontrollü çok-agent iş akışı.

    Bu sürümde agentlar ardışık ve izlenebilir şekilde çalışır:
    Reader → RAG Retrieval → Classifier/Extractor → Routing → Drafting → Review.
    LLM agent başarısız olursa sistem kural tabanlı üretime düşer.
    """

    trace = AgentTrace()
    total_start = perf_counter()
    document_text = document_text or ""

    # 1) Reader Agent
    start = perf_counter()
    text_debug = document_debug_info(document_text)
    reader_warnings: List[str] = []
    if text_debug.get("is_empty"):
        reader_warnings.append("Evrak metni boş görünüyor.")
    if text_debug.get("character_count", 0) < 80:
        reader_warnings.append("Evrak metni çok kısa; OCR veya metin çıkarma kontrol edilmeli.")
    trace.add(
        "Reader Agent",
        "warning" if reader_warnings else "success",
        "Evrak metni alındı ve temel kalite kontrolü yapıldı.",
        start,
        {
            "character_count": text_debug.get("character_count", 0),
            "word_count": text_debug.get("word_count", 0),
            "line_count": text_debug.get("line_count", 0),
            "warnings": reader_warnings,
        },
    )

    # 2) RAG Retrieval Agent
    start = perf_counter()
    rag_info: Dict[str, Any]
    rag_warning: Optional[str] = None
    try:
        if rag_mode == "Embedding RAG":
            rag = VectorRAGService(source_dirs=source_dirs, vector_store_dir=vector_store_dir)
            rag_info = rag.build_index(force_rebuild=force_rebuild_index)
            matched_sources = rag.search(document_text, top_k=top_k)
        else:
            rag = LocalRAGService(source_dirs=source_dirs)
            matched_sources = rag.search(document_text, top_k=top_k)
            rag_info = {"backend": "tfidf", "status": "manual", "chunk_count": len(matched_sources)}
        trace.add(
            "RAG Retrieval Agent",
            "success",
            f"{len(matched_sources)} kaynak parçası getirildi.",
            start,
            {
                "rag_backend": rag_info.get("backend"),
                "rag_status": rag_info.get("status"),
                "chunk_count": rag_info.get("chunk_count"),
                "top_sources": [src.get("title") for src in matched_sources[:3]],
            },
        )
    except Exception as exc:
        rag_warning = f"Embedding RAG çalışmadı, Basit TF-IDF moduna geçildi. Detay: {exc}"
        rag = LocalRAGService(source_dirs=source_dirs)
        matched_sources = rag.search(document_text, top_k=top_k)
        rag_info = {"backend": "tfidf", "status": "fallback", "chunk_count": len(matched_sources)}
        trace.add(
            "RAG Retrieval Agent",
            "fallback",
            "Embedding RAG başarısız oldu; TF-IDF yedek arama kullanıldı.",
            start,
            {"error": str(exc), "top_sources": [src.get("title") for src in matched_sources[:3]]},
        )

    # 3) Classifier / Extractor Agent
    start = perf_counter()
    rule_analysis = analyze_document(document_text)
    trace.add(
        "Classifier & Extractor Agent",
        "success",
        f"Evrak türü: {rule_analysis.get('document_type')} / Güven: %{int(rule_analysis.get('confidence', 0) * 100)}",
        start,
        {
            "document_type": rule_analysis.get("document_type"),
            "confidence": rule_analysis.get("confidence"),
            "extracted_fields": rule_analysis.get("extracted_fields"),
            "missing_count": len(rule_analysis.get("missing_information") or []),
        },
    )

    # 4) Routing Agent
    start = perf_counter()
    routing = recommend_unit(document_text, scenario=scenario)
    trace.add(
        "Routing Agent",
        "success",
        f"Önerilen birim: {routing.get('recommended_unit')}",
        start,
        {
            "recommended_unit": routing.get("recommended_unit"),
            "confidence": routing.get("confidence"),
            "reason": routing.get("reason"),
            "alternative_units": routing.get("alternative_units"),
        },
    )

    # 5) Drafting Agent / LLM Agent
    start = perf_counter()
    llm_status: Dict[str, Any] = {
        "mode": llm_mode,
        "status": "not_used",
        "detail": "Kural tabanlı analiz kullanıldı.",
        "text_debug": text_debug,
    }
    llm_review: Optional[Dict[str, Any]] = None

    if llm_mode in ["OpenAI LLM Agent", "OpenRouter LLM Agent"]:
        try:
            if llm_mode == "OpenRouter LLM Agent":
                selected_model = openrouter_model.strip() or "openrouter/free"
                llm_output = analyze_and_draft_with_openrouter(
                    document_text=document_text,
                    matched_sources=matched_sources,
                    routing=routing,
                    draft_type_preference=draft_type_preference,
                    model=selected_model,
                )
            else:
                selected_model = openai_model.strip() or "gpt-4.1-mini"
                llm_output = analyze_and_draft_with_openai(
                    document_text=document_text,
                    matched_sources=matched_sources,
                    routing=routing,
                    draft_type_preference=draft_type_preference,
                    model=selected_model,
                )

            analysis = merge_llm_with_rule_analysis(llm_output.get("analysis", {}), rule_analysis)
            draft = llm_output.get("draft") or {}
            if not draft.get("subject") or str(draft.get("subject")).lower() in ["null", "none", ""]:
                draft["subject"] = analysis.get("extracted_fields", {}).get("subject") or "Evrak Hakkında"
            draft["requires_human_approval"] = True
            llm_review = llm_output.get("review", {})
            provider_meta = llm_output.get("provider_meta", {})
            llm_status = {
                "mode": llm_mode,
                "status": "success",
                "detail": f"{llm_mode} ile JSON analiz ve taslak üretildi.",
                "model": selected_model,
                "provider_meta": provider_meta,
                "review": llm_review,
                "text_debug": text_debug,
            }
            trace.add(
                "Drafting LLM Agent",
                "success",
                f"LLM ile {draft.get('draft_type', 'taslak')} üretildi.",
                start,
                {"mode": llm_mode, "model": selected_model, "draft_type": draft.get("draft_type"), "provider_meta": provider_meta},
            )
        except Exception as exc:
            analysis = rule_analysis
            draft = generate_official_draft(
                document_text=document_text,
                analysis=analysis,
                routing=routing,
                matched_sources=matched_sources,
                draft_type_preference=draft_type_preference,
            )
            llm_status = {
                "mode": llm_mode,
                "status": "fallback",
                "detail": f"LLM Agent çalışmadı, kural tabanlı moda geçildi. Detay: {exc}",
                "text_debug": text_debug,
            }
            trace.add(
                "Drafting LLM Agent",
                "fallback",
                "LLM çağrısı başarısız oldu; kural tabanlı taslak üretildi.",
                start,
                {"error": str(exc)},
            )
    else:
        analysis = rule_analysis
        draft = generate_official_draft(
            document_text=document_text,
            analysis=analysis,
            routing=routing,
            matched_sources=matched_sources,
            draft_type_preference=draft_type_preference,
        )
        trace.add(
            "Drafting Agent",
            "success",
            f"Kural tabanlı {draft.get('draft_type', 'taslak')} üretildi.",
            start,
            {"draft_type": draft.get("draft_type"), "subject": draft.get("subject")},
        )

    # 6) Validation Agent
    start = perf_counter()
    analysis, analysis_validation_warnings = validate_analysis(analysis)
    draft, draft_validation_warnings = validate_draft(draft, analysis=analysis)
    validation_warnings = analysis_validation_warnings + draft_validation_warnings
    trace.add(
        "Validation Agent",
        "warning" if validation_warnings else "success",
        "Analiz ve taslak JSON şeması doğrulandı; eksik alanlar normalize edildi.",
        start,
        {"warnings": validation_warnings, "warning_count": len(validation_warnings)},
    )

    # 7) Review Agent
    start = perf_counter()
    review = _build_review(analysis, draft, llm_review=llm_review)
    llm_status["final_review"] = review
    review_step_status = "warning" if review.get("severity") == "warning" else "info"
    trace.add(
        "Review & Safety Agent",
        review_step_status,
        review.get("label", "İnsan onayı gerekli"),
        start,
        review,
    )

    return {
        "analysis": analysis,
        "matched_sources": matched_sources,
        "rag_info": rag_info,
        "rag_warning": rag_warning,
        "routing": routing,
        "draft": draft,
        "llm_status": llm_status,
        "agent_trace": trace.as_list(),
        "pipeline_meta": {
            "version": "MVP-8 Resource Managed Multi-Agent Workflow",
            "duration_ms": int((perf_counter() - total_start) * 1000),
            "agent_count": len(trace.steps),
        },
    }
