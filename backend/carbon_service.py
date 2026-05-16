import asyncio
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models import CarbonReading, ForecastPoint, ForecastResponse

TURKEY_TZ = timezone(timedelta(hours=3))
CURRENT_TTL = 900    # 15 dakika
FORECAST_TTL = 1800  # 30 dakika
API_TIMEOUT = 3.0    # saniye — bu süreyi aşarsa JSON fallback devreye girer

FALLBACK_JSON = Path(__file__).parent / "mock_epias_data.json"

EMISSION_FACTORS: dict[str, float] = {
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
    "wasteheat":      200,
    "importExport":   400,
}

RENEWABLE_SOURCES: set[str] = {"dammedHydro", "river", "wind", "sun", "geothermal", "biomass"}

SOLAR_CURVE: dict[int, float] = {
    0: 0.0,  1: 0.0,  2: 0.0,  3: 0.0,  4: 0.0,  5: 0.0,
    6: 0.02, 7: 0.10, 8: 0.25, 9: 0.45, 10: 0.65, 11: 0.82,
    12: 0.95, 13: 1.0, 14: 0.95, 15: 0.82, 16: 0.65, 17: 0.45,
    18: 0.25, 19: 0.10, 20: 0.02, 21: 0.0, 22: 0.0, 23: 0.0,
}

_MOCK_BASELINE: dict[str, float] = {
    "naturalGas": 6200.0, "dammedHydro": 13000.0, "lignite": 3100.0,
    "river": 5600.0, "importCoal": 1300.0, "wind": 2300.0, "sun": 0.0,
    "fueloil": 1.0, "geothermal": 1100.0, "asphaltiteCoal": 180.0,
    "blackCoal": 580.0, "biomass": 530.0, "naphta": 0.0,
    "lng": 0.0, "importExport": -250.0, "wasteheat": 75.0,
}

_SOLAR_PEAK_MOCK = 5000.0  # Mayıs Türkiye tahmini MW

# Türkiye şebekesi için beklenen karbon yoğunluğu aralığı (gCO₂/kWh)
_CARBON_VALID_RANGE = (50.0, 800.0)

# Saatlik mock PTF (₺/MWh) — gündüz talebi yüksek → fiyat yüksek
_MOCK_PTF: dict[int, float] = {
    0: 950.0,  1: 900.0,  2: 870.0,  3: 850.0,  4: 860.0,  5: 920.0,
    6: 1050.0, 7: 1250.0, 8: 1450.0, 9: 1600.0, 10: 1700.0, 11: 1750.0,
    12: 1720.0, 13: 1680.0, 14: 1650.0, 15: 1630.0, 16: 1680.0, 17: 1800.0,
    18: 1900.0, 19: 1950.0, 20: 1850.0, 21: 1600.0, 22: 1300.0, 23: 1050.0,
}

_cache: dict = {}
_last_known_mix: dict | None = None


def _validate_carbon(value: float, source: str) -> float | None:
    lo, hi = _CARBON_VALID_RANGE
    if not (lo <= value <= hi):
        print(f"[carbon_service] ANOMALİ: {value:.1f} gCO₂/kWh aralık dışı [{lo}, {hi}] — kaynak: {source}")
        return None
    return value


# --- Cache ---

def _cache_get(key: str):
    entry = _cache.get(key)
    if entry and entry["expires_at"] > time.monotonic():
        return entry["data"]
    return None


def _cache_set(key: str, data, ttl: int) -> None:
    _cache[key] = {"data": data, "expires_at": time.monotonic() + ttl}


# --- Helpers ---

def _confidence(hour_offset: int) -> float:
    return round(max(0.55, 0.90 - (hour_offset - 1) * (0.35 / 23)), 2)


def _is_mock_mode() -> bool:
    return os.getenv("MOCK_MODE", "false").lower() == "true"


def calculate_carbon_intensity(gen_row: dict) -> dict:
    total_mwh = 0.0
    total_co2 = 0.0
    renewable_mwh = 0.0

    for fuel, factor in EMISSION_FACTORS.items():
        mwh = float(gen_row.get(fuel) or 0.0)
        if fuel == "importExport":
            mwh = max(0.0, mwh)
        total_mwh += mwh
        total_co2 += mwh * factor
        if fuel in RENEWABLE_SOURCES:
            renewable_mwh += mwh

    if total_mwh == 0:
        return {"carbon_intensity": 0.0, "renewable_ratio": 0.0, "total_mwh": 0.0}

    return {
        "timestamp": gen_row.get("date"),
        "carbon_intensity": round(total_co2 / total_mwh, 1),
        "renewable_ratio": round(renewable_mwh / total_mwh, 3),
        "total_mwh": round(total_mwh, 1),
    }


def _get_eptr_client():
    from eptr2 import EPTR2
    return EPTR2(postprocess=False)


def _parse_items(data: dict) -> list[dict]:
    body = data.get("body", data)
    items = body.get("items") or body.get("hourlyGenerations") or []
    if not items:
        raise ValueError("EPİAŞ boş items listesi döndü")
    return items


# --- JSON Fallback ---

def _load_fallback_points() -> list[dict]:
    try:
        with open(FALLBACK_JSON, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("points", [])
    except Exception as e:
        print(f"[carbon_service] fallback JSON okunamadı: {e}")
        return []


def _fallback_current() -> CarbonReading:
    points = _load_fallback_points()
    if not points:
        return _generate_mock_current()
    last = points[-1]
    ts = datetime.fromisoformat(last["timestamp"])
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=TURKEY_TZ)
    return CarbonReading(
        timestamp=ts,
        carbon_intensity=last["carbon_intensity"],
        renewable_ratio=last["renewable_ratio"],
        source="fallback",
    )


def _fallback_forecast(hours: int) -> ForecastResponse:
    points = _load_fallback_points()
    now = datetime.now(tz=TURKEY_TZ).replace(minute=0, second=0, microsecond=0)

    # Saate göre ortalama karbon yoğunluğu — gerçek EPİAŞ verisinden
    by_hour: dict[int, list[float]] = defaultdict(list)
    by_hour_ratio: dict[int, list[float]] = defaultdict(list)
    for p in points:
        ts = datetime.fromisoformat(p["timestamp"])
        by_hour[ts.hour].append(p["carbon_intensity"])
        by_hour_ratio[ts.hour].append(p["renewable_ratio"])

    forecast_points = []
    for h in range(1, hours + 1):
        ts = now + timedelta(hours=h)
        hour = ts.hour
        if by_hour.get(hour):
            avg_ci = round(sum(by_hour[hour]) / len(by_hour[hour]), 1)
            avg_rr = round(sum(by_hour_ratio[hour]) / len(by_hour_ratio[hour]), 3)
        else:
            avg_ci = 350.0
            avg_rr = 0.50
        forecast_points.append(ForecastPoint(
            timestamp=ts,
            carbon_intensity=avg_ci,
            renewable_ratio=avg_rr,
            confidence=_confidence(h),
            ptf_tl_per_mwh=_MOCK_PTF[hour],
        ))

    return ForecastResponse(
        generated_at=now,
        source="fallback",
        points=forecast_points,
    )


# --- Mock generators ---

def _generate_mock_current() -> CarbonReading:
    now = datetime.now(tz=TURKEY_TZ).replace(minute=0, second=0, microsecond=0)
    mix = dict(_MOCK_BASELINE)
    mix["sun"] = _SOLAR_PEAK_MOCK * SOLAR_CURVE[now.hour]
    calc = calculate_carbon_intensity({**mix, "date": now.isoformat()})
    return CarbonReading(
        timestamp=now,
        carbon_intensity=calc["carbon_intensity"],
        renewable_ratio=calc["renewable_ratio"],
        source="mock",
    )


def generate_mock_forecast(hours: int = 24) -> ForecastResponse:
    now = datetime.now(tz=TURKEY_TZ).replace(minute=0, second=0, microsecond=0)
    points = []
    for h in range(1, hours + 1):
        ts = now + timedelta(hours=h)
        mix = dict(_MOCK_BASELINE)
        mix["sun"] = _SOLAR_PEAK_MOCK * SOLAR_CURVE[ts.hour]
        mix["naturalGas"] *= 1.10 if 8 <= ts.hour <= 22 else 0.90
        calc = calculate_carbon_intensity({**mix, "date": ts.isoformat()})
        points.append(ForecastPoint(
            timestamp=ts,
            carbon_intensity=calc["carbon_intensity"],
            renewable_ratio=calc["renewable_ratio"],
            confidence=_confidence(h),
            ptf_tl_per_mwh=_MOCK_PTF[ts.hour],
        ))
    return ForecastResponse(
        generated_at=datetime.now(tz=TURKEY_TZ),
        source="mock",
        points=points,
    )


# --- Live fetchers (sync — to_thread içinde çalışır) ---

def _fetch_current_live() -> CarbonReading:
    global _last_known_mix
    client = _get_eptr_client()
    now = datetime.now(tz=TURKEY_TZ)
    start = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:00:00+03:00")
    end = now.strftime("%Y-%m-%dT%H:00:00+03:00")

    data = client.call("rt-gen", postprocess=False, start_date=start, end_date=end)
    items = _parse_items(data)

    valid_row = None
    for row in reversed(items):
        if float(row.get("total") or 0) > 0:
            valid_row = row
            break

    if valid_row is None:
        raise ValueError("Geçerli üretim satırı bulunamadı (total=0)")

    _last_known_mix = dict(valid_row)
    calc = calculate_carbon_intensity(valid_row)

    validated = _validate_carbon(calc["carbon_intensity"], "epias:rt-gen")
    if validated is None:
        raise ValueError(f"Anomali: {calc['carbon_intensity']:.1f} gCO₂/kWh aralık dışı — fallback devreye girecek")

    return CarbonReading(
        timestamp=datetime.fromisoformat(valid_row["date"]),
        carbon_intensity=validated,
        renewable_ratio=calc["renewable_ratio"],
        source="epias",
    )


def _fetch_forecast_live(hours: int) -> ForecastResponse:
    global _last_known_mix
    client = _get_eptr_client()
    now = datetime.now(tz=TURKEY_TZ).replace(minute=0, second=0, microsecond=0)

    # Baseline yoksa canlı veriden çek
    if _last_known_mix is None:
        _fetch_current_live()

    baseline = dict(_last_known_mix)

    # Güneş pik hesabı — gündüz ise mevcut üretimden türet
    current_sun = float(baseline.get("sun") or 0)
    current_hour_curve = SOLAR_CURVE.get(now.hour, 0)
    if current_sun > 0 and current_hour_curve > 0:
        solar_peak = current_sun / current_hour_curve
    else:
        solar_peak = _SOLAR_PEAK_MOCK

    # Rüzgar tahmini
    wind_hourly: dict[datetime, float] = {}
    wind_source = "epias"
    try:
        end_str = (now + timedelta(hours=hours + 1)).strftime("%Y-%m-%dT%H:00:00+03:00")
        now_str = now.strftime("%Y-%m-%dT%H:00:00+03:00")
        wdata = client.call("wind-forecast", postprocess=False,
                            start_date=now_str, end_date=end_str)
        witems = _parse_items(wdata)

        by_hour: dict[datetime, list[float]] = defaultdict(list)
        for item in witems:
            dt = datetime.fromisoformat(item["date"]).replace(minute=0, second=0, microsecond=0)
            val = float(item.get("value") or item.get("forecast") or item.get("generation") or 0.0)
            by_hour[dt].append(val)
        wind_hourly = {k: sum(v) / len(v) for k, v in by_hour.items()}
    except Exception as e:
        print(f"[carbon_service] wind-forecast hatası, baseline kullanılıyor: {e}")
        wind_source = "epias-partial"

    # Tahmin noktaları
    points = []
    for h in range(1, hours + 1):
        ts = now + timedelta(hours=h)
        mix = dict(baseline)
        mix["wind"] = wind_hourly.get(ts, float(baseline.get("wind") or 0))
        mix["sun"] = solar_peak * SOLAR_CURVE[ts.hour]

        calc = calculate_carbon_intensity({**mix, "date": ts.isoformat()})
        conf = _confidence(h) if wind_source == "epias" else 0.5
        points.append(ForecastPoint(
            timestamp=ts,
            carbon_intensity=calc["carbon_intensity"],
            renewable_ratio=calc["renewable_ratio"],
            confidence=conf,
        ))

    return ForecastResponse(
        generated_at=datetime.now(tz=TURKEY_TZ),
        source=wind_source,
        points=points,
    )


# --- Public async API ---

async def get_current_carbon() -> CarbonReading:
    cached = _cache_get("current")
    if cached:
        return cached

    if _is_mock_mode():
        result = _generate_mock_current()
        _cache_set("current", result, CURRENT_TTL)
        return result

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_fetch_current_live),
            timeout=API_TIMEOUT,
        )
    except asyncio.TimeoutError:
        print(f"[carbon_service] EPİAŞ {API_TIMEOUT}s timeout — JSON fallback")
        result = _fallback_current()
    except Exception as e:
        print(f"[carbon_service] get_current_carbon hatası, fallback kullanılıyor: {e}")
        result = _fallback_current()

    _cache_set("current", result, CURRENT_TTL)
    return result


async def get_forecast(hours: int = 24) -> ForecastResponse:
    cached = _cache_get("forecast")
    if cached:
        return cached

    if _is_mock_mode():
        result = generate_mock_forecast(hours)
        _cache_set("forecast", result, FORECAST_TTL)
        return result

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_fetch_forecast_live, hours),
            timeout=API_TIMEOUT,
        )
    except asyncio.TimeoutError:
        print(f"[carbon_service] EPİAŞ forecast {API_TIMEOUT}s timeout — JSON fallback")
        result = _fallback_forecast(hours)
    except Exception as e:
        print(f"[carbon_service] get_forecast hatası, fallback kullanılıyor: {e}")
        result = _fallback_forecast(hours)

    # PTF zenginleştirme: gerçek EPİAŞ verisi varsa kullan, yoksa saatlik mock
    try:
        from grid_service import get_ptf_hourly
        ptf_map = await get_ptf_hourly(hours)
    except Exception:
        ptf_map = {}

    enriched_points = []
    for p in result.points:
        real_ptf = ptf_map.get(p.timestamp) or ptf_map.get(p.timestamp.replace(tzinfo=None))
        ptf_val = real_ptf or p.ptf_tl_per_mwh or _MOCK_PTF[p.timestamp.hour]
        enriched_points.append(p.model_copy(update={"ptf_tl_per_mwh": ptf_val}))
    result = result.model_copy(update={"points": enriched_points})

    _cache_set("forecast", result, FORECAST_TTL)
    return result
