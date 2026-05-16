# EPİAŞ Şeffaflık Platformu — API Referansı

Kaynak: https://seffaflik.epias.com.tr  
Kütüphane: `eptr2==1.3.7`

---

## Kimlik Doğrulama (TGT)

EPİAŞ CAS tabanlı TGT (Ticket Granting Ticket) sistemi kullanır.  
**eptr2 bunu otomatik yönetir** — TGT alır, 2 saat dolmadan yeniler.

```bash
# Manuel TGT alma (referans)
curl -X POST https://giris.epias.com.tr/cas/v1/tickets \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept: text/plain" \
  -d 'username=EMAIL&password=SIFRE'
# → HTTP 201, yanıt: TGT-xxxx...
```

**`.env` değişkenleri** (eptr2'nin beklediği isimler):
```
EPTR_USERNAME=epias@email.com
EPTR_PASSWORD=sifre
```

> `EPIAS_USERNAME` / `EPIAS_PASSWORD` eptr2 tarafından **okunmaz**. Her iki seti de `.env`'de tut.

---

## eptr2 Kullanımı

```python
from eptr2 import EPTR2

client = EPTR2(postprocess=False)  # EPTR_USERNAME/PASSWORD .env'den okunur
data = client.call("rt-gen", postprocess=False, start_date=start, end_date=end)
items = data["body"]["items"]  # list[dict]
```

Tarih formatı (tüm endpoint'ler): `"2026-05-16T14:00:00+03:00"` (ISO-8601, UTC+3)

---

## Kullandığımız Endpoint'ler

### `rt-gen` — Saatlik Gerçek Zamanlı Üretim
- **Zorunlu:** `start_date`, `end_date`
- **EPİAŞ 1-2 saat gecikmeli** → son 3 saati çek, `total > 0` olan en yeni satırı al

**Yanıt alanları ve emisyon faktörleri (gCO2eq/kWh):**

| Alan | Yakıt | gCO2eq/kWh |
|---|---|---|
| `naturalGas` | Doğal gaz | 490 |
| `lignite` | Linyit | 1050 |
| `importCoal` | İthal taşkömürü | 820 |
| `blackCoal` | Taşkömürü | 820 |
| `asphaltiteCoal` | Asfaltit | 980 |
| `fueloil` | Fuel oil | 650 |
| `naphta` | Nafta | 650 |
| `lng` | LNG | 490 |
| `dammedHydro` | Barajlı hidro | 4 |
| `river` | Nehir tipi hidro | 4 |
| `wind` | Rüzgar | 11 |
| `sun` | Güneş | 45 |
| `geothermal` | Jeotermal | 38 |
| `biomass` | Biyokütle | 230 |
| `wasteheat` | Atık ısı | 200 |
| `importExport` | İthalat (pozitif) | 400 |
| `total` | Toplam MWh | — |

**Yenilenebilir kaynaklar:** `dammedHydro`, `river`, `wind`, `sun`, `geothermal`, `biomass`

**Örnek kayıt (16 Mayıs 2026, 00:00):**
```json
{
  "date": "2026-05-16T00:00:00+03:00",
  "hour": "00:00",
  "total": 33835.16,
  "naturalGas": 6210.73,
  "dammedHydro": 13034.45,
  "lignite": 3113.98,
  "river": 5643.41,
  "importCoal": 1346.15,
  "wind": 2280.01,
  "sun": 0.01,
  "fueloil": 0.96,
  "geothermal": 1092.05,
  "asphaltiteCoal": 181.05,
  "blackCoal": 585.11,
  "biomass": 538.39,
  "naphta": 0,
  "lng": 0,
  "importExport": -267.53,
  "wasteheat": 76.39
}
```

---

### `ren-rt-gen` — Yenilenebilir Gerçek Zamanlı Üretim
- **Zorunlu:** `start_date`, `end_date`
- Alanlar Türkçe: `ruzgar`, `jeotermal`, `rezervuarli`, `kanalTipi`, `nehirTipi`, `gunes`, `biyokutle`, `toplam`
- `rt-gen` zaten tüm kaynakları içerdiğinden karbon hesabı için `rt-gen` yeterli

---

### `wind-forecast` — 24 Saatlik Rüzgar Tahmini
- **Zorunlu:** `start_date`, `end_date`
- ~189 nokta döner (çeyreklik, ~48 saatlik kapsam)

**Örnek kayıt:**
```json
{
  "date": "2026-05-16T14:00:00+03:00",
  "time": "14:00",
  "quarter1": 3820.0,
  "quarter2": 3850.0,
  "quarter3": 3900.0,
  "quarter4": 3870.0,
  "generation": 3820.0,
  "forecast": 3860.0
}
```

Alan önceliği: `value` → `forecast` → `generation` → 0.0  
Saatlik ortalama için: aynı saate düşen tüm noktaların ortalaması alınır.

---

### `rt-cons` — Gerçek Zamanlı Tüketim
- **Zorunlu:** `start_date`, `end_date`
- Alanlar: `date`, `time`, `consumption` (MWh)

---

## Sayfalama (gerekirse)
```json
{
  "page": {
    "number": 1,
    "size": 20,
    "sort": {"direction": "ASC", "field": "date"},
    "total": 0
  }
}
```

---

## Gözlemlenen Gerçek Değerler (16 Mayıs 2026 gece)

| Metrik | Değer |
|---|---|
| Karbon yoğunluğu | ~240 gCO2eq/kWh |
| Yenilenebilir oran | ~%68 |
| Toplam üretim | ~30-34 GWh/saat |
| Dominant kaynak | Barajlı hidro (~13 GWh) |
