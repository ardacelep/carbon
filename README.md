# kAIser — Veri Merkezi Karbon Zeka Platformu

**100 StaryUP Bootcamp Hackathon** · 15–17 Mayıs 2026 · YTÜ Davutpaşa · NVIDIA Altyapısıyla

**Tema:** `A2` Sürdürülebilirlik + `B4` Veri Merkezi + `C1` Metin üretimi/sohbet + `C7` Ajan ve araç kullanımı + `D4` Zaman serisi tahmini + `D5` Anomali tespiti + `D7` Öneri sistemi

---

## Problem

Türkiye'de bir veri merkezinin saatte harcadığı enerji sabittir — ama o enerjinin **karbon maliyeti sabit değildir.**

Türkiye şebekesinde linyit kömürünün karbon yoğunluğu **1050 gCO₂/kWh** iken hidrolik santraller yalnızca **4 gCO₂/kWh** üretir. Gün içinde yakıt karışımı sürekli değiştiğinden şebeke karbon yoğunluğu **200 ile 700 gCO₂eq/kWh** arasında gidip gelir — bazen 3–4 kata varan bir fark.

GPU eğitimi, yedekleme, veri sıkıştırma, toplu raporlama gibi **esnek iş yükleri** belirli bir saatte başlamak zorunda değildir. Bu işleri "kirli" bir saatte çalıştırmak yerine birkaç saat sonrasına ötelemek, **aynı işi %20–40 daha az CO₂ ile** tamamlamak anlamına gelir.

Sorun şu: veri merkezi operatörleri bu pencereyi manuel olarak takip edemez.

---

## Çözüm: kAIser

**kAIser**, anlık EPİAŞ verilerini ve 24 saatlik tahminleri kullanarak veri merkezi iş yüklerini otomatik olarak en düşük karbon maliyetli zaman dilimine zamanlar.

Doğal dil ile komut verin:

> *"Önümüzdeki 24 saatte 200 kW'lık ML eğitimini en yeşil pencerede başlat"*

kAIser şebekeyi analiz eder, optimal pencereyi hesaplar, sizi onaya çağırır. Onayladığınızda iş takvime eklenir, plan otomatik olarak yeniden optimize edilir.

---

## Özellikler

### Ana Sayfa — Kontrol Merkezi
- Anlık karbon yoğunluğu, yenilenebilir oran ve aktif iş sayısı kartları
- AI tarafından önerilen en iyi çalışma penceresi
- Saatlik karbon yoğunluğu trend grafiği
- PTF (piyasa fiyatı) maliyet grafiği
- Tüm iş yüklerinin durum tablosu

### Canlı Veri Takibi — Şebekeyi Anlık İzle
- **Anomali tespiti:** Z-score bazlı anormallik uyarıları (örn. "Karbon yoğunluğu normalin 2.3σ üstünde")
- **Şebeke özeti:** PTF, baraj doluluk oranı, toplam üretim (MW), yenilenebilir payı
- **Karbon göstergesi:** Yeşil/sarı/kırmızı skalasında anlık yoğunluk
- **Enerji dağılımı:** EPİAŞ RT-Gen'den çekilen gerçek yakıt karışımı pasta grafiği (Kömür, Hidrolik, Rüzgar, Doğalgaz, Güneş, Jeotermal)
- **Planlı kesintiler:** TEDAŞ bildirilen planlı bakım listesi
- **24 saat tahmin:** Saatlik karbon tahmini + tahmin doğruluğu metrikleri

### Takvim — Optimize Edilmiş İş Planı
- Google Calendar tarzı haftalık görünüm
- Tüm planlanmış iş yükleri karbon yoğunluğuna göre renklendirilmiş
- İşlerin başlangıç/bitiş saatleri ve tahmini CO₂ tasarrufu

### Raporlar — Ölçülebilir Etki
- Toplam CO₂ tasarrufu (kg), ağaç eşdeğeri, maliyet tasarrufu (TL)
- Ortalama tasarruf oranı (%)
- Haftalık tasarruf trendi grafiği
- İş durumu dağılımı (donut grafik)
- Filtrelenebilir ve CSV'ye aktarılabilir iş geçmişi tablosu

### AI Asistan — Doğal Dil ile Planlama
- LLM tabanlı sohbet arayüzü (NVIDIA / Llama-3.3-70B)
- Sol panelden iş seçimi → AI analizi → onay kartı akışı
- Serbest metin komutları ("3 saatlik yedekleme işi ekle")
- **Öneri kartı:** AI hiçbir işi otomatik kaydetmez; "Takvime Ekle / Vazgeç" onayı beklenir
- Onayda tüm plan yeniden optimize edilir

---

## Nasıl Çalışır?

```
EPİAŞ Şeffaflık Platformu
    │
    ├─ RT-Gen API ──────────→ Anlık yakıt karışımı + MWh değerleri
    │                              │
    │                         Emisyon faktörleriyle
    │                         ağırlıklı ortalama
    │                              │
    ├─ Rüzgar tahmini ─────→ 24 saat karbon yoğunluğu tahmini
    ├─ Güneş eğrisi ───────→ (SOLAR_CURVE + wind-forecast + baz karışım)
    │
    └─ MCP API ────────────→ PTF (Piyasa Takas Fiyatı)

                                   │
                            OR-Tools LP Optimizer
                            find_optimal_window()
                            [karbon + maliyet ağırlıklı skor]
                                   │
                            En iyi başlangıç saati
                                   │
                         NVIDIA Llama-3.3-70B
                         (tool-calling, propose-only)
                                   │
                            Öneri Kartı ──→ Kullanıcı Onayı ──→ Takvim
```

### Karbon Yoğunluğu Hesabı

```
CI = Σ(fuel_MWh × emission_factor) / total_MWh

Emisyon faktörleri (gCO₂eq/kWh):
  Linyit:   1050  |  Doğalgaz: 490  |  Rüzgar:    11
  Kömür:     820  |  Güneş:     45  |  Hidrolik:   4
```

### CO₂ Tasarrufu Formülü

```
kwh        = power_kw × duration_hours
baseline   = avg_ci / (1 - savings_pct/100)
saved_kg   = kwh × (baseline - avg_ci) / 1000
```

---

## Ekran Görüntüleri

> *(Deploy sonrası eklenecek)*

---

## Teknoloji Yığını

### Backend

| Teknoloji | Versiyon | Kullanım |
|-----------|---------|----------|
| **FastAPI** | 0.136 | REST API + SSE streaming |
| **NVIDIA build.nvidia.com** | — | Llama-3.3-70B-Instruct (chat + tool-calling) |
| **eptr2** | 1.3.7 | EPİAŞ Şeffaflık Platformu istemcisi |
| **OR-Tools** | 9.15 | LP optimizasyon — optimal pencere hesabı |
| **Supabase** | 2.30 | PostgreSQL veritabanı + auth |
| **Pydantic** | 2.13 | Veri doğrulama ve şema |
| **uvicorn** | 0.47 | ASGI sunucu |
| **Python** | 3.11 | — |

### Frontend

| Teknoloji | Versiyon | Kullanım |
|-----------|---------|----------|
| **React** | 18 | UI framework |
| **Vite** | — | Build tool + geliştirme proxy |
| **Tailwind CSS** | v4 | Utility-first stil sistemi |
| **Recharts** | — | Grafik ve veri görselleştirme |
| **React Router** | v7 | SPA routing |
| **Lucide React** | — | İkon seti |

### Altyapı & Servisler

| Servis | Kullanım |
|--------|----------|
| **Railway** | Backend deploy |
| **Vercel** | Frontend deploy |
| **Supabase** | Veritabanı |
| **EPİAŞ** | Gerçek zamanlı şebeke ve enerji verisi |
| **GitHub** | Versiyon kontrolü + CI |

---

## Kurulum (Lokal)

### Gereksinimler

| Araç | Minimum Sürüm |
|------|--------------|
| Python | 3.11 |
| Node.js | 18 |
| npm | 9 |

### 1 — Repoları klonla

```bash
# Backend
git clone https://github.com/ardacelep/carbon.git
cd carbon

# Frontend (ayrı repo)
git clone https://github.com/lamia0118/axiom.git
```

### 2 — Backend kurulumu

```bash
cd carbon/backend

# Sanal ortam
python3.11 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Bağımlılıklar
pip install -r requirements.txt

# Ortam değişkenleri
cp .env.example .env
# .env dosyasını düzenle (aşağıdaki tabloya bak)

# Sunucuyu başlat
uvicorn main:app --reload --port 8000
```

Backend çalışıyor: `http://localhost:8000`  
Swagger UI: `http://localhost:8000/docs`

**EPİAŞ erişimi yoksa** mock mod:
```bash
MOCK_MODE=true uvicorn main:app --reload --port 8000
```

### 3 — Frontend kurulumu

```bash
cd axiom
npm install
npm run dev
```

Uygulama: `http://localhost:5173`

> Geliştirme modunda Vite, `/api/*` isteklerini otomatik olarak `localhost:8000`'e proxy'ler.  
> `.env` dosyası oluşturmana gerek yok.

---

## Ortam Değişkenleri (`backend/.env`)

| Değişken | Zorunlu | Açıklama |
|----------|:-------:|----------|
| `SUPABASE_URL` | ✅ | Supabase proje URL'i |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Supabase service role anahtarı |
| `NVIDIA_API_KEY` | ✅ | build.nvidia.com API anahtarı (`nvapi-…`) |
| `EPTR_USERNAME` | ✅ | EPİAŞ Şeffaflık Platformu kullanıcı adı |
| `EPTR_PASSWORD` | ✅ | EPİAŞ Şeffaflık Platformu şifresi |
| `MOCK_MODE` | — | `true` → gerçek API yerine simüle veri (varsayılan: `false`) |
| `ALLOWED_ORIGINS` | — | CORS: Vercel URL'ini virgülle ekle |
| `LLM_MODEL` | — | Varsayılan: `meta/llama-3.3-70b-instruct` |
| `LLM_BASE_URL` | — | Varsayılan: `https://integrate.api.nvidia.com/v1` |
| `API_TIMEOUT` | — | EPİAŞ timeout (sn), varsayılan: `12` |

Örnek `.env.example` dosyası repo'da mevcuttur.

---

## API Endpoint'leri

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| `GET` | `/api/carbon/current` | Anlık karbon yoğunluğu + yakıt karışımı |
| `GET` | `/api/carbon/forecast` | 24 saatlik tahmin |
| `GET` | `/api/carbon/anomaly` | Z-score anomali raporu |
| `GET` | `/api/carbon/forecast/accuracy` | Tahmin doğruluğu |
| `GET` | `/api/grid/status` | PTF, baraj doluluk, şebeke stresi |
| `POST` | `/api/jobs` | İş ekle + AI öneri |
| `GET` | `/api/jobs` | İş listesi |
| `POST` | `/api/jobs/analyze` | İşi kaydetmeden pencere analizi |
| `POST` | `/api/jobs/optimize` | Tüm işleri yeniden optimize et |
| `GET` | `/api/savings/summary` | CO₂ tasarruf özeti |
| `GET` | `/api/schedule` | Optimize edilmiş takvim |
| `POST` | `/api/chat/stream` | SSE streaming chatbot |
| `GET` | `/api/debug/datasources` | Veri kaynağı bağlantı durumu |

Tam interaktif dokümantasyon: `/docs`

---

## Deploy

### Backend → Railway

```
1. railway.app → New Project → Deploy from GitHub → ardacelep/carbon
2. Settings → Root Directory: backend
3. Variables: .env içeriğini yapıştır
4. ALLOWED_ORIGINS: https://your-vercel-app.vercel.app
```

### Frontend → Vercel

```
1. vercel.com → New Project → lamia0118/axiom
2. Environment Variables:
   VITE_API_BASE_URL = https://your-railway-url.up.railway.app
3. Deploy
```

> `VITE_API_BASE_URL` build anında bundle'a gömülür.
> Railway URL'ini önce al, Vercel'e deploy ederken gir.

---

## Canlı Demo

- **Uygulama:** https://axiom-eight-kappa.vercel.app
- **Backend API Docs:** https://carbon-production-2576.up.railway.app/docs

---

## Ekip

| İsim | Rol |
|------|-----|
| Hüseyin Arda Celep | Backend Developer |
| Kaan Yıldız | Frontend Developer |
| Lamia Ucun | Ürün Yöneticisi |
| Ayşenur Demir | Tasarımcı |
| Ahmet Eren Çimen | İş Geliştirmeci |

---

## Repo Yapısı

```
carbon/                       ← Bu repo (backend)
├── backend/
│   ├── main.py               FastAPI uygulaması + tüm endpoint'ler
│   ├── carbon_service.py     EPİAŞ RT-Gen entegrasyonu + karbon hesabı
│   ├── grid_service.py       PTF, baraj doluluk, arz-talep
│   ├── scheduler.py          find_optimal_window() — OR-Tools LP
│   ├── llm_service.py        NVIDIA API + tool-calling (propose-only mod)
│   ├── anomaly_service.py    Z-score anomali + doğruluk raporları
│   ├── database.py           Supabase async client
│   ├── models.py             Pydantic şemalar
│   ├── workload_profiles.py  İş yükü profilleri (GPU eğitim, yedekleme…)
│   ├── .env.example          Ortam değişkeni şablonu
│   ├── railway.toml          Railway deploy konfigürasyonu
│   └── requirements.txt      Python bağımlılıkları

axiom/ (→ github.com/lamia0118/axiom)  ← Frontend
├── src/
│   ├── pages/
│   │   ├── AnaSayfa.jsx      Kontrol merkezi (özet + iş tablosu)
│   │   ├── CanliVeri.jsx     Şebeke izleme + anomali + tahmin
│   │   ├── Schedule.jsx      Takvim görünümü
│   │   ├── Raporlar.jsx      CO₂ tasarruf raporları
│   │   └── JobsChat.jsx      AI chatbot + onay akışı
│   ├── components/
│   │   ├── karbon/           Header, WorkloadTable, GlassCard, grafikler
│   │   │   └── live/         Canlı veri bileşenleri
│   │   ├── jobschat/         ChatPanel, ChatMessage, ProposalCard
│   │   └── reports/          Rapor bileşenleri
│   ├── services/             API istemcileri
│   └── utils/                Veri dönüşüm ve CO₂ formülleri
├── vercel.json               Vercel SPA routing
└── public/kaiser-logo.png    Uygulama logosu
```

---

*100 StaryUP Bootcamp Hackathon — YTU Startup House & Türksat — NVIDIA Altyapı Desteğiyle*
