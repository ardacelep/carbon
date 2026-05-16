import json
import math
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models import AnomalyReport, ForecastAccuracyResponse

TURKEY_TZ = timezone(timedelta(hours=3))
ANOMALY_TTL = 900    # 15 dakika
ACCURACY_TTL = 3600  # 1 saat — statik hesap

FALLBACK_JSON = Path(__file__).parent / "mock_epias_data.json"

_cache: dict = {}


# --- Cache ---

def _cache_get(key: str):
    entry = _cache.get(key)
    if entry and entry["expires_at"] > time.monotonic():
        return entry["data"]
    return None


def _cache_set(key: str, data, ttl: int) -> None:
    _cache[key] = {"data": data, "expires_at": time.monotonic() + ttl}


# --- Veri yükleme ---

def _load_points() -> list[dict]:
    try:
        with open(FALLBACK_JSON, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("points", [])
    except Exception as e:
        print(f"[anomaly_service] mock veri okunamadı: {e}")
        return []


# --- Baseline oluşturma ---

def _build_hourly_baseline() -> dict[int, dict]:
    """Tüm mock noktalarından saat bazlı mean/std hesaplar."""
    points = _load_points()
    by_hour: dict[int, list[float]] = defaultdict(list)

    for p in points:
        try:
            ts = datetime.fromisoformat(p["timestamp"])
            by_hour[ts.hour].append(float(p["carbon_intensity"]))
        except Exception:
            continue

    baseline: dict[int, dict] = {}
    for hour, values in by_hour.items():
        n = len(values)
        mean = sum(values) / n
        if n > 1:
            variance = sum((v - mean) ** 2 for v in values) / (n - 1)
            std = math.sqrt(variance)
        else:
            std = 0.0
        baseline[hour] = {"mean": round(mean, 2), "std": round(std, 2), "count": n}

    return baseline


_baseline_cache: dict[int, dict] | None = None


def _get_baseline() -> dict[int, dict]:
    global _baseline_cache
    if _baseline_cache is None:
        _baseline_cache = _build_hourly_baseline()
    return _baseline_cache


# --- Anomali tespiti ---

def detect_anomaly(carbon_intensity: float, hour: int) -> dict:
    baseline = _get_baseline()
    stats = baseline.get(hour)

    if stats is None or stats["std"] == 0.0:
        direction_msg = ""
        if stats is not None:
            direction_msg = (
                f"Saat {hour:02d}:00 için tüm geçmiş değerler aynı "
                f"({stats['mean']:.1f} gCO2/kWh) — Z-skoru hesaplanamıyor."
            )
        else:
            direction_msg = f"Saat {hour:02d}:00 için geçmiş veri yok."
        return {
            "z_score": 0.0,
            "severity": "unknown",
            "is_anomaly": False,
            "hour_mean": stats["mean"] if stats else None,
            "hour_std": stats["std"] if stats else None,
            "sample_count": stats["count"] if stats else 0,
            "message": direction_msg,
            "recommendation": "Yeterli geçmiş veri olmadığı için anomali tespiti yapılamıyor.",
        }

    z = (carbon_intensity - stats["mean"]) / stats["std"]
    abs_z = abs(z)

    if abs_z >= 2.0:
        severity = "high"
        is_anomaly = True
    elif abs_z >= 1.5:
        severity = "medium"
        is_anomaly = True
    elif abs_z >= 1.0:
        severity = "low"
        is_anomaly = True
    else:
        severity = "normal"
        is_anomaly = False

    direction = "yüksek" if z > 0 else "düşük"

    message = (
        f"Saat {hour:02d}:00 için beklenen ortalama {stats['mean']:.1f} gCO2/kWh "
        f"(±{stats['std']:.1f}, {stats['count']} gözlem). "
        f"Anlık değer {carbon_intensity:.1f} gCO2/kWh — normalden {abs_z:.1f} sigma {direction}."
    )

    if is_anomaly and z > 0:
        recommendation = (
            f"Karbon yoğunluğu bu saat için normalin {abs_z:.1f} sigma üzerinde. "
            "İş yüklerini daha düşük karbonlu bir zaman dilimine ertelemeniz önerilir."
        )
    elif is_anomaly and z < 0:
        recommendation = (
            f"Karbon yoğunluğu normalin {abs_z:.1f} sigma altında — "
            "iş yüklerinizi şimdi çalıştırmak için iyi bir fırsat."
        )
    else:
        recommendation = (
            "Karbon yoğunluğu normal aralıkta. Planlanan programa göre devam edebilirsiniz."
        )

    return {
        "z_score": round(z, 3),
        "severity": severity,
        "is_anomaly": is_anomaly,
        "hour_mean": stats["mean"],
        "hour_std": stats["std"],
        "sample_count": stats["count"],
        "message": message,
        "recommendation": recommendation,
    }


# --- D4: Tahmin doğruluğu backtest ---

def compute_forecast_accuracy() -> dict:
    """
    14 Mayıs'ı train, 15 Mayıs'ı test olarak kullanarak
    saatlik ortalama modelin MAE ve RMSE'sini hesaplar.
    """
    points = _load_points()
    train = points[:24]   # 14 Mayıs 00-23
    test = points[24:48]  # 15 Mayıs 00-23

    if not train or not test:
        return {
            "mae_gco2_kwh": 0.0,
            "rmse_gco2_kwh": 0.0,
            "train_days": 0,
            "test_days": 0,
            "train_points": 0,
            "test_points": 0,
            "model_type": "hourly-mean",
            "predictions": [],
        }

    # Saat bazlı ortalama (train setinden)
    hour_avg: dict[int, list[float]] = defaultdict(list)
    for p in train:
        try:
            h = datetime.fromisoformat(p["timestamp"]).hour
            hour_avg[h].append(float(p["carbon_intensity"]))
        except Exception:
            continue
    hour_mean = {h: sum(v) / len(v) for h, v in hour_avg.items()}

    # Global fallback ortalaması (saat verisi yoksa)
    global_mean = sum(hour_mean.values()) / len(hour_mean) if hour_mean else 260.0

    errors: list[float] = []
    squared_errors: list[float] = []
    predictions: list[dict] = []

    for p in test:
        try:
            ts = datetime.fromisoformat(p["timestamp"])
            actual = float(p["carbon_intensity"])
            predicted = round(hour_mean.get(ts.hour, global_mean), 1)
            err = actual - predicted
            abs_err = abs(err)
            errors.append(abs_err)
            squared_errors.append(abs_err ** 2)
            predictions.append({
                "timestamp": p["timestamp"],
                "actual": actual,
                "predicted": predicted,
                "error": round(err, 1),
            })
        except Exception:
            continue

    if not errors:
        mae = rmse = 0.0
    else:
        mae = round(sum(errors) / len(errors), 2)
        rmse = round(math.sqrt(sum(squared_errors) / len(squared_errors)), 2)

    return {
        "mae_gco2_kwh": mae,
        "rmse_gco2_kwh": rmse,
        "train_days": 1,
        "test_days": 1,
        "train_points": len(train),
        "test_points": len(predictions),
        "model_type": "hourly-mean",
        "predictions": predictions,
    }


# --- Public async API ---

async def get_anomaly_report() -> AnomalyReport:
    cached = _cache_get("anomaly")
    if cached:
        return cached

    # Lazy import — circular import önlemek için
    from carbon_service import get_current_carbon

    reading = await get_current_carbon()
    now = datetime.now(tz=TURKEY_TZ)
    hour = reading.timestamp.hour if reading.timestamp.tzinfo else now.hour

    result = detect_anomaly(reading.carbon_intensity, hour)

    report = AnomalyReport(
        timestamp=reading.timestamp,
        carbon_intensity=reading.carbon_intensity,
        hour=hour,
        z_score=result["z_score"],
        severity=result["severity"],
        is_anomaly=result["is_anomaly"],
        hour_mean=result["hour_mean"],
        hour_std=result["hour_std"],
        sample_count=result["sample_count"],
        message=result["message"],
        recommendation=result["recommendation"],
        source=reading.source,
        generated_at=now,
    )

    _cache_set("anomaly", report, ANOMALY_TTL)
    return report


async def get_accuracy_report() -> ForecastAccuracyResponse:
    cached = _cache_get("accuracy")
    if cached:
        return cached

    data = compute_forecast_accuracy()
    report = ForecastAccuracyResponse(**data)
    _cache_set("accuracy", report, ACCURACY_TTL)
    return report
