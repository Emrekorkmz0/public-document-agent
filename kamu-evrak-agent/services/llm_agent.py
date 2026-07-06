import json
import os
import re
from typing import Any, Dict, List, Tuple


ANALYSIS_AND_DRAFT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["analysis", "draft", "review"],
    "properties": {
        "analysis": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "document_type",
                "confidence",
                "summary",
                "extracted_fields",
                "missing_information",
                "risk_level",
                "user_recommendation",
            ],
            "properties": {
                "document_type": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "summary": {"type": "string"},
                "extracted_fields": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "sender",
                        "receiver",
                        "date",
                        "subject",
                        "document_number",
                        "request_or_action",
                        "signature_present",
                        "contact_info_present",
                        "address_present",
                    ],
                    "properties": {
                        "sender": {"type": ["string", "null"]},
                        "receiver": {"type": ["string", "null"]},
                        "date": {"type": ["string", "null"]},
                        "subject": {"type": ["string", "null"]},
                        "document_number": {"type": ["string", "null"]},
                        "request_or_action": {"type": ["string", "null"]},
                        "signature_present": {"type": "boolean"},
                        "contact_info_present": {"type": "boolean"},
                        "address_present": {"type": "boolean"},
                    },
                },
                "missing_information": {"type": "array", "items": {"type": "string"}},
                "risk_level": {"type": "string", "enum": ["Düşük", "Orta", "Yüksek"]},
                "user_recommendation": {"type": "string"},
            },
        },
        "draft": {
            "type": "object",
            "additionalProperties": False,
            "required": ["draft_type", "subject", "body", "source_note", "requires_human_approval"],
            "properties": {
                "draft_type": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "source_note": {"type": "string"},
                "requires_human_approval": {"type": "boolean"},
            },
        },
        "review": {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "issues", "safety_note"],
            "properties": {
                "status": {"type": "string", "enum": ["ok", "requires_review"]},
                "issues": {"type": "array", "items": {"type": "string"}},
                "safety_note": {"type": "string"},
            },
        },
    },
}


def _sources_to_context(matched_sources: List[Dict[str, Any]], max_chars: int = 5500) -> str:
    parts: List[str] = []
    used = 0
    for idx, src in enumerate(matched_sources[:6], start=1):
        title = src.get("title", "Kaynak")
        source_type = src.get("source_type", "-")
        score = src.get("score", 0)
        content = (src.get("content") or "").strip()
        block = f"[Kaynak {idx}] Başlık: {title}\nTür: {source_type}\nBenzerlik: {score:.3f}\nİçerik:\n{content}\n"
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining > 500:
                parts.append(block[:remaining])
            break
        parts.append(block)
        used += len(block)
    return "\n---\n".join(parts) if parts else "Kaynak bulunamadı."


def _build_prompt(
    document_text: str,
    matched_sources: List[Dict[str, Any]],
    routing: Dict[str, Any],
    draft_type_preference: str,
) -> Tuple[str, str]:
    sources_context = _sources_to_context(matched_sources)
    preferred_type = draft_type_preference or "Otomatik seç"

    system_prompt = """Sen kamu evrak ve resmi yazışma süreçleri için çalışan yardımcı bir analiz ajanısın.
Görevin: evrakı sınıflandırmak, özetlemek, eksik bilgileri bulmak, RAG kaynaklarına dayanarak güvenli bir resmi yazı taslağı oluşturmaktır.
Kesin idari karar verme. Hukuki hüküm kurma. Kaynaklarda olmayan mevzuat maddesi uydurma.
Çıktıyı sadece istenen JSON şemasına uygun üret.
Türkçe, sade, resmi ve temkinli bir kamu yazışma dili kullan.
Eksik bilgi varsa kesin cevap yazısı yerine eksik bilgi talebi veya ön inceleme üslubu kullan.
Nihai onayın yetkili personelde olduğunu belirt.
"""

    user_prompt = f"""Aşağıdaki evrakı analiz et ve uygun resmi yazı taslağı üret.

KULLANICI TASLAK TÜRÜ TERCİHİ:
{preferred_type}

ÖNERİLEN BİRİM BİLGİSİ:
- Birim: {routing.get('recommended_unit', '-')}
- Gerekçe: {routing.get('reason', '-')}
- Güven: {routing.get('confidence', '-')}

RAG KAYNAKLARI:
{sources_context}

EVRAK METNİ:
{document_text[:9000]}

Kurallar:
1. Evrakta olmayan kişisel bilgiyi, tarih/sayı/isim bilgisini uydurma; yoksa null veya eksik bilgi olarak yaz.
2. Taslakta nihai karar verme; "değerlendirilmek üzere", "incelenmek üzere", "gerekli işlemlerin yürütülmesi" gibi temkinli ifadeler kullan.
3. RAG kaynaklarından yararlandıysan draft.source_note alanında kısa kaynak notu yaz.
4. Eksik bilgi varsa review.status alanını "requires_review" yap.
5. requires_human_approval her zaman true olmalı.
6. Sadece geçerli JSON döndür. JSON dışında açıklama, markdown veya kod bloğu yazma.
"""
    return system_prompt, user_prompt


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    """Model JSON dışı birkaç karakter döndürürse mümkün olduğunca toparlar."""
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Model boş yanıt döndürdü.")

    # ```json ... ``` gibi kod bloklarını temizle
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _ensure_output_shape(data: Dict[str, Any]) -> Dict[str, Any]:
    """Arayüzün beklediği temel alanları garanti eder."""
    analysis = data.setdefault("analysis", {})
    analysis.setdefault("document_type", "Belirsiz")
    analysis.setdefault("confidence", 0.5)
    analysis.setdefault("summary", "Özet üretilemedi.")
    analysis.setdefault("missing_information", [])
    analysis.setdefault("risk_level", "Orta")
    analysis.setdefault("user_recommendation", "Yetkili personel kontrolü önerilir.")
    fields = analysis.setdefault("extracted_fields", {})
    for key in [
        "sender",
        "receiver",
        "date",
        "subject",
        "document_number",
        "request_or_action",
    ]:
        fields.setdefault(key, None)
    for key in ["signature_present", "contact_info_present", "address_present"]:
        fields.setdefault(key, False)

    draft = data.setdefault("draft", {})
    draft.setdefault("draft_type", "Ön inceleme yazısı")
    draft.setdefault("subject", fields.get("subject") or "Evrak Hakkında")
    draft.setdefault("body", "İlgili evrakın yetkili personel tarafından incelenmesi önerilir.")
    draft.setdefault("source_note", "Kaynak notu üretilemedi.")
    draft["requires_human_approval"] = True

    review = data.setdefault("review", {})
    review.setdefault("status", "requires_review")
    review.setdefault("issues", [])
    review.setdefault("safety_note", "Nihai onay yetkili personele aittir.")
    return data


def _json_schema_response_format() -> Dict[str, Any]:
    """OpenAI Chat Completions ve OpenRouter ile uyumlu response_format."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "kamu_evrak_analysis_and_draft",
            "strict": True,
            "schema": ANALYSIS_AND_DRAFT_SCHEMA,
        },
    }


def _json_object_response_format() -> Dict[str, Any]:
    """Bazı OpenRouter/free modelleri json_schema desteklemez; json_object yedek modudur."""
    return {"type": "json_object"}


def _create_completion_resilient(client, model: str, system_prompt: str, user_prompt: str, provider: str):
    """Önce strict JSON schema dener, olmazsa json_object, o da olmazsa düz metin JSON ister.

    Ücretsiz OpenRouter modellerinde schema desteği değişken olabildiği için uygulamanın
    hemen kural tabanlı fallback'e düşmemesi adına üç kademeli deneme yapılır.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    attempts = [
        ("json_schema", {"response_format": _json_schema_response_format()}),
        ("json_object", {"response_format": _json_object_response_format()}),
        ("plain", {}),
    ]

    last_error = None
    for response_mode, extra_kwargs in attempts:
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
                **extra_kwargs,
            )
            raw_text = completion.choices[0].message.content or ""
            data = _ensure_output_shape(_extract_json_object(raw_text))
            data.setdefault("provider_meta", {})
            data["provider_meta"].update({
                "provider": provider,
                "requested_model": model,
                "response_mode": response_mode,
            })
            if getattr(completion, "model", None):
                data["provider_meta"]["actual_model"] = completion.model
            return data
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"LLM JSON çıktı üretimi başarısız oldu. Son hata: {last_error}")


def analyze_and_draft_with_openai(
    document_text: str,
    matched_sources: List[Dict[str, Any]],
    routing: Dict[str, Any],
    draft_type_preference: str = "Otomatik seç",
    model: str = "gpt-4.1-mini",
) -> Dict[str, Any]:
    """OpenAI Chat Completions ile analiz + taslak üretir."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY bulunamadı. .env dosyasına veya ortam değişkenlerine ekle.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("OpenAI paketi kurulu değil. Kurulum: pip install openai") from exc

    system_prompt, user_prompt = _build_prompt(
        document_text=document_text,
        matched_sources=matched_sources,
        routing=routing,
        draft_type_preference=draft_type_preference,
    )

    client = OpenAI(api_key=api_key)
    return _create_completion_resilient(
        client=client,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        provider="openai",
    )


def analyze_and_draft_with_openrouter(
    document_text: str,
    matched_sources: List[Dict[str, Any]],
    routing: Dict[str, Any],
    draft_type_preference: str = "Otomatik seç",
    model: str = "openrouter/free",
) -> Dict[str, Any]:
    """OpenRouter üzerinden OpenAI-compatible Chat Completions ile analiz + taslak üretir.

    .env içinde OPENROUTER_API_KEY gerekir. Ücretsiz denemeler için model olarak
    OPENROUTER_MODEL=openrouter/free kullanılabilir.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY bulunamadı. .env dosyasına ekle. OpenRouter anahtarları genelde sk-or- ile başlar.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("OpenAI paketi kurulu değil. Kurulum: pip install openai") from exc

    system_prompt, user_prompt = _build_prompt(
        document_text=document_text,
        matched_sources=matched_sources,
        routing=routing,
        draft_type_preference=draft_type_preference,
    )

    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    referer = os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost:8501")
    title = os.getenv("OPENROUTER_APP_TITLE", "Kamu Evrak Agent Sistemi")

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers={
            "HTTP-Referer": referer,
            "X-OpenRouter-Title": title,
        },
    )

    return _create_completion_resilient(
        client=client,
        model=model or "openrouter/free",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        provider="openrouter",
    )
