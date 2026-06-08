from fastapi.testclient import TestClient


def test_health_endpoint():
    from app.main import app

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_analysis_endpoint_smoke():
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/stocks/2330/analysis")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "2330"
    assert "recommendation" in body
    assert body["decision_plan"]["checklist"]["進場條件"]
    assert body["decision_plan"]["scenarios"]
