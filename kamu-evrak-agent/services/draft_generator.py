from typing import Dict, Any, List


def generate_official_draft(
    document_text: str,
    analysis: Dict[str, Any],
    routing: Dict[str, Any],
    matched_sources: List[Dict[str, Any]],
    draft_type_preference: str = "Otomatik seç",
) -> Dict[str, Any]:
    missing = analysis.get("missing_information", [])
    subject = analysis.get("extracted_fields", {}).get("subject") or "Başvuru Hakkında"
    unit = routing.get("recommended_unit", "İlgili Birim")

    if draft_type_preference != "Otomatik seç":
        draft_type = draft_type_preference
    elif missing:
        draft_type = "Eksik bilgi talebi"
    elif unit != "Yazı İşleri Müdürlüğü":
        draft_type = "İç yönlendirme"
    else:
        draft_type = "Cevap yazısı"

    if draft_type == "Eksik bilgi talebi":
        missing_lines = "\n".join([f"- {item}" for item in missing])
        body = f"""İlgi başvurunuzun incelenmesi neticesinde, işlem yapılabilmesi için aşağıda belirtilen bilgilerin tamamlanmasına ihtiyaç duyulduğu değerlendirilmiştir:\n\n{missing_lines}\n\nEksik bilgilerin tamamlanmasının ardından başvurunuz yeniden değerlendirmeye alınacaktır.\n\nBilgilerinize rica ederim."""
    elif draft_type == "İç yönlendirme":
        body = f"""Kurumumuza iletilen başvuru incelenmiş olup, başvuru içeriğinin {unit} görev alanıyla ilişkili olduğu değerlendirilmiştir.\n\nSöz konusu evrakın ilgili birim tarafından incelenerek gerekli işlemlerin yürütülmesi hususunda gereğini rica ederim."""
    elif draft_type == "Üst yazı":
        body = f"""İlgi evrak kapsamında belirtilen hususların değerlendirilmesi amacıyla gerekli incelemenin yapılması ve sonucundan kurumumuza bilgi verilmesi hususunda gereğini arz/rica ederim."""
    else:
        body = f"""İlgi başvurunuzda belirtilen hususlar incelenmek üzere ilgili birime iletilmiştir.\n\nBaşvurunuza konu talep hakkında gerekli değerlendirme yapılacak olup, süreç sonucunda tarafınıza ayrıca bilgi verilecektir.\n\nBilgilerinize rica ederim."""

    source_titles = ", ".join([src["title"] for src in matched_sources[:2]]) if matched_sources else "Kaynak bulunamadı"

    return {
        "draft_type": draft_type,
        "subject": subject,
        "body": body,
        "source_note": source_titles,
        "requires_human_approval": True,
    }


def build_download_text(
    analysis: Dict[str, Any],
    routing: Dict[str, Any],
    draft: Dict[str, Any],
    sources: List[Dict[str, Any]],
) -> str:
    source_lines = "\n".join([
        f"- {src['title']} / Benzerlik: %{int(src['score'] * 100)} / Dosya: {src['file_name']}"
        for src in sources
    ]) or "- Kaynak bulunamadı"

    missing_lines = "\n".join([f"- {item}" for item in analysis.get("missing_information", [])]) or "- Belirgin eksik bilgi yok"

    return f"""KAMU EVRAK VE YAZIŞMA AGENT SİSTEMİ ÇIKTISI\n\nEVRAK ANALİZİ\nEvrak Türü: {analysis.get('document_type')}\nÖzet: {analysis.get('summary')}\nRisk Seviyesi: {analysis.get('risk_level')}\n\nEKSİK BİLGİLER\n{missing_lines}\n\nBİRİM YÖNLENDİRME\nÖnerilen Birim: {routing.get('recommended_unit')}\nGerekçe: {routing.get('reason')}\n\nRAG KAYNAKLARI\n{source_lines}\n\nRESMÎ YAZI TASLAĞI\nYazı Türü: {draft.get('draft_type')}\nKonu: {draft.get('subject')}\n\n{draft.get('body')}\n\nNot: Bu çıktı otomatik taslak niteliğindedir. Nihai karar ve onay yetkili personele aittir.\n"""
