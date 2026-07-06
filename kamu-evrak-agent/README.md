# Kamu Evrak ve Yazışma Agent Sistemi — MVP-15

Bu sürümde MVP-14 kurumsal veri katmanı korunmuştur. Ek olarak ürünleşme yolunda **EBYS benzeri iş akışı ve onay süreci** eklenmiştir.

## Yeni Özellikler

- İş Akışı / Onay Paneli eklendi.
- Analiz sonucu tek butonla iş akışına aktarılabilir.
- Evrak durumları EBYS mantığına göre takip edilir.
- Rol bazlı durum geçişleri eklendi.
- Birim yetkilisi inceleme notu girebilir.
- Onay yetkilisi taslağı onaylayabilir, revizyona gönderebilir veya reddedebilir.
- İş akışı geçmişi tutulur.
- İş akışı kayıtları JSON, CSV ve ZIP olarak dışa aktarılabilir.
- İş akışı taslağı tekrar DOCX olarak indirilebilir.

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
cd kamu-evrak-agent_v15
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

MVP-15 hâlâ Streamlit tabanlıdır. Sonraki ürünleşme adımı güvenlik, KVKK ve audit log politikasını güçlendirmektir.
