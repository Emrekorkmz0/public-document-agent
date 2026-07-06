import re
import unicodedata
from typing import Dict, Any, List, Tuple, Optional


def normalize_tr(text: str) -> str:
    """Türkçe metinde anahtar kelime yakalamayı kolaylaştırır."""
    text = (text or "").lower()
    replacements = {
        "ı": "i",
        "ğ": "g",
        "ü": "u",
        "ş": "s",
        "ö": "o",
        "ç": "c",
        "İ": "i",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


DOCUMENT_TYPES = {
    "dilekçe": ["dilekce", "arz ederim", "geregini arz", "basvuru", "talep ederim", "adi soyadi", "imza"],
    "şikâyet / talep": ["sikayet", "talep", "magdur", "onarim", "bakim", "yol", "kaldirim", "cukur", "altyapi"],
    "bilgi edinme başvurusu": ["bilgi edinme", "4982", "bilgi talep", "tarafima bildirilmesini"],
    "kurumlar arası üst yazı": ["ilgi", "dagitim", "sayi", "konu", "mudurlugune", "baskanligina", "geregini rica"],
    "satın alma / malzeme talebi": ["satin alma", "teklif", "malzeme", "hizmet alimi", "piyasa arastirmasi", "klavye", "mouse"],
    "personel izin / görevlendirme": ["izin", "gorevlendirme", "personel", "olur", "rapor", "ozluk", "yillik izin"],
}


REQUEST_PATTERNS = [
    r"(?P<req>[^.\n]*?(?:talep ederim|arz ederim|gereğini arz ederim|geregini arz ederim)[^.\n]*[.]?)",
    r"(?P<req>[^.\n]*?(?:yapılmasını|yapilmasini|başlatılmasını|baslatilmasini|bildirilmesini)[^.\n]*[.]?)",
]


def analyze_document(text: str) -> Dict[str, Any]:
    original = text or ""
    normalized = normalize_tr(original)

    if not original.strip():
        return {
            "document_type": "boş metin",
            "confidence": 0.0,
            "summary": "Analiz için metin bulunamadı.",
            "extracted_fields": default_fields(),
            "missing_information": ["Analiz için evrak metni bulunamadı."],
            "risk_level": "Yüksek",
            "user_recommendation": "Önce evrak metninin çıkarıldığından veya metin alanına yapıştırıldığından emin olun.",
        }

    doc_type, confidence = classify_document(normalized)
    fields = extract_fields(original, normalized)
    missing = find_missing_information(fields, normalized)
    summary = create_summary(original, doc_type, fields)
    risk_level = "Yüksek" if len(missing) >= 4 else ("Orta" if missing else "Düşük")

    return {
        "document_type": doc_type,
        "confidence": confidence,
        "summary": summary,
        "extracted_fields": fields,
        "missing_information": missing,
        "risk_level": risk_level,
        "user_recommendation": build_user_recommendation(missing),
    }


def default_fields() -> Dict[str, Any]:
    return {
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


def classify_document(normalized_text: str) -> Tuple[str, float]:
    scores = {}
    for doc_type, keywords in DOCUMENT_TYPES.items():
        score = 0
        for kw in keywords:
            if normalize_tr(kw) in normalized_text:
                score += 1
        scores[doc_type] = score

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    if best_score == 0:
        return "belirsiz evrak", 0.35

    # Aynı anda dilekçe ve talep izleri varsa vatandaş talebi daha açıklayıcıdır.
    if scores.get("şikâyet / talep", 0) >= 2 and scores.get("dilekçe", 0) >= 2:
        best_type = "şikâyet / talep"
        best_score = max(scores[best_type], scores.get("dilekçe", 0))

    total_possible = max(len(DOCUMENT_TYPES[best_type]), 1)
    confidence = min(0.95, 0.50 + (best_score / total_possible) * 0.45)
    return best_type, round(confidence, 2)


def extract_fields(text: str, normalized: Optional[str] = None) -> Dict[str, Any]:
    normalized = normalized or normalize_tr(text)
    fields = default_fields()

    date_match = re.search(r"(?:Tarih\s*[:：-]\s*)?(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})", text, flags=re.IGNORECASE)
    subject_match = re.search(r"Konu\s*[:：-]\s*(.+)", text, flags=re.IGNORECASE)
    number_match = re.search(r"Sayı\s*[:：-]\s*(.+)", text, flags=re.IGNORECASE)

    fields.update({
        "sender": find_sender(text),
        "receiver": find_receiver(text),
        "date": date_match.group(1).strip() if date_match else None,
        "subject": clean_line(subject_match.group(1)) if subject_match else infer_subject(normalized),
        "document_number": clean_line(number_match.group(1)) if number_match else None,
        "request_or_action": extract_request_or_action(text),
        "signature_present": has_signature(normalized),
        "contact_info_present": has_contact_info(text),
        "address_present": has_address(normalized),
    })
    return fields


def clean_line(value: str) -> str:
    return (value or "").strip().strip("-:： ")[:240]


def find_receiver(text: str) -> Optional[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:16]:
        upper = line.upper()
        if any(token in upper for token in ["BELEDİYE", "BELEDIYE", "MÜDÜRLÜ", "MUDURLU", "BAŞKANLI", "BASKANLI", "VALİLİ", "VALILI", "REKTÖRLÜ", "REKTORLU"]):
            if not re.search(r"^Konu\s*[:：-]", line, flags=re.IGNORECASE):
                return line
    return None


def find_sender(text: str) -> Optional[str]:
    patterns = [
        r"Ad[ıi]?\s*Soyad[ıi]?\s*[:：-]\s*(.+)",
        r"Ad\s*Soyad\s*[:：-]\s*(.+)",
        r"Başvuru\s*Sahibi\s*[:：-]\s*(.+)",
        r"Basvuru\s*Sahibi\s*[:：-]\s*(.+)",
        r"Gönderen\s*[:：-]\s*(.+)",
        r"Gonderen\s*[:：-]\s*(.+)",
    ]
    for pat in patterns:
        match = re.search(pat, text, flags=re.IGNORECASE)
        if match:
            value = clean_line(match.group(1))
            if value:
                return value

    # Son satırlarda iki kelimeli ad-soyad benzeri satırı yakalamaya çalış.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines[-10:]):
        if any(skip in normalize_tr(line) for skip in ["telefon", "adres", "imza", "tarih", "konu"]):
            continue
        if re.match(r"^[A-ZÇĞİÖŞÜ][a-zçğıöşü]+\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+", line):
            return clean_line(line)
    return None


def infer_subject(normalized: str) -> str:
    if any(word in normalized for word in ["yol", "kaldirim", "asfalt", "cukur", "altyapi"]):
        return "Yol bakım ve onarım talebi"
    if any(word in normalized for word in ["satin alma", "malzeme", "teklif", "hizmet alimi"]):
        return "Malzeme / satın alma talebi"
    if any(word in normalized for word in ["izin", "gorevlendirme", "personel"]):
        return "İzin / görevlendirme işlemi"
    if "bilgi edinme" in normalized:
        return "Bilgi edinme başvurusu"
    return "Evrak konusu otomatik olarak belirlenemedi"


def extract_request_or_action(text: str) -> Optional[str]:
    for pat in REQUEST_PATTERNS:
        match = re.search(pat, text, flags=re.IGNORECASE)
        if match:
            return clean_line(match.group("req"))

    # Konudan sonraki ilk anlamlı paragrafı kısa eylem özeti olarak al.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates = []
    for line in lines:
        n = normalize_tr(line)
        if any(skip in n for skip in ["t.c", "konu", "tarih", "adi soyadi", "telefon", "adres", "imza"]):
            continue
        if len(line) > 25:
            candidates.append(line)
    return clean_line(candidates[0]) if candidates else None


def has_signature(normalized_text: str) -> bool:
    return any(word in normalized_text for word in ["imza", "adi soyadi", "ad soyad", "arz ederim", "geregini arz"])


def has_contact_info(text: str) -> bool:
    return bool(re.search(r"(05\d{9}|05X{9}|\+90\s?5\d{9}|[\w.-]+@[\w.-]+\.\w+)", text, flags=re.IGNORECASE))


def has_address(normalized_text: str) -> bool:
    return any(word in normalized_text for word in ["mahalle", "mahallesi", "sokak", "cadde", "caddesi", "no:", "no ", "adres"])


def find_missing_information(fields: Dict[str, Any], normalized_text: str) -> List[str]:
    missing = []
    if not fields.get("sender"):
        missing.append("Başvuru sahibi / gönderen açık şekilde tespit edilemedi.")
    if not fields.get("date"):
        missing.append("Tarih bilgisi tespit edilemedi.")
    if not fields.get("contact_info_present"):
        missing.append("Telefon veya e-posta iletişim bilgisi tespit edilemedi.")
    if not fields.get("address_present") and any(word in normalized_text for word in ["yol", "altyapi", "kaldirim", "asfalt", "cukur"]):
        missing.append("Yerinde inceleme gerektiren talep için açık adres / konum bilgisi eksik olabilir.")
    if not fields.get("signature_present"):
        missing.append("İmza / ad-soyad alanı tespit edilemedi.")
    return missing


def create_summary(text: str, doc_type: str, fields: Dict[str, Any]) -> str:
    subject = fields.get("subject") or "belirtilen konu"
    sender = fields.get("sender") or "başvuru sahibi/gönderen"
    request = fields.get("request_or_action")

    if request:
        return f"{sender} tarafından iletilen evrak, {subject} konusuna ilişkindir. Evrakta öne çıkan talep/işlem: {request}"
    return f"Bu evrak '{doc_type}' türünde değerlendirilmiştir. Evrakta temel konu: {subject}. Sistem bu belge için ön inceleme, eksik bilgi kontrolü, kaynak eşleştirme ve birim yönlendirme önerisi üretmiştir."


def build_user_recommendation(missing: List[str]) -> str:
    if missing:
        return "İşlem öncesinde eksik görünen bilgilerin kullanıcıdan veya ilgili birimden tamamlatılması önerilir. Taslak yazı kesin karar içermemeli, ön inceleme veya bilgi talebi üslubunda hazırlanmalıdır."
    return "Evrak temel bilgiler açısından işlenebilir görünüyor. Yine de nihai değerlendirme ve onay yetkili personel tarafından yapılmalıdır."
