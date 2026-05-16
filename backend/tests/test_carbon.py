def test_current_carbon_200(client):
    r = client.get("/api/carbon/current")
    assert r.status_code == 200
    data = r.json()
    assert data["carbon_intensity"] > 0
    assert 0.0 <= data["renewable_ratio"] <= 1.0
    assert data["source"] in ("epias", "mock", "fallback")
    assert "updated_minutes_ago" in data
    assert data["updated_minutes_ago"] >= 0


def test_current_carbon_has_timestamp(client):
    r = client.get("/api/carbon/current")
    assert r.status_code == 200
    assert "timestamp" in r.json()


def test_forecast_default_24_points(client):
    r = client.get("/api/carbon/forecast")
    assert r.status_code == 200
    data = r.json()
    assert len(data["points"]) == 24


def test_forecast_ptf_filled(client):
    r = client.get("/api/carbon/forecast")
    assert r.status_code == 200
    points = r.json()["points"]
    assert points[0]["ptf_tl_per_mwh"] is not None
    assert points[0]["ptf_tl_per_mwh"] > 0


def test_forecast_confidence_decreases(client):
    r = client.get("/api/carbon/forecast")
    points = r.json()["points"]
    assert points[0]["confidence"] > points[-1]["confidence"]


def test_forecast_custom_hours(client):
    r = client.get("/api/carbon/forecast?hours=6")
    assert r.status_code == 200
    assert len(r.json()["points"]) == 6


def test_forecast_hours_too_low_422(client):
    r = client.get("/api/carbon/forecast?hours=0")
    assert r.status_code == 422


def test_forecast_hours_too_high_422(client):
    r = client.get("/api/carbon/forecast?hours=49")
    assert r.status_code == 422


def test_forecast_source_field(client):
    r = client.get("/api/carbon/forecast")
    assert r.json()["source"] in ("epias", "epias-partial", "fallback", "mock")
