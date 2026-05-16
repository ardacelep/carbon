import asyncio
import os

os.environ.setdefault("MOCK_MODE", "true")
os.environ.setdefault("SUPABASE_URL", "http://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("NVIDIA_API_KEY", "test-nvidia-key")

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from main import app, get_current_user
import carbon_service
import grid_service


class _SupabaseChain:
    """MagicMock-like chain that returns self on every attribute/call except execute (async)."""

    def __getattr__(self, name: str):
        return self

    def __call__(self, *args, **kwargs):
        return self

    async def execute(self, *args, **kwargs):
        return type("Result", (), {"data": []})()


_SUPABASE_MOCK = _SupabaseChain()

TEST_USER_ID = "test-user-00000000-0000-0000-0000-000000000001"

_jobs: dict[int, dict] = {}
_counter: dict = {"n": 0}


def _next_id() -> int:
    _counter["n"] += 1
    return _counter["n"]


def _make_row(uid: str, body, window=None) -> dict:
    return {
        "id": _next_id(),
        "user_id": uid,
        "name": body.name,
        "duration_hours": body.duration_hours,
        "deadline": body.deadline.isoformat() if body.deadline else None,
        "priority": body.priority,
        "power_kw": body.power_kw,
        "status": "scheduled" if window else "pending",
        "created_at": "2026-05-16T12:00:00+03:00",
        "scheduled_start": window.start_time.isoformat() if window else None,
        "optimal_start_time": window.start_time.isoformat() if window else None,
        "optimal_end_time": window.end_time.isoformat() if window else None,
        "avg_carbon_intensity": window.avg_carbon_intensity if window else None,
        "estimated_savings_pct": window.estimated_savings_pct if window else None,
        "reasoning": window.reasoning if window else None,
        "ai_recommendation": None,
    }


async def _create_job(uid, body, window, ai_rec):
    row = _make_row(uid, body, window)
    _jobs[row["id"]] = row
    return row


async def _get_jobs(uid):
    return [r for r in _jobs.values() if r["user_id"] == uid]


async def _get_job(jid, uid):
    r = _jobs.get(jid)
    return r if (r and r["user_id"] == uid) else None


async def _update_job(jid, uid, updates):
    r = _jobs.get(jid)
    if not r or r["user_id"] != uid:
        return None
    r.update(updates)
    return r


async def _noop_auto_progress():
    pass


async def _mock_stream(*args, **kwargs):
    import json
    yield f'data: {json.dumps({"token": "Test "})}\n\n'
    yield f'data: {json.dumps({"token": "yanıt"})}\n\n'
    yield "data: [DONE]\n\n"


@pytest.fixture(scope="session")
def client():
    app.dependency_overrides[get_current_user] = lambda: TEST_USER_ID

    with (
        patch("main._auto_progress_jobs", new=_noop_auto_progress),
        patch("main.create_job", new=AsyncMock(side_effect=_create_job)),
        patch("main.get_jobs", new=AsyncMock(side_effect=_get_jobs)),
        patch("main.get_job", new=AsyncMock(side_effect=_get_job)),
        patch("main.update_job", new=AsyncMock(side_effect=_update_job)),
        patch("main.get_supabase", new=AsyncMock(return_value=_SUPABASE_MOCK)),
        patch("main.get_job_recommendation", new=AsyncMock(return_value=None)),
        patch("main.get_chat_response", new=AsyncMock(return_value="Test karbon yanıtı")),
        patch("main.stream_chat_response", new=_mock_stream),
    ):
        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clear_store():
    _jobs.clear()
    _counter["n"] = 0
    carbon_service._cache.clear()
    grid_service._cache.clear()
    yield


@pytest.fixture
def client_no_auth(client):
    from fastapi import HTTPException

    async def _reject():
        raise HTTPException(status_code=401, detail="Bearer token gerekli")

    app.dependency_overrides[get_current_user] = _reject
    yield client
    app.dependency_overrides[get_current_user] = lambda: TEST_USER_ID


