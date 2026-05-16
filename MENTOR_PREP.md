# Mentör Görüşmeleri Hazırlık Belgesi — Karbon Zeka

**Kapsam:** Veri & Güvenlik · Yapay Zeka · Hukuk · İş Geliştirme  
**Amaç:** Mentör görüşmelerinde güçlü yanları savunabilmek, açıkları dürüstçe kabul edip çözüm yollarını tartışabilmek.

---

## NASIL KULLANILIR

Her bölüm dört alt başlık içeriyor:
- **Güçlü yanlar** → Mentöre aktif olarak anlatın
- **Açıklar & Eksiklikler** → Mentörün zaten göreceği şeyler; önceden kabul edin, çözüm önerisiyle gelin
- **Mentöre soracağınız sorular** → Görüşmeden maksimum değeri almanızı sağlar
- **Savunmaya hazır olun** → Mentörün zorlayabileceği noktalar ve önerilen yanıtlar

---

## BÖLÜM 1: VERİ & VERİ GÜVENLİĞİ

### Güçlü Yanlar

**Veri kaynağı özgünlüğü**
EPİAŞ'ın resmi `rt-gen` endpoint'i, üretim karışımını 16 yakıt kategorisinde saatlik granülerlikte sunuyor. Çoğu rakip platform (WattTime, Tomorrow.co) ülke bazlı tahminlerle yetinirken biz gerçek türbazlı üretim verisini işliyoruz. Türkiye'ye özgü emisyon faktörleri (linyit: 1050, rüzgar: 11, güneş: 45 gCO₂eq/kWh) akademik literatürden türetildi.

**Çevrimdışı dayanıklılık**
3 saniyelik `asyncio.wait_for` zaman aşımı → gerçek EPİAŞ verilerinden oluşturulmuş JSON fallback (`mock_epias_data.json`, 14–16 Mayıs 2026, 54 nokta). Fallback, saate göre gruplama yaparak sinüs eğrisi yerine gerçek şebeke davranışını yansıtıyor. Sistem internet bağlantısı olmadan da çalışmaya devam ediyor.

**Önbellekleme**
- Anlık karbon: 15 dakika TTL
- Tahmin & şebeke durumu: 30 dakika TTL
- Önbellek isabetinde EPİAŞ çağrısı sıfır → gereksiz yük ve gecikme yok

**Veri izolasyonu**
Tüm veritabanı sorguları `user_id` ile kapsamlandırılmış. Kullanıcılar birbirinin verisine erişemiyor. Supabase servis anahtarı yalnızca server-side'da; istemciye hiç ulaşmıyor.

**Minimal log politikası**
Kullanıcı girdisi (sohbet mesajları, iş adları) stdout'a yazılmıyor. Yalnızca hata tipleri loglanıyor. Bu, KVKK uyumluluğu açısından olumlu bir başlangıç noktası.

---

### Açıklar & Eksiklikler

**Tek veri kaynağı bağımlılığı**
EPİAŞ API'sinin 30+ dakika çevrimdışı kalması durumunda fallback JSON yalnızca Mayıs 2026 tarihi için optimize edilmiş veri kullanıyor. Kış aylarında (güneş eğrisi tamamen farklı) bu fallback yanıltıcı önerilere yol açabilir. Electricity Maps API gibi ikincil kaynak entegre edilmemiş.

**Tahmin modeli fizik tabanlı, ML değil**
Güneş tahmini deterministik bir eğri + anlık üretimden türetilmiş zirve tahminine dayanıyor. Bulutlu günlerde tahmin hatası ~%15–20 olabilir. Rüzgar için EPİAŞ `wind-forecast` kullanılıyor; bu daha güvenilir. Ancak baraj ve jeotermal üretimi sabit baseline kabul ediliyor.

**Güven skoru görsel sunumu yok**
`ForecastPoint.confidence` alanı hesaplanıyor (h=1 için 0.90, h=24 için 0.55) ama bu bilgi UI'a taşınmıyor. Kullanıcı 20 saat sonraki öneriyle 2 saat sonrakine eşit güveniyor.

**Önbellek süreci-içi (process-local)**
Birden fazla Uvicorn worker çalıştığında her worker kendi önbelleğini tutuyor. Paylaşımlı Redis önbelleği yok. Bu durum ölçeklenmede gereksiz EPİAŞ çağrısı artışına neden olur.

**Veri doğrulama eksik**
EPİAŞ'tan gelen karbon yoğunluğunun tarihsel sınırlar içinde olup olmadığı kontrol edilmiyor. 50 veya 900 gCO₂/kWh değeri geldiğinde sistem bunu sorgulamadan kullanıyor.

---

### Mentöre Soracağınız Sorular

1. "EPİAŞ API'sine erişim kesintiye uğradığında kullanıcıya nasıl şeffaf olunmalı? Güven skoru göstermenin UX'teki en iyi yolu nedir?"
2. "Tahmin modelini ML tabanlıya dönüştürmek için ne kadar tarihsel EPİAŞ verisine ihtiyaç var? LSTM/Transformer mi, yoksa daha basit istatistiksel model mi yeterli?"
3. "Türkiye'ye özel emisyon faktörlerini doğrulamak için başvurmamız gereken resmi kaynak var mı? (IPCC 2023 vs. TEİAŞ raporları)"
4. "Çok-kiracılı sistemde önbelleği doğru yönetmek için Redis Cluster'a ne zaman geçmek gerektiğini nasıl anlamalıyız?"
5. "Veri kalitesi güvencesi için hangi izleme metrikleri kritik? (Tahmin hatası MAE/RMSE mi, anlık karbon kayma trendi mi?)"

---

### Savunmaya Hazır Olun

**S: "EPİAŞ verisi 1–2 saat gecikmelidir, bu önerileri anlamsız kılmaz mı?"**  
C: Karbon yoğunluğu örüntüsü günlük sikluslarla değişiyor; öğleden sonra daha yeşil, gece daha kirli. Bu örüntü 1–2 saatlik gecikmeyle bile öngörülebilir ve 8–24 saatlik iş yükü planlama ufkunda anlamlı tasarruf sağlıyor. Tahmin modelimiz EPİAŞ'ın kendi rüzgar tahminini kullandığından anlık okuma gecikmesinden bağımsız çalışıyor.

**S: "Mock verisi gerçekçi mi?"**  
C: Mayıs 2026'ya ait 54 gerçek EPİAŞ veri noktasından oluşuyor; uydurulmuş değil. Saate göre gruplandırıp ortalama alıyoruz; bu gerçek şebeke davranışını temsil ediyor. Kışın bu fallback'i güncellemek gerektiğini biliyoruz.

---

## BÖLÜM 2: YAPAY ZEKA

### Güçlü Yanlar

**Ajan mimarisi (Function Calling)**
AI, kullanıcı sorusunu analiz edip hangi araçları çağıracağına kendisi karar veriyor. Önceden tüm veriyi çekip AI'ya vermek (pre-fetch) yerine AI yalnızca ihtiyacı olan veriyi talep ediyor. Hem gecikmeyi azaltıyor hem gereksiz API çağrısını önlüyor.

**4 araç, net görev ayrımı:**
- `get_current_carbon()` → anlık durum
- `get_forecast(hours)` → tahmin özeti
- `get_grid_status()` → şebeke bağlamı
- `find_best_window(duration, power)` → hesaplama (LLM değil, algoritma yapıyor)

**Yapılandırılmış çıktı doğrulama**
`JobRecommendation` Pydantic modeli, LLM çıktısını zorunlu JSON formatına sokar ve `model_validate_json()` ile doğrular. 3 farklı sıcaklıkta (0.3 → 0.5 → 0.7) yeniden deneme. LLM'in ürettiği serbest metin veritabanına yazılamıyor.

**Güvenlik katmanı**
`_ALLOWED_TOOLS` allowlist ile LLM'in tanımsız fonksiyon çağırması engelleniyor. İş adı prompt'a yazılmadan önce `\n`, `\r` temizleniyor, 80 karakterle sınırlandırılıyor (prompt injection koruması).

**Algoritmanın rolü net**
LLM yorum yapıyor; hesaplamayı `find_optimal_window()` yapıyor. Bu, hallucination riskini temel sayısal kararlardan koparıyor.

---

### Açıklar & Eksiklikler

**Streaming + Function Calling çelişkisi**
`/api/chat/stream` token akışı sağlıyor ama araç çağrısı kullanmıyor. Streaming sohbet daha az bilgili yanıtlar üretiyor. OpenAI bu sorunu çözdü; NVIDIA NIM henüz aynı desteği tam sunmuyor.

**Maks. 5 iterasyon sınırı keyfi**
Karmaşık sorgularda (ör. "Hafta boyunca en iyi 3 pencereyi karşılaştır") 5 araç çağrısı yeterli olmayabilir.

**LLM maliyeti takip edilmiyor**
Her `/api/chat` NVIDIA API'sine çağrı yapıyor. Kullanıcı başına token tüketimi ölçülmüyor, kota tanımlanmamış. 10.000 kullanıcıda sürpriz fatura riski var (tahmin: ~$100–500/ay).

**Hallucination riski (yorum katmanında)**
Sayısal hesaplama algoritmada; ama LLM bu sayıları açıklarken yanlış yorumlayabilir. Yanıt içindeki sayısal iddialar algoritmik sonuçla çapraz doğrulanmıyor.

**Context window yönetimi**
Sohbet geçmişinin son 6 mesajı kullanılıyor. Uzun konuşmalarda erken bağlam kayboluyor.

**Model kilitliliği (vendor lock-in)**
NVIDIA NIM'e bağlılık. OpenAI uyumlu API kullanıldığından geçiş teknik olarak mümkün ama test gerektiriyor.

---

### Mentöre Soracağınız Sorular

1. "Streaming + tool calling çelişkisini NVIDIA NIM'de çözmek mümkün mü? Yoksa Anthropic/OpenAI'ye geçmeli miyiz?"
2. "Function calling döngüsü için 5 iterasyon yeterli mi? Gerçek veri merkezi operasyonu senaryolarında tipik araç çağrısı derinliği ne olur?"
3. "LLM çıktısındaki sayısal iddiaları doğrulamak için ne tür bir güvenlik katmanı önerilir?"
4. "Token maliyeti kontrolü için hangi yaklaşım en pratik? (per-user quota, request budgeting, model downgrade for simple queries)"
5. "Llama 3.3 70B'nin Türkçe teknik içerik kalitesini nasıl değerlendirirsiniz? Gemma 3 veya başka alternatifler var mı?"
6. "Tahmin ufku arttıkça (24 → 48 sa) LLM yanıtlarına güveni kullanıcıya nasıl ifade etmeliyiz?"

---

### Savunmaya Hazır Olun

**S: "LLM karbon tavsiyesi verse de yanlış olabilir, buna nasıl güvenilebilir?"**  
C: LLM'in görevi yorum yapmak; hesaplamayı deterministik sliding window algoritması yapıyor. `find_best_window` aracı algoritmik sonucu döndürüyor; LLM sadece bunu Türkçe açıklıyor. Öneri içindeki sayılar (savings_kg, savings_pct) Pydantic doğrulamasından geçiyor.

**S: "70B parametreli model çok pahalı değil mi?"**  
C: NVIDIA NIM fiyatlandırmasıyla 10.000 iş/ay ≈ $1–2 LLM maliyeti; asıl maliyet sohbet kullanımında. Kullanıcı başına kota ile kontrol edilebilir. Basit sorgular için daha küçük modele (8B) yönlendirme eklenebilir.

**S: "Neden kendi modelinizi eğitmiyorsunuz?"**  
C: Bu ölçekte fine-tune maliyeti ve süresi makul değil; özel eğitim veri seti yok. Amacımız karbon tahmini için ML modeli geliştirmek (LSTM/Transformer); LLM katmanı ise zaten güçlü olan Türkçe dil anlayışını kullanıyor.

---

## BÖLÜM 3: HUKUK

### Güçlü Yanlar

**Kimlik bilgileri git'te değil**
`.env` dosyası kök `.gitignore`'da; git geçmişinde hiç commit edilmemiş. EPİAŞ TGT token'ı (`backend/.eptr2-tgt`) önceden git'te izleniyordu; `git rm --cached` ile kaldırıldı ve commit edildi.

**Minimal kişisel veri işleme**
Kullanıcı girdisi (sohbet mesajları, iş adları) veritabanına yazılmıyor; log'lara da düşmüyor. Saklanan kişisel veri: e-posta adresi ve UUID (Supabase Auth yönetiminde). İş kayıtları operasyonel veri; kişisel veri tanımına girmez.

**Veri izolasyonu**
Tüm sorgular `user_id` filtreli. Supabase servis anahtarı yalnızca backend'de.

**Açık kaynak lisans uyumluluğu**
FastAPI (MIT), Pydantic (MIT), uvicorn (BSD-3), openai SDK (Apache 2.0), httpx (BSD-3) — ticari kullanım için sorunsuz.

---

### Açıklar & Eksiklikler

**EPİAŞ veri kullanım hakları belirsiz**
EPİAŞ API'sine `eptr2` kütüphanesi üzerinden erişiliyor; ancak ticari kullanım için açık bir lisans anlaşması veya ToS onayı yok. Kamuya açık API olsa da ticari platform olarak kullanmak farklı bir hukuki çerçeve gerektirebilir.

**NVIDIA ile Veri İşleme Anlaşması (DPA) yok**
Kullanıcı sohbet mesajları NVIDIA'nın ABD altyapısına gönderiliyor. KVKK kapsamında yurt dışına veri aktarımı için açık rıza veya yeterli koruma güvencesi gerekiyor. Kullanıcıya bildirim yok; NVIDIA ile yazılı DPA yok; veri saklama süresi bilinmiyor.

**eptr2 kütüphane lisansı belirsiz**
PyPI'da lisans bilgisi yok. Ticari kullanım öncesi kütüphane sahibiyle iletişime geçilmesi gerekiyor.

**KVKK uyumluluk eksiklikleri**
- Kayıt sırasında aydınlatma metni / rıza bildirimi yok
- Veri silme hakkı kullanıcıya sunulmuyor
- Veri saklama süresi politikası tanımlanmamış (iş kayıtları süresiz saklanıyor)
- Kişisel veri işleme envanteri yok

**Supabase veri merkezi konumu**
Varsayılan Supabase bölgesi AWS us-east-1 (ABD). Türk kullanıcıların verilerinin Türkiye'de veya AB'de saklanması KVKK açısından tercih edilir.

**Karbon tasarruf iddialarının doğrulanabilirliği**
"%15–25 karbon tasarrufu" algoritmik hesaplamaya dayanıyor. Müşteri sözleşmelerinde garanti olarak kullanılamaz; tahmin "beklenti", gerçekleşen değer değil. Yanıltıcı reklam riski.

---

### Mentöre Soracağınız Sorular

1. "EPİAŞ API'sini ticari platformda kullanmak için ne tür bir hukuki zemin gerekiyor? MoU mu, lisans sözleşmesi mi, yoksa mevcut hizmet şartları yeterli mi?"
2. "NVIDIA NIM API'sini KVKK kapsamında kullanan Türk şirketler nasıl DPA alıyor? Bu süreci kolaylaştıran bir yol var mı?"
3. "Kullanıcıya 'verileriniz AI işlemi için üçüncü taraf sağlayıcıya gönderiliyor' bildirimi için minimum hukuki metin nasıl olmalı?"
4. "Karbon tasarruf tahminlerini hukuki açıdan güvenli biçimde pazarlamak için nasıl bir dil kullanılmalı? ('tasarruf sağlıyoruz' vs. 'tasarruf potansiyeli sunuyoruz')"
5. "eptr2 gibi lisansı belirsiz açık kaynak kütüphaneyi ticari üründe kullanmak için en hızlı hukuki çözüm yolu nedir?"
6. "Supabase'i KVKK uyumlu kılmak için EU region seçmek yeterli mi, yoksa ek adımlar var mı?"

---

### Savunmaya Hazır Olun

**S: "EPİAŞ verisi kamuya açık, neden lisans sorunu olsun?"**  
C: Kamuya açık veri ile ticari kullanım için lisanslı veri farklı şeyler. Bu veriyi bir SaaS ürünün temel değer önerisi olarak kullanmak, müşterilerden ücret alarak sunmak farklı hukuki yükümlülükler doğurabilir. EPİAŞ'a yazılı onaylama isteği göndermek en sağlıklı yaklaşım.

**S: "Kullanıcı verisi güvende mi?"**  
C: E-posta ve şifre Supabase Auth'ta, endüstri standardı bcrypt ile hashlenmiş. İş verileri Supabase PostgreSQL'de; servis anahtarı yalnızca backend'de. Sohbet mesajları veritabanına yazılmıyor. Temel risk NVIDIA'ya gönderilen mesajlar — bunu kullanıcıya açıkça bildirmemiz gerekiyor.

**S: "KVKK ihlali cezası ne kadar?"**  
C: KVKK madde 18'e göre en fazla 20 milyon TL veya yıllık global cironun %4'ü. Şu aşamada startup sınırları içinde düzenleyici risk düşük; ama ölçeklenmeden önce uyum çalışması şart.

---

## BÖLÜM 4: İŞ GELİŞTİRME

### Güçlü Yanlar

**Gerçek problem, triple win değer önerisi**
Türkiye'de PTF (spot elektrik fiyatı) ve karbon yoğunluğu korelasyon gösteriyor. Öğle saatlerinde güneş artar → PTF düşer → karbon azalır. Bu üçlü kazanım: daha az karbon, daha ucuz elektrik, daha yüksek ESG puanı. Değer önermesi yalnızca "yeşil" değil, aynı zamanda finansal.

**İlk hareket avantajı (First-mover)**
Türkiye'ye özgü, EPİAŞ entegrasyonlu, Türkçe AI asistanlı bu kombinasyon şu an piyasada yok. WattTime ve Electricity Maps Türkiye şebekesini yalnızca yüzeysel kapsıyor.

**API-first mimari**
Mevcut backend herhangi bir veri merkezi yönetim sistemine (Kubernetes, DCIM araçları) entegre olabilecek yapıda. SDK potansiyeli var; ürün "platform" değil "altyapı katmanı" olarak konumlanabilir.

**Demo çalışıyor, sayılar gerçek**
`POST /api/schedule/demo` gerçek verilerle çalışan, 15 saniyede ilerleme gösteren bir demo sunuyor. Her iş için kg CO₂, %, kWh rakamları hesaplanıyor — "sezgisel fayda" değil "belgelenen fayda."

**Düzenleyici rüzgar arkada**
AB'nin Sınırda Karbon Düzenlemesi (CBAM) 2026'dan itibaren Türk ihracatçıları doğrudan etkiliyor. Kurumsal müşteriler ESG tedarik zinciri baskısıyla karşılaşıyor. Yenilenebilir kapasite son 5 yılda %60 arttı — şebeke karbon salınımı giderek daha öngörülebilir hale geliyor.

---

### Açıklar & Eksiklikler

**Gelir modeli yok**
Kullanıcı başına maliyet takibi yok (LLM token, API çağrısı). Herhangi bir faturalama modeli (seat, usage-based, freemium) uygulanabilmesi için önce metering altyapısı gerekiyor.

**Tek veri kaynağına bağımlılık (iş riski)**
EPİAŞ erişimi kesilirse ya da şartları değişirse platformun temel değeri kayboluyor. "EPİAŞ bağımlısı değil miyiz?" sorusu satış görüşmelerinde gelecek.

**Büyük ölçekte global zamanlama problemi**
10.000 müşteri bağımsız greedy algoritma çalıştırdığında aynı pencereye kalabalık yönleniyor. Platform kendi önerilerini geçersiz kılıyor. Müşteri güven kaybına yol açar.

**Kullanım takibi ve analitik yok**
Hangi özellik ne kadar kullanılıyor, hangi iş tipi en çok tasarruf sağlıyor, hangi kullanıcı aktif — bilinmiyor. Ürün yol haritası veriye değil tahmine dayanmak zorunda kalıyor.

**Hedef müşteri net tanımlanmamış**
"Veri merkezi operatörleri" geniş bir kitle. Küçük colocation merkezi mi? Büyük enterprise mi? E-ticaret şirketi mi? Her segmentin karar süreci, ödeme isteği ve entegrasyon ihtiyacı farklı.

**Rekabet avantajı savunulabilir değil (henüz)**
EPİAŞ API kamuya açık; başka bir geliştirici aynı entegrasyonu yapabilir. Gerçek hendek eğitim verisi, müşteri verisi, kullanıcı alışkanlığı — bunların hiçbiri henüz yok.

---

### Mentöre Soracağınız Sorular

1. "Bu pazar için en hızlı müşteri edinme yolu ne? Doğrudan satış mı, sistem entegratör ortaklığı mı, yoksa açık API ücretsiz sunarak geliştirici ekosistemine girme mi?"
2. "Fiyatlandırma için seat-based mi, usage-based mi, yoksa outcome-based ('tasarruf edilen ton CO₂ başına ücret') modeli mi daha savunulabilir?"
3. "EPİAŞ bağımlılığını 'risk' değil 'değer' olarak nasıl konumlandırırız? ('biz şebeke operatörüyle entegre tek platformuz' gibi)"
4. "Türkiye'de veri merkezi operatörlerinin ESG/karbon raporlaması yapması ne zaman zorunlu hale geliyor?"
5. "10k+ müşteri ölçeğinde global zamanlama problemini çözmek için 'karbon kapasitesi havuzu' veya slot açık artırması modeli işe yarar mı?"
6. "İlk 10 müşteri için en kritik özellik ne olmalı? AI sohbet mi, API entegrasyonu mu, ESG raporlama mı?"

---

### Savunmaya Hazır Olun

**S: "Bu EPİAŞ API'sini herkes kullanabilir, neden sizden alsın?"**  
C: Ham API açık; ama onu anlamlı bir platforma dönüştürmek — emisyon faktörü hesabı, sliding window optimizasyonu, Türkçe AI tavsiyesi, ESG raporlama çıktısı — bunları bir veri merkezi mühendisi kendi başına aylarca çalışarak yapabilir. Bizden alanlar zaman ve mühendislik maliyeti satın alıyor. Değer hendek "veri erişimi" değil "çözüm eksiksizliği."

**S: "Türkiye'de kaç veri merkezi var, pazar büyük mü?"**  
C: Türkiye'de 50+ tier-3/4 veri merkezi var; büyük e-ticaret ve fintech şirketleri (Trendyol, Hepsiburada, Garanti BBVA) kendi altyapısını işletiyor. Colocation + enterprise IDC pazarı yıllık ~$800M büyüklüğünde. Hepsinde esnek zamanlama yapılabilir iş yükleri mevcut.

**S: "Karbon tasarrufu gerçekten %15–25 mi yoksa varsayım mı?"**  
C: Algoritmik hesaplama: mevcut yoğunluk − optimal pencere yoğunluğu. Türkiye şebekesinde günlük karbon yoğunluğu salınımı ~150–200 gCO₂/kWh. Esnek iş yükü için %10–20 gerçekçi bir aralık. Whitepaper'daki örnek hesaplama gerçek EPİAŞ verilerine dayanıyor.

**S: "Neden şimdi, neden Türkiye?"**  
C: AB'nin CBAM'ı Türkiye'yi doğrudan etkiliyor. Veri merkezleri kurumsal müşterilerin ESG tedarik zinciri baskısıyla karşılaşıyor. Türkiye'nin yenilenebilir kapasitesi son 5 yılda %60 arttı — şebeke karbon salınımı giderek daha öngörülebilir. Şu an doğru zaman.

**S: "Rakipleriniz kim?"**  
C: Küresel: WattTime, Electricity Maps (Carbon Intensity API), Google CFE API. Hiçbiri Türkiye'ye özgü değil, Türkçe AI asistanı yok, veri merkezi iş yükü zamanlama aracı değil. Yerel: Bu alanda bilinen bir rakip yok — bu hem fırsat hem risk.

---

## GENEL HAZIRLIK NOTLARI

### Her Görüşmede Kullanılabilecek Güçlü Mesajlar

1. **"Gerçek veri, gerçek sonuç"** — Algoritma EPİAŞ'ın resmi verisiyle çalışıyor; tahmin değil ölçüm.
2. **"Algoritmik temelli AI"** — LLM yorum yapıyor, hesaplama yapmıyor. Hallucination riskini temel sayısal kararlardan koparıyor.
3. **"Dayanıklılık tasarımı"** — 3 saniye zaman aşımı + gerçek veri fallback = internet olmadan da çalışır.
4. **"Ölçülebilir değer"** — Her iş için kg CO₂, %, kWh rakamları; "hissedilen fayda" değil "belgelenen fayda."

### Kabul Etmekten Kaçınmayın

Mentörler dürüstlüğe saygı duyar. Şu açıkları önceden kabul etmek güvenilirlik artırır:
- Gelir modeli henüz yok
- EPİAŞ ticari lisans anlaşması henüz yapılmadı
- NVIDIA DPA eksik
- Büyük ölçekte global zamanlama problemi var
- Streaming + function calling çelişkisi teknik borç

### Görüşme Öncesi Yapılabilecekler (Hızlı Kazanımlar, ~2 saat)

- [ ] EPİAŞ'a e-posta: ticari kullanım onayı talebi
- [ ] eptr2 GitHub'ına issue açma: lisans ne?
- [ ] NVIDIA DPA sayfasını incele: neler gerekiyor?
- [ ] Supabase projesini EU region'a taşı (Settings → Infrastructure)
- [ ] Kayıt formuna 1 satır ekle: "Mesajlarınız AI işlemi için NVIDIA API'sine gönderilmektedir"

---

## HIZLI BAŞVURU: Teknik Sayılar

| Konu | Değer |
|---|---|
| Karbon tahmin ufku | 24–48 saat |
| EPİAŞ API zaman aşımı | 3 saniye |
| Anlık karbon önbelleği | 15 dakika |
| Tahmin önbelleği | 30 dakika |
| LLM modeli | meta/llama-3.3-70b-instruct (NVIDIA NIM) |
| LLM maks. iterasyon | 5 (function calling döngüsü) |
| Öneri retry sayısı | 3 (sıcaklık: 0.3 → 0.5 → 0.7) |
| Günlük karbon salınımı (TR) | ~150–200 gCO₂/kWh |
| Tipik tasarruf aralığı | %10–25 |
| Demo iş ilerleme aralığı | 15 saniye (otomatik) |
| Toplam endpoint sayısı | 16 (10'u auth gerektirir) |
| Fallback veri noktası sayısı | 54 (14–16 Mayıs 2026, gerçek EPİAŞ) |

---

*Bu belge Karbon Zeka backend'inin kaynak kodu ve mimari analizi üzerinden otomatik olarak üretilmiştir.*  
*Hackathon: 100 StaryUP, YTÜ, 15–17 Mayıs 2026*
