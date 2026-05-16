import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from models import ForecastResponse, OptimalWindow

TURKEY_TZ = timezone(timedelta(hours=3))


def find_optimal_window(
    forecast: ForecastResponse,
    duration_hours: float,
    deadline: datetime | None,
    power_kw: float,
    current_intensity: float,
    cost_weight: float = 0.0,
) -> OptimalWindow:
    points = forecast.points
    if not points:
        raise ValueError("Tahmin verisi mevcut değil")

    # Deadline filtresi
    if deadline:
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=TURKEY_TZ)
        points = [p for p in points if p.timestamp <= deadline]
    if not points:
        points = forecast.points  # deadline geçmişse tüm forecast'i kullan

    window_size = max(1, math.ceil(duration_hours))
    if window_size > len(points):
        window_size = len(points)

    # Kombine skor: karbon normalize + PTF normalize (cost_weight>0 ise)
    has_ptf = cost_weight > 0 and any(p.ptf_tl_per_mwh is not None for p in points)

    carbon_values = [p.carbon_intensity for p in points]
    carbon_min = min(carbon_values)
    carbon_max = max(carbon_values)
    carbon_range = carbon_max - carbon_min or 1.0

    if has_ptf:
        ptf_values = [p.ptf_tl_per_mwh or 0.0 for p in points]
        ptf_min = min(ptf_values)
        ptf_max = max(ptf_values)
        ptf_range = ptf_max - ptf_min or 1.0

    best_score = float("inf")
    best_avg = float("inf")
    best_idx = 0

    for i in range(len(points) - window_size + 1):
        window = points[i: i + window_size]
        avg_carbon = sum(p.carbon_intensity for p in window) / window_size

        if has_ptf:
            avg_ptf = sum(p.ptf_tl_per_mwh or 0.0 for p in window) / window_size
            carbon_norm = (avg_carbon - carbon_min) / carbon_range
            ptf_norm = (avg_ptf - ptf_min) / ptf_range
            score = (1 - cost_weight) * carbon_norm + cost_weight * ptf_norm
        else:
            score = avg_carbon

        if score < best_score:
            best_score = score
            best_avg = avg_carbon
            best_idx = i

    best_window = points[best_idx: best_idx + window_size]
    start_time = best_window[0].timestamp
    end_time = best_window[-1].timestamp + timedelta(hours=1)
    avg_carbon = round(best_avg, 1)

    savings_pct = round(max(0.0, (current_intensity - avg_carbon) / current_intensity * 100), 1)

    # Türkçe reasoning
    start_str = start_time.strftime("%H:%M")
    end_str = end_time.strftime("%H:%M")
    date_str = start_time.strftime("%d.%m")

    if savings_pct > 0:
        reasoning = (
            f"{date_str} tarihinde {start_str}–{end_str} arası en uygun pencere. "
            f"Ortalama karbon yoğunluğu {avg_carbon} gCO2eq/kWh — "
            f"şu anki değerden %{savings_pct:.0f} daha düşük."
        )
    else:
        reasoning = (
            f"{start_str}–{end_str} arası önerilir. "
            f"Karbon yoğunluğu sabit seyrediyor ({avg_carbon} gCO2eq/kWh)."
        )

    # Pencereye özel not ekle
    hours_in_window = [p.timestamp.hour for p in best_window]
    if any(10 <= h <= 15 for h in hours_in_window):
        reasoning += " Güneş üretiminin yüksek olduğu öğle saatlerinden yararlanıyor."
    elif all(h < 6 or h >= 22 for h in hours_in_window):
        reasoning += " Düşük talebin olduğu gece saatlerinde yenilenebilir oran artıyor."

    return OptimalWindow(
        start_time=start_time,
        end_time=end_time,
        avg_carbon_intensity=avg_carbon,
        estimated_savings_pct=savings_pct,
        reasoning=reasoning,
    )


def schedule_multiple_jobs(
    jobs: list[dict],
    forecast: ForecastResponse,
    current_intensity: float,
) -> dict[int, OptimalWindow]:
    # Öncelik azalan, deadline artan sırada işle (None deadline = sonsuz)
    _INF = datetime.max.replace(tzinfo=TURKEY_TZ)
    sorted_jobs = sorted(
        jobs,
        key=lambda j: (-j.get("priority", 1), j.get("deadline") or _INF),
    )

    used_slots: set[datetime] = set()
    results: dict[int, OptimalWindow] = {}

    for job in sorted_jobs:
        available_points = [p for p in forecast.points if p.timestamp not in used_slots]
        if not available_points:
            continue

        filtered_forecast = ForecastResponse(
            generated_at=forecast.generated_at,
            source=forecast.source,
            points=available_points,
        )

        try:
            window = find_optimal_window(
                forecast=filtered_forecast,
                duration_hours=job["duration_hours"],
                deadline=job.get("deadline"),
                power_kw=job["power_kw"],
                current_intensity=current_intensity,
                cost_weight=job.get("cost_weight", 0.0),
            )
            results[job["id"]] = window
            for p in forecast.points:
                if window.start_time <= p.timestamp < window.end_time:
                    used_slots.add(p.timestamp)
        except Exception as e:
            print(f"[scheduler] job {job['id']} için slot bulunamadı: {e}")

    return results
