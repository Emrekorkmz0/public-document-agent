from typing import Dict, Any


UNIT_KEYWORDS = {
    "Fen İşleri Müdürlüğü": ["yol", "asfalt", "kaldırım", "altyapı", "bakım", "onarım", "çukur", "kanal"],
    "İnsan Kaynakları Müdürlüğü": ["personel", "izin", "görevlendirme", "rapor", "atama", "özlük"],
    "Destek Hizmetleri Müdürlüğü": ["satın alma", "malzeme", "teklif", "hizmet alımı", "araç", "bakım sözleşmesi"],
    "Mali Hizmetler Müdürlüğü": ["ödeme", "bütçe", "fatura", "tahakkuk", "mali", "harcama"],
    "Bilgi İşlem Müdürlüğü": ["yazılım", "donanım", "bilgisayar", "internet", "sistem", "veri", "ebys"],
    "Basın ve Halkla İlişkiler Müdürlüğü": ["duyuru", "basın", "vatandaş", "iletişim", "sosyal medya", "halkla ilişkiler"],
    "Yazı İşleri Müdürlüğü": ["evrak", "dağıtım", "sayı", "konu", "ilgi", "üst yazı", "kurumlar arası"],
}


def recommend_unit(text: str, scenario: str = "Belediye") -> Dict[str, Any]:
    lower = text.lower()
    scores = {}
    for unit, keywords in UNIT_KEYWORDS.items():
        scores[unit] = sum(1 for kw in keywords if kw in lower)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_unit, best_score = ranked[0]

    if best_score == 0:
        return {
            "recommended_unit": "Yazı İşleri Müdürlüğü",
            "confidence": 0.45,
            "reason": "Evrakta belirgin bir uzman birim anahtar kelimesi bulunamadığı için ön kayıt ve genel yönlendirme amacıyla Yazı İşleri Müdürlüğü önerildi.",
            "alternative_units": ["Basın ve Halkla İlişkiler Müdürlüğü", "İlgili uzman birim"],
        }

    alternatives = [unit for unit, score in ranked[1:4] if score > 0]
    if "Yazı İşleri Müdürlüğü" not in alternatives and best_unit != "Yazı İşleri Müdürlüğü":
        alternatives.append("Yazı İşleri Müdürlüğü")

    confidence = min(0.95, 0.55 + best_score * 0.1)
    return {
        "recommended_unit": best_unit,
        "confidence": round(confidence, 2),
        "reason": f"Evrak metninde {best_unit} görev alanıyla ilişkili ifadeler tespit edildi.",
        "alternative_units": alternatives[:3],
    }
