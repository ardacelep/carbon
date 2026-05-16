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
    current_ptf: float | None = None,
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

    savings_tl = None
    if current_ptf is not None:
        ptf_vals = [p.ptf_tl_per_mwh for p in best_window if p.ptf_tl_per_mwh is not None]
        if ptf_vals:
            avg_ptf = sum(ptf_vals) / len(ptf_vals)
            savings_tl = round(max(0.0, power_kw * duration_hours * (current_ptf - avg_ptf) / 1000), 2)

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
        estimated_savings_tl=savings_tl,
    )


def schedule_multiple_jobs(
    jobs: list[dict],
    forecast: ForecastResponse,
    current_intensity: float,
    outage_slots: set | None = None,
    current_ptf: float | None = None,
) -> dict[int, OptimalWindow]:
    try:
        result = _schedule_ortools(jobs, forecast, current_intensity, outage_slots, current_ptf)
        print(f"[scheduler] OR-Tools: {len(result)}/{len(jobs)} iş planlandı")
        return result
    except Exception as e:
        print(f"[scheduler] OR-Tools başarısız ({e}), greedy fallback devreye giriyor")
        return _schedule_greedy(jobs, forecast, current_intensity, outage_slots, current_ptf)


def _schedule_ortools(
    jobs: list[dict],
    forecast: ForecastResponse,
    current_intensity: float,
    outage_slots: set | None = None,
    current_ptf: float | None = None,
) -> dict[int, OptimalWindow]:
    from ortools.sat.python import cp_model

    points = forecast.points
    n_slots = len(points)
    if n_slots == 0 or not jobs:
        return {}

    model = cp_model.CpModel()
    job_vars: dict[int, dict] = {}

    for job in jobs:
        job_id = job["id"]
        duration = max(1, math.ceil(job["duration_hours"]))

        # Deadline'a göre son geçerli başlangıç slotunu hesapla
        max_start = n_slots - duration
        if job.get("deadline"):
            try:
                deadline = job["deadline"]
                if isinstance(deadline, str):
                    deadline = datetime.fromisoformat(deadline)
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=TURKEY_TZ)
                for i, p in enumerate(points):
                    ts = p.timestamp if p.timestamp.tzinfo else p.timestamp.replace(tzinfo=TURKEY_TZ)
                    if ts >= deadline:
                        max_start = min(max_start, max(0, i - duration))
                        break
            except Exception:
                pass

        max_start = max(0, max_start)

        # Her başlangıç slotu için karbon maliyeti (tamsayı, 10x ölçekli)
        SCALE = 10
        FORBIDDEN = int(999999 * SCALE)
        costs = []
        for s in range(max_start + 1):
            window_pts = points[s: s + duration]
            if outage_slots and any(p.timestamp in outage_slots for p in window_pts):
                costs.append(FORBIDDEN)
                continue
            avg_ci = sum(p.carbon_intensity for p in window_pts) / len(window_pts) if window_pts else current_intensity
            costs.append(int(avg_ci * SCALE))

        if not costs:
            continue

        start = model.NewIntVar(0, max_start, f"s_{job_id}")
        interval = model.NewFixedSizeIntervalVar(start, duration, f"i_{job_id}")
        carbon = model.NewIntVar(min(costs), max(costs) + 1, f"c_{job_id}")
        model.AddElement(start, costs, carbon)

        job_vars[job_id] = {
            "start": start,
            "interval": interval,
            "carbon": carbon,
            "duration": duration,
            "costs": costs,
        }

    if not job_vars:
        return {}

    # Çakışma yasağı
    model.AddNoOverlap([v["interval"] for v in job_vars.values()])

    # Amaç: toplam karbonu minimize et (önceliğe göre ağırlıklı)
    obj = []
    for job in jobs:
        jid = job["id"]
        if jid not in job_vars:
            continue
        weight = max(1, 6 - job.get("priority", 1))
        obj.append(job_vars[jid]["carbon"] * weight)
    model.Minimize(sum(obj))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5.0
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"Çözüm bulunamadı (status={status})")

    result: dict[int, OptimalWindow] = {}
    for job in jobs:
        jid = job["id"]
        if jid not in job_vars:
            continue

        s = solver.Value(job_vars[jid]["start"])
        dur = job_vars[jid]["duration"]
        window_pts = points[s: s + dur]

        avg_ci = sum(p.carbon_intensity for p in window_pts) / len(window_pts) if window_pts else current_intensity
        avg_ci = round(avg_ci, 1)
        savings_pct = round(max(0.0, (current_intensity - avg_ci) / current_intensity * 100), 1) if current_intensity > 0 else 0.0

        start_time = points[s].timestamp
        end_time = points[min(s + dur - 1, n_slots - 1)].timestamp + timedelta(hours=1)

        hours_in = [p.timestamp.hour for p in window_pts]
        note = ""
        if any(10 <= h <= 15 for h in hours_in):
            note = " Güneş üretiminin yüksek olduğu öğle saatlerinden yararlanıyor."
        elif all(h < 6 or h >= 22 for h in hours_in):
            note = " Düşük talebin olduğu gece saatlerinde yenilenebilir oran artıyor."

        savings_tl = None
        if current_ptf is not None:
            ptf_vals = [p.ptf_tl_per_mwh for p in window_pts if p.ptf_tl_per_mwh is not None]
            if ptf_vals:
                avg_ptf = sum(ptf_vals) / len(ptf_vals)
                savings_tl = round(max(0.0, job["power_kw"] * job["duration_hours"] * (current_ptf - avg_ptf) / 1000), 2)

        result[jid] = OptimalWindow(
            start_time=start_time,
            end_time=end_time,
            avg_carbon_intensity=avg_ci,
            estimated_savings_pct=savings_pct,
            reasoning=(
                f"Global optimizasyon: {start_time.strftime('%d.%m %H:%M')}–{end_time.strftime('%H:%M')}, "
                f"ortalama {avg_ci} gCO₂/kWh — şu anki değerden %{savings_pct:.0f} tasarruf.{note}"
            ),
            estimated_savings_tl=savings_tl,
        )

    return result


def _schedule_greedy(
    jobs: list[dict],
    forecast: ForecastResponse,
    current_intensity: float,
    outage_slots: set | None = None,
    current_ptf: float | None = None,
) -> dict[int, OptimalWindow]:
    _INF = datetime.max.replace(tzinfo=TURKEY_TZ)
    sorted_jobs = sorted(
        jobs,
        key=lambda j: (-j.get("priority", 1), j.get("deadline") or _INF),
    )

    used_slots: set[datetime] = set()
    results: dict[int, OptimalWindow] = {}

    for job in sorted_jobs:
        blocked = used_slots | (outage_slots or set())
        available = [p for p in forecast.points if p.timestamp not in blocked]
        if not available:
            continue
        filtered = ForecastResponse(generated_at=forecast.generated_at, source=forecast.source, points=available)
        try:
            window = find_optimal_window(
                forecast=filtered,
                duration_hours=job["duration_hours"],
                deadline=job.get("deadline"),
                power_kw=job["power_kw"],
                current_intensity=current_intensity,
                cost_weight=job.get("cost_weight", 0.0),
                current_ptf=current_ptf,
            )
            results[job["id"]] = window
            for p in forecast.points:
                if window.start_time <= p.timestamp < window.end_time:
                    used_slots.add(p.timestamp)
        except Exception as e:
            print(f"[scheduler] greedy: job {job['id']} planlanamadı: {e}")

    return results
