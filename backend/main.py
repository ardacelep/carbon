import os
import math
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

from models import (
    UserCreate, UserLogin, TokenResponse,
    JobCreate, JobResponse, JobListResponse, JobStatusUpdate, JobPinUpdate,
    JobTemplate, JobAnalyzeRequest, JobAnalyzeResponse,
    ChatRequest, ChatResponse,
    CurrentCarbonResponse, ForecastResponse, SavingsSummary,
    GridStatus,
    ScheduleResponse, ScheduledJobEntry, ScheduleSummary, OptimalWindow,
    AnomalyReport, ForecastAccuracyResponse,
)
from carbon_service import get_current_carbon, get_forecast
from grid_service import get_grid_status
from anomaly_service import get_anomaly_report, get_accuracy_report
from scheduler import find_optimal_window, schedule_multiple_jobs
from llm_service import get_chat_response, get_job_recommendation, stream_chat_response
from database import get_supabase, create_job, get_jobs, get_job, update_job, _row_to_job_response

load_dotenv()

TURKEY_TZ = timezone(timedelta(hours=3))

app = FastAPI(
    title="Karbon Zeka API",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": True},
)

_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://undistractedly-gimlety-angelena.ngrok-free.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "ngrok-skip-browser-warning"],
)


# --- Startup ---

@app.on_event("startup")
async def startup():
    import asyncio
    asyncio.create_task(_auto_progress_jobs())


async def _auto_progress_jobs():
    import asyncio
    while True:
        await asyncio.sleep(15)
        try:
            supabase = await get_supabase()
            now = datetime.now(tz=TURKEY_TZ)
            now_iso = now.isoformat()

            await supabase.table("jobs") \
                .update({"status": "running"}) \
                .eq("status", "scheduled") \
                .not_.is_("scheduled_start", "null") \
                .lte("scheduled_start", now_iso) \
                .execute()

            result = await supabase.table("jobs") \
                .select("id,scheduled_start,duration_hours") \
                .eq("status", "running") \
                .execute()
            for row in result.data:
                start = datetime.fromisoformat(row["scheduled_start"])
                if start.tzinfo is None:
                    start = start.replace(tzinfo=TURKEY_TZ)
                end = start + timedelta(hours=row["duration_hours"])
                if now >= end:
                    await supabase.table("jobs") \
                        .update({"status": "completed"}) \
                        .eq("id", row["id"]) \
                        .execute()
        except Exception as e:
            print(f"[auto-progress] hata: {e}")


# --- Auth Dependency ---

class UserContext:
    def __init__(self, user_id: str, token: str):
        self.user_id = user_id
        self.token = token

async def get_current_user(authorization: str = Header(...)) -> UserContext:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token gerekli")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        async with httpx.AsyncClient(timeout=5.0) as http:
            r = await http.get(
                f"{supabase_url}/auth/v1/user",
                headers={"Authorization": f"Bearer {token}", "apikey": supabase_key},
            )
        if r.status_code != 200:
            raise HTTPException(status_code=401, detail="Geçersiz veya süresi dolmuş token")
        return UserContext(user_id=str(r.json()["id"]), token=token)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Geçersiz veya süresi dolmuş token")


# --- Auth ---

@app.post("/api/auth/signup", response_model=TokenResponse, status_code=201)
async def signup(body: UserCreate):
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.post(
                f"{supabase_url}/auth/v1/signup",
                headers={"apikey": supabase_key, "Content-Type": "application/json"},
                json={"email": body.email, "password": body.password},
            )
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=400, detail="Kayıt başarısız")
        data = r.json()
        token = data.get("access_token")
        user_id = data.get("id") or data.get("user", {}).get("id")
        if not token or not user_id:
            raise HTTPException(status_code=400, detail="Email onayı gerekiyor — Supabase'de email onayını kapatın")
        return TokenResponse(access_token=token, user_id=str(user_id))
    except HTTPException:
        raise
    except Exception as e:
        print(f"[signup] hata: {e}")
        raise HTTPException(status_code=400, detail="Kayıt başarısız")


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(body: UserLogin):
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.post(
                f"{supabase_url}/auth/v1/token?grant_type=password",
                headers={"apikey": supabase_key, "Content-Type": "application/json"},
                json={"email": body.email, "password": body.password},
            )
        if r.status_code != 200:
            raise HTTPException(status_code=401, detail="Geçersiz email veya şifre")
        data = r.json()
        token = data.get("access_token")
        user_id = data.get("user", {}).get("id")
        if not token or not user_id:
            raise HTTPException(status_code=401, detail="Geçersiz email veya şifre")
        return TokenResponse(access_token=token, user_id=str(user_id))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Geçersiz email veya şifre")


# --- Carbon ---

@app.get("/api/carbon/current", response_model=CurrentCarbonResponse)
async def current_carbon():
    reading = await get_current_carbon()
    now = datetime.now(tz=TURKEY_TZ)
    ts = reading.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=TURKEY_TZ)
    minutes_ago = max(0, int((now - ts).total_seconds() / 60))
    return CurrentCarbonResponse(
        carbon_intensity=reading.carbon_intensity,
        renewable_ratio=reading.renewable_ratio,
        timestamp=reading.timestamp,
        source=reading.source,
        updated_minutes_ago=minutes_ago,
    )


@app.get("/api/carbon/forecast", response_model=ForecastResponse)
async def carbon_forecast(hours: int = Query(default=24, ge=1, le=48)):
    return await get_forecast(hours)


@app.get("/api/carbon/anomaly", response_model=AnomalyReport)
async def carbon_anomaly():
    return await get_anomaly_report()


@app.get("/api/carbon/forecast/accuracy", response_model=ForecastAccuracyResponse)
async def forecast_accuracy():
    return await get_accuracy_report()


# --- Grid ---

@app.get("/api/grid/status", response_model=GridStatus)
async def grid_status():
    return await get_grid_status()


# --- Jobs ---

@app.post("/api/jobs", response_model=JobResponse, status_code=201)
async def create_job_endpoint(body: JobCreate, ctx: UserContext = Depends(get_current_user)):
    current = await get_current_carbon()
    forecast = await get_forecast(24)

    # Yeni iş için geçici (provisional) yerleşim — mevcut işlerin dolu slotlarını atla.
    # Bu kilitleme değil; kullanıcı "Yeniden Optimize Et" ile tüm planı yeniden kurabilir.
    place_forecast = forecast
    try:
        occupied = _occupied_slots(await get_jobs(ctx.user_id))
        free_points = [p for p in forecast.points if _slot_key(p.timestamp) not in occupied]
        if len(free_points) >= max(1, math.ceil(body.duration_hours)):
            place_forecast = ForecastResponse(
                generated_at=forecast.generated_at, source=forecast.source, points=free_points
            )
    except Exception as e:
        print(f"[main] provisional yerleşim hatası: {e}")

    optimal_window = None
    try:
        optimal_window = find_optimal_window(
            forecast=place_forecast,
            duration_hours=body.duration_hours,
            deadline=body.deadline,
            power_kw=body.power_kw,
            current_intensity=current.carbon_intensity,
            cost_weight=body.cost_weight,
        )
    except Exception as e:
        print(f"[main] scheduler hatası: {e}")

    grid_ctx = None
    try:
        grid = await get_grid_status()
        grid_ctx = {
            "dam_fullness_pct": grid.dam_fullness_pct,
            "dam_trend": grid.dam_trend,
            "ptf_tl_per_mwh": grid.ptf_tl_per_mwh,
            "supply_demand_mw": grid.supply_demand_mw,
            "grid_stress": grid.grid_stress,
        }
    except Exception:
        pass

    ai_rec = None
    if optimal_window:
        try:
            ai_rec = await get_job_recommendation(
                job_name=body.name,
                duration_hours=body.duration_hours,
                power_kw=body.power_kw,
                optimal_window=optimal_window,
                current_intensity=current.carbon_intensity,
                grid_context=grid_ctx,
            )
        except Exception as e:
            print(f"[main] LLM hatası: {e}")

    row = await create_job(ctx.user_id, body, optimal_window, ai_rec)
    return _row_to_job_response(row)


@app.get("/api/jobs", response_model=JobListResponse)
async def list_jobs(ctx: UserContext = Depends(get_current_user)):
    rows = await get_jobs(ctx.user_id)
    jobs = [_row_to_job_response(r) for r in rows]
    return JobListResponse(jobs=jobs, total=len(jobs))


@app.get("/api/jobs/templates", response_model=list[JobTemplate])
async def get_job_templates():
    return [JobTemplate(**t) for t in JOB_TEMPLATES]


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job_endpoint(job_id: int, ctx: UserContext = Depends(get_current_user)):
    row = await get_job(job_id, ctx.user_id)
    if not row:
        raise HTTPException(status_code=404, detail="İş bulunamadı")
    return _row_to_job_response(row)


@app.delete("/api/jobs/{job_id}")
async def delete_job_endpoint(job_id: int, ctx: UserContext = Depends(get_current_user)):
    row = await get_job(job_id, ctx.user_id)
    if not row:
        raise HTTPException(status_code=404, detail="İş bulunamadı")
    supabase = await get_supabase()
    await supabase.table("jobs").delete().eq("id", job_id).eq("user_id", ctx.user_id).execute()
    return {"deleted": True}


@app.post("/api/jobs/analyze", response_model=JobAnalyzeResponse)
async def analyze_job(body: JobAnalyzeRequest, ctx: UserContext = Depends(get_current_user)):
    current = await get_current_carbon()
    forecast = await get_forecast(24)

    try:
        window = find_optimal_window(
            forecast=forecast,
            duration_hours=body.duration_hours,
            deadline=body.deadline,
            power_kw=body.power_kw,
            current_intensity=current.carbon_intensity,
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"Tahmin verisi yetersiz: {e}")

    grid_ctx = None
    try:
        grid = await get_grid_status()
        grid_ctx = {
            "dam_fullness_pct": grid.dam_fullness_pct,
            "dam_trend": grid.dam_trend,
            "ptf_tl_per_mwh": grid.ptf_tl_per_mwh,
            "supply_demand_mw": grid.supply_demand_mw,
            "grid_stress": grid.grid_stress,
        }
    except Exception:
        pass

    rec = await get_job_recommendation(
        job_name=body.name,
        duration_hours=body.duration_hours,
        power_kw=body.power_kw,
        optimal_window=window,
        current_intensity=current.carbon_intensity,
        grid_context=grid_ctx,
    )

    if rec:
        reply = (
            f"**{body.name} İş Analizi**\n\n"
            f"📅 Önerilen Pencere: {rec.date} {rec.window}\n"
            f"💚 CO₂ Tasarrufu: {rec.savings_kg:.2f} kg (%%{rec.savings_pct:.0f})\n"
            f"⚡ Mevcut Yoğunluk: {current.carbon_intensity:.0f} gCO₂/kWh\n\n"
            f"**Değerlendirme:** {rec.reasoning}\n\n"
            f"**Öneri:** {rec.action}"
        )
    else:
        reply = (
            f"**{body.name}** için optimal pencere: "
            f"{window.start_time.strftime('%d.%m %H:%M')}–{window.end_time.strftime('%H:%M')}. "
            f"Tahmini tasarruf: %{window.estimated_savings_pct:.0f}. {window.reasoning}"
        )

    return JobAnalyzeResponse(
        reply=reply,
        optimal_window=window,
        recommendation=rec,
        current_carbon_intensity=current.carbon_intensity,
    )


@app.patch("/api/jobs/{job_id}/status", response_model=JobResponse)
async def update_job_status(job_id: int, body: JobStatusUpdate, ctx: UserContext = Depends(get_current_user)):
    row = await update_job(job_id, ctx.user_id, {"status": body.status})
    if not row:
        raise HTTPException(status_code=404, detail="İş bulunamadı")
    return _row_to_job_response(row)


# --- Schedule ---

def _carbon_color(ci: float) -> str:
    if ci < 200: return "#22c55e"
    if ci < 250: return "#eab308"
    if ci < 350: return "#f97316"
    return "#ef4444"


def _build_schedule_response(rows: list[dict], windows: dict[int, object]) -> ScheduleResponse:
    entries = []
    total_saved = 0.0
    total_kwh = 0.0
    savings_list = []

    for row in rows:
        job_id = row["id"]
        window = windows.get(job_id)
        if not window:
            continue

        kwh = row["power_kw"] * row["duration_hours"]
        pct = window.estimated_savings_pct
        ci = window.avg_carbon_intensity
        if pct > 0 and pct < 100:
            baseline_ci = ci / (1 - pct / 100)
            total_saved += kwh * baseline_ci * (pct / 100) / 1000
        total_kwh += kwh
        savings_list.append(pct)

        entries.append(ScheduledJobEntry(
            job_id=job_id,
            name=row["name"],
            start_time=window.start_time,
            end_time=window.end_time,
            duration_hours=row["duration_hours"],
            power_kw=row["power_kw"],
            avg_carbon_intensity=window.avg_carbon_intensity,
            estimated_savings_pct=window.estimated_savings_pct,
            estimated_savings_tl=window.estimated_savings_tl,
            status=row["status"],
            pinned=bool(row.get("pinned")),
            color=_carbon_color(window.avg_carbon_intensity),
            reasoning=window.reasoning,
            ai_recommendation=row.get("ai_recommendation"),
        ))

    entries.sort(key=lambda e: e.start_time)

    tl_values = [e.estimated_savings_tl for e in entries if e.estimated_savings_tl is not None]
    total_cost_saved_tl = round(sum(tl_values), 2) if tl_values else None

    summary = ScheduleSummary(
        total_jobs=len(rows),
        scheduled_jobs=len(entries),
        total_carbon_saved_kg=round(total_saved, 3),
        total_energy_kwh=round(total_kwh, 2),
        avg_savings_pct=round(sum(savings_list) / len(savings_list), 1) if savings_list else 0.0,
        total_cost_saved_tl=total_cost_saved_tl,
    )
    return ScheduleResponse(
        generated_at=datetime.now(tz=TURKEY_TZ),
        jobs=entries,
        summary=summary,
    )


def _build_outage_slots(grid: GridStatus) -> set:
    slots: set = set()
    for outage in grid.planned_outages:
        ts = outage.start_time
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=TURKEY_TZ)
        end = outage.end_time
        if end.tzinfo is None:
            end = end.replace(tzinfo=TURKEY_TZ)
        while ts < end:
            slots.add(ts)
            ts += timedelta(hours=1)
    return slots


def _slot_key(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=TURKEY_TZ)
    return ts.replace(minute=0, second=0, microsecond=0)


def _occupied_slots(rows: list[dict]) -> set:
    """Aktif (planlanmış/çalışan) işlerin kapladığı saat slotları."""
    occupied: set = set()
    for r in rows:
        if r["status"] not in ("scheduled", "running") or not r.get("scheduled_start"):
            continue
        start = datetime.fromisoformat(r["scheduled_start"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=TURKEY_TZ)
        for h in range(max(1, math.ceil(r["duration_hours"]))):
            occupied.add(_slot_key(start + timedelta(hours=h)))
    return occupied


def _window_from_row(row: dict) -> OptimalWindow:
    """DB'de kayıtlı yerleşimden OptimalWindow kur (yeniden hesaplama yok)."""
    start = datetime.fromisoformat(row["scheduled_start"])
    if start.tzinfo is None:
        start = start.replace(tzinfo=TURKEY_TZ)
    end = start + timedelta(hours=row["duration_hours"])
    return OptimalWindow(
        start_time=start,
        end_time=end,
        avg_carbon_intensity=row.get("avg_carbon_intensity") or 0.0,
        estimated_savings_pct=row.get("estimated_savings_pct") or 0.0,
        estimated_savings_tl=row.get("estimated_savings_tl"),
        reasoning=row.get("reasoning") or "Planlanmış pencere.",
    )


def _fixed_interval_for_row(row: dict, base_ts: datetime, n_slots: int) -> tuple[int, int] | None:
    """Sabit işi (çalışan/sabitlenmiş/imminent) forecast slot aralığına çevir."""
    if not row.get("scheduled_start"):
        return None
    start = datetime.fromisoformat(row["scheduled_start"])
    if start.tzinfo is None:
        start = start.replace(tzinfo=TURKEY_TZ)
    idx = round((start - base_ts).total_seconds() / 3600)
    dur = max(1, math.ceil(row["duration_hours"]))
    end = idx + dur
    if end <= 0 or idx >= n_slots:
        return None
    idx = max(0, idx)
    return (idx, min(end, n_slots) - idx)


@app.get("/api/schedule", response_model=ScheduleResponse)
async def get_schedule(ctx: UserContext = Depends(get_current_user)):
    """Saf DB okuması — kayıtlı plana göre takvimi döndürür, yeniden hesaplama yapmaz."""
    rows = await get_jobs(ctx.user_id)
    placed = [
        r for r in rows
        if r["status"] in ("pending", "scheduled", "running") and r.get("scheduled_start")
    ]
    if not placed:
        return ScheduleResponse(
            generated_at=datetime.now(tz=TURKEY_TZ),
            jobs=[],
            summary=ScheduleSummary(total_jobs=0, scheduled_jobs=0,
                                    total_carbon_saved_kg=0.0, total_energy_kwh=0.0, avg_savings_pct=0.0),
        )
    windows = {r["id"]: _window_from_row(r) for r in placed}
    return _build_schedule_response(placed, windows)


@app.post("/api/schedule/optimize", response_model=ScheduleResponse)
async def optimize_schedule(ctx: UserContext = Depends(get_current_user)):
    """
    Tüm planı yeniden optimize eder. Çalışan, sabitlenmiş (pinned) ve başlamak üzere
    olan işler sabit engel sayılır — taşınmaz, üstüne iş gelmez. Geri kalan işler
    OR-Tools ile en güncel tahmine göre yeniden yerleştirilir.
    """
    rows = await get_jobs(ctx.user_id)
    active = [r for r in rows if r["status"] in ("pending", "scheduled", "running")]
    if not active:
        raise HTTPException(status_code=404, detail="Optimize edilecek iş bulunamadı")

    current = await get_current_carbon()
    forecast = await get_forecast(24)
    if not forecast.points:
        raise HTTPException(status_code=503, detail="Tahmin verisi yetersiz")

    base_ts = forecast.points[0].timestamp
    if base_ts.tzinfo is None:
        base_ts = base_ts.replace(tzinfo=TURKEY_TZ)
    n_slots = len(forecast.points)

    outage_slots: set = set()
    current_ptf = None
    try:
        grid = await get_grid_status()
        current_ptf = grid.ptf_tl_per_mwh
        outage_slots = _build_outage_slots(grid)
    except Exception:
        pass

    # Sabit (taşınmaz) vs taşınabilir iş ayrımı
    imminent_cutoff = datetime.now(tz=TURKEY_TZ) + timedelta(hours=1)
    movable: list[dict] = []
    fixed: list[dict] = []
    for r in active:
        if r["status"] == "running" or r.get("pinned"):
            fixed.append(r)
            continue
        start_iso = r.get("scheduled_start")
        if start_iso:
            st = datetime.fromisoformat(start_iso)
            if st.tzinfo is None:
                st = st.replace(tzinfo=TURKEY_TZ)
            if st <= imminent_cutoff:
                fixed.append(r)
                continue
        movable.append(r)

    fixed_intervals = [
        iv for iv in (_fixed_interval_for_row(r, base_ts, n_slots) for r in fixed) if iv
    ]

    if movable:
        windows = schedule_multiple_jobs(
            movable, forecast, current.carbon_intensity,
            outage_slots or None, current_ptf, fixed_intervals or None,
        )
        for row in movable:
            w = windows.get(row["id"])
            if not w:
                continue
            await update_job(row["id"], ctx.user_id, {
                "status": "scheduled",
                "scheduled_start": w.start_time.isoformat(),
                "optimal_start_time": w.start_time.isoformat(),
                "optimal_end_time": w.end_time.isoformat(),
                "avg_carbon_intensity": w.avg_carbon_intensity,
                "estimated_savings_pct": w.estimated_savings_pct,
                "estimated_savings_tl": w.estimated_savings_tl,
                "reasoning": w.reasoning,
            })

    updated = await get_jobs(ctx.user_id)
    active_ids = {r["id"] for r in active}
    placed = [
        r for r in updated
        if r["id"] in active_ids and r.get("scheduled_start")
    ]
    fresh_windows = {r["id"]: _window_from_row(r) for r in placed}
    return _build_schedule_response(placed, fresh_windows)


@app.patch("/api/jobs/{job_id}/pin", response_model=JobResponse)
async def update_job_pin(job_id: int, body: JobPinUpdate, ctx: UserContext = Depends(get_current_user)):
    row = await update_job(job_id, ctx.user_id, {"pinned": body.pinned})
    if not row:
        raise HTTPException(status_code=404, detail="İş bulunamadı")
    return _row_to_job_response(row)


JOB_TEMPLATES = [
    {"name": "Log Processing",          "duration_hours": 2,  "power_kw": 50,  "priority": 1, "description": "Sistem log dosyalarının işlenmesi ve arşivlenmesi"},
    {"name": "Backup İşlemi",           "duration_hours": 3,  "power_kw": 80,  "priority": 2, "description": "Kritik verilerin yedeklenmesi"},
    {"name": "ML Model Eğitimi",        "duration_hours": 8,  "power_kw": 300, "priority": 3, "description": "Makine öğrenmesi modelinin sıfırdan eğitimi"},
    {"name": "Model Fine-tuning",       "duration_hours": 12, "power_kw": 250, "priority": 3, "description": "Mevcut modelin ince ayarı"},
    {"name": "Veri Senkronizasyonu",    "duration_hours": 1,  "power_kw": 30,  "priority": 2, "description": "Veritabanları arası veri senkronizasyonu"},
    {"name": "Batch Data Processing",   "duration_hours": 6,  "power_kw": 150, "priority": 2, "description": "Toplu veri işleme ve dönüşüm"},
    {"name": "Database Optimizasyonu",  "duration_hours": 4,  "power_kw": 100, "priority": 1, "description": "Veritabanı indeks ve sorgu optimizasyonu"},
]

DEMO_JOB_TEMPLATES = [
    {"name": "Veri Yedekleme", "duration_hours": 1, "power_kw": 50, "priority": 2},
    {"name": "Model Eğitimi",  "duration_hours": 2, "power_kw": 250, "priority": 3},
    {"name": "Log Analizi",    "duration_hours": 1, "power_kw": 30, "priority": 1},
]


@app.post("/api/schedule/demo", response_model=ScheduleResponse)
async def demo_schedule(ctx: UserContext = Depends(get_current_user)):
    current = await get_current_carbon()
    forecast = await get_forecast(24)

    created_rows = []
    for tmpl in DEMO_JOB_TEMPLATES:
        from models import JobCreate
        job_body = JobCreate(**tmpl)
        window = None
        try:
            window = find_optimal_window(
                forecast=forecast,
                duration_hours=job_body.duration_hours,
                deadline=None,
                power_kw=job_body.power_kw,
                current_intensity=current.carbon_intensity,
            )
        except Exception:
            pass
        row = await create_job(ctx.user_id, job_body, window, None)
        created_rows.append(row)

    active = [r for r in created_rows if r["status"] in ("pending", "scheduled")]
    windows = schedule_multiple_jobs(active, forecast, current.carbon_intensity)

    now = datetime.now(tz=TURKEY_TZ)
    for i, row in enumerate(active):
        window = windows.get(row["id"])
        if not window:
            continue
        start = now + timedelta(seconds=15 + i * 90)
        await update_job(row["id"], ctx.user_id, {"scheduled_start": start.isoformat(), "status": "scheduled"})

    updated = await get_jobs(ctx.user_id)
    created_ids = {r["id"] for r in created_rows}
    active_updated = [r for r in updated if r["id"] in created_ids]
    return _build_schedule_response(active_updated, windows)


# --- Chat ---

@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, ctx: UserContext = Depends(get_current_user)):
    history_dicts = [{"role": m.role, "content": m.content} for m in body.history]
    reply = await get_chat_response(body.message, history_dicts, {}, user_id=ctx.user_id)
    return ChatResponse(reply=reply, timestamp=datetime.now(tz=TURKEY_TZ))


@app.post("/api/chat/stream")
async def chat_stream(body: ChatRequest, ctx: UserContext = Depends(get_current_user)):
    history_dicts = [{"role": m.role, "content": m.content} for m in body.history]

    return StreamingResponse(
        stream_chat_response(body.message, history_dicts, {}, user_id=ctx.user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# --- Savings ---

@app.get("/api/savings/summary", response_model=SavingsSummary)
async def savings_summary(ctx: UserContext = Depends(get_current_user)):
    rows = await get_jobs(ctx.user_id)

    if not rows:
        return SavingsSummary(
            total_jobs=0, optimized_jobs=0, total_carbon_saved_kg=0.0,
            total_energy_kwh=0.0, avg_carbon_intensity=0.0,
            best_saving_pct=0.0, period_start=None, period_end=None,
        )

    optimized = [r for r in rows if r.get("optimal_start_time")]

    total_carbon_saved_kg = 0.0
    for r in optimized:
        kwh = r["power_kw"] * r["duration_hours"]
        pct = (r["estimated_savings_pct"] or 0.0) / 100
        ci = r["avg_carbon_intensity"] or 0.0
        if pct < 1.0:
            baseline_ci = ci / (1 - pct)
            total_carbon_saved_kg += kwh * baseline_ci * pct / 1000

    total_energy_kwh = sum(r["power_kw"] * r["duration_hours"] for r in rows)
    avg_carbon = (
        sum(r["avg_carbon_intensity"] or 0 for r in optimized) / len(optimized)
        if optimized else 0.0
    )
    best_saving_pct = max((r["estimated_savings_pct"] or 0.0 for r in optimized), default=0.0)

    created_dates = [datetime.fromisoformat(r["created_at"]) for r in rows]

    tl_vals = [r["estimated_savings_tl"] for r in optimized if r.get("estimated_savings_tl")]
    total_cost_saved_tl = round(sum(tl_vals), 2) if tl_vals else None

    return SavingsSummary(
        total_jobs=len(rows),
        optimized_jobs=len(optimized),
        total_carbon_saved_kg=round(total_carbon_saved_kg, 3),
        total_energy_kwh=round(total_energy_kwh, 2),
        avg_carbon_intensity=round(avg_carbon, 1),
        best_saving_pct=round(best_saving_pct, 1),
        total_cost_saved_tl=total_cost_saved_tl,
        period_start=min(created_dates),
        period_end=max(created_dates),
    )


# --- Debug ---

@app.get("/api/debug/data-sources")
async def debug_data_sources():
    """Anlık veri kaynağı durumunu gösterir — mock mu, gerçek EPİAŞ mı?"""
    import carbon_service as cs
    import grid_service as gs

    carbon = await get_current_carbon()
    forecast = await get_forecast(24)
    grid = await get_grid_status()

    return {
        "mock_mode": os.getenv("MOCK_MODE", "false"),
        "api_timeout_s": float(os.getenv("API_TIMEOUT", "12.0")),
        "carbon_current": {
            "source": carbon.source,
            "carbon_intensity": carbon.carbon_intensity,
        },
        "forecast": {
            "source": forecast.source,
            "points": len(forecast.points),
            "first_ptf": forecast.points[0].ptf_tl_per_mwh if forecast.points else None,
        },
        "grid": {
            "source": grid.source,
            "ptf_tl_per_mwh": grid.ptf_tl_per_mwh,
            "dam_fullness_pct": grid.dam_fullness_pct,
        },
        "fallback_json_exists": (
            __import__("pathlib").Path(__file__).parent / "mock_epias_data.json"
        ).exists(),
    }


# --- Swagger Bearer Auth ---

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title="Karbon Zeka API", version="1.0.0", routes=app.routes)
    schema.setdefault("components", {})["securitySchemes"] = {
        "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    }
    for path in schema["paths"].values():
        for operation in path.values():
            operation["security"] = [{"BearerAuth": []}]
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi
