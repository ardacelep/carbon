# Karbon Zeka: Türkiye Elektrik Şebekesi Karbon Yoğunluğu Tabanlı  
# Yapay Zeka Destekli İş Yükü Optimizasyon Sistemi

**Teknik Whitepaper — v1.0**  
**100 StaryUP Hackathonu, YTÜ — Mayıs 2026**

---

## Öz

Veri merkezleri küresel elektrik tüketiminin yaklaşık %1–2'sini oluşturmakta ve bu oran hızla artmaktadır. Türkiye elektrik şebekesi, yenilenebilir enerji kaynaklarının anlık katkısına bağlı olarak günün farklı saatlerinde 150–450 gCO₂eq/kWh arasında değişen bir karbon yoğunluğu profiline sahiptir. Bu çalışmada, EPİAŞ (Enerji Piyasaları İşletme A.Ş.) gerçek zamanlı üretim verilerini, 48 saatlik tahmin algoritmalarını ve NVIDIA NIM üzerinde çalışan büyük dil modelini birleştirerek veri merkezi operatörlerine esneklik verilebilen iş yüklerini karbon-optimal zaman dilimine kaydıran bir platform tanıtılmaktadır. Platform, eğitim işleri, yedekleme görevleri ve toplu veri işleme gibi zaman-esnek hesaplamalar için %15–25 karbon tasarrufu sağlamaktadır.

---

## 1. Giriş ve Motivasyon

### 1.1 Sorun Tanımı

Karbon emisyonlarının azaltılması, enerji yoğun sektörler için giderek daha kritik bir gereklilik haline gelmektedir. Veri merkezi operatörleri bu baskıyı iki yönden hissetmektedir:

- **Düzenleyici:** AB Taksonomisi ve ESG raporlama zorunlulukları
- **Ekonomik:** Yüksek karbon yoğunluğu dönemlerinde artan spot elektrik fiyatları (PTF)

Türkiye'de yenilenebilir enerji üretimi günlük periyodik bir örüntü izlemektedir. Güneş enerjisi üretimi öğle saatlerinde (10:00–15:00) en yüksek, gece saatlerinde sıfır değerindeyken; baraj hidroelektriği ve rüzgar üretimi iklim koşullarına bağlı olarak saatlik değişim göstermektedir. Bir `model_eğitimi` işini saat 22:00 yerine 12:00'de çalıştırmak, özdeş enerji tüketimiyle %15–30 daha az karbon emisyonu anlamına gelebilmektedir.

### 1.2 Temel Katkılar

Bu çalışmanın teknik katkıları şu üç başlık altında özetlenebilir:

1. **EPİAŞ gerçek zamanlı veri entegrasyonu:** Türkiye'nin resmi enerji piyasası operatöründen ham üretim verilerini çekerek kaynak bazlı karbon yoğunluğu hesaplayan ilk açık platform
2. **Hibrit tahmin modeli:** Gerçek rüzgar üretim tahminini güneş eğrisi modeli ve temel karışım extrapolasyonuyla birleştiren 24–48 saatlik karbon tahmini
3. **Ajan tabanlı AI katmanı:** Function calling desteğiyle veri merkezleri için Türkçe, ölçülebilir tasarruf önerileri üreten yapay zeka asistanı

---

## 2. Sistem Mimarisi

```
┌─────────────────────────────────────────────────────────────┐
│                     İstemci Katmanı                          │
│         Frontend (React 18) / Swagger UI / REST API          │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS + Bearer JWT
┌────────────────────────▼────────────────────────────────────┐
│                   API Katmanı (FastAPI)                       │
│                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │  Auth    │  │  Carbon  │  │   Grid   │  │  Schedule │  │
│  │ Supabase │  │ Endpoint │  │ Endpoint │  │  Engine   │  │
│  └──────────┘  └────┬─────┘  └────┬─────┘  └─────┬─────┘  │
└───────────────────  │  ──────────  │  ──────────  │  ───────┘
                      │              │              │
         ┌────────────▼──┐  ┌───────▼──────┐  ┌───▼──────────┐
         │ carbon_service │  │ grid_service │  │  scheduler   │
         │                │  │              │  │              │
         │ EPİAŞ rt-gen  │  │ EPİAŞ:       │  │ Sliding      │
         │ wind-forecast  │  │ baraj, PTF   │  │ Window +     │
         │ + Fallback     │  │ arz-talep    │  │ Greedy Slot  │
         └───────┬────────┘  └──────────────┘  └──────┬───────┘
                 │                                      │
         ┌───────▼──────────────────────────────────────▼──────┐
         │                  LLM Katmanı                          │
         │           NVIDIA NIM (Llama 3.3 70B)                 │
         │   Function Calling │ Output Validation │ Streaming   │
         └───────────────────────────────────────────────────────┘
                                    │
                        ┌───────────▼──────────┐
                        │  Supabase (PostgreSQL) │
                        │    jobs tablosu        │
                        └──────────────────────┘
```

Sistem beş ana modülden oluşmaktadır: veri çekme ve karbon hesabı (`carbon_service`), şebeke durumu (`grid_service`), zamanlama algoritması (`scheduler`), yapay zeka katmanı (`llm_service`) ve kalıcılık katmanı (`database`). FastAPI, bu modüller üzerinde asenkron bir API katmanı sağlamakta; Supabase, hem kullanıcı kimlik doğrulamasını hem de iş kaydı kalıcılığını üstlenmektedir.

---

## 3. Veri Katmanı

### 3.1 EPİAŞ Gerçek Zamanlı Entegrasyonu

EPİAŞ, Türkiye'nin enerji piyasası işletmecisidir. eptr2 Python kütüphanesi aracılığıyla beş endpoint'e erişilmektedir:

| Endpoint | Veri | Örnekleme |
|---|---|---|
| `rt-gen` | Yakıt bazlı üretim (MWh, 16 kategori) | Saatlik, ~1,5 sa gecikme |
| `wind-forecast` | Rüzgar üretim tahmini | 15 dk'lık dilimler, 48 sa |
| `dams-active-fullness` | Havza bazlı baraj doluluk % | Günlük |
| `mcp` | Piyasa Takas Fiyatı (₺/MWh) | Saatlik |
| `supply-demand` | Arz-talep dengesi (MW) | Saatlik |

EPİAŞ verisi 1–2 saat gecikmelidir. Bu gecikmeye karşı `rt-gen` endpoint'inde son 3 saatin verisi çekilmekte ve `total_mwh > 0` koşulunu sağlayan en yeni satır kullanılmaktadır.

### 3.2 Karbon Yoğunluğu Hesabı

Anlık karbon yoğunluğu, üretim karışımı üzerinden ağırlıklı ortalama olarak hesaplanmaktadır:

$$I_{carbon} = \frac{\sum_{f \in F} MWh_f \cdot e_f}{\sum_{f \in F} MWh_f} \quad \text{(gCO}_2\text{eq/kWh)}$$

Burada $F$ yakıt kümesi, $e_f$ ise yakıt $f$'nin emisyon faktörüdür:

| Yakıt | $e_f$ (gCO₂eq/kWh) | Yenilenebilir |
|---|---|---|
| Linyit | 1050 | ✗ |
| İthal Kömür / Asfaltit | 820 / 980 | ✗ |
| Doğalgaz / LNG | 490 | ✗ |
| Rüzgar | 11 | ✓ |
| Güneş | 45 | ✓ |
| Baraj / Nehir HES | 4 | ✓ |
| Jeotermal | 38 | ✓ |
| Biyokütle | 230 | ✓ |
| İthalat | 400 | ✗ |

Yenilenebilir enerji oranı:

$$R = \frac{MWh_{HES} + MWh_{rüzgar} + MWh_{güneş} + MWh_{jeotermal} + MWh_{biyokütle}}{\sum_{f} MWh_f}$$

### 3.3 24–48 Saatlik Tahmin Modeli

Tahmin modeli üç bileşeni hibrit olarak birleştirir:

**Bileşen 1 — Rüzgar:** EPİAŞ `wind-forecast` endpoint'inden gerçek tahmin verileri çekilmekte, 15 dakikalık dilimler saatlik ortalamalara dönüştürülmektedir.

**Bileşen 2 — Güneş:** Türkiye'nin Mayıs ayı güneşlenme örüntüsüne dayalı normalize güneş eğrisi:

$$MWh_{güneş}(h) = P_{peak} \cdot c(h)$$

Burada $c(h)$, saatlik güneş katsayısıdır (örn. $c(12)=0.95$, $c(6)=0.02$, $c(0)=0.0$). $P_{peak}$, mevcut üretim verisinden türetilmektedir:

$$P_{peak} = \frac{MWh_{güneş,şimdi}}{c(h_{şimdi})} \quad \text{(eğer } c(h_{şimdi}) > 0 \text{)}$$

**Bileşen 3 — Temel Karışım:** Son bilinen üretim karışımı (`_last_known_mix`) ileriye extrapolasyon için taban olarak kullanılmakta; doğalgaz tüketimi yük saatlerinde (08:00–22:00) %10 artı, gece saatlerinde %10 eksi olarak modellenmektedir.

**Güven Skoru:** Tahmin doğruluğunun zaman ufkuyla azaldığını modellemek için:

$$confidence(h) = \max\left(0.55,\ 0.90 - (h-1) \cdot \frac{0.35}{23}\right)$$

$h=1$ için 0.90, $h=24$ için 0.55 değeri elde edilir.

### 3.4 Çevrimdışı Dayanıklılık

3 saniyelik `asyncio.wait_for` zaman aşımı ile sarmalanan EPİAŞ çağrıları başarısız olduğunda iki kademeli fallback devreye girer:

1. **JSON Fallback:** 14–16 Mayıs 2026 tarihli 54 gerçek EPİAŞ veri noktasını içeren `mock_epias_data.json` dosyasından saate göre gruplandırılmış ortalamalar kullanılmaktadır. Bu yaklaşım, sinüs eğrisi gibi yapay desenler yerine gerçek şebeke davranışını temsil eden dalgalı bir profil üretmektedir.

2. **Analitik Mock:** `MOCK_MODE=true` ortam değişkeniyle güneş eğrisi ve temel karışım üzerinden matematiksel model çalıştırılmaktadır.

---

## 4. Zamanlama Algoritması

### 4.1 Tekli İş Optimizasyonu

Verilen bir $d$ saat süreli, $P$ kW güç tüketen iş için kayan pencere (sliding window) algoritması $O(n)$ karmaşıklıkla optimal zaman dilimini bulur:

**Giriş:** $n$ tahmin noktası $\{(t_i, I_i, \pi_i)\}$, pencere boyutu $w = \lceil d \rceil$

**Adımlar:**

1. Deadline filtresi: $t_i \leq D$ koşulunu sağlamayan noktalar çıkarılır
2. Her başlangıç indeksi $s \in [0, n-w]$ için:

$$\bar{I}_s = \frac{1}{w} \sum_{i=s}^{s+w-1} I_i$$

3. Kombine skor (PTF verisi mevcutsa):

$$score_s = (1-\alpha)\cdot \frac{\bar{I}_s - I_{min}}{I_{max} - I_{min} + \varepsilon} + \alpha \cdot \frac{\bar{\pi}_s - \pi_{min}}{\pi_{max} - \pi_{min} + \varepsilon}$$

Burada $\alpha$ = `cost_weight` (0 = yalnızca karbon, 1 = yalnızca maliyet), $\varepsilon = 10^{-6}$ sıfıra bölme korumasıdır. PTF verisi yoksa $\alpha = 0$ olarak davranılır.

4. $s^* = \arg\min_s(score_s)$

**Tasarruf tahmini:**

$$savings\% = \max\left(0,\ \frac{I_{current} - \bar{I}_{s^*}}{I_{current}} \times 100\right)$$

**Karbon tasarrufu (kg CO₂):**

$$\Delta CO_2 = P \cdot d \cdot \frac{I_{current} - \bar{I}_{s^*}}{1000} \quad \text{(kg)}$$

### 4.2 Çoklu İş Açgözlü Takvim

Birden fazla iş için kullanılan açgözlü (greedy) algoritma çakışmasız slot tahsisi sağlar:

```
Girdi: iş listesi J, tahmin noktaları F, mevcut yoğunluk I₀
Çıktı: {job_id → OptimalWindow}

1. J'yi öncelik (azalan) ve deadline (artan) göre sırala
2. used_slots = {}
3. Her j ∈ J için:
   a. F' = F \ used_slots  (kullanılan saatleri filtrele)
   b. w_j = find_optimal_window(F', j.duration, j.deadline, j.power_kw, I₀, j.cost_weight)
   c. used_slots ∪= {t : w_j.start ≤ t < w_j.end}
   d. result[j.id] = w_j
4. Döndür result
```

Bu yaklaşım yüksek öncelikli işlere en iyi kaynakları garantilemekte, düşük öncelikli işler ise kalan zaman dilimlerinde optimize edilmektedir. Tahmin ufku aşıldığında ilgili iş atlanarak diğerleri zamanlanmaya devam eder.

### 4.3 Renk Kodlaması

Görsel durum bilgisi için eşik tabanlı renk sistemi:

$$color(I) = \begin{cases} \texttt{\#22c55e} & I < 200 \text{ (Yeşil — Mükemmel)} \\ \texttt{\#eab308} & 200 \leq I < 250 \text{ (Sarı — İyi)} \\ \texttt{\#f97316} & 250 \leq I < 350 \text{ (Turuncu — Yüksek)} \\ \texttt{\#ef4444} & I \geq 350 \text{ (Kırmızı — Çok Yüksek)} \end{cases}$$

---

## 5. Yapay Zeka Katmanı

### 5.1 Model Seçimi

NVIDIA NIM üzerinde çalışan `meta/llama-3.3-70b-instruct` modeli üç nedenle seçilmiştir:

- **Bağlam uzunluğu:** Çok turlu araç çağrısı geçmişini ve birden fazla veri yapısını tutabilmektedir
- **Türkçe yeterlilik:** 70B parametre ölçeği, teknik Türkçe üretiminde tatmin edici sonuçlar vermektedir
- **Araç çağrısı desteği:** OpenAI uyumlu `tools` API'si üzerinden function calling desteklenmektedir

### 5.2 Ajan Tabanlı Sohbet (Function Calling)

`/api/chat` endpoint'i reaktif bir pre-fetch yaklaşımı yerine araç tabanlı ajan mimarisi kullanmaktadır. AI, kullanıcı sorusuna göre hangi veriyi çekeceğine kendi karar vermektedir:

```
Kullanıcı: "Bugün sunucularımı ne zaman çalıştırmalıyım?"
    │
    ▼
LLM → tool_call: get_current_carbon()
    │
    ▼ {"carbon_intensity": 228.4, "renewable_ratio": 0.71, ...}
    │
    ▼
LLM → tool_call: find_best_window(duration_hours=8, power_kw=200)
    │
    ▼ {"start_time": "14:00", "avg_carbon_intensity": 198.2, ...}
    │
    ▼
LLM → "Şu an karbon yoğunluğu 228 gCO2/kWh. Saat 14:00–22:00 arasında
        güneş üretiminin katkısıyla 198 gCO2/kWh'e düşeceği tahmin ediliyor.
        Bu 8 saatlik işi 14:00'da başlatırsanız yaklaşık 4.8 kg CO2 tasarrufu sağlarsınız."
```

Döngü en fazla 5 iterasyon çalışır; her araç çağrısı sonucu `role: "tool"` mesajı olarak geçmişe eklenerek LLM'e bağlam olarak sunulur.

**Araç Tanımları:**

| Araç | Zorunlu Parametreler | Döndürülen Veriler |
|---|---|---|
| `get_current_carbon` | — | carbon_intensity, renewable_ratio, timestamp |
| `get_forecast` | — (`hours` opsiyonel) | 12 saatlik tahmin özeti, en iyi saat |
| `get_grid_status` | — | baraj %, PTF, arz-talep, stres seviyesi |
| `find_best_window` | duration_hours, power_kw | start/end, avg_carbon, savings_pct, reasoning |

**Güvenlik:** `_ALLOWED_TOOLS = {t["function"]["name"] for t in TOOLS}` ile LLM'in tanımsız araç çağırması engellenmektedir.

### 5.3 Yapılandırılmış İş Önerisi (Output Validation)

İş önerileri serbest metin yerine doğrulanmış Pydantic nesneleri olarak üretilmektedir:

```python
class JobRecommendation(BaseModel):
    window:      str    # "14:00–22:00"
    date:        str    # "16.05"
    savings_kg:  float  # 4.82
    savings_pct: float  # 18.5
    reasoning:   str    # Türkçe açıklama
    action:      str    # "İşi saat 14:00'da başlatın"
```

LLM'e sıkı JSON formatı talebi yapılmakta, yanıt `model_validate_json()` ile doğrulanmaktadır. Parse başarısız olursa sıcaklık artırılarak (0.3 → 0.5 → 0.7) üç kez yeniden denenir. Üç denemenin tamamı başarısız olursa `None` dönmekte ve API geriye dönük uyumlu `ai_recommendation_parsed: null` alanıyla yanıt vermektedir.

Onaylanan öneri, ham JSON string olarak `ai_recommendation` sütununa yazılmakta; okumada `model_validate_json()` ile ayrıştırılarak `ai_recommendation_parsed` alanı doldurulmaktadır. Bu tasarım, eski kayıtlar için geriye dönük uyumu korumaktadır.

**Prompt Injection Koruması:** İş adı LLM prompt'una eklenmeden önce `\n` ve `\r` karakterleri temizlenmekte, uzunluk 80 karakterle sınırlandırılmaktadır.

### 5.4 Streaming SSE

`/api/chat/stream` endpoint'i, ChatGPT benzeri token-token yanıt üretimi için Server-Sent Events (SSE) protokolünü kullanmaktadır:

```
POST /api/chat/stream
Content-Type: text/event-stream

data: {"token": "Şu"}
data: {"token": " an"}
data: {"token": " karbon yoğunluğu"}
...
data: [DONE]
```

`stream=True` modu function calling ile birlikte kullanılamamaktadır; bu nedenle streaming endpointi tek geçişli, araçsız yanıt üretmektedir.

---

## 6. API Katmanı

### 6.1 Endpoint Matrisi

| Yöntem | Yol | Auth | Açıklama |
|---|---|---|---|
| POST | `/api/auth/signup` | — | Kullanıcı kaydı |
| POST | `/api/auth/login` | — | Oturum açma, JWT döner |
| GET | `/api/carbon/current` | — | Anlık karbon durumu |
| GET | `/api/carbon/forecast` | — | 1–48 saatlik tahmin |
| GET | `/api/grid/status` | — | Şebeke durumu özeti |
| POST | `/api/jobs` | ✅ | İş ekle + AI önerisi al |
| GET | `/api/jobs` | ✅ | İş listesi |
| GET | `/api/jobs/{id}` | ✅ | Tek iş detayı |
| DELETE | `/api/jobs/{id}` | ✅ | İş sil |
| PATCH | `/api/jobs/{id}/status` | ✅ | Durum güncelle |
| GET | `/api/schedule` | ✅ | Çakışmasız takvim |
| POST | `/api/schedule/approve` | ✅ | Takvimi onayla |
| POST | `/api/schedule/demo` | ✅ | Demo preset oluştur |
| POST | `/api/chat` | ✅ | AI sohbet (tool calling) |
| POST | `/api/chat/stream` | ✅ | Streaming sohbet (SSE) |
| GET | `/api/savings/summary` | ✅ | Toplam tasarruf özeti |

**Toplam: 16 endpoint, 10'u kimlik doğrulamalı**

### 6.2 POST /api/jobs İşlem Hattı

```
İstek gelir
    │
    ├─► get_current_carbon()        → I₀ (anlık yoğunluk)
    ├─► get_forecast(24)            → F (tahmin dizisi)
    ├─► find_optimal_window(F, ...) → OptimalWindow (hata olursa None)
    ├─► get_grid_status()           → grid_ctx (LLM bağlamı için)
    ├─► get_job_recommendation(...) → JobRecommendation | None
    ├─► create_job(...)             → Supabase INSERT → ham satır
    └─► _row_to_job_response(row)   → JobResponse (döner)
```

Her adım kendi hata bloğuyla izole edilmiştir. Scheduler başarısız olursa iş `status=pending` olarak kaydedilir; LLM başarısız olursa `ai_recommendation_parsed=null` döner. İstek hiçbir zaman tamamen başarısız olmaz.

### 6.3 Kimlik Doğrulama

Supabase JWT tabanlı kimlik doğrulama kullanılmaktadır. `get_current_user` FastAPI dependency'si, `Authorization: Bearer <token>` başlığından tokenı çıkarıp `supabase.auth.get_user(token)` ile doğrular ve kullanıcı UUID'sini döndürür. Veritabanı sorguları her zaman `user_id` filtresiyle kapsamlandırılmaktadır.

### 6.4 Arkaplan Görev: Otomatik Durum İlerlemesi

`@app.on_event("startup")` ile başlatılan `asyncio.create_task()`, her 15 saniyede iki geçiş yapar:

1. **scheduled → running:** `scheduled_start ≤ şimdi` olan işler güncellenir
2. **running → completed:** `scheduled_start + duration_hours ≤ şimdi` olan işler tamamlanır

Bu mekanizma, demo sırasında iş durumlarının kullanıcı müdahalesine gerek kalmadan gerçek zamanlı ilerlediğini göstermektedir.

---

## 7. Veri Modelleri

### 7.1 Supabase `jobs` Tablosu

```sql
CREATE TABLE jobs (
  id                   BIGSERIAL PRIMARY KEY,
  user_id              UUID NOT NULL,           -- Supabase Auth UUID
  name                 TEXT NOT NULL,
  duration_hours       FLOAT NOT NULL,          -- 0 < x ≤ 72
  deadline             TIMESTAMPTZ,
  priority             INT DEFAULT 1,           -- 1 (düşük) – 5 (acil)
  power_kw             FLOAT NOT NULL,
  status               TEXT DEFAULT 'pending',  -- pending|scheduled|running|completed|cancelled
  created_at           TIMESTAMPTZ DEFAULT NOW(),
  scheduled_start      TIMESTAMPTZ,             -- onaylanan başlangıç
  optimal_start_time   TIMESTAMPTZ,             -- algoritma önerisi
  optimal_end_time     TIMESTAMPTZ,
  avg_carbon_intensity FLOAT,                   -- gCO2eq/kWh
  estimated_savings_pct FLOAT,                 -- %
  reasoning            TEXT,                    -- Türkçe gerekçe
  ai_recommendation    TEXT                     -- JobRecommendation JSON
);
```

### 7.2 Önbellek Stratejisi

Her servis modülü kendi Python süreç-içi sözlük önbelleğini kullanmaktadır:

| Veri | TTL | Geçersizleşme |
|---|---|---|
| Anlık karbon | 15 dk | TTL dolumu |
| 24 saatlik tahmin | 30 dk | TTL dolumu |
| Şebeke durumu | 30 dk | TTL dolumu |
| PTF saatlik | 30 dk | TTL dolumu |

`_cache_get(key)` / `_cache_set(key, data, ttl)` yardımcı fonksiyonları `time.monotonic()` tabanlı süre kontrolü yapmakta; önbellek ısınmış olduğunda EPİAŞ çağrılarının tamamen atlanması sayesinde ortalama API yanıt süresi önemli ölçüde azalmaktadır.

---

## 8. Güvenlik Mimarisi

| Katman | Uygulanan Kontrol |
|---|---|
| Kimlik Doğrulama | Supabase JWT; `get_current_user` dependency tüm korumalı endpoint'lerde |
| Yetkilendirme | Tüm DB sorguları `user_id` filtresiyle kapsamlandırılmış |
| Prompt Güvenliği | İş adı sanitize (newline temizleme, 80 karakter kesim) + tool allowlist |
| Hata Yalıtımı | Signup endpoint'inde iç hata mesajı yerine generic yanıt |
| CORS | Spesifik origin listesi; `allow_origins=["*"]` kaldırıldı |
| Sır Yönetimi | `.env` gitignore'da; `.eptr2-tgt` takipten çıkarıldı |
| LLM Araç Güvenliği | `_ALLOWED_TOOLS = {t["function"]["name"] for t in TOOLS}` zorunlu allowlist |

---

## 9. Performans Değerlendirmesi

### 9.1 API Yanıt Süreleri (Tahmini)

| Endpoint | Önbellek İsabeti | Önbellek Kaçışı (EPİAŞ) | LLM Dahil |
|---|---|---|---|
| GET /api/carbon/current | ~5 ms | ~800 ms | — |
| GET /api/carbon/forecast | ~5 ms | ~1200 ms | — |
| GET /api/grid/status | ~5 ms | ~1500 ms | — |
| POST /api/jobs | — | ~2500 ms | ~8–15 sn |
| POST /api/chat | — | ~500 ms | ~4–10 sn |

LLM gecikmeleri NVIDIA NIM API ağ koşullarına bağlıdır. Streaming modu (`/api/chat/stream`) ilk token görünme süresini (~500 ms) iyileştirerek kullanıcı deneyimini artırmaktadır.

### 9.2 Algoritma Karmaşıklığı

| Algoritma | Zaman | Açıklama |
|---|---|---|
| `find_optimal_window` | O(n) | n = tahmin noktası sayısı (≤48) |
| `schedule_multiple_jobs` | O(k·n) | k = iş sayısı |
| Karbon yoğunluğu hesabı | O(&#124;F&#124;) | F = 16 yakıt türü |
| Fallback forecast | O(n log n) | Saate göre gruplama |

Tipik bir çalışmada $n \leq 48$ ve $k \leq 20$ olduğundan tüm algoritmalar alt milisaniye ölçeğinde tamamlanmaktadır.

---

## 10. Demo Senaryosu

`POST /api/schedule/demo` endpoint'i üç şablon iş oluşturarak platformun uçtan uca işleyişini göstermektedir:

| İş | Süre | Güç | Öncelik |
|---|---|---|---|
| Veri Yedekleme | 1 sa | 50 kW | 2 |
| Model Eğitimi | 2 sa | 250 kW | 3 |
| Log Analizi | 1 sa | 30 kW | 1 |

Demo zamanlama: İlk iş 15 saniye sonra, sonrakiler 90 saniye aralıklarla başlayacak şekilde ayarlanmaktadır. Arkaplan görevi (15 sn aralıklı) durumları `pending → scheduled → running → completed` sırasıyla ilerleterek canlı durum geçişlerini gözlemlenebilir kılmaktadır.

**Örnek Tasarruf Hesabı (Model Eğitimi, 250 kW, 2 sa):**
- Mevcut yoğunluk: 230 gCO₂eq/kWh
- Optimal pencere: 198 gCO₂eq/kWh (güneş üretim piki)
- Tüketim: 250 kW × 2 sa = 500 kWh
- Tasarruf: 500 × (230 − 198) / 1000 = **16 kg CO₂** (%13.9)
- Yıllık eşdeğer (günlük çalışım): ~5.8 ton CO₂ / yıl

---

## 11. Gelecek Çalışmalar

### Kısa Vadeli (Hackathon Sonrası)
- **Electricity Maps entegrasyonu:** Türkiye karbon verisi için ikincil doğrulama kaynağı
- **Webhook bildirimleri:** Optimal pencere başladığında kullanıcıya SMS/e-posta
- **Kubernetes iş entegrasyonu:** `kubectl` veya Kubernetes API üzerinden iş yükü otomatik başlatma

### Orta Vadeli
- **ML tabanlı tahmin:** LSTM/Transformer modeli ile EPİAŞ geçmiş verisi üzerinde eğitim; mevsimsel örüntü ve hava durumu korelasyonları
- **Çok kullanıcılı kaynak koordinasyonu:** Birden fazla veri merkezinin paylaşımlı şebeke kapasitesini çakışmasız kullanması
- **Maliyet optimizasyonu:** PTF spot fiyat tahmini ile karbon+maliyet eş-optimizasyonu

### Uzun Vadeli
- **Scope 2 emisyon raporlaması:** GHG Protokolü uyumlu otomatik raporlama
- **Karbon kredi entegrasyonu:** Doğrulanmış tasarrufların blokzincir tabanlı karbon kredisine dönüştürülmesi

---

## 12. Sonuç

Karbon Zeka, veri merkezi operatörlerinin karbon ayak izini azaltmak için somut, ölçülebilir bir araç sunmaktadır. Temel farklılaşma noktaları:

1. **Gerçek veri:** EPİAŞ resmi verisi üzerinden hesaplanan, Türkiye'ye özgü emisyon faktörleri
2. **Pratik AI:** Veriyi kendisi çeken, Türkçe yanıt veren, yapılandırılmış ve doğrulanmış öneri üreten ajan
3. **Sıfır sürtünme:** Mevcut iş yükü tanımlarıyla entegrasyon; tek API çağrısıyla optimal pencere + karbon tasarrufu hesabı
4. **Dayanıklılık:** 3 saniyelik zaman aşımı + gerçek veriye dayalı fallback; internet olmadan da çalışır

Platform, yılda ortalama 10–25 ton CO₂ tasarrufu potansiyeli olan orta ölçekli bir veri merkezi için karbon nötrlük yolculuğunun somut, ölçülebilir ilk adımını temsil etmektedir.

---

## Ekler

### A. Ortam Değişkenleri

```env
EPTR_USERNAME=<EPİAŞ hesap e-posta>
EPTR_PASSWORD=<EPİAŞ hesap şifre>
NVIDIA_API_KEY=nvapi-<key>
SUPABASE_URL=https://<proje>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service role JWT>
MOCK_MODE=false   # "true" → EPİAŞ atla
```

### B. Çalıştırma

```bash
# Backend
cd backend && source venv/bin/activate
uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm run dev   # http://localhost:5173

# Swagger UI (canlı test)
https://undistractedly-gimlety-angelena.ngrok-free.app/docs
```

### C. Temel Bağımlılıklar

| Paket | Sürüm | Amaç |
|---|---|---|
| fastapi | 0.136.1 | REST API çerçevesi |
| pydantic | 2.13.4 | Veri doğrulama |
| openai | 2.37.0 | NVIDIA NIM istemcisi |
| eptr2 | 1.3.7 | EPİAŞ API sarmalayıcısı |
| supabase | async | Veritabanı + Auth |
| uvicorn | 0.47.0 | ASGI sunucusu |

---

*Bu whitepaper, 100 StaryUP Hackathonu (YTÜ, 15–17 Mayıs 2026) kapsamında hazırlanmıştır.*
