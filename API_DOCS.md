# Karbon Zeka — Backend API Referansı

**Base URL:** `http://localhost:8000`  
**Format:** JSON (`Content-Type: application/json`)  
**Auth:** Bearer token — korumalı endpoint'lere her istekte `Authorization: Bearer <token>` header'ı gönderilmeli

---

## İçindekiler

1. [Kimlik Doğrulama (Auth)](#1-kimlik-doğrulama)
2. [Anlık Karbon](#2-anlık-karbon)
3. [24 Saatlik Tahmin](#3-24-saatlik-tahmin)
4. [Şebeke Durumu](#4-şebeke-durumu)
5. [İş Kuyruğu (Jobs)](#5-i̇ş-kuyruğu)
6. [Sohbet (Chat)](#6-sohbet)
7. [Streaming Sohbet (SSE)](#7-streaming-sohbet)
8. [Tasarruf Özeti](#8-tasarruf-özeti)
9. [Hata Kodları](#9-hata-kodları)
10. [Hızlı Başlangıç](#10-hızlı-başlangıç)

---

## 1. Kimlik Doğrulama

### `POST /api/auth/signup` — Kayıt

**Auth gerekmez.**

**İstek:**
```json
{
  "email": "test@example.com",
  "password": "sifre123"
}
```

**Yanıt `201`:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user_id": "a3f2c1d4-8b7e-4f5a-9c2b-1e3d5f7a9b0c"
}
```

---

### `POST /api/auth/login` — Giriş

**Auth gerekmez.**

**İstek:**
```json
{
  "email": "test@example.com",
  "password": "sifre123"
}
```

**Yanıt `200`:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user_id": "a3f2c1d4-8b7e-4f5a-9c2b-1e3d5f7a9b0c"
}
```

**Token saklama:** `localStorage.setItem('token', access_token)` — korumalı isteklerde:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## 2. Anlık Karbon

### `GET /api/carbon/current` — Şu anki karbon yoğunluğu

**Auth gerekmez.**

**Yanıt `200`:**
```json
{
  "carbon_intensity": 219.1,
  "renewable_ratio": 0.724,
  "timestamp": "2026-05-16T04:00:00+03:00",
  "source": "epias",
  "updated_minutes_ago": 141
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `carbon_intensity` | `float` | gCO2eq/kWh — düşük = iyi |
| `renewable_ratio` | `float` | 0.0–1.0 (örn. `0.724` = %72.4 yenilenebilir) |
| `timestamp` | ISO-8601 string | Verinin ait olduğu saat (EPİAŞ 1-2 saat gecikmeli verir) |
| `source` | `"epias"` \| `"fallback"` \| `"mock"` | `"fallback"` = API timeout, yerel JSON kullanıldı |
| `updated_minutes_ago` | `int` | `> 90` ise "veri güncel olmayabilir" uyarısı göster |

**Renk eşikleri:**
```js
function getCarbonColor(ci) {
  if (ci < 200) return '#22c55e'   // yeşil  — mükemmel
  if (ci < 250) return '#eab308'   // sarı   — iyi
  if (ci < 350) return '#f97316'   // turuncu — yüksek
  return '#ef4444'                  // kırmızı — çok yüksek
}
```

**Cache:** 15 dakika. Her 5 dakikada bir polling önerilir.

---

## 3. 24 Saatlik Tahmin

### `GET /api/carbon/forecast` — Karbon yoğunluğu tahmini

**Auth gerekmez.**

**Query parametresi:**
| Parametre | Tip | Varsayılan | Aralık |
|---|---|---|---|
| `hours` | `int` | `24` | 1–48 |

**Yanıt `200`:**
```json
{
  "generated_at": "2026-05-16T06:00:00+03:00",
  "source": "epias",
  "points": [
    {
      "timestamp": "2026-05-16T07:00:00+03:00",
      "carbon_intensity": 245.2,
      "renewable_ratio": 0.698,
      "confidence": 0.90,
      "ptf_tl_per_mwh": null,
      "combined_score": null
    },
    {
      "timestamp": "2026-05-16T13:00:00+03:00",
      "carbon_intensity": 195.0,
      "renewable_ratio": 0.761,
      "confidence": 0.72,
      "ptf_tl_per_mwh": null,
      "combined_score": null
    }
  ]
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `source` | `"epias"` \| `"epias-partial"` \| `"fallback"` \| `"mock"` | `"epias-partial"` = rüzgar tahmini alınamadı |
| `points[].confidence` | `float` | 0.55–0.90. Yakın saat = yüksek güven. Grafik şeffaflığı için kullan |
| `points[].ptf_tl_per_mwh` | `float \| null` | Elektrik spot fiyatı (ileriki versiyonda dolu gelecek) |

**Cache:** 30 dakika. Her 15 dakikada bir polling önerilir.

---

## 4. Şebeke Durumu

### `GET /api/grid/status` — EPİAŞ şebeke özeti

**Auth gerekmez.**

**Yanıt `200`:**
```json
{
  "dam_fullness_pct": 68.4,
  "dam_trend": "stable",
  "ptf_tl_per_mwh": 295.99,
  "supply_demand_mw": 820.0,
  "planned_outages": [
    {
      "plant_name": "Atatürk HES",
      "start_time": "2026-05-17T08:00:00+03:00",
      "end_time": "2026-05-17T18:00:00+03:00",
      "capacity_mw": 240.0
    }
  ],
  "grid_stress": "low",
  "updated_at": "2026-05-16T06:22:04+03:00",
  "source": "epias"
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `dam_fullness_pct` | `float \| null` | Türkiye ortalama baraj doluluk % |
| `dam_trend` | `"increasing"` \| `"stable"` \| `"declining"` \| `null` | Baraj doluluk trendi |
| `ptf_tl_per_mwh` | `float \| null` | Elektrik piyasa fiyatı ₺/MWh |
| `supply_demand_mw` | `float \| null` | Pozitif = arz fazlası, negatif = açık |
| `planned_outages` | `array` | Önümüzdeki 7 günün planlı kesintileri |
| `grid_stress` | `"low"` \| `"medium"` \| `"high"` | Genel şebeke yük değerlendirmesi |

**Cache:** 30 dakika.

---

## 5. İş Kuyruğu

Tüm job endpoint'leri **auth gerektirir.**

---

### `POST /api/jobs` — İş ekle + AI öneri al

**İstek:**
```json
{
  "name": "Model Eğitimi v2",
  "duration_hours": 4,
  "power_kw": 250,
  "priority": 3,
  "deadline": "2026-05-17T18:00:00+03:00",
  "cost_weight": 0.0
}
```

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| `name` | `string` | ✅ | 1–200 karakter |
| `duration_hours` | `float` | ✅ | 0 < değer ≤ 72 |
| `power_kw` | `float` | ✅ | İş yükünün güç tüketimi (kW) |
| `priority` | `int` | — | 1 (düşük) – 5 (acil), varsayılan `1` |
| `deadline` | ISO-8601 string | — | Opsiyonel. Varsa bu saatten önce bir pencere aranır |
| `cost_weight` | `float` | — | 0.0–1.0. `0.0` = sadece karbon optimize et, `1.0` = sadece maliyet. Varsayılan `0.0` |

**Yanıt `201`:**
```json
{
  "id": 7,
  "name": "Model Eğitimi v2",
  "duration_hours": 4,
  "deadline": "2026-05-17T18:00:00+03:00",
  "priority": 3,
  "power_kw": 250,
  "status": "scheduled",
  "created_at": "2026-05-16T06:15:00+03:00",
  "scheduled_start": null,
  "optimal_window": {
    "start_time": "2026-05-16T11:00:00+03:00",
    "end_time": "2026-05-16T15:00:00+03:00",
    "avg_carbon_intensity": 202.3,
    "estimated_savings_pct": 18.5,
    "reasoning": "16.05 tarihinde 11:00–15:00 arası en uygun pencere. Ortalama karbon yoğunluğu 202.3 gCO2eq/kWh — şu anki değerden %18 daha düşük. Güneş üretiminin yüksek olduğu öğle saatlerinden yararlanıyor."
  },
  "ai_recommendation": "Model Eğitimi v2 için en uygun çalışma penceresi 11:00–15:00 arasıdır; güneş üretiminin pik yaptığı bu saatlerde karbon yoğunluğu %18 daha düşük seyrediyor. Bu optimizasyonla 45.5 kg CO2 tasarruf etmiş olacaksınız. İşinizi hemen bu pencereye alın!"
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `status` | `string` | `"scheduled"` = optimal pencere bulundu, `"pending"` = bulunamadı |
| `optimal_window` | `object \| null` | `null` ise zamanlamada uygun pencere yok |
| `ai_recommendation` | `string \| null` | Llama 3.3 70B tarafından üretilen Türkçe öneri |

---

### `GET /api/jobs` — İş listesi

**Yanıt `200`:**
```json
{
  "jobs": [
    { ...job object... },
    { ...job object... }
  ],
  "total": 2
}
```

`jobs` dizisindeki her eleman yukarıdaki job response şemasıyla aynıdır.

---

### `GET /api/jobs/{job_id}` — Tek iş getir

**Yanıt `200`:** Job response (yukarıdakiyle aynı şema)  
**Yanıt `404`:** `{"detail": "İş bulunamadı"}`

---

### `DELETE /api/jobs/{job_id}` — İş sil

**Yanıt `200`:**
```json
{ "deleted": true }
```

**Yanıt `404`:** `{"detail": "İş bulunamadı"}`

---

### `PATCH /api/jobs/{job_id}/status` — İş durumunu güncelle

**İstek:**
```json
{ "status": "running" }
```

Geçerli değerler: `"pending"` `"scheduled"` `"running"` `"completed"` `"cancelled"`

**Yanıt `200`:** Güncellenmiş job response  
**Yanıt `422`:** Geçersiz status değeri  
**Yanıt `404`:** İş bulunamadı

---

## 6. Sohbet

### `POST /api/chat` — AI chat (tam yanıt)

**Auth gerekmez.**

AI her yanıtta anlık karbon yoğunluğunu, şebeke durumunu (baraj, PTF, stres) ve bağlamı otomatik alır — kullanıcının bunu söylemesine gerek yok.

**İstek:**
```json
{
  "message": "Bugün sunucularımı ne zaman çalıştırmalıyım?",
  "history": [
    { "role": "user", "content": "Merhaba" },
    { "role": "assistant", "content": "Merhaba! Nasıl yardımcı olabilirim?" }
  ]
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `message` | `string` | 1–2000 karakter |
| `history` | `array` | Önceki konuşma. `role`: `"user"` veya `"assistant"`. Son 6 mesaj dikkate alınır |

**Yanıt `200`:**
```json
{
  "reply": "Şu an şebeke karbon yoğunluğu 219 gCO2eq/kWh ile oldukça düşük seyrediyor...",
  "timestamp": "2026-05-16T06:30:00+03:00"
}
```

---

## 7. Streaming Sohbet

### `POST /api/chat/stream` — SSE token stream

**Auth gerekmez.**  
İstek body `POST /api/chat` ile aynıdır.

**Yanıt:** `Content-Type: text/event-stream`

Her satır SSE formatında:
```
data: {"token": "Şu"}

data: {"token": " an"}

data: {"token": " şebeke"}

...

data: [DONE]
```

Hata durumunda:
```
data: {"error": "Yapay zeka servisi şu anda kullanılamıyor."}

data: [DONE]
```

**React'ta kullanım:**
```js
async function streamChat(message, history, onToken) {
  const res = await fetch('http://localhost:8000/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
  })

  const reader = res.body.getReader()
  const decoder = new TextDecoder()

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const lines = decoder.decode(value).split('\n')
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6)
      if (payload === '[DONE]') return
      try {
        const { token, error } = JSON.parse(payload)
        if (token) onToken(token)
      } catch {}
    }
  }
}

// Kullanım:
let reply = ''
await streamChat(
  'Ne zaman çalıştırmalıyım?',
  history,
  (token) => { reply += token; setReply(reply) }
)
```

---

## 8. Tasarruf Özeti

### `GET /api/savings/summary` — Kullanıcının toplam tasarrufu

**Auth gerekir.**

**Yanıt `200`:**
```json
{
  "total_jobs": 12,
  "optimized_jobs": 9,
  "total_carbon_saved_kg": 142.8,
  "total_energy_kwh": 8400.0,
  "avg_carbon_intensity": 218.5,
  "best_saving_pct": 24.3,
  "period_start": "2026-05-15T00:00:00+03:00",
  "period_end": "2026-05-16T06:00:00+03:00"
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `total_carbon_saved_kg` | `float` | Kaçınılan toplam CO2 (kg) |
| `total_energy_kwh` | `float` | Tüm işlerin toplam enerji tüketimi |
| `avg_carbon_intensity` | `float` | Optimize edilmiş işlerin ortalama gCO2/kWh |
| `best_saving_pct` | `float` | Tek bir işte elde edilen en yüksek tasarruf (%) |
| `optimized_jobs` | `int` | Optimal pencere bulunan iş sayısı |

**Önerilen türetilmiş metrikler (frontend):**
```js
const optimizationRate = (optimized_jobs / total_jobs * 100).toFixed(0)   // "75"
const treesEquivalent  = (total_carbon_saved_kg / 21.7).toFixed(1)        // yıllık CO2 emip tüketimi
const avgSavingPerJob  = (total_carbon_saved_kg / optimized_jobs).toFixed(1)
```

---

## 9. Hata Kodları

| HTTP Kodu | Durum | Açıklama |
|---|---|---|
| `400` | Bad Request | Geçersiz istek body (eksik alan, format hatası) |
| `401` | Unauthorized | Token eksik, geçersiz veya süresi dolmuş |
| `404` | Not Found | İstenen kaynak bulunamadı |
| `422` | Unprocessable Entity | Pydantic validation hatası (alan tipi yanlış, kısıt ihlali) |
| `500` | Internal Server Error | Beklenmeyen sunucu hatası |

**401 örneği:**
```json
{ "detail": "Geçersiz veya süresi dolmuş token" }
```

**422 örneği:**
```json
{
  "detail": [
    {
      "loc": ["body", "duration_hours"],
      "msg": "Input should be greater than 0",
      "type": "greater_than"
    }
  ]
}
```

---

## 10. Hızlı Başlangıç

Uçtan uca minimum akış — kayıt, token alma, iş ekleme:

```js
const BASE = 'http://localhost:8000'

// 1. Kayıt veya giriş
async function login(email, password) {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  const { access_token, user_id } = await res.json()
  localStorage.setItem('token', access_token)
  return { access_token, user_id }
}

// 2. Auth header helper
function authHeaders() {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${localStorage.getItem('token')}`,
  }
}

// 3. Anlık karbon (public)
async function getCurrentCarbon() {
  const res = await fetch(`${BASE}/api/carbon/current`)
  return res.json()
}

// 4. Şebeke durumu (public)
async function getGridStatus() {
  const res = await fetch(`${BASE}/api/grid/status`)
  return res.json()
}

// 5. Tahmin (public)
async function getForecast(hours = 24) {
  const res = await fetch(`${BASE}/api/carbon/forecast?hours=${hours}`)
  return res.json()
}

// 6. İş ekle (auth)
async function createJob(name, duration_hours, power_kw) {
  const res = await fetch(`${BASE}/api/jobs`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ name, duration_hours, power_kw, priority: 1 }),
  })
  return res.json()   // optimal_window + ai_recommendation içerir
}

// 7. İşleri listele (auth)
async function getJobs() {
  const res = await fetch(`${BASE}/api/jobs`, { headers: authHeaders() })
  return res.json()   // { jobs: [...], total: N }
}

// 8. İş durumunu güncelle (auth)
async function updateJobStatus(jobId, status) {
  const res = await fetch(`${BASE}/api/jobs/${jobId}/status`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({ status }),
  })
  return res.json()
}

// 9. Tasarruf özeti (auth)
async function getSavingsSummary() {
  const res = await fetch(`${BASE}/api/savings/summary`, { headers: authHeaders() })
  return res.json()
}
```

---

## Notlar

- **Saat dilimi:** Tüm tarihler `+03:00` (Türkiye, yaz/kış saati yok)
- **EPİAŞ gecikmesi:** `updated_minutes_ago > 90` ise kullanıcıya uyarı göster
- **`source` alanı:** `"fallback"` görünce API erişimi yok demektir; veriler yerel JSON'dan geliyor, grafik çalışmaya devam eder
- **CORS:** Tüm origin'lere açık — deploy sonrası da ek ayar gerekmez
- **Swagger UI:** `http://localhost:8000/docs` — tüm endpoint'leri tarayıcıdan deneyebilirsin
