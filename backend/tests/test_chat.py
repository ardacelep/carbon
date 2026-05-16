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
