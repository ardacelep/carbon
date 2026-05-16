# Karbon Zeka — Frontend Geliştirici Rehberi

> Backend hazır ve dışarıya açık. Bu rehberi okuyarak hiçbir ek kurulum yapmadan API'ye bağlanabilirsin.

---

## Bağlantı

```
Base URL: https://undistractedly-gimlety-angelena.ngrok-free.app
```

> **Not:** ngrok URL'si bilgisayar her yeniden başlatıldığında değişir. Değişirse Arda'dan yenisini iste.

Bağlantıyı test et — tarayıcıda aç veya terminalde:
```bash
curl https://undistractedly-gimlety-angelena.ngrok-free.app/api/carbon/current
```

Şuna benzer bir JSON dönmeli:
```json
{
  "carbon_intensity": 219.1,
  "renewable_ratio": 0.724,
  "timestamp": "2026-05-16T04:00:00+03:00",
  "source": "epias",
  "updated_minutes_ago": 141
}
```

---

## Projeye Ekle

```js
// src/api.js (veya config.js)
export const BASE_URL = 'https://undistractedly-gimlety-angelena.ngrok-free.app'
```

---

## 1. Kayıt ve Giriş

Korumalı endpoint'leri kullanmak için önce token almanı gerekiyor.

### Kayıt ol
```js
const res = await fetch(`${BASE_URL}/api/auth/signup`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    email: 'sen@example.com',
    password: 'sifren123'
  })
})
const { access_token, user_id } = await res.json()
localStorage.setItem('token', access_token)
```

### Giriş yap (sonraki oturumlarda)
```js
const res = await fetch(`${BASE_URL}/api/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: 'sen@example.com', password: 'sifren123' })
})
const { access_token } = await res.json()
localStorage.setItem('token', access_token)
```

### Token'ı her korumalı isteğe ekle
```js
// Bu helper'ı bir kez yaz, her yerde kullan
function authHeaders() {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${localStorage.getItem('token')}`
  }
}
```

---

## 2. Anlık Karbon Yoğunluğu

**`GET /api/carbon/current`** — Auth gerekmez

```js
const res = await fetch(`${BASE_URL}/api/carbon/current`)
const data = await res.json()

// data örneği:
// {
//   carbon_intensity: 219.1,      → gCO2eq/kWh (düşük = iyi)
//   renewable_ratio: 0.724,       → 0.724 = %72.4 yenilenebilir
//   timestamp: "2026-05-16T04:00:00+03:00",
//   source: "epias",              → "fallback" ise API erişimi yok ama sistem çalışıyor
//   updated_minutes_ago: 141      → 90'ı geçerse "veri güncel olmayabilir" uyarısı göster
// }
```

**Renk kodlaması:**
```js
function getCarbonColor(ci) {
  if (ci < 200) return '#22c55e'   // yeşil  — mükemmel
  if (ci < 250) return '#eab308'   // sarı   — iyi
  if (ci < 350) return '#f97316'   // turuncu — yüksek
  return '#ef4444'                  // kırmızı — çok yüksek
}

function getCarbonLabel(ci) {
  if (ci < 200) return 'Mükemmel'
  if (ci < 250) return 'İyi'
  if (ci < 350) return 'Yüksek'
  return 'Çok Yüksek'
}
```

**React hook örneği:**
```jsx
function useCarbonCurrent() {
  const [data, setData] = useState(null)

  useEffect(() => {
    const fetch_ = () =>
      fetch(`${BASE_URL}/api/carbon/current`)
        .then(r => r.json())
        .then(setData)

    fetch_()
    const interval = setInterval(fetch_, 5 * 60 * 1000) // her 5 dk
    return () => clearInterval(interval)
  }, [])

  return data
}

// Kullanım:
function CarbonGauge() {
  const carbon = useCarbonCurrent()
  if (!carbon) return <div>Yükleniyor...</div>

  return (
    <div style={{ color: getCarbonColor(carbon.carbon_intensity) }}>
      <h2>{carbon.carbon_intensity} gCO2/kWh</h2>
      <p>%{(carbon.renewable_ratio * 100).toFixed(1)} Yenilenebilir</p>
      {carbon.updated_minutes_ago > 90 && (
        <small>⚠ Veri güncel olmayabilir</small>
      )}
    </div>
  )
}
```

---

## 3. 24 Saatlik Tahmin

**`GET /api/carbon/forecast?hours=24`** — Auth gerekmez

```js
const res = await fetch(`${BASE_URL}/api/carbon/forecast?hours=24`)
const { points, source } = await res.json()

// points dizisindeki her eleman:
// {
//   timestamp: "2026-05-16T13:00:00+03:00",
//   carbon_intensity: 195.0,
//   renewable_ratio: 0.761,
//   confidence: 0.72    → 0.55–0.90 arası. Grafik şeffaflığı için kullan.
// }
```

**Recharts ile alan grafiği:**
```jsx
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

function ForecastChart({ points }) {
  const formatted = points.map(p => ({
    hour: new Date(p.timestamp).getHours() + ':00',
    karbon: p.carbon_intensity,
    opacity: p.confidence
  }))

  return (
    <ResponsiveContainer width="100%" height={250}>
      <AreaChart data={formatted}>
        <XAxis dataKey="hour" />
        <YAxis domain={['auto', 'auto']} unit=" gCO2" />
        <Tooltip formatter={v => `${v} gCO2/kWh`} />
        <Area
          type="monotone"
          dataKey="karbon"
          stroke="#22c55e"
          fill="#22c55e"
          fillOpacity={0.3}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
```

---

## 4. Şebeke Durumu

**`GET /api/grid/status`** — Auth gerekmez

```js
const res = await fetch(`${BASE_URL}/api/grid/status`)
const grid = await res.json()

// {
//   dam_fullness_pct: 68.4,           → baraj doluluk %
//   dam_trend: "stable",              → "increasing" | "stable" | "declining"
//   ptf_tl_per_mwh: 295.99,          → elektrik spot fiyatı ₺/MWh
//   supply_demand_mw: 820.0,          → pozitif=fazla, negatif=açık
//   grid_stress: "low",               → "low" | "medium" | "high"
//   planned_outages: [...],           → önümüzdeki 7 günün planlı kesintileri
//   source: "epias"
// }
```

---

## 5. İş Ekleme ve Zamanlama

**`POST /api/jobs`** — Auth gerekir

```js
const res = await fetch(`${BASE_URL}/api/jobs`, {
  method: 'POST',
  headers: authHeaders(),
  body: JSON.stringify({
    name: 'Model Eğitimi',
    duration_hours: 4,       // kaç saat sürecek
    power_kw: 250,           // kaç kW çekiyor
    priority: 3,             // 1 (düşük) – 5 (acil)
    deadline: '2026-05-17T18:00:00+03:00',  // opsiyonel
    cost_weight: 0.0         // 0=sadece karbon, 1=sadece maliyet optimize et
  })
})
const job = await res.json()

// Yanıtta optimal pencere ve AI önerisi gelir:
// {
//   id: 7,
//   name: "Model Eğitimi",
//   status: "scheduled",
//   optimal_window: {
//     start_time: "2026-05-16T11:00:00+03:00",
//     end_time: "2026-05-16T15:00:00+03:00",
//     avg_carbon_intensity: 202.3,
//     estimated_savings_pct: 18.5,
//     reasoning: "Güneş üretiminin yüksek olduğu saatler..."
//   },
//   ai_recommendation: "Bu iş için en uygun pencere 11:00–15:00..."
// }
```

---

## 6. İş Listesi ve CRUD

```js
// Tüm işleri getir
const { jobs, total } = await fetch(`${BASE_URL}/api/jobs`, {
  headers: authHeaders()
}).then(r => r.json())

// Tek iş
const job = await fetch(`${BASE_URL}/api/jobs/7`, {
  headers: authHeaders()
}).then(r => r.json())

// Durumu güncelle
await fetch(`${BASE_URL}/api/jobs/7/status`, {
  method: 'PATCH',
  headers: authHeaders(),
  body: JSON.stringify({ status: 'running' })
  // Geçerli değerler: "pending" | "scheduled" | "running" | "completed" | "cancelled"
})

// Sil
await fetch(`${BASE_URL}/api/jobs/7`, {
  method: 'DELETE',
  headers: authHeaders()
})
```

---

## 7. AI Sohbet

**`POST /api/chat`** — Auth gerekmez

```js
const res = await fetch(`${BASE_URL}/api/chat`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    message: 'Bugün sunucularımı ne zaman çalıştırmalıyım?',
    history: [
      { role: 'user', content: 'Merhaba' },
      { role: 'assistant', content: 'Merhaba! Nasıl yardımcı olabilirim?' }
    ]
  })
})
const { reply } = await res.json()
// reply: "Şu an şebeke karbon yoğunluğu 219 gCO2eq/kWh ile düşük seyrediyor..."
```

---

## 8. Streaming Sohbet (ChatGPT gibi token token)

**`POST /api/chat/stream`** — Auth gerekmez, aynı body

```jsx
async function streamChat(message, history, onToken, onDone) {
  const res = await fetch(`${BASE_URL}/api/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history })
  })

  const reader = res.body.getReader()
  const decoder = new TextDecoder()

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    for (const line of decoder.decode(value).split('\n')) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6)
      if (payload === '[DONE]') { onDone?.(); return }
      try {
        const { token } = JSON.parse(payload)
        if (token) onToken(token)
      } catch {}
    }
  }
}

// React kullanımı:
function ChatBox() {
  const [reply, setReply] = useState('')
  const [loading, setLoading] = useState(false)

  const send = async (message) => {
    setReply('')
    setLoading(true)
    await streamChat(
      message,
      [],
      (token) => setReply(prev => prev + token),
      () => setLoading(false)
    )
  }

  return (
    <div>
      <button onClick={() => send('Bugün ne zaman çalıştırmalıyım?')}>
        Sor
      </button>
      <p>{loading && !reply ? 'Düşünüyor...' : reply}</p>
    </div>
  )
}
```

---

## 9. Tasarruf Özeti

**`GET /api/savings/summary`** — Auth gerekir

```js
const summary = await fetch(`${BASE_URL}/api/savings/summary`, {
  headers: authHeaders()
}).then(r => r.json())

// {
//   total_jobs: 12,
//   optimized_jobs: 9,
//   total_carbon_saved_kg: 142.8,
//   total_energy_kwh: 8400.0,
//   best_saving_pct: 24.3
// }

// Türetilmiş metrikler:
const optimizationRate = ((summary.optimized_jobs / summary.total_jobs) * 100).toFixed(0) + '%'
const treesEquivalent  = (summary.total_carbon_saved_kg / 21.7).toFixed(1)  // yıllık ağaç eşdeğeri
```

---

## Hata Yönetimi

```js
async function apiFetch(url, options = {}) {
  const res = await fetch(url, options)

  if (res.status === 401) {
    localStorage.removeItem('token')
    window.location.href = '/login'   // token süresi dolmuş
    return
  }

  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Bir hata oluştu')
  }

  return res.json()
}

// Kullanım (try/catch ile):
try {
  const jobs = await apiFetch(`${BASE_URL}/api/jobs`, { headers: authHeaders() })
} catch (e) {
  console.error(e.message)
}
```

| HTTP Kodu | Anlam | Ne yapmalı |
|---|---|---|
| `401` | Token geçersiz / süresi dolmuş | Tekrar login yaptır |
| `404` | Kaynak bulunamadı | UI'da "bulunamadı" göster |
| `422` | Gönderilen veri hatalı | Form validasyonunu güçlendir |
| `500` | Sunucu hatası | "Daha sonra tekrar dene" göster |

---

## Tüm Endpoint'ler Özeti

| Method | URL | Auth | Açıklama |
|---|---|---|---|
| POST | `/api/auth/signup` | — | Kayıt ol |
| POST | `/api/auth/login` | — | Giriş yap |
| GET | `/api/carbon/current` | — | Anlık karbon |
| GET | `/api/carbon/forecast` | — | 24 sa tahmin |
| GET | `/api/grid/status` | — | Şebeke durumu |
| POST | `/api/jobs` | ✅ | İş ekle + AI öneri |
| GET | `/api/jobs` | ✅ | İş listesi |
| GET | `/api/jobs/{id}` | ✅ | Tek iş |
| DELETE | `/api/jobs/{id}` | ✅ | İş sil |
| PATCH | `/api/jobs/{id}/status` | ✅ | Durum güncelle |
| POST | `/api/chat` | — | AI sohbet |
| POST | `/api/chat/stream` | — | Streaming sohbet |
| GET | `/api/savings/summary` | ✅ | Tasarruf özeti |

---

> **Swagger UI:** `https://undistractedly-gimlety-angelena.ngrok-free.app/docs`  
> Tüm endpoint'leri tarayıcıdan deneyebilirsin. Auth için sağ üstteki **Authorize** butonuna token'ı yapıştır.
