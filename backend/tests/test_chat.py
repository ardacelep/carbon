import json
import pytest
from unittest.mock import AsyncMock, patch

CHAT_BODY = {"message": "Bugün ne zaman çalıştırmalıyım?", "history": []}


def test_chat_no_auth_401(client_no_auth):
    r = client_no_auth.post("/api/chat", json=CHAT_BODY)
    assert r.status_code == 401


def test_chat_200(client):
    r = client.post("/api/chat", json=CHAT_BODY)
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert len(data["reply"]) > 0
    assert "timestamp" in data


def test_chat_with_history(client):
    body = {
        "message": "Tekrar söyle",
        "history": [
            {"role": "user", "content": "Merhaba"},
            {"role": "assistant", "content": "Merhaba, nasıl yardımcı olabilirim?"},
        ],
    }
    r = client.post("/api/chat", json=body)
    assert r.status_code == 200


def test_chat_message_too_long_422(client):
    r = client.post("/api/chat", json={"message": "x" * 2001, "history": []})
    assert r.status_code == 422


def test_chat_empty_message_422(client):
    r = client.post("/api/chat", json={"message": "", "history": []})
    assert r.status_code == 422


def test_stream_no_auth_401(client_no_auth):
    r = client_no_auth.post("/api/chat/stream", json=CHAT_BODY)
    assert r.status_code == 401


def test_stream_200_sse(client):
    r = client.post("/api/chat/stream", json=CHAT_BODY)
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]


def test_stream_body_contains_done(client):
    r = client.post("/api/chat/stream", json=CHAT_BODY)
    assert "[DONE]" in r.text


def test_stream_body_has_tokens(client):
    r = client.post("/api/chat/stream", json=CHAT_BODY)
    lines = [l for l in r.text.splitlines() if l.startswith("data: ") and "[DONE]" not in l]
    assert len(lines) > 0


# --- _execute_tool unit tests ---

@pytest.mark.asyncio
async def test_execute_tool_create_job_no_user():
    from llm_service import _execute_tool
    result = await _execute_tool("create_job", json.dumps({"name": "Test", "duration_hours": 2, "power_kw": 100}), user_id=None)
    assert "error" in result


@pytest.mark.asyncio
async def test_execute_tool_unknown_tool():
    from llm_service import _execute_tool
    result = await _execute_tool("nonexistent_tool", "{}", user_id=None)
    assert "error" in result


@pytest.mark.asyncio
async def test_execute_tool_find_best_window_cost_weight():
    from llm_service import _execute_tool
    result = await _execute_tool(
        "find_best_window",
        json.dumps({"duration_hours": 2, "power_kw": 100, "cost_weight": 0.5}),
        user_id=None,
    )
    assert "start_time" in result
    assert "avg_carbon_intensity" in result


@pytest.mark.asyncio
async def test_execute_tool_create_job_with_user():
    from llm_service import _execute_tool

    fake_row = {"id": 42, "name": "AI Testi", "status": "scheduled", "created_at": "2026-05-16T12:00:00+03:00"}
    with patch("database.create_job", new=AsyncMock(return_value=fake_row)):
        result = await _execute_tool(
            "create_job",
            json.dumps({"name": "AI Testi", "duration_hours": 2, "power_kw": 100, "cost_weight": 0.0}),
            user_id="test-user-id",
        )
    assert result["job_id"] == 42
    assert result["status"] == "scheduled"
    assert "optimal_window" in result
