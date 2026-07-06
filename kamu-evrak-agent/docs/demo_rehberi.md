# Kamu Evrak ve Yazışma Agent Sistemi — MVP-11 Final Demo Rehberi

Oluşturulma zamanı: 2026-07-04T11:28:22

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

- Yönetmelik/kural dosyası: 4
- Yazı şablonu: 5
- Birim görev tanımı: 8
- Örnek evrak: 5
- Test vakası dosyası: 1

## 6. Mevcut Çıktı Sayıları

- Arşivlenen analiz: 0
- Değerlendirme raporu: 0
- Feedback dosyası: 0

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
venv\Scripts\activate
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
