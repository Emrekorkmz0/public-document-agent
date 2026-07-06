from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def _safe_read(path: Path, max_chars: int = 20000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return text[:max_chars]
    except Exception:
        return ""


def _count_files(path: Path, patterns: List[str] | None = None) -> int:
    if not path.exists():
        return 0
    if not patterns:
        return sum(1 for p in path.rglob("*") if p.is_file())
    total = 0
    for pattern in patterns:
        total += sum(1 for p in path.rglob(pattern) if p.is_file())
    return total


def build_project_snapshot(base_dir: Path) -> Dict[str, Any]:
    data_dir = base_dir / "data"
    outputs_dir = base_dir / "outputs"
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "project_name": "Kamu Evrak ve Yazışma Agent Sistemi",
        "version": "MVP-11 Final Demo",
        "main_features": [
            "Evrak yükleme ve metin çıkarma",
            "Embedding veya TF-IDF tabanlı RAG kaynak eşleştirme",
            "OpenRouter/OpenAI veya kural tabanlı agent analizi",
            "Çok-agent iş akışı: Reader, RAG, Classifier, Routing, Drafting, Validation, Review",
            "Resmî yazı taslağı ve DOCX çıktısı",
            "Kaynak yönetimi paneli",
            "Arşiv/geçmiş paneli",
            "Test/değerlendirme ve raporlama paneli",
            "Geri bildirim veri seti toplama",
        ],
        "resource_counts": {
            "regulations": _count_files(data_dir / "regulations", ["*.txt"]),
            "templates": _count_files(data_dir / "templates", ["*.txt"]),
            "unit_definitions": _count_files(data_dir / "unit_definitions", ["*.txt"]),
            "sample_documents": _count_files(data_dir / "sample_documents", ["*.txt"]),
            "test_cases_files": _count_files(data_dir / "test_cases", ["*.json"]),
        },
        "output_counts": {
            "archived_cases": _count_files(outputs_dir / "cases", ["*.json"]),
            "evaluation_reports": _count_files(outputs_dir / "evaluation_reports", ["*.json"]),
            "feedback_records": _count_files(outputs_dir / "feedback", ["*.jsonl"]),
        },
    }


def build_demo_markdown(base_dir: Path) -> str:
    snapshot = build_project_snapshot(base_dir)
    resource_counts = snapshot["resource_counts"]
    output_counts = snapshot["output_counts"]
    return f"""# Kamu Evrak ve Yazışma Agent Sistemi — MVP-11 Final Demo Rehberi

Oluşturulma zamanı: {snapshot['created_at']}

## 1. Projenin Kısa Tanımı

Bu sistem, kamu kurumlarına gelen evrakların okunması, sınıflandırılması, özetlenmesi, eksik bilgi kontrolü, ilgili birime yönlendirilmesi ve resmî yazı taslağı oluşturulması için geliştirilen çok-agent destekli bir RAG prototipidir.

Sistem karar vermez; analiz, öneri ve taslak üretir. Nihai onay yetkili kullanıcıya aittir.

## 2. Demo Sırasında Gösterilecek Ana Akış

1. Uygulamayı başlat.
2. Sol menüden `Agent modu: OpenRouter LLM Agent` veya `Kural tabanlı` seç.
3. `RAG modu: Embedding RAG` seç; sorun olursa `Basit TF-IDF` ile devam et.
4. `data/sample_documents/sample_yol_bakim_dilekcesi.txt` evrakını yükle.
5. `Metni Hazırla` butonuna bas.
6. Çıkarılan metni kontrol et.
7. `Analiz Et ve Taslak Oluştur` butonuna bas.
8. Şu sekmeleri sırayla göster:
   - Evrak Analizi
   - Eksik Bilgiler
   - RAG Kaynakları
   - Birim Yönlendirme
   - Resmî Yazı Taslağı
   - Agent Durumu
   - Agent Akışı
9. DOCX taslağını indir.
10. Analizi yerel arşive kaydet.
11. Arşiv panelini açıp kaydı göster.
12. Test/değerlendirme panelinden toplu test çalıştır ve raporu indir.

## 3. Demo Konuşma Metni

“Bu projede kamu kurumlarında gelen evrakların ilk inceleme, yönlendirme ve yazışma taslaklama süreçlerini hızlandırmak amacıyla çok-agent destekli bir yapay zeka sistemi geliştirdik. Sistem evrakı okuyor, RAG kaynaklarından ilgili mevzuat, yazı şablonu ve birim görev tanımlarını getiriyor, ardından agent iş akışıyla evrak türünü belirliyor, önemli alanları çıkarıyor, eksik bilgileri tespit ediyor, ilgili birimi öneriyor ve resmî yazı taslağı oluşturuyor. Son aşamada Review Agent, çıktının insan onayı gerektirdiğini ve varsa eksik/kritik noktaları gösteriyor. Sistem nihai karar vermez; kamu personeline karar destek ve taslak üretim desteği sağlar.”

## 4. Sistem Bileşenleri

- Reader Agent: metin kalitesi ve temel evrak kontrolü
- RAG Retrieval Agent: ilgili kaynakları getirme
- Classifier & Extractor Agent: evrak türü ve alan çıkarımı
- Routing Agent: birim yönlendirme
- Drafting Agent: resmî yazı taslağı üretimi
- Validation Agent: çıktı şeması ve eksik alan kontrolü
- Review & Safety Agent: insan onayı, risk ve güvenlik kontrolü

## 5. Mevcut Kaynak Sayıları

- Yönetmelik/kural dosyası: {resource_counts['regulations']}
- Yazı şablonu: {resource_counts['templates']}
- Birim görev tanımı: {resource_counts['unit_definitions']}
- Örnek evrak: {resource_counts['sample_documents']}
- Test vakası dosyası: {resource_counts['test_cases_files']}

## 6. Mevcut Çıktı Sayıları

- Arşivlenen analiz: {output_counts['archived_cases']}
- Değerlendirme raporu: {output_counts['evaluation_reports']}
- Feedback dosyası: {output_counts['feedback_records']}

## 7. Demo Öncesi Kontrol Listesi

- `.env` dosyasında OpenRouter API key var mı?
- `pip install -r requirements.txt` çalıştırıldı mı?
- `streamlit run app.py` ile uygulama açılıyor mu?
- Örnek evrak yüklenince metin görünüyor mu?
- RAG kaynakları listeleniyor mu?
- Agent Akışı sekmesinde agent adımları görünüyor mu?
- DOCX indirilebiliyor mu?
- Arşive kaydetme ve arşivden açma çalışıyor mu?
- Toplu test çalıştırılabiliyor mu?

## 8. Hızlı Çalıştırma

```bash
cd kamu-evrak-agent_v11
venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py
```

Linux/macOS:

```bash
cd kamu-evrak-agent_v11
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## 9. Notlar

- OpenRouter ücretsiz modeller bazen JSON formatında zayıf kalabilir. Sistem bu durumda kural tabanlı tamamlayıcı analize düşer.
- Embedding RAG çalışmazsa Basit TF-IDF modu demo için yeterlidir.
- Gerçek kurum verisi kullanılmadan önce KVKK, erişim yetkisi, log maskeleme ve kurum içi güvenlik politikaları ayrıca uygulanmalıdır.
"""


def build_demo_checklist_markdown() -> str:
    return """# Demo Kontrol Listesi

## Başlatma

- [ ] `.env` dosyası proje kökünde mi?
- [ ] `OPENROUTER_API_KEY` doğru girildi mi?
- [ ] `pip install -r requirements.txt` tamamlandı mı?
- [ ] Uygulama `streamlit run app.py` ile açıldı mı?

## Ana Demo

- [ ] Örnek evrak yüklendi.
- [ ] Metin çıkarıldı.
- [ ] Analiz çalıştı.
- [ ] Evrak türü doğru göründü.
- [ ] Eksik bilgiler listelendi.
- [ ] RAG kaynakları göründü.
- [ ] Birim yönlendirme göründü.
- [ ] Resmî yazı taslağı üretildi.
- [ ] DOCX indirildi.
- [ ] Agent Akışı sekmesi gösterildi.

## Yönetim Panelleri

- [ ] Kaynak Yönetimi Paneli gösterildi.
- [ ] Arşiv Paneli gösterildi.
- [ ] Test/Değerlendirme Paneli gösterildi.

## Kapanış

- [ ] Sistemin karar vermediği, insan onayı gerektirdiği vurgulandı.
- [ ] Sonraki ürünleşme adımları anlatıldı.
"""


def build_demo_package_zip(base_dir: Path) -> bytes:
    snapshot = build_project_snapshot(base_dir)
    demo_md = build_demo_markdown(base_dir)
    checklist_md = build_demo_checklist_markdown()
    readme = _safe_read(base_dir / "README.md")
    test_cases = _safe_read(base_dir / "data" / "test_cases" / "test_cases.json")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("demo_rehberi.md", demo_md)
        zf.writestr("demo_kontrol_listesi.md", checklist_md)
        zf.writestr("project_snapshot.json", json.dumps(snapshot, ensure_ascii=False, indent=2))
        if readme:
            zf.writestr("README.md", readme)
        if test_cases:
            zf.writestr("test_cases.json", test_cases)

        # Include sample docs and core resource inventory for offline demo review.
        for folder in ["data/sample_documents", "data/regulations", "data/templates", "data/unit_definitions"]:
            root = base_dir / folder
            if root.exists():
                for path in root.rglob("*"):
                    if path.is_file() and path.suffix.lower() in {".txt", ".json", ".md"}:
                        zf.write(path, arcname=str(Path("kaynaklar") / path.relative_to(base_dir)))
    buffer.seek(0)
    return buffer.getvalue()
