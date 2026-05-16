VALID_JOB = {"name": "Test İşi", "duration_hours": 2, "power_kw": 100, "priority": 1}


def test_create_job_201(client):
    r = client.post("/api/jobs", json=VALID_JOB)
    assert r.status_code == 201
    data = r.json()
    assert data["id"] > 0
    assert data["name"] == VALID_JOB["name"]
    assert data["status"] in ("pending", "scheduled")


def test_create_job_has_optimal_window(client):
    r = client.post("/api/jobs", json=VALID_JOB)
    data = r.json()
    assert data["optimal_window"] is not None
    assert data["optimal_window"]["avg_carbon_intensity"] > 0
    assert data["optimal_window"]["estimated_savings_pct"] >= 0.0


def test_create_job_no_auth_401(client_no_auth):
    r = client_no_auth.post("/api/jobs", json=VALID_JOB)
    assert r.status_code == 401


def test_create_job_invalid_duration_422(client):
    r = client.post("/api/jobs", json={**VALID_JOB, "duration_hours": 0})
    assert r.status_code == 422


def test_create_job_duration_too_large_422(client):
    r = client.post("/api/jobs", json={**VALID_JOB, "duration_hours": 73})
    assert r.status_code == 422


def test_create_job_invalid_power_422(client):
    r = client.post("/api/jobs", json={**VALID_JOB, "power_kw": 0})
    assert r.status_code == 422


def test_create_job_invalid_priority_422(client):
    r = client.post("/api/jobs", json={**VALID_JOB, "priority": 6})
    assert r.status_code == 422


def test_list_jobs_empty(client):
    r = client.get("/api/jobs")
    assert r.status_code == 200
    data = r.json()
    assert data["jobs"] == []
    assert data["total"] == 0


def test_list_jobs_after_create(client):
    client.post("/api/jobs", json=VALID_JOB)
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_list_jobs_no_auth_401(client_no_auth):
    r = client_no_auth.get("/api/jobs")
    assert r.status_code == 401


def test_get_templates_no_auth_200(client):
    r = client.get("/api/jobs/templates")
    assert r.status_code == 200
    templates = r.json()
    assert len(templates) == 7
    for t in templates:
        assert "name" in t
        assert "duration_hours" in t
        assert "power_kw" in t
        assert "priority" in t
        assert "description" in t


def test_analyze_job_returns_reply(client):
    r = client.post("/api/jobs/analyze", json=VALID_JOB)
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert len(data["reply"]) > 0
    assert VALID_JOB["name"] in data["reply"]


def test_analyze_job_has_optimal_window(client):
    r = client.post("/api/jobs/analyze", json=VALID_JOB)
    assert r.status_code == 200
    data = r.json()
    assert data["optimal_window"] is not None
    assert data["current_carbon_intensity"] > 0


def test_analyze_job_no_db_save(client):
    client.post("/api/jobs/analyze", json=VALID_JOB)
    jobs = client.get("/api/jobs").json()
    assert jobs["total"] == 0  # analyze endpoint does not save to DB


def test_analyze_no_auth_401(client_no_auth):
    r = client_no_auth.post("/api/jobs/analyze", json=VALID_JOB)
    assert r.status_code == 401


def test_get_job_404(client):
    r = client.get("/api/jobs/99999")
    assert r.status_code == 404


def test_get_job_after_create(client):
    created = client.post("/api/jobs", json=VALID_JOB).json()
    r = client.get(f"/api/jobs/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_delete_job_404(client):
    r = client.delete("/api/jobs/99999")
    assert r.status_code == 404


def test_delete_job_after_create(client):
    created = client.post("/api/jobs", json=VALID_JOB).json()
    r = client.delete(f"/api/jobs/{created['id']}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_patch_status_invalid_422(client):
    created = client.post("/api/jobs", json=VALID_JOB).json()
    r = client.patch(
        f"/api/jobs/{created['id']}/status",
        json={"status": "flying"},
    )
    assert r.status_code == 422


def test_patch_status_valid(client):
    created = client.post("/api/jobs", json=VALID_JOB).json()
    r = client.patch(
        f"/api/jobs/{created['id']}/status",
        json={"status": "running"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "running"


def test_patch_status_all_valid_values(client):
    for status in ("pending", "scheduled", "running", "completed", "cancelled"):
        client.post("/api/jobs", json=VALID_JOB)
        jobs = client.get("/api/jobs").json()["jobs"]
        jid = jobs[-1]["id"]
        r = client.patch(f"/api/jobs/{jid}/status", json={"status": status})
        assert r.status_code == 200, f"status={status} failed"
