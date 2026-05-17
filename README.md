# kAIser — Karbon Zeka Platformu

> **100 StaryUP Bootcamp Hackathon** · 15–17 Mayıs 2026 · YTÜ Davutpaşa  
> **Tema:** `A2 Sürdürülebilirlik` + `B4 Veri Merkezi` + `C1 Metin üretimi/sohbet` + `C7 Ajan ve araç kullanımı` + `D4 Zaman serisi tahmini` + `D5 Anomali tespiti`

---

## Proje Hakkında

**kAIser**, Türkiye elektrik şebekesinin anlık karbon yoğunluğunu takip eden, 24 saatlik tahmin yapan ve veri merkezi operatörlerine iş yükü zamanlama önerisi sunan yapay zeka platformudur.

### Çözülen Problem

Veri merkezleri 7/24 çalışır ve enerji tüketimlerini saatler içinde kaydıramazlar — ancak Türkiye şebekesindeki karbon yoğunluğu gün içinde **3–4 kat** değişebilir. GPU eğitimleri, yedekleme işleri ve toplu hesaplamalar gibi esnek iş yükleri, yoğunluğun düşük olduğu "yeşil pencere"lere taşındığında **aynı işi %20–40 daha az CO₂ ile** tamamlamak mümkündür.

### Nasıl Çalışır?

1. **Canlı veri** — EPİAŞ RT-Gen API'sinden anlık yakıt karışımı ve karbon yoğunluğu çekilir.
2. **24 saat tahmin** — Rüzgar tahmini + güneş eğrisi + baz karışımdan zaman serisi oluşturulur.
3. **Anomali tespiti** — Z-score bazlı anormallik ve şebeke stres göstergeleri hesaplanır.
4. **Optimal pencere** — OR-Tools ile en düşük karbon maliyetli başlangıç saati bulunur.
5. **AI asistan** — NVIDIA/Llama-3.3-70B tabanlı chatbot, iş yükü önerilerini kullanıcı onayına sunar (otomatik kayıt yapmaz).

---

## Mimari

```
karbon-zeka/          ← Bu repo (backend)
└── backend/
    ├── main.py           FastAPI uygulaması · tüm endpoint'ler
    ├── carbon_service.py EPİAŞ entegrasyonu · karbon hesabı · önbellek
    ├── grid_service.py   PTF, baraj doluluk, planlı kesinti
    ├── scheduler.py      find_optimal_window() — OR-Tools LP optimizer
    ├── llm_service.py    NVIDIA API · LLM tool-calling · propose-only modu
    ├── anomaly_service.py Z-score anomali · doğruluk raporları
    ├── database.py       Supabase async client
    └── models.py         Pydantic şemalar

axend/ (ayrı repo → github.com/lamia0118/axiom)  ← Frontend
└── src/
    ├── pages/            Dashboard, Canlı Veri, İş Yükü, Raporlar, ChatBot
    ├── components/       GlassCard, Header, WorkloadTable, Charts…
    ├── services/         apiClient, carbonApi, jobsApi, chatApi…
    └── utils/            mapJobToUi, deriveEnergyMix…
```

---

## Kurulum

### Gereksinimler

| Araç | Sürüm |
|------|-------|
| Python | 3.11+ |
| Node.js | 18+ |
| npm | 9+ |

### 1 — Backend

```bash
# Repoyu klonla
git clone https://github.com/ardacelep/carbon.git
cd carbon/backend

# Sanal ortam oluştur ve bağımlılıkları yükle
python3.11 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Ortam değişkenlerini ayarla
cp .env.example .env
# .env dosyasını düzenle (aşağıdaki Ortam Değişkenleri bölümüne bak)

# Sunucuyu başlat
uvicorn main:app --reload --port 8000
```

API dokümantasyonu: `http://localhost:8000/docs`

**Mock mod** (EPİAŞ erişimi yoksa):

```bash
MOCK_MODE=true uvicorn main:app --reload --port 8000
```

### 2 — Frontend

```bash
# Frontend reposunu klonla
git clone https://github.com/lamia0118/axiom.git
cd axiom

# Bağımlılıkları yükle
npm install

# Ortam değişkenini ayarla (geliştirme için opsiyonel — proxy otomatik çalışır)
# Üretim için: .env dosyasında VITE_API_BASE_URL=https://your-backend-url

# Geliştirme sunucusunu başlat
npm run dev
```

Uygulama: `http://localhost:5173`

> **Not:** Geliştirme modunda Vite, `/api/*` isteklerini otomatik olarak backend'e (8000) proxy'ler.  
> Üretimde `VITE_API_BASE_URL` ortam değişkeni set edilmelidir.

---

## Ortam Değişkenleri

`backend/.env.example` dosyasını kopyalayıp doldur:

| Değişken | Zorunlu | Açıklama |
|----------|---------|----------|
| `SUPABASE_URL` | ✅ | Supabase proje URL'i |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Supabase service role anahtarı |
| `NVIDIA_API_KEY` | ✅ | build.nvidia.com API anahtarı (`nvapi-…`) |
| `EPTR_USERNAME` | ✅ | EPİAŞ Şeffaflık Platformu kullanıcı adı |
| `EPTR_PASSWORD` | ✅ | EPİAŞ Şeffaflık Platformu şifresi |
| `MOCK_MODE` | — | `true` → EPİAŞ yerine simüle veri kullanır |
| `ALLOWED_ORIGINS` | — | Virgülle ayrılmış CORS domain listesi (Vercel URL'i) |
| `LLM_MODEL` | — | Varsayılan: `meta/llama-3.3-70b-instruct` |
| `LLM_BASE_URL` | — | Varsayılan: `https://integrate.api.nvidia.com/v1` |
| `API_TIMEOUT` | — | EPİAŞ timeout saniyesi, varsayılan: `12` |

---

## API Endpoint'leri

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| `GET` | `/api/carbon/current` | Anlık karbon yoğunluğu + yakıt karışımı |
| `GET` | `/api/carbon/forecast` | 24 saatlik tahmin listesi |
| `GET` | `/api/carbon/anomaly` | Z-score anomali raporu |
| `GET` | `/api/carbon/forecast/accuracy` | Tahmin doğruluğu metrikleri |
| `GET` | `/api/grid/status` | PTF, baraj doluluk, şebeke stresi |
| `POST` | `/api/jobs` | İş ekle + AI öneri al |
| `GET` | `/api/jobs` | İş listesi |
| `POST` | `/api/jobs/analyze` | İşi kaydetmeden pencere analizi yap |
| `POST` | `/api/jobs/optimize` | Tüm bekleyen işleri yeniden optimize et |
| `GET` | `/api/savings/summary` | CO₂ tasarruf özeti |
| `POST` | `/api/chat/stream` | SSE streaming chatbot (öneri modunda) |
| `GET` | `/api/schedule` | Optimize edilmiş iş takvimi |
| `GET` | `/api/debug/datasources` | Veri kaynağı bağlantı durumu |

Tam interaktif dokümantasyon: `/docs` (Swagger UI)

---

## Kullanılan Teknolojiler

### Backend
| Teknoloji | Kullanım |
|-----------|----------|
| **FastAPI** | REST API + SSE streaming |
| **NVIDIA build.nvidia.com** | Llama-3.3-70B LLM (chat + tool-calling) |
| **eptr2** | EPİAŞ Şeffaflık Platformu API istemcisi |
| **OR-Tools** | Optimal pencere hesabı (LP optimizasyon) |
| **Supabase** | Veritabanı (PostgreSQL) + auth |
| **Pydantic** | Veri doğrulama ve şema |
| **uvicorn** | ASGI sunucu |

### Frontend
| Teknoloji | Kullanım |
|-----------|----------|
| **React 18** | UI framework |
| **Vite** | Build tool + dev proxy |
| **Tailwind CSS** | Stil |
| **Recharts** | Grafik ve görselleştirme |
| **React Router** | SPA routing |

### Altyapı
| Servis | Kullanım |
|--------|----------|
| **Railway** | Backend deploy |
| **Vercel** | Frontend deploy |
| **Supabase** | Veritabanı |
| **EPİAŞ** | Gerçek zamanlı enerji verisi |

---

## Deploy

### Backend → Railway

1. [railway.app](https://railway.app) üzerinde yeni proje oluştur → **Deploy from GitHub** → `ardacelep/carbon`
2. **Root Directory:** `backend` olarak ayarla
3. Environment Variables'a `.env` içeriklerini ekle
4. `ALLOWED_ORIGINS` değişkenine Vercel URL'ini gir

### Frontend → Vercel

1. [vercel.com](https://vercel.com) üzerinde yeni proje → `lamia0118/axiom`
2. **Environment Variables:** `VITE_API_BASE_URL=https://your-railway-url.up.railway.app`
3. Deploy et

---

## Canlı Demo

- **Frontend:** https://axiom.vercel.app *(deploy sonrası güncellenecek)*
- **Backend API:** https://your-railway-url.up.railway.app/docs *(deploy sonrası güncellenecek)*

---

## Ekip

| İsim | Rol |
|------|-----|
| H. Arda Celep | Tech Lead / Backend |
| *(ekip üyesi)* | *(rol)* |
| *(ekip üyesi)* | *(rol)* |

---

## Lisans

MIT
