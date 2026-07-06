from typing import Dict, Any


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def merge_llm_with_rule_analysis(llm_analysis: Dict[str, Any], rule_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """LLM JSON çıktısında null/boş kalan alanları kural tabanlı analizle tamamlar.

    OpenRouter ücretsiz modelleri bazen geçerli JSON döndürse bile birçok alanı null bırakabiliyor.
    Bu fonksiyon arayüzde Belirsiz/Null görünmesini azaltır.
    """
    if not llm_analysis:
        return rule_analysis

    result = dict(llm_analysis)

    for key in ["document_type", "summary", "risk_level", "user_recommendation"]:
        if _is_empty(result.get(key)) or str(result.get(key)).lower() in ["belirsiz", "belirsiz evrak", "özet üretilemedi."]:
            result[key] = rule_analysis.get(key)

    if not isinstance(result.get("confidence"), (int, float)) or result.get("confidence", 0) < rule_analysis.get("confidence", 0):
        result["confidence"] = rule_analysis.get("confidence", result.get("confidence", 0.5))

    llm_fields = result.get("extracted_fields") or {}
    rule_fields = rule_analysis.get("extracted_fields") or {}
    merged_fields = dict(llm_fields)
    for key, value in rule_fields.items():
        if _is_empty(merged_fields.get(key)) or merged_fields.get(key) is False:
            # Boolean alanlarda LLM false dediyse ama kural tabanlı true bulduysa true'ya yükselt.
            if isinstance(value, bool):
                merged_fields[key] = bool(merged_fields.get(key) or value)
            else:
                merged_fields[key] = value
    result["extracted_fields"] = merged_fields

    llm_missing = result.get("missing_information") or []
    rule_missing = rule_analysis.get("missing_information") or []
    # LLM alanları dolu görünüyor ama missing listesi boşsa kural tabanlı eksikleri ekle.
    seen = set(str(item) for item in llm_missing)
    for item in rule_missing:
        if str(item) not in seen:
            llm_missing.append(item)
            seen.add(str(item))
    result["missing_information"] = llm_missing

    return result


def document_debug_info(document_text: str) -> Dict[str, Any]:
    text = document_text or ""
    lines = [line for line in text.splitlines() if line.strip()]
    return {
        "character_count": len(text),
        "word_count": len(text.split()),
        "line_count": len(lines),
        "first_500_chars": text[:500],
        "is_empty": not bool(text.strip()),
    }
