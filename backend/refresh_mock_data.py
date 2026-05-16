"""
EPİAŞ'tan son 48 saatlik gerçek veriyi çekip mock_epias_data.json'u günceller.
Kullanım: python refresh_mock_data.py
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TURKEY_TZ = timezone(timedelta(hours=3))
OUTPUT = Path(__file__).parent / "mock_epias_data.json"

EMISSION_FACTORS = {
    "naturalGas":     490,
    "lignite":        1050,
    "importCoal":     820,
    "blackCoal":      820,
    "asphaltiteCoal": 980,
    "fueloil":        650,
    "naphta":         650,
    "lng":            490,
    "dammedHydro":    4,
    "river":          4,
    "wind":           11,
    "sun":            45,
    "geothermal":     38,
    "biomass":        230,
    "wasteheat":      0,
    "nuclear":        12,
    "others":         300,
}
RENEWABLE = {"dammedHydro", "river", "wind", "sun", "geothermal", "biomass"}


def calculate_carbon_intensity(row: dict) -> tuple[float, float]:
    total = row.get("total", 0) or 0
    if total <= 0:
        return 0.0, 0.0
    weighted_co2 = sum(
        row.get(fuel, 0) * factor
        for fuel, factor in EMISSION_FACTORS.items()
        if row.get(fuel, 0)
    )
    renewable = sum(row.get(f, 0) for f in RENEWABLE if row.get(f, 0))
    return weighted_co2 / total, renewable / total


def fetch_48h():
    from dotenv import load_dotenv
    load_dotenv()

    from eptr2 import EPTR2
    client = EPTR2(postprocess=False)

    now = datetime.now(TURKEY_TZ)
    start = now - timedelta(hours=48)

    print(f"EPİAŞ'tan veri çekiliyor: {start:%Y-%m-%d %H:%M} → {now:%Y-%m-%d %H:%M} (TR)")
    data = client.call("rt-gen", postprocess=False, start_date=start, end_date=now)

    items = data if isinstance(data, list) else (
        data.get("items") or data.get("body", {}).get("hourlyGenerations", [])
        if isinstance(data, dict) else []
    )
    if not items:
        raise RuntimeError("EPİAŞ boş items listesi döndü")

    points = []
    for row in items:
        total = row.get("total", 0) or 0
        if total <= 0:
            continue
        ts_raw = row.get("date") or row.get("datetime") or row.get("startDate")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        ci, rr = calculate_carbon_intensity(row)
        if ci < 50 or ci > 800:
            continue
        points.append({
            "timestamp": ts.isoformat(),
            "carbon_intensity": round(ci, 2),
            "renewable_ratio": round(rr, 4),
            "total_mwh": round(total, 1),
        })

    return points


def main():
    try:
        points = fetch_48h()
    except Exception as e:
        print(f"HATA: {e}", file=sys.stderr)
        sys.exit(1)

    if not points:
        print("HATA: Geçerli veri noktası bulunamadı", file=sys.stderr)
        sys.exit(1)

    payload = {
        "generated_at": datetime.now(TURKEY_TZ).isoformat(),
        "source": "epias",
        "points": points,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"{len(points)} nokta kaydedildi → {OUTPUT}")
    print(f"Son nokta: {points[-1]['timestamp']} — {points[-1]['carbon_intensity']:.1f} gCO₂/kWh")


if __name__ == "__main__":
    main()
