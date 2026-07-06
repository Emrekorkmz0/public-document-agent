🚀 Kamu Evrak ve Yazışma Süreçleri İçin Akıllı Agent Destek Sistemi geliştiriyoruz.

Kamu kurumlarında evrak inceleme, sınıflandırma, yönlendirme, resmi yazı taslaklama ve arşivleme süreçleri çoğu zaman manuel ilerleyen, zaman alan ve hata riskine açık iş akışlarından oluşuyor.

Bu ihtiyaca yönelik olarak geliştirdiğimiz sistem; LLM tabanlı agent mimarisi, RAG destekli bilgi erişimi, çok aşamalı analiz mekanizması ve insan onaylı iş akışı ile kamu evrak süreçlerini daha hızlı, izlenebilir ve güvenli hale getirmeyi hedefliyor.

Sistem şu anda;

✅ Evrak metni çıkarma ve analiz
✅ RAG tabanlı mevzuat, şablon ve birim görev tanımı eşleştirme
✅ Evrak türü sınıflandırma
✅ Eksik bilgi ve risk tespiti
✅ Birim yönlendirme önerisi
✅ Resmî yazı taslağı oluşturma
✅ DOCX çıktı alma
✅ Arşiv ve geçmiş kaydı
✅ Test/değerlendirme paneli
✅ Kullanıcı rolleri ve yetkilendirme
✅ EBYS benzeri onay akışı
✅ KVKK odaklı maskeleme ve audit log

gibi modüllerle çalışır hale getirildi.

Bu projede fine-tuning yerine kaynak kontrollü RAG yaklaşımını tercih ettik. Böylece sistemin kararları mevzuat, kurum şablonları ve birim görev tanımları gibi güncellenebilir kaynaklara dayandırılıyor. Bu yaklaşım, kamu süreçlerinde ihtiyaç duyulan güvenilirlik, açıklanabilirlik ve kontrol edilebilirlik açısından daha sağlıklı bir yapı sunuyor.

## İş Akışı Durumları

```text
Yeni Evrak
Analiz Edildi
Yönlendirme Bekliyor
Birimde İncelemede
Taslak Hazırlandı
Onay Bekliyor
Revizyon Gerekli
Onaylandı
Arşivlendi
Reddedildi
```

## Rol Mantığı

| Rol | İş Akışı Yetkisi |
|---|---|
| Admin | Tüm kayıtları görür, günceller, silebilir |
| Yazı İşleri | Evrakı iş akışına alır, yönlendirir, onaya gönderir |
| Birim Yetkilisi | Birim incelemesi ve görüş/revizyon adımlarını yürütür |
| Onay Yetkilisi | Onay, revizyon veya ret kararı verir |
| Görüntüleyen | Kayıtları yalnızca görüntüler |

## Çalıştırma

```bash
cd kamu-evrak-agent
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

OpenRouter ayarları için `.env.example` dosyasını `.env` olarak kopyala ve API anahtarını doldur.

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openrouter/free
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_HTTP_REFERER=http://localhost:8501
OPENROUTER_APP_TITLE=Kamu Evrak Agent Sistemi
```

## Kullanım Akışı

1. Kullanıcı girişi yap.
2. Evrak yükle veya metin yapıştır.
3. Metni hazırla.
4. Analiz et ve taslak oluştur.
5. Resmî Yazı Taslağı sekmesinden **İş Akışına Gönder / Onaya Al** butonuna bas.
6. Sol menüden **İş akışı / onay panelini göster** seçeneğiyle kaydı takip et.
7. Rolüne göre durum güncellemesi yap.

## Demo Kullanıcıları

| Kullanıcı | Şifre | Rol |
|---|---|---|
| admin | admin123 | Admin |
| yaziisleri | yazi123 | Yazı İşleri Personeli |
| birim | birim123 | Birim Yetkilisi |
| onayci | onay123 | Onay Yetkilisi |
| viewer | viewer123 | Görüntüleyen |

## Veriler Nerede Tutulur?

İş akışı kayıtları:

```text
outputs/workflows/
```

Silinen iş akışı kayıtları:

```text
outputs/deleted_workflows/
```

Veritabanı:

```text
outputs/database/kamu_evrak_agent.sqlite3
```


<img width="1600" height="498" alt="WhatsApp Image 2026-07-06 at 10 55 51" src="https://github.com/user-attachments/assets/fd2aa82d-bfd5-494f-b748-2c660f8bc07b" />
<img width="1600" height="759" alt="WhatsApp Image 2026-07-06 at 10 55 28" src="https://github.com/user-attachments/assets/41d7e72f-b072-4308-bd5f-af900867db8c" />
<img width="1600" height="758" alt="WhatsApp Image 2026-07-06 at 10 54 50" src="https://github.com/user-attachments/assets/b40961ec-37c0-401f-8cf1-8a0b22ac723f" />
<img width="1600" height="855" alt="WhatsApp Image 2026-07-06 at 10 53 25" src="https://github.com/user-attachments/assets/5af173f5-1827-4666-bae1-5907e6e895df" />
<img width="1132" height="749" alt="WhatsApp Image 2026-07-06 at 10 57 40" src="https://github.com/user-attachments/assets/956bd8e7-7530-46c4-9925-0be7976a0b1d" />





