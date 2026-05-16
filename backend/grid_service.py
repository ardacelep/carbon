import asyncio
import os
import time
from datetime import datetime, timedelta, timezone

from models import GridStatus, PlannedOutage

TURKEY_TZ = timezone(timedelta(hours=3))
GRID_TTL = 1800  # 30 dakika

_cache: dict = {}


def _cache_get(key: str):
    entry = _cache.get(key)
    if entry and entry["expires_at"] > time.monotonic():
        return entry["data"]
    return None


def _cache_set(key: str, data, ttl: int) -> None:
    _cache[key] = {"data": data, "expires_at": time.monotonic() + ttl}


def _is_mock_mode() -> bool:
    return os.getenv("MOCK_MODE", "false").lower() == "true"


def _get_eptr_client():
    from eptr2 import EPTR2
    return EPTR2(postprocess=False)


def _parse_items(data: dict) -> list[dict]:
    body = data.get("body", data)
    items = body.get("items") or body.get("hourlyGenerations") or []
    if not items:
        raise ValueError("EPİAŞ boş items listesi döndü")
    return items


def _generate_mock_grid_status() -> GridStatus:
    return GridStatus(
        dam_fullness_pct=68.4,
        dam_trend="stable",
        ptf_tl_per_mwh=1247.0,
        supply_demand_mw=820.0,
        planned_outages=[],
        grid_stress="low",
        updated_at=datetime.now(tz=TURKEY_TZ),
        source="mock",
    )


def _fetch_grid_status_live() -> GridStatus:
    client = _get_eptr_client()
    now = datetime.now(tz=TURKEY_TZ)

    # 1. Baraj doluluk
    dam_fullness_pct = None
    dam_trend = None
    try:
        dam_data = client.call("dams-active-fullness", postprocess=False)
        items = _parse_items(dam_data)
        if items:
            values = [float(item.get("activeFullness") or item.get("value") or 0.0) for item in items if item.get("activeFullness") or item.get("value")]
            if values:
                dam_fullness_pct = round(sum(values) / len(values), 1)
                if len(values) >= 2:
                    diff = values[-1] - values[-2]
                    dam_trend = "increasing" if diff > 0.5 else "declining" if diff < -0.5 else "stable"
                else:
                    dam_trend = "stable"
    except Exception as e:
        print(f"[grid_service] baraj verisi hatası: {e}")

    # 2. PTF (Piyasa Takas Fiyatı)
    ptf_tl_per_mwh = None
    try:
        ptf_start = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:00:00+03:00")
        ptf_end = now.strftime("%Y-%m-%dT%H:00:00+03:00")
        mcp_data = client.call("mcp", postprocess=False, start_date=ptf_start, end_date=ptf_end)
        items = _parse_items(mcp_data)
        if items:
            last = items[-1]
            ptf_tl_per_mwh = float(last.get("price") or last.get("mcp") or last.get("value") or 0.0)
    except Exception as e:
        print(f"[grid_service] PTF verisi hatası: {e}")

    # 3. Arz-talep dengesi
    supply_demand_mw = None
    try:
        sd_start = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:00:00+03:00")
        sd_end = now.strftime("%Y-%m-%dT%H:00:00+03:00")
        sd_data = client.call("supply-demand", postprocess=False, start_date=sd_start, end_date=sd_end)
        items = _parse_items(sd_data)
        if items:
            last = items[-1]
            supply = float(last.get("supply") or last.get("totalSupply") or 0.0)
            demand = float(last.get("demand") or last.get("totalDemand") or 0.0)
            if supply > 0 or demand > 0:
                supply_demand_mw = round(supply - demand, 1)
    except Exception as e:
        print(f"[grid_service] arz-talep verisi hatası: {e}")

    # 4. Planlı kesintiler
    planned_outages: list[PlannedOutage] = []
    try:
        outage_start = now.strftime("%Y-%m-%dT00:00:00+03:00")
        outage_end = (now + timedelta(days=7)).strftime("%Y-%m-%dT23:59:59+03:00")
        po_data = client.call("planned-outages", postprocess=False, start_date=outage_start, end_date=outage_end)
        items = _parse_items(po_data)
        for item in items[:20]:  # maksimum 20 kesinti
            try:
                planned_outages.append(PlannedOutage(
                    plant_name=item.get("powerPlantName") or item.get("name") or "Bilinmiyor",
                    start_time=datetime.fromisoformat(item.get("startDate") or item.get("start") or ""),
                    end_time=datetime.fromisoformat(item.get("endDate") or item.get("end") or ""),
                    capacity_mw=float(item.get("capacity") or item.get("capacityMw") or 0.0),
                ))
            except Exception:
                continue
    except Exception as e:
        print(f"[grid_service] planlı kesinti verisi hatası: {e}")

    # 5. Şebeke stresi skoru
    stress_score = 0
    if supply_demand_mw is not None:
        if supply_demand_mw < 0:
            stress_score += 2
        elif supply_demand_mw < 500:
            stress_score += 1
    if dam_fullness_pct is not None and dam_fullness_pct < 40:
        stress_score += 1
    if dam_trend == "declining":
        stress_score += 1
    grid_stress = "high" if stress_score >= 3 else "medium" if stress_score >= 1 else "low"

    return GridStatus(
        dam_fullness_pct=dam_fullness_pct,
        dam_trend=dam_trend,
        ptf_tl_per_mwh=ptf_tl_per_mwh,
        supply_demand_mw=supply_demand_mw,
        planned_outages=planned_outages,
        grid_stress=grid_stress,
        updated_at=datetime.now(tz=TURKEY_TZ),
        source="epias",
    )


def _fetch_ptf_hourly_live(hours: int) -> dict[datetime, float]:
    client = _get_eptr_client()
    now = datetime.now(tz=TURKEY_TZ)
    start = (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:00:00+03:00")
    end = now.strftime("%Y-%m-%dT%H:00:00+03:00")
    try:
        data = client.call("mcp", postprocess=False, start_date=start, end_date=end)
        items = _parse_items(data)
        result = {}
        for item in items:
            try:
                dt = datetime.fromisoformat(item.get("date") or item.get("startDate") or "")
                price = float(item.get("price") or item.get("mcp") or item.get("value") or 0.0)
                result[dt] = price
            except Exception:
                continue
        return result
    except Exception as e:
        print(f"[grid_service] PTF saatlik verisi hatası: {e}")
        return {}


async def get_grid_status() -> GridStatus:
    cached = _cache_get("grid_status")
    if cached:
        return cached

    if _is_mock_mode():
        result = _generate_mock_grid_status()
        _cache_set("grid_status", result, GRID_TTL)
        return result

    try:
        result = await asyncio.to_thread(_fetch_grid_status_live)
    except Exception as e:
        print(f"[grid_service] get_grid_status hatası, mock kullanılıyor: {e}")
        result = _generate_mock_grid_status()

    _cache_set("grid_status", result, GRID_TTL)
    return result


async def get_ptf_hourly(hours: int = 24) -> dict[datetime, float]:
    cache_key = f"ptf_hourly_{hours}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    if _is_mock_mode():
        return {}

    result = await asyncio.to_thread(_fetch_ptf_hourly_live, hours)
    _cache_set(cache_key, result, GRID_TTL)
    return result
