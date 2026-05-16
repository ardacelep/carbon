VALID_JOB = {"name": "Test İşi", "duration_hours": 2, "power_kw": 100, "priority": 1}


def test_schedule_empty_jobs(client):
    r = client.get("/api/schedule")
    assert r.status_code == 200
    data = r.json()
    assert data["jobs"] == []
    assert data["summary"]["total_jobs"] == 0
    assert data["summary"]["total_carbon_saved_kg"] == 0.0


def test_schedule_with_one_job(client):
    client.post("/api/jobs", json=VALID_JOB)
    r = client.get("/api/schedule")
    assert r.status_code == 200
    data = r.json()
    assert len(data["jobs"]) == 1
    entry = data["jobs"][0]
    assert entry["avg_carbon_intensity"] > 0
    assert entry["start_time"] is not None
    assert entry["end_time"] is not None
    assert entry["color"] in ("#22c55e", "#eab308", "#f97316", "#ef4444")


def test_schedule_no_overlap(client):
    jobs = [
        {"name": "Job A", "duration_hours": 2, "power_kw": 100, "priority": 1},
        {"name": "Job B", "duration_hours": 3, "power_kw": 200, "priority": 2},
        {"name": "Job C", "duration_hours": 1, "power_kw": 50, "priority": 1},
    ]
    for j in jobs:
        client.post("/api/jobs", json=j)

    r = client.get("/api/schedule")
    assert r.status_code == 200
    entries = r.json()["jobs"]
    assert len(entries) == 3

    # Verify no time overlap
    windows = [(e["start_time"], e["end_time"]) for e in entries]
    windows.sort()
    for i in range(len(windows) - 1):
        assert windows[i][1] <= windows[i + 1][0], "Zaman çakışması var"


def test_schedule_summary_fields(client):
    client.post("/api/jobs", json=VALID_JOB)
    r = client.get("/api/schedule")
    s = r.json()["summary"]
    assert "total_jobs" in s
    assert "scheduled_jobs" in s
    assert "total_carbon_saved_kg" in s
    assert "total_energy_kwh" in s
    assert "avg_savings_pct" in s


def test_schedule_no_auth_401(client_no_auth):
    r = client_no_auth.get("/api/schedule")
    assert r.status_code == 401


def test_approve_schedule_sets_status(client):
    client.post("/api/jobs", json=VALID_JOB)
    r = client.post("/api/schedule/approve", json={"demo_mode": False})
    assert r.status_code == 200
    data = r.json()
    assert len(data["jobs"]) == 1


def test_approve_schedule_demo_mode(client):
    client.post("/api/jobs", json=VALID_JOB)
    r = client.post("/api/schedule/approve", json={"demo_mode": True})
    assert r.status_code == 200
    data = r.json()
    assert len(data["jobs"]) == 1


def test_approve_no_auth_401(client_no_auth):
    r = client_no_auth.post("/api/schedule/approve", json={"demo_mode": False})
    assert r.status_code == 401


def test_demo_schedule_creates_three_jobs(client):
    r = client.post("/api/schedule/demo")
    assert r.status_code == 200
    data = r.json()
    assert len(data["jobs"]) == 3


def test_demo_schedule_no_auth_401(client_no_auth):
    r = client_no_auth.post("/api/schedule/demo")
    assert r.status_code == 401
