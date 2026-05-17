import os
from datetime import datetime
from dotenv import load_dotenv
from supabase import acreate_client, AsyncClient

from models import JobCreate, JobResponse, OptimalWindow, JobRecommendation

load_dotenv()

_supabase_client: AsyncClient | None = None


async def get_supabase() -> AsyncClient:
    global _supabase_client
    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL ve SUPABASE_SERVICE_ROLE_KEY .env'de olmalı")
        _supabase_client = await acreate_client(url, key)
    return _supabase_client


def _row_to_job_response(row: dict) -> JobResponse:
    optimal_window = None
    if row.get("optimal_start_time"):
        optimal_window = OptimalWindow(
            start_time=datetime.fromisoformat(row["optimal_start_time"]),
            end_time=datetime.fromisoformat(row["optimal_end_time"]),
            avg_carbon_intensity=row["avg_carbon_intensity"] or 0.0,
            estimated_savings_pct=row["estimated_savings_pct"] or 0.0,
            estimated_savings_tl=row.get("estimated_savings_tl"),
            reasoning=row["reasoning"] or "",
        )

    ai_parsed = None
    raw = row.get("ai_recommendation")
    if raw:
        try:
            ai_parsed = JobRecommendation.model_validate_json(raw)
        except Exception:
            pass

    return JobResponse(
        id=row["id"],
        name=row["name"],
        duration_hours=row["duration_hours"],
        deadline=datetime.fromisoformat(row["deadline"]) if row.get("deadline") else None,
        priority=row["priority"],
        power_kw=row["power_kw"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        scheduled_start=datetime.fromisoformat(row["scheduled_start"]) if row.get("scheduled_start") else None,
        optimal_window=optimal_window,
        ai_recommendation=raw,
        ai_recommendation_parsed=ai_parsed,
    )


async def create_job(
    user_id: str,
    job: JobCreate,
    optimal_window: OptimalWindow | None,
    ai_recommendation: JobRecommendation | None,
) -> dict:
    payload = {
        "user_id": user_id,
        "name": job.name,
        "duration_hours": job.duration_hours,
        "deadline": job.deadline.isoformat() if job.deadline else None,
        "priority": job.priority,
        "power_kw": job.power_kw,
        "status": "scheduled" if optimal_window else "pending",
        "optimal_start_time": optimal_window.start_time.isoformat() if optimal_window else None,
        "optimal_end_time": optimal_window.end_time.isoformat() if optimal_window else None,
        "scheduled_start": optimal_window.start_time.isoformat() if optimal_window else None,
        "avg_carbon_intensity": optimal_window.avg_carbon_intensity if optimal_window else None,
        "estimated_savings_pct": optimal_window.estimated_savings_pct if optimal_window else None,
        "estimated_savings_tl": optimal_window.estimated_savings_tl if optimal_window else None,
        "reasoning": optimal_window.reasoning if optimal_window else None,
        "ai_recommendation": ai_recommendation.model_dump_json() if ai_recommendation else None,
    }
    client = await get_supabase()
    result = await client.table("jobs").insert(payload).execute()
    return result.data[0]


async def get_jobs(user_id: str) -> list[dict]:
    client = await get_supabase()
    result = await client.table("jobs").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    return result.data


async def get_job(job_id: int, user_id: str) -> dict | None:
    try:
        client = await get_supabase()
        result = await client.table("jobs").select("*").eq("id", job_id).eq("user_id", user_id).single().execute()
        return result.data
    except Exception:
        return None


async def update_job(job_id: int, user_id: str, updates: dict) -> dict | None:
    client = await get_supabase()
    result = await client.table("jobs").update(updates).eq("id", job_id).eq("user_id", user_id).execute()
    return result.data[0] if result.data else None
