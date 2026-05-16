# Karbon Zeka — Claude Code Bağlamı

## Proje
Türkiye elektrik şebekesi karbon yoğunluğunu takip eden, 24 saatlik tahmin yapan
ve veri merkezi operatörlerine iş yükü zamanlama önerisi sunan AI platformu.
Hackathon: 100 StaryUP, YTÜ, 15-17 Mayıs 2026.

## Stack
- Backend: Python 3.11 + FastAPI + uvicorn, port 8000
- Veri: eptr2 (EPİAŞ API) + simüle fallback
- AI: NVIDIA build.nvidia.com → meta/llama-3.3-70b-instruct
- DB: SQLite (aiosqlite)
- Frontend: React 18 + Tailwind CSS + Recharts, port 5173

## Komutlar
```bash
# Backend
cd backend && source venv/bin/activate && uvicorn main:app --reload --port 8000

# Frontend  
cd frontend && npm run dev

# Test
cd backend && python -m pytest tests/ -v
```

## Klasör Yapısı
karbon-zeka/
├── backend/
│   ├── main.py           ← FastAPI app + tüm endpointler
│   ├── carbon_service.py ← EPİAŞ veri çekme + karbon hesaplama
│   ├── scheduler.py      ← find_optimal_window() algoritması
│   ├── llm_service.py    ← NVIDIA API çağrıları
│   ├── models.py         ← Pydantic şemaları
│   ├── database.py       ← SQLite init + bağlantı
│   └── requirements.txt
└── frontend/
└── src/
├── pages/
│   ├── Dashboard.jsx
│   ├── JobQueue.jsx
│   └── Chat.jsx
└── components/
├── CarbonGauge.jsx
├── ForecastChart.jsx
└── SavingsCard.jsx

## API Endpointleri
GET  /api/carbon/current      → anlık karbon yoğunluğu
GET  /api/carbon/forecast     → 24 saatlik tahmin listesi
POST /api/jobs                → iş ekle + anında AI öneri döndür
GET  /api/jobs                → iş listesi
POST /api/chat                → doğal dil sohbet
GET  /api/savings/summary     → tasarruf özeti

## EPİAŞ API Notları
Detaylı dokümantasyon: `backend/EPIAS_API.md`

- **Auth:** eptr2 TGT'yi otomatik yönetir. `.env`'de `EPTR_USERNAME` / `EPTR_PASSWORD` olmalı (`EPIAS_` prefix'li değişkenler eptr2 tarafından okunmaz)
- **Karbon hesabı:** `rt-gen` endpoint'i → yakıt bazlı MWh → emisyon faktörleriyle ağırlıklı ortalama
- **Tahmin:** `wind-forecast` (~48 saatlik, çeyreklik) + güneş eğrisi (SOLAR_CURVE) + baseline mix
- **Gecikme:** EPİAŞ verisi 1-2 saat gecikmeli → son 3 saati çek, `total > 0` olan en yeni satırı al
- **Cache:** current=15 dk, forecast=30 dk (in-memory, `carbon_service.py`)
- **Script çalıştırma:** `python test_api.py` (venv aktifken) — `/opt/homebrew/bin/python3` kullanma

## Kritik Kurallar
- API key'leri ASLA hardcode etme, .env'den oku
- EPİAŞ çalışmazsa MOCK_MODE=true ile generate_mock_forecast() kullan
- CORS: localhost:5173 ve vercel deploy domain'ine açık olmalı
- EPİAŞ verisi 1-2 saat gecikmeli — frontend'de "Son güncelleme: X dk önce" göster
- Tüm DB işlemleri aiosqlite ile async yap, sqlite3 kullanma

## Gemini Helper — Token Tasarrufu
Şu görevler için gemini-helper subagent'ı kullan:
- Büyük dosyaları okuyup özetlemek
- "Hangi dosyada X var?" aramaları
- EPİAŞ ham JSON çıktısını analiz etmek
- Hata loglarını özetlemek
- Fonksiyon/endpoint listesi çıkarmak

Şu görevler için ASLA gemini-helper kullanma (kendin yap):
- Kod yazmak ve düzenlemek
- API entegrasyonu
- Bug fix, refactor
