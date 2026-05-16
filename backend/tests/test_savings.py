VALID_JOB = {"name": "Test İşi", "duration_hours": 2, "power_kw": 100, "priority": 1}


def test_savings_empty(client):
    r = client.get("/api/savings/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["total_jobs"] == 0
    assert data["optimized_jobs"] == 0
    assert data["total_carbon_saved_kg"] == 0.0
    assert data["total_energy_kwh"] == 0.0


def test_savings_no_auth_401(client_no_auth):
    r = client_no_auth.get("/api/savings/summary")
    assert r.status_code == 401


def test_savings_summary_fields(client):
    r = client.get("/api/savings/summary")
    data = r.json()
    for field in ("total_jobs", "optimized_jobs", "total_carbon_saved_kg",
                  "total_energy_kwh", "avg_carbon_intensity", "best_saving_pct"):
        assert field in data, f"Eksik alan: {field}"


def test_savings_after_job_creation(client):
    client.post("/api/jobs", json=VALID_JOB)
    r = client.get("/api/savings/summary")
    data = r.json()
    assert data["total_jobs"] == 1
    assert data["total_energy_kwh"] == VALID_JOB["power_kw"] * VALID_JOB["duration_hours"]


def test_savings_carbon_saved_positive_when_optimized(client):
    client.post("/api/jobs", json=VALID_JOB)
    r = client.get("/api/savings/summary")
    data = r.json()
    if data["optimized_jobs"] > 0:
        assert data["total_carbon_saved_kg"] >= 0.0
        assert data["best_saving_pct"] >= 0.0
