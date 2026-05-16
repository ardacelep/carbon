# Karbon Zeka — Frontend Veri Rehberi

> Backend API'sinden gelen veriler, hesaplanan metrikler ve önerilen görselleştirmeler.  
> Tüm endpoint'ler `http://localhost:8000` üzerinde çalışır.

---

## İçindekiler

1. [Anlık Karbon Yoğunluğu](#1-anlık-karbon-yoğunluğu)
2. [24 Saatlik Tahmin](#2-24-saatlik-tahmin)
3. [İş Kuyruğu ve Optimal Pencere](#3-i̇ş-kuyruğu-ve-optimal-pencere)
4. [Tasarruf Özeti](#4-tasarruf-özeti)
5. [Sohbet (AI Chat)](#5-sohbet-ai-chat)
6. [Renk ve Eşik Değerleri](#6-renk-ve-eşik-değerleri)
7. [Güncelleme Sıklıkları](#7-güncelleme-sıklıkları)

---

## 1. Anlık Karbon Yoğunluğu

**Endpoint:** `GET /api/carbon/current`

```json
{
  "carbon_intensity": 240.9,
  "renewable_ratio": 0.679,
  "timestamp": "2026-05-16T01:00:00+03:00",
  "source": "epias",
  "updated_minutes_ago": 67
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `carbon_intensity` | `float` | gCO2eq/kWh — ne kadar düşükse o kadar iyi |
| `renewable_ratio` | `float` | 0.0–1.0 arası (0.679 = %67.9 yenilenebilir) |
| `timestamp` | `string` ISO-8601 | Verinin ait olduğu saat (EPİAŞ 1-2 saat gecikmeli) |
| `source` | `"epias"` \| `"mock"` | `"mock"` ise canlı bağlantı yok |
| `updated_minutes_ago` | `int` | Verinin kaç dakika önce güncellendiği |

**Gözlemlenen gerçek aralıklar (Türkiye şebekesi):**
- Gece (00-06): ~230–250 gCO2/kWh, yenilenebilir %65–70
- Gündüz güneşli (10-16): ~190–220 gCO2/kWh, yenilenebilir %70–80
- Akşam pik (18-22): ~260–300 gCO2/kWh, yenilenebilir %55–65

### Önerilen Görselleştirmeler

#### A. Gösterge (Gauge / Speedometer)
Yarım daire gauge, merkeze büyük sayı:
- Merkez: `carbon_intensity` değeri + "gCO2/kWh"
- Alt: `renewable_ratio` → "%68 Yenilenebilir"
- Renk: aşağıdaki eşiklere göre (bkz. [Bölüm 6](#6-renk-ve-eşik-değerleri))

```
        240.9
      gCO2/kWh
    %67.9 Yenilenebilir
    ● Gece 01:00 verisi
    Son güncelleme: 67 dk önce
```

#### B. Yakıt Karışımı Pie/Donut Chart
EPİAŞ `rt-gen` verisinden türetilmiş — backend bu dağılımı ileride `/api/carbon/mix` endpoint'i olarak açabilir. Şimdilik `carbon_intensity` düşükken "yenilenebilir ağırlıklı", yüksekken "fosil ağırlıklı" label'ı gösterilebilir.

Gerçek MWh dağılımı (örnek):
| Kaynak | MWh | Pay |
|---|---|---|
| Barajlı Hidro | 13.034 | %38.5 |
| Doğal Gaz | 6.210 | %18.4 |
| Nehir Hidro | 5.643 | %16.7 |
| Linyit | 3.113 | %9.2 |
| Rüzgar | 2.280 | %6.7 |
| Diğer | 3.552 | %10.5 |

---

## 2. 24 Saatlik Tahmin

**Endpoint:** `GET /api/carbon/forecast`

```json
{
  "generated_at": "2026-05-16T03:00:00+03:00",
  "source": "epias",
  "points": [
    {
      "timestamp": "2026-05-16T04:00:00+03:00",
      "carbon_intensity": 238.7,
      "renewable_ratio": 0.682,
      "confidence": 0.90
    },
    {
      "timestamp": "2026-05-16T13:00:00+03:00",
      "carbon_intensity": 195.0,
      "renewable_ratio": 0.761,
      "confidence": 0.72
    }
  ]
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `generated_at` | `string` ISO-8601 | Tahminin üretildiği an |
| `source` | `"epias"` \| `"epias-partial"` \| `"mock"` | `"epias-partial"` = rüzgar tahmini alınamadı |
| `points[].timestamp` | `string` ISO-8601 | Tahminin ait olduğu saat |
| `points[].carbon_intensity` | `float` | gCO2eq/kWh |
| `points[].renewable_ratio` | `float` | 0.0–1.0 |
| `points[].confidence` | `float` | 0.55–0.90 (yakın saat → yüksek güven) |

**Tahmin nasıl üretiliyor:**
1. Son bilinen üretim karışımı baseline olarak alınıyor
2. EPİAŞ rüzgar tahmini (`wind-forecast`) ile rüzgar bileşeni güncelleniyor
3. Güneş üretimi saat başına güneş eğrisiyle tahmin ediliyor (gece=0, saat 13=pik)
4. Diğer kaynaklar sabit tutuluyor

**Beklenen örüntü (Mayıs, güneşli gün):**
```
Saat  04:00  07:00  10:00  13:00  16:00  19:00  22:00
CI    239    235    210    195    205    250    265   gCO2/kWh
Ren   68%    69%    73%    76%    74%    64%    60%
```

### Önerilen Görselleştirmeler

#### A. Alan Grafiği (Area Chart) — Ana görsel
X ekseni: Saat (24 nokta)  
Y ekseni: gCO2/kWh  
Gölge alanı: `confidence` değerine göre şeffaflık (confidence=0.9 → koyu, 0.55 → soluk)

```
gCO2/kWh
300 |
270 |    ╭──╮                              ╭──
240 |───╯    ╰──╮                    ╭──╯
210 |             ╰──╮          ╭──╯
180 |                 ╰────────╯   ← güneş piki
    └─────────────────────────────────────────▶ saat
     00  03  06  09  12  15  18  21  24
```

Renk bantları: yeşil bölge (< 220), sarı (220–280), kırmızı (> 280)

#### B. İş Zamanlaması İçin Highlight
En iyi pencereyi renkli bant olarak göster:
- `carbon_intensity` en düşük olan ardışık N saati bul (N = iş süresi)
- O bloğu yeşil dikdörtgen ile vurgula
- Tooltip: "Bu pencerede %18 daha az karbon"

#### C. Yenilenebilir Oran Çizgisi (ikincil eksen)
Aynı grafik üzerinde `renewable_ratio` için ikinci Y ekseni (sağ taraf, %0–100)

---

## 3. İş Kuyruğu ve Optimal Pencere

**Endpoint:** `POST /api/jobs` — iş ekleme

**İstek:**
```json
{
  "name": "Model Eğitimi v2",
  "duration_hours": 4,
  "deadline": "2026-05-17T18:00:00+03:00",
  "priority": 3,
  "power_kw": 250
}
```

| Alan | Tip | Kısıt |
|---|---|---|
| `name` | `string` | 1–200 karakter |
| `duration_hours` | `float` | 0 < değer ≤ 72 |
| `deadline` | `string` ISO-8601 \| `null` | Opsiyonel |
| `priority` | `int` | 1 (düşük) – 5 (acil) |
| `power_kw` | `float` | İş yükünün güç tüketimi |

**Yanıt:**
```json
{
  "id": 1,
  "name": "Model Eğitimi v2",
  "duration_hours": 4,
  "deadline": "2026-05-17T18:00:00+03:00",
  "priority": 3,
  "power_kw": 250,
  "status": "scheduled",
  "created_at": "2026-05-16T03:15:00+03:00",
  "scheduled_start": "2026-05-16T11:00:00+03:00",
  "optimal_window": {
    "start_time": "2026-05-16T11:00:00+03:00",
    "end_time": "2026-05-16T15:00:00+03:00",
    "avg_carbon_intensity": 202.3,
    "estimated_savings_pct": 18.5,
    "reasoning": "Güneş üretiminin pik yaptığı ve rüzgar tahmininin güçlü olduğu bu pencerede..."
  },
  "ai_recommendation": "Bu iş için en uygun pencere 11:00–15:00 arasıdır. ..."
}
```

**Endpoint:** `GET /api/jobs` — iş listesi

```json
{
  "jobs": [ ... ],
  "total": 5
}
```

**İş durumları (`status`):**
| Değer | Anlam |
|---|---|
| `"pending"` | Henüz zamanlanmadı |
| `"scheduled"` | Optimal pencere bulundu |
| `"running"` | Şu an çalışıyor |
| `"completed"` | Tamamlandı |

### Önerilen Görselleştirmeler

#### A. Gantt / Zaman Çizelgesi
Forecast grafiğinin alt kısmına iş bloklarını ekle:

```
gCO2/kWh
250 |──╮            ╭──
220 |   ╰──╮    ╭──╯       ← karbon eğrisi
190 |       ╰──╯
    |    [══════]           ← optimal pencere (yeşil)
    |         [════════]    ← başka bir iş (mavi)
    └─────────────────────▶ saat
     06   09   12   15   18
```

Her blokta:
- İş adı
- Süre (N saat)
- Tahmini tasarruf %'si

#### B. İş Kartı Bileşeni
```
┌─────────────────────────────────────┐
│ Model Eğitimi v2          [scheduled]│
│ Süre: 4 sa  |  Güç: 250 kW          │
│ ─────────────────────────────────── │
│ Optimal Başlangıç: 16 May 11:00     │
│ Tahmini Karbon: 202 gCO2/kWh        │
│ ✓ %18.5 tasarruf                    │
│ ─────────────────────────────────── │
│ [AI Öneri göster ▼]                 │
└─────────────────────────────────────┘
```

#### C. Önce/Sonra Karşılaştırması
Küçük bar chart — "şimdi çalıştırsan" vs "önerilen pencerede":
```
Şimdi:    ████████████████  265 gCO2/kWh
Önerilen: █████████████     202 gCO2/kWh  ← %18.5 daha az
```

---

## 4. Tasarruf Özeti

**Endpoint:** `GET /api/savings/summary`

```json
{
  "total_jobs": 12,
  "optimized_jobs": 9,
  "total_carbon_saved_kg": 142.8,
  "total_energy_kwh": 8400.0,
  "avg_carbon_intensity": 228.5,
  "best_saving_pct": 24.3,
  "period_start": "2026-05-15T00:00:00+03:00",
  "period_end": "2026-05-16T03:00:00+03:00"
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `total_carbon_saved_kg` | `float` | Toplam kaçınılan CO2 (kg) |
| `total_energy_kwh` | `float` | Toplam tüketilen enerji |
| `avg_carbon_intensity` | `float` | Ortalama gCO2/kWh (optimize edilmiş işlerde) |
| `best_saving_pct` | `float` | En iyi tek iş tasarrufu (%) |
| `optimized_jobs` | `int` | Zamanlama optimizasyonundan yararlanan iş sayısı |

**Türetilmiş metrikler (frontend hesaplıyor):**
```js
const optimization_rate = (optimized_jobs / total_jobs) * 100  // %75
const trees_equivalent = total_carbon_saved_kg / 21.7          // ~6.6 ağaç/yıl
const avg_saving_per_job = total_carbon_saved_kg / optimized_jobs
```

### Önerilen Görselleştirmeler

#### A. KPI Kartları (3–4 kart yan yana)
```
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  142.8 kg    │ │   %75        │ │  %24.3       │ │  ~6.6        │
│  CO2 Tasarr. │ │  Optimize    │ │  En İyi      │ │  Ağaç/Yıl   │
│              │ │  Oran        │ │  Tasarruf    │ │  Eşdeğeri   │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

#### B. Zaman İçinde Tasarruf (Bar Chart)
X: Gün  
Y: O gün tasarruf edilen kg CO2  
Renk: İş adedine göre ton

---

## 5. Sohbet (AI Chat)

**Endpoint:** `POST /api/chat`

**İstek:**
```json
{
  "message": "Bugün sunucularımı ne zaman çalıştırmalıyım?",
  "history": [
    {"role": "user", "content": "Merhaba"},
    {"role": "assistant", "content": "Merhaba! Size nasıl yardımcı olabilirim?"}
  ]
}
```

**Yanıt:**
```json
{
  "reply": "Bugün en düşük karbon dönemi öğleden sonra 12:00–15:00 arasında...",
  "timestamp": "2026-05-16T03:20:00+03:00"
}
```

AI her yanıtta anlık karbon verisi ve forecast'e erişir — kullanıcı elle sormak zorunda değil.

### Önerilen Görselleştirmeler

Standart chat UI + şu özel bileşenler:

- **Karbon rozeti:** AI yanıtlarının altında küçük renkli chip: `● 240 gCO2/kWh şu an`
- **Saat önerisi vurgusu:** AI "11:00–15:00" gibi saat aralığı verirse, bunu tıklanabilir chip olarak göster → takvime ekle veya job queue'ya at

---

## 6. Renk ve Eşik Değerleri

Tüm bileşenlerde tutarlı kullanım için:

```js
function getCarbonColor(gCO2perKwh) {
  if (gCO2perKwh < 200) return '#22c55e'  // yeşil  — mükemmel
  if (gCO2perKwh < 250) return '#eab308'  // sarı   — orta
  if (gCO2perKwh < 350) return '#f97316'  // turuncu — yüksek
  return '#ef4444'                         // kırmızı — çok yüksek
}

function getCarbonLabel(gCO2perKwh) {
  if (gCO2perKwh < 200) return 'Mükemmel'
  if (gCO2perKwh < 250) return 'İyi'
  if (gCO2perKwh < 350) return 'Orta'
  return 'Yüksek'
}
```

**Yenilenebilir oran renklendirmesi:**
```js
function getRenewableColor(ratio) {  // 0.0–1.0
  if (ratio > 0.70) return '#22c55e'  // yeşil
  if (ratio > 0.50) return '#eab308'  // sarı
  return '#ef4444'                    // kırmızı
}
```

**Türkiye şebekesi için gerçekçi referans değerleri:**
| | gCO2/kWh | Yenilenebilir |
|---|---|---|
| En iyi (güneş+rüzgar piki) | ~180–200 | %75–80 |
| Tipik gündüz | ~220–250 | %65–70 |
| Tipik gece | ~230–260 | %60–68 |
| En kötü (pik talep+az rüzgar) | ~350–400 | %40–50 |

---

## 7. Güncelleme Sıklıkları

| Veri | Backend Cache | Önerilen Frontend Polling |
|---|---|---|
| Anlık karbon (`/current`) | 15 dakika | Her 5 dakika |
| 24 sa tahmin (`/forecast`) | 30 dakika | Her 15 dakika |
| İş listesi (`/jobs`) | Cache yok | Her 30 saniye veya event-driven |
| Tasarruf özeti (`/savings/summary`) | Cache yok | Her 5 dakika |

> **Not:** EPİAŞ'ın veri yayınlama gecikmesi 1-2 saattir. `updated_minutes_ago` değeri 90'ı geçerse kullanıcıya `"Veri güncellenmemiş olabilir"` uyarısı göster.

---

## Veri Akış Diyagramı

```
EPİAŞ rt-gen                    Backend
(saatlik üretim) ──────────────▶ calculate_carbon_intensity()
                                        │
EPİAŞ wind-forecast                    ▼
(48 sa rüzgar)   ──────────────▶ get_forecast()
                                        │
                           ┌────────────┼──────────────┐
                           ▼            ▼              ▼
                    /api/carbon/  /api/carbon/   /api/jobs
                      current      forecast    (optimal pencere)
                           │            │              │
                           └────────────┴──────────────┘
                                        │
                                   Frontend
                            ┌───────────┼──────────────┐
                            ▼           ▼              ▼
                         Gauge      ForecastChart   JobQueue
                       (anlık CI)   (24 sa trend)  (Gantt/kart)
```
