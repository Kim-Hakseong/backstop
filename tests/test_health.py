"""P0 게이트의 로컬 대응물. 배포 전에 /health가 200인지 여기서 먼저 깨진다."""

from fastapi.testclient import TestClient

from api.main import app


def test_health_returns_200():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
