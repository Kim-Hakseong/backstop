"""T2.3: 크래시 주입 경로.

`when="now"` 는 프로세스를 진짜로 죽이므로 테스트에서 부르지 않는다. 여기서는
자물쇠와 무장(arm) 동작만 검증한다. 실제 크래시는 scripts/crash_demo.py 가 확인한다.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import _ARMED_CRASH, app


@pytest.fixture(autouse=True)
def disarm():
    _ARMED_CRASH["value"] = False
    yield
    _ARMED_CRASH["value"] = False


def test_arms_a_crash_for_the_next_tick(monkeypatch):
    monkeypatch.delenv("BACKSTOP_KILL_TOKEN", raising=False)
    resp = TestClient(app).post("/admin/kill", json={"when": "before_effect"})

    assert resp.status_code == 200
    assert resp.json()["armed"] is True
    assert _ARMED_CRASH["value"] is True


def test_token_is_required_when_configured(monkeypatch):
    """공개 URL 에 놓인 자살 버튼이다. 토큰이 설정되면 아무나 못 누른다."""
    monkeypatch.setenv("BACKSTOP_KILL_TOKEN", "secret")
    resp = TestClient(app).post("/admin/kill", json={"when": "before_effect"})

    assert resp.status_code == 403
    assert _ARMED_CRASH["value"] is False


def test_correct_token_is_accepted(monkeypatch):
    monkeypatch.setenv("BACKSTOP_KILL_TOKEN", "secret")
    resp = TestClient(app).post(
        "/admin/kill",
        json={"when": "before_effect"},
        headers={"X-Backstop-Kill": "secret"},
    )

    assert resp.status_code == 200
    assert _ARMED_CRASH["value"] is True


def test_tick_disarms_after_firing(monkeypatch):
    """무장은 1회용이다. 안 그러면 재개 tick 도 계속 죽어 재개가 증명되지 않는다."""
    monkeypatch.setenv("BACKSTOP_OFFLINE", "1")
    monkeypatch.delenv("BACKSTOP_KILL_TOKEN", raising=False)
    from backstop.ledger import reset_default_ledger

    reset_default_ledger()
    client = TestClient(app)
    client.post("/admin/kill", json={"when": "before_effect"})

    # 실제로 죽이지 않고 무장 해제 경로만 확인한다: _suicide 를 무해하게 교체
    import api.main as main

    fired = []
    monkeypatch.setattr(main, "_suicide", lambda reason: fired.append(reason))

    client.post("/tick", json={"run_id": "kill-run"})
    assert len(fired) == 1
    assert _ARMED_CRASH["value"] is False

    client.post("/tick", json={"run_id": "kill-run"})
    assert len(fired) == 1  # 두 번째 tick 은 죽지 않는다
    reset_default_ledger()
