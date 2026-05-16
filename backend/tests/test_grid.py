def test_grid_status_200(client):
    r = client.get("/api/grid/status")
    assert r.status_code == 200
    data = r.json()
    assert "dam_fullness_pct" in data
    assert "ptf_tl_per_mwh" in data
    assert "supply_demand_mw" in data
    assert "planned_outages" in data
    assert "grid_stress" in data
    assert "updated_at" in data
    assert "source" in data


def test_grid_stress_valid_values(client):
    r = client.get("/api/grid/status")
    assert r.json()["grid_stress"] in ("low", "medium", "high")


def test_grid_planned_outages_is_list(client):
    r = client.get("/api/grid/status")
    assert isinstance(r.json()["planned_outages"], list)


def test_grid_dam_trend_valid(client):
    r = client.get("/api/grid/status")
    trend = r.json()["dam_trend"]
    assert trend is None or trend in ("increasing", "stable", "declining")


def test_grid_mock_mode_returns_data(client):
    r = client.get("/api/grid/status")
    data = r.json()
    assert data["dam_fullness_pct"] is not None
    assert data["ptf_tl_per_mwh"] is not None
