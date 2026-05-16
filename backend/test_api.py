"""
EPİAŞ API bağlantı ve veri yapısı testi.
Gerçek credentials varsa canlı veri çeker; yoksa mock yapıyı gösterir.
"""

import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Gerçek rt-gen API alan adları → gCO2eq/kWh emisyon faktörleri
EMISSION_FACTORS = {
    "naturalGas":     490,
    "lignite":        1050,  # linyit
    "importCoal":     820,   # ithal taşkömürü
    "blackCoal":      820,   # taşkömürü
    "asphaltiteCoal": 980,   # asfaltit
    "fueloil":        650,
    "naphta":         650,
    "lng":            490,
    "dammedHydro":    4,
    "river":          4,
    "wind":           11,
    "sun":            45,
    "geothermal":     38,
    "biomass":        230,
    "wasteheat":      200,
    "importExport":   400,   # pozitifse ithalat sayılır
}

RENEWABLE_SOURCES = {"dammedHydro", "river", "wind", "sun", "geothermal", "biomass"}


def test_credentials():
    username = os.getenv("EPIAS_USERNAME", "")
    password = os.getenv("EPIAS_PASSWORD", "")

    has_creds = username and username != "your_username"
    print(f"[CREDENTIALS] {'✓ Gerçek credentials mevcut' if has_creds else '✗ Placeholder credentials — mock mod kullanılacak'}")
    print(f"  Kullanıcı: {username[:3]}{'*' * (len(username)-3) if len(username) > 3 else ''}")
    return has_creds


def test_live_api():
    from eptr2 import EPTR2

    print("\n[EPİAŞ] Bağlantı deneniyor...")
    try:
        client = EPTR2()
        now = datetime.now()
        start = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:00:00+03:00")
        end = now.strftime("%Y-%m-%dT%H:00:00+03:00")

        endpoints = {
            "rt-gen":      {"start_date": start, "end_date": end},
            "ren-rt-gen":  {"start_date": start, "end_date": end},
            "wind-forecast": {"start_date": start, "end_date": (now + timedelta(hours=24)).strftime("%Y-%m-%dT%H:00:00+03:00")},
            "rt-cons":     {"start_date": start, "end_date": end},
        }

        results = {}
        for key, params in endpoints.items():
            try:
                data = client.call(key, postprocess=False, **params)
                # İlk item'ı göster
                body = data.get("body", data)
                items = body.get("items", body.get("hourlyGenerations", [data]))
                sample = items[0] if items else {}
                print(f"  ✓ {key} — {len(items)} kayıt | Alan adları: {list(sample.keys())[:8]}")
                results[key] = items
            except Exception as e:
                print(f"  ✗ {key} — Hata: {e}")
                results[key] = None

        return results

    except Exception as e:
        print(f"  ✗ Bağlantı başarısız: {e}")
        return None


def generate_mock_rt_gen():
    """Gerçek rt-gen alan adlarıyla mock veri üretir."""
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    rows = []
    for i in range(3):
        ts = now - timedelta(hours=i)
        rows.append({
            "date": ts.isoformat(),
            "hour": ts.strftime("%H:%M"),
            "total": 33000.0,
            "naturalGas": 6200.0,
            "dammedHydro": 13000.0,
            "lignite": 3100.0,
            "river": 5600.0,
            "importCoal": 1300.0,
            "wind": 2300.0,
            "sun": 1100.0 if 7 <= ts.hour <= 19 else 0.0,
            "fueloil": 1.0,
            "geothermal": 1100.0,
            "asphaltiteCoal": 180.0,
            "blackCoal": 580.0,
            "biomass": 530.0,
            "naphta": 0,
            "lng": 0,
            "importExport": -250.0,
            "wasteheat": 75.0,
        })
    return rows


def calculate_carbon_intensity(gen_row: dict) -> dict:
    """Üretim karışımından karbon yoğunluğunu hesaplar."""
    total_mwh = 0.0
    total_co2 = 0.0
    renewable_mwh = 0.0

    for fuel, factor in EMISSION_FACTORS.items():
        mwh = gen_row.get(fuel, 0.0) or 0.0
        total_mwh += mwh
        total_co2 += mwh * factor
        if fuel in RENEWABLE_SOURCES:
            renewable_mwh += mwh

    if total_mwh == 0:
        return {"carbon_intensity": 0.0, "renewable_ratio": 0.0, "total_mwh": 0.0}

    return {
        "timestamp": gen_row.get("date"),
        "carbon_intensity": round(total_co2 / total_mwh, 1),   # gCO2eq/kWh
        "renewable_ratio": round(renewable_mwh / total_mwh, 3),
        "total_mwh": round(total_mwh, 1),
    }


def test_mock_pipeline():
    print("\n[MOCK] Mock veri pipeline testi...")
    rows = generate_mock_rt_gen()
    print(f"  Üretilen {len(rows)} saatlik üretim kaydı")
    print(f"  Alan adları: {list(rows[0].keys())}")
    print()

    for row in rows:
        result = calculate_carbon_intensity(row)
        print(f"  {result['timestamp']}")
        print(f"    Karbon yoğunluğu : {result['carbon_intensity']} gCO2eq/kWh")
        print(f"    Yenilenebilir oran: {result['renewable_ratio']*100:.1f}%")
        print(f"    Toplam üretim     : {result['total_mwh']} MWh")
        print()


def test_wind_forecast_structure():
    print("[MOCK] wind-forecast veri yapısı:")
    sample = {
        "date": "2026-05-16T14:00:00+03:00",
        "forecastDate": "2026-05-16T12:00:00+03:00",
        "value": 3850.5,   # MW — tüm Türkiye rüzgar tahmini
    }
    print(f"  {json.dumps(sample, ensure_ascii=False, indent=4)}")
    print("  → 24 saatlik bu veri, düşük karbon dönemlerini tahmin etmede kullanılacak.")


if __name__ == "__main__":
    print("=" * 55)
    print("  KARBON ZEKA — EPİAŞ API TEST")
    print("=" * 55)

    has_creds = test_credentials()

    if has_creds:
        live_results = test_live_api()
        if live_results and live_results.get("rt-gen"):
            print("\n[CARBON] Gerçek veriden karbon yoğunluğu:")
            for row in live_results["rt-gen"][:2]:
                result = calculate_carbon_intensity(row)
                print(f"  {result}")
    else:
        test_mock_pipeline()
        test_wind_forecast_structure()
        print("\n[BİLGİ] EPİAŞ hesabı açmak için:")
        print("  → seffaflik.epias.com.tr → Kayıt Ol")
        print("  → Onay sonrası .env dosyasını güncelle:")
        print("    EPIAS_USERNAME=epias_kullanici_adi")
        print("    EPIAS_PASSWORD=epias_sifre")

    print("\n[TAMAMLANDI]")
