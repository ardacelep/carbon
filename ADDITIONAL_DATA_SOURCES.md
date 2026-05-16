# Ek Veri Kaynakları — Analiz ve Öneriler

> Bu doküman 3 API dokümantasyonunu (EPİAŞ Elektrik, Doğalgaz, Raporlama) ve  
> Carbon Aware SDK / Electricity Maps'i inceleyerek çıkarılan bulgulardır.

---

## Özet: Neler Kullanılabilir?

| Kaynak | Türkiye Desteği | Ücretsiz mi? | Değer | Öncelik |
|---|---|---|---|---|
| EPİAŞ — ek endpoint'ler | ✅ Türkiye verisi | ✅ Hesap yeterli | Yüksek | 🔴 Hemen |
| Electricity Maps | ✅ TR — TIER_A | ⚠️ Startup başvurusu | Çok Yüksek | 🟡 Başvur |
| Carbon Aware SDK | ❌ TR listede yok | ✅ Açık kaynak | Düşük | ⚪ Gerek yok |
| EPİAŞ Doğalgaz | ✅ Türkiye verisi | ✅ Hesap yeterli | Orta | 🟡 İkinci aşama |
| EPİAŞ Raporlama | ✅ Türkiye verisi | ✅ Hesap yeterli | Orta | 🟡 İkinci aşama |

---

## 1. EPİAŞ — Kullanmadığımız Endpoint'ler

Mevcut hesapla, hiç ek kurulum gerekmeden çekilebilir.

### 1.1 Baraj Doluluk Oranları (`dams-active-fullness`)

**Neden önemli:** Barajlı hidro Türkiye üretiminin %38'i. Doluluk düşükse gelecek haftalarda hidro üretimi azalır → karbon yoğunluğu artar. Öngörü için kritik.

```python
client.call("dams-active-fullness", postprocess=False)
# → Havza bazında doluluk yüzdesi
```

**Görselleştirme fikirleri:**
- Türkiye haritası üzerinde havza bazlı doluluk (renk kodu)
- "Baraj dolulukları düşüyor — önümüzdeki haftalarda karbon yoğunluğu artabilir" uyarı kartı
- Zaman serisi: doluluk % vs. karbon yoğunluğu korelasyon grafiği

---

### 1.2 Piyasa Takas Fiyatı (`mcp` / `smp`)

**Neden önemli:** PTF (Piyasa Takas Fiyatı) = elektrik spot fiyatı. Karbon yoğunluğu ile yüksek korelasyon — fossil kaynaklı üretim pahalıya mal olur. Veri merkezi operatörleri için hem karbon hem maliyet optimizasyonu yapılabilir.

```python
client.call("mcp", postprocess=False)   # Piyasa Takas Fiyatı (₺/MWh)
client.call("smp", postprocess=False)   # Sistem Marjinal Fiyatı (₺/MWh)
```

**Görselleştirme fikirleri:**
- İkili grafik: karbon yoğunluğu (gCO2/kWh) + PTF (₺/MWh) aynı zaman ekseninde
- "En ucuz + en temiz pencere" vurgulayıcı → hem para hem çevre tasarrufu
- Örnek metrik: "Bu pencerede çalıştırarak 18% daha az karbon VE ₺240 daha az ödedik"

---

### 1.3 Arz-Talep Dengesi (`supply-demand`)

**Neden önemli:** Talep > arz olduğunda pahalı/kirli peaker santraller devreye girer. Bu veri, yüksek karbon dönemlerini önceden haber verir.

```python
client.call("supply-demand", postprocess=False)
```

**Görselleştirme fikirleri:**
- Arz/talep fark çizgisi — negatif bölge = stres, karbon artışı sinyali
- "Şebeke şu an dengeli/stres altında" badge'i

---

### 1.4 Planlı Bakım Kesintileri (`planned-outages`)

**Neden önemli:** Büyük bir santral bakıma girdiğinde arzda boşluk oluşur, başka (genellikle daha kirli) kapasite devreye girer.

```python
client.call("planned-outages", postprocess=False, start_date=..., end_date=...)
```

**Görselleştirme fikirleri:**
- Önümüzdeki 7 gün planlı kapasite kayıpları → "Bu hafta büyük bakım var, karbon artabilir" uyarısı
- Takvim üzerinde kesinti dönemleri

---

### 1.5 Talep Tahmini (`load-plan`)

**Neden önemli:** EPİAŞ'ın kendi yük tahmin planı. Bizim karbon tahminimizle birleştirince daha güçlü bir model elde edilir.

```python
client.call("load-plan", postprocess=False, start_date=..., end_date=...)
```

---

### 1.6 Tüketim Dağılımı (`consumption-breakdown`)

**Neden önemli:** Sanayi vs. konut tüketimini gösterir. Yoğun sanayi dönemlerinde karbon yoğunluğu artar.

---

## 2. Electricity Maps — En Değerli Keşif

**Türkiye `TR` zone kodu ile ticari olarak mevcut (TIER_A).**

Bu, EPİAŞ'tan bağımsız, uluslararası standartta bir karbon yoğunluğu kaynağı. Aşağıdaki verileri sağlıyor:

### Sunduğu Endpoint'ler

| Endpoint | Veri | Değeri |
|---|---|---|
| `/carbon-intensity/latest` | Anlık gCO2eq/kWh | EPİAŞ'a bağımsız doğrulama |
| `/carbon-intensity/history` | Geçmiş 24 saat | Tarihsel trend |
| `/carbon-intensity/forecast` | 24–48 sa tahmin | **Bizim tahminimizin alternatifi** |
| `/power-breakdown/latest` | Kaynak bazlı üretim (MW) | rt-gen ile karşılaştırma |
| `/renewable-percentage/latest` | Anlık yenilenebilir % | Çift kaynak doğrulama |
| `/carbon-free-percentage` | Nükleer dahil temiz enerji % | Daha kapsamlı metrik |

### Nasıl Başvurulur?

Electricity Maps'in akademik/startup programı var:
- **Academic:** Ücretsiz, araştırma projeleri için
- **Startup:** Düşük maliyetli, erken aşama için
- Hackathon için: `app.electricitymaps.com` → "Get Access" → akademik/startup seç

### Projeye Katkısı

```
EPİAŞ rt-gen    →  bizim hesabımız: 240.9 gCO2/kWh
Electricity Maps →  uluslararası kaynak: ~243 gCO2/kWh  ← doğrulama
```

İki kaynağı karşılaştıran küçük bir widget: **"İki bağımsız kaynak uyuşuyor → verimize güvenin"**

Ayrıca tahmin karşılaştırması:
```
Bizim tahminimiz (rüzgar + güneş eğrisi): saat 13 → 195 gCO2/kWh
Electricity Maps forecast:                 saat 13 → 198 gCO2/kWh
```

---

## 3. Carbon Aware SDK — Neden Gerek Yok?

Carbon Aware SDK bir **wrapper** — asıl veriyi WattTime veya Electricity Maps'ten alıyor. Biz EPİAŞ ile daha doğrudan ve daha güncel Türkiye verisine erişiyoruz.

SDK'nın tek değerli konsepti `/emissions/bylocations/best` endpoint'i:
> "Birden fazla veri merkezi konumu arasında şu an en düşük karbonlu olanı bul"

Bu fikri kendi sistemimize uygulayabiliriz: kullanıcı birden fazla workload lokasyonu girebilsin, biz en temiz olanı önerelim (Türkiye + Almanya + İrlanda gibi).

---

## 4. EPİAŞ Doğalgaz — Ne Zaman Yararlı?

### Spot Gaz Fiyatı (`ng-spot-prices`)

**Bağlantı:** Doğal gaz fiyatı arttığında → gaz santralleri daha pahalı → gaz üretimi azalır veya maliyet yükselir → elektrik fiyatına yansır → karbon yoğunluğuyla korelasyon.

```python
client.call("ng-spot-prices", postprocess=False)
# → Günlük SGP spot fiyatı (TL/1000 Sm³)
```

**Görselleştirme:** Gaz fiyatı vs. karbon yoğunluğu korelasyon scatter plot

### Sistem Yönü (`ng-system-direction`)

Gaz sistemi arz fazlası mı yoksa açık mı? Açık = pahalı gaz = yüksek elektrik maliyeti sinyali.

---

## 5. Raporlama API — Aylık Trend için Değerli

### Aylık Ortalama PTF

```
GET /reporting-service → AOF (Sistem Ortalama Fiyatı) — aylık
```

**Görselleştirme:** Son 12 ay elektrik fiyatı + karbon yoğunluğu trend grafiği — "Bu yılın en temiz ayı Mayıs'tı" gibi içgörüler

---

## 6. Öneri: Genişletilmiş Dashboard Fikirleri

Tüm bu verilerle yapılabilecekler:

### A. "Şebeke Sağlığı" Paneli
```
┌─────────────────────────────────────────────────────────┐
│  ŞEBEKE DURUMU — 16 Mayıs 03:00                        │
│                                                         │
│  Karbon Yoğunluğu: 240 gCO2/kWh  ● İyi               │
│  Yenilenebilir:    %67.9                               │
│  Arz-Talep:        Dengeli (+340 MW fazla)             │
│  Baraj Dolulukları: %72 ↓ (geçen hafta %75)           │
│  PTF:              1.240 ₺/MWh                         │
│                                                         │
│  ⚠ Önümüzdeki 3 günde büyük bakım kesintisi yok        │
└─────────────────────────────────────────────────────────┘
```

### B. "Hem Ucuz Hem Temiz" Pencere Skoru
Karbon ve fiyatı birleştiren kompozit skor:
```
skor = 0.6 × (1 - karbon_normalize) + 0.4 × (1 - fiyat_normalize)
```
Kullanıcı ağırlıkları ayarlayabilsin: "Benim için karbon daha önemli / maliyet daha önemli"

### C. Hidro Kapasitesi Uyarısı
```
Baraj dolulukları son 2 haftada %5 düştü.
Eğer bu trend devam ederse, önümüzdeki ay
karbon yoğunluğu ortalama +30 gCO2/kWh artabilir.
```

### D. Karbon Yoğunluğu Karşılaştırma Haritası
Türkiye'yi Avrupa ortalamasıyla karşılaştır (Electricity Maps verisiyle):
```
Türkiye (şu an): 240 gCO2/kWh
Almanya:         180 gCO2/kWh
Fransa:           60 gCO2/kWh  ← nükleer ağırlıklı
AB Ortalaması:   210 gCO2/kWh
```

---

## 7. Hemen Yapılabilecekler (Bu Hafta Sonu)

Ek API key gerekmeden, sadece mevcut EPİAŞ hesabıyla:

1. **`dams-active-fullness`** → Baraj doluluk widget'ı ekle
2. **`mcp`** → PTF fiyatını forecast grafiğinde ikinci eksen olarak göster
3. **`supply-demand`** → "Şebeke şu an dengeli" badge'i
4. **`planned-outages`** → Önümüzdeki 7 gün uyarı kartı

Electricity Maps ücretsiz erişim alınırsa eklenecekler:

5. Bağımsız karbon doğrulama widget'ı
6. 24 sa gelişmiş karbon tahmini (Electricity Maps'inki vs. bizimki)
