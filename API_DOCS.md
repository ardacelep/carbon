# Karbon Zeka — Backend API Referansı

**Base URL:** `https://undistractedly-gimlety-angelena.ngrok-free.dev`  
**Format:** JSON (`Content-Type: application/json`)  
**Auth:** Bearer token — korumalı endpoint'lere her istekte `Authorization: Bearer <token>` header'ı gönderilmeli

---

## İçindekiler

1. [Kimlik Doğrulama (Auth)](#1-kimlik-doğrulama)
2. [Anlık Karbon](#2-anlık-karbon)
3. [24 Saatlik Tahmin](#3-24-saatlik-tahmin)
4. [Şebeke Durumu](#4-şebeke-durumu)
5. [İş Kuyruğu (Jobs)](#5-i̇ş-kuyruğu)
   - 5.1 İş Oluştur / Listele / Getir / Sil / Güncelle
   - [5.2 İş Şablonları](#52-i̇ş-şablonları--get-apijobstemplates)
   - [5.3 Analiz (kayıtsız)](#53-analiz-kayıtsız--post-apijobsanalyze)
6. [Zamanlama (Schedule)](#6-zamanlama-schedule)
7. [Sohbet (Chat)](#7-sohbet)
8. [Streaming Sohbet (SSE)](#8-streaming-sohbet)
9. [Tasarruf Özeti](#9-tasarruf-özeti)
10. [Arka Plan İş İlerlemesi](#10-arka-plan-i̇ş-i̇lerlemesi)
11. [Hata Kodları](#11-hata-kodları)
12. [Hızlı Başlangıç](#12-hızlı-başlangıç)

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
| `points[].ptf_tl_per_mwh` | `float` | Saatlik elektrik spot fiyatı ₺/MWh. EPİAŞ verisi varsa gerçek, yoksa saatlik mock pattern (850–1950 ₺/MWh) |

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
    "estimated_savings_tl": 124.5,
    "reasoning": "16.05 tarihinde 11:00–15:00 arası en uygun pencere. Ortalama karbon yoğunluğu 202.3 gCO2eq/kWh — şu anki değerden %18 daha düşük. Güneş üretiminin yüksek olduğu öğle saatlerinden yararlanıyor."
  },
  "ai_recommendation": "Model Eğitimi v2 için en uygun çalışma penceresi 11:00–15:00 arasıdır; güneş üretiminin pik yaptığı bu saatlerde karbon yoğunluğu %18 daha düşük seyrediyor. Bu optimizasyonla 45.5 kg CO2 tasarruf etmiş olacaksınız. İşinizi hemen bu pencereye alın!"
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `status` | `string` | `"scheduled"` = optimal pencere bulundu, `"pending"` = bulunamadı |
| `optimal_window` | `object \| null` | `null` ise zamanlamada uygun pencere yok |
| `optimal_window.estimated_savings_tl` | `float \| null` | Optimal pencerede mevcut PTF'e göre tahmini TL elektrik tasarrufu |
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

### 5.2 İş Şablonları — `GET /api/jobs/templates`

**Auth gerekmez.**  
Frontend'deki "hızlı ekle" butonları için 7 hazır şablon.

**Yanıt `200`:**
```json
[
  {
    "name": "Log Processing",
    "duration_hours": 2,
    "power_kw": 50,
    "priority": 1,
    "description": "Sistem log dosyalarının işlenmesi ve arşivlenmesi"
  },
  {
    "name": "ML Model Eğitimi",
    "duration_hours": 8,
    "power_kw": 300,
    "priority": 3,
    "description": "Makine öğrenmesi modelinin sıfırdan eğitimi"
  }
]
```

**Kullanım:** Kullanıcı şablona tıkladığında bu değerler `POST /api/jobs/analyze`'e gönderilir, yanıttaki `reply` chatbota eklenir.

---

### 5.3 Analiz (kayıtsız) — `POST /api/jobs/analyze`

**Auth gerekir.** DB'ye kayıt yapmaz. Şablon tıklandığında çağrılır.

**İstek:**
```json
{
  "name": "ML Model Eğitimi",
  "duration_hours": 8,
  "power_kw": 300,
  "priority": 3
}
```

| Alan | Tip | Zorunlu |
|---|---|---|
| `name` | `string` | ✅ |
| `duration_hours` | `float` | ✅ |
| `power_kw` | `float` | ✅ |
| `priority` | `int` | — (varsayılan 1) |
| `deadline` | ISO-8601 | — |

**Yanıt `200`:**
```json
{
  "reply": "**ML Model Eğitimi İş Analizi**\n\n📅 Önerilen Pencere: 16.05 11:00–19:00\n💚 CO₂ Tasarrufu: 38.40 kg (%18)\n⚡ Mevcut Yoğunluk: 247 gCO₂/kWh\n\n**Değerlendirme:** Güneş üretiminin yüksek olduğu öğle saatleri...",
  "optimal_window": {
    "start_time": "2026-05-16T11:00:00+03:00",
    "end_time": "2026-05-16T19:00:00+03:00",
    "avg_carbon_intensity": 203.5,
    "estimated_savings_pct": 17.7,
    "estimated_savings_tl": 312.0,
    "reasoning": "..."
  },
  "recommendation": {
    "window": "11:00–19:00",
    "date": "16.05",
    "savings_kg": 38.4,
    "savings_pct": 17.7,
    "reasoning": "...",
    "action": "İşi hemen 11:00'e planlayın"
  },
  "current_carbon_intensity": 247.1
}
```

**React entegrasyonu:**
```js
async function analyzeTemplate(template) {
  const res = await fetch('/api/jobs/analyze', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(template),
  })
  const data = await res.json()
  // reply'ı chatbota ekle:
  addMessage({ role: 'assistant', content: data.reply })
}
```

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

## 6. Zamanlama (Schedule)

Tüm zamanlama endpoint'leri **auth gerektirir.**

Zamanlayıcı, kullanıcının tüm `pending` ve `scheduled` işleri için karbon yoğunluğu tahmini üzerinde çakışmasız pencere ataması yapar. Planlı kesintiler (EPİAŞ'tan çekilen `planned_outages`) otomatik olarak dikkate alınır.

---

### `GET /api/schedule` — Mevcut takvimi görüntüle

İşleri henüz onaylamadan takvimi hesaplar — **DB'ye yazmaz.**

**Yanıt `200`:**
```json
{
  "generated_at": "2026-05-16T09:00:00+03:00",
  "jobs": [
    {
      "job_id": 1,
      "name": "Model Eğitimi v2",
      "start_time": "2026-05-16T11:00:00+03:00",
      "end_time": "2026-05-16T15:00:00+03:00",
      "duration_hours": 4,
      "power_kw": 250,
      "avg_carbon_intensity": 202.3,
      "estimated_savings_pct": 18.5,
      "estimated_savings_tl": 124.5,
      "status": "scheduled",
      "color": "#22c55e",
      "reasoning": "16.05 tarihinde 11:00–15:00 arası en uygun pencere.",
      "ai_recommendation": "..."
    },
    {
      "job_id": 2,
      "name": "Log Processing",
      "start_time": "2026-05-16T15:00:00+03:00",
      "end_time": "2026-05-16T17:00:00+03:00",
      "duration_hours": 2,
      "power_kw": 50,
      "avg_carbon_intensity": 218.0,
      "estimated_savings_pct": 11.2,
      "estimated_savings_tl": 18.3,
      "status": "scheduled",
      "color": "#eab308",
      "reasoning": "...",
      "ai_recommendation": null
    }
  ],
  "summary": {
    "total_jobs": 2,
    "scheduled_jobs": 2,
    "total_carbon_saved_kg": 47.6,
    "total_energy_kwh": 1100.0,
    "avg_savings_pct": 14.9,
    "total_cost_saved_tl": 142.8
  }
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `jobs[].color` | hex string | Karbon yoğunluğuna göre: `#22c55e` (<200), `#eab308` (<250), `#f97316` (<350), `#ef4444` (≥350) |
| `jobs[].estimated_savings_tl` | `float \| null` | PTF fiyat farkına dayalı tahmini TL elektrik tasarrufu |
| `summary.total_cost_saved_tl` | `float \| null` | Tüm işlerin TL tasarruf toplamı |

**Çakışma garantisi:** Her iki iş aynı saat dilimine atanmaz. İş önceliği (`priority` DESC) ve deadline'a göre sıralanır.

---

### `POST /api/schedule/approve` — Takvimi onayla

Hesaplanan takvimi DB'ye yazar; `scheduled_start` alanlarını doldurur.

**İstek:**
```json
{
  "job_ids": [],
  "demo_mode": false
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `job_ids` | `int[]` | Onaylanacak iş ID'leri. **Boş dizi = tüm aktif işler onaylanır** |
| `demo_mode` | `bool` | `true` → `scheduled_start` değerleri şimdiki zamana çekilir (demo/sunum için) |

**Yanıt `200`:** `ScheduleResponse` — onaylanmış işleri içerir (`GET /api/schedule` şemasıyla aynı)

**Tipik akış:**
```js
// 1. Önizle
const preview = await fetch('/api/schedule', { headers: authHeaders() }).then(r => r.json())
// 2. Kullanıcı onaylarsa kaydet
const approved = await fetch('/api/schedule/approve', {
  method: 'POST',
  headers: authHeaders(),
  body: JSON.stringify({ job_ids: [], demo_mode: false }),
}).then(r => r.json())
```

---

### `POST /api/schedule/demo` — Demo preset çalıştır

3 hazır demo işi oluşturur (Veri Yedekleme, Model Eğitimi, Log Analizi) ve hemen onaylar. Sunum ve demo amacıyla kullanılır.

**İstek body gerekmez.**

**Yanıt `200`:** `ScheduleResponse` — 3 iş, çakışmasız zaman dilimleriyle

```json
{
  "generated_at": "...",
  "jobs": [
    { "name": "Veri Yedekleme", "duration_hours": 2, ... },
    { "name": "Model Eğitimi", "duration_hours": 4, ... },
    { "name": "Log Analizi",   "duration_hours": 1, ... }
  ],
  "summary": { "total_jobs": 3, "scheduled_jobs": 3, ... }
}
```

**Not:** Demo modunda `scheduled_start` değerleri sırasıyla 30 sn, 2 dk, 4 dk sonrası olarak atanır — arkaplanda ilerleme animasyonu otomatik başlar.

---

## 7. Sohbet

### `POST /api/chat` — AI chat (tam yanıt)

**Auth gerekir.**

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

## 8. Streaming Sohbet

### `POST /api/chat/stream` — SSE token stream

**Auth gerekir.**  
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
  const res = await fetch('https://undistractedly-gimlety-angelena.ngrok-free.dev/api/chat/stream', {
    method: 'POST',
    headers: authHeaders(),
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

## 9. Tasarruf Özeti

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

## 10. Arka Plan İş İlerlemesi

Sunucu başladığında her **15 saniyede** bir arka planda çalışan bir görev iş durumlarını otomatik günceller:

| Koşul | Geçiş |
|---|---|
| `status = "scheduled"` ve `scheduled_start ≤ şimdi` | → `"running"` |
| `status = "running"` ve `scheduled_start + duration_hours ≤ şimdi` | → `"completed"` |

**Frontend polling önerisi:**
```js
// Her 10 saniyede iş listesini çek — status güncellemelerini yakala
useEffect(() => {
  const interval = setInterval(async () => {
    const data = await getJobs()
    setJobs(data.jobs)
  }, 10_000)
  return () => clearInterval(interval)
}, [])
```

**Demo akışı:**
1. `POST /api/schedule/demo` → 3 iş oluşturulur, `scheduled_start` sırasıyla 30 sn / 2 dk / 4 dk sonrası
2. 30 sn sonra ilk iş `"running"` olur
3. Birkaç dakika içinde tüm işler `"completed"` olur

**Not:** Arka plan görevi yalnızca `scheduled_start` alanı dolu olan işleri günceller. `POST /api/schedule/approve` çağrısına kadar bu alan boştur.

---

## 11. Hata Kodları

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

## 12. Hızlı Başlangıç

Uçtan uca minimum akış — kayıt, token alma, iş ekleme:

```js
const BASE = 'https://undistractedly-gimlety-angelena.ngrok-free.dev'

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
- **Swagger UI:** `https://undistractedly-gimlety-angelena.ngrok-free.dev/docs` — tüm endpoint'leri tarayıcıdan deneyebilirsin
