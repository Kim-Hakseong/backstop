"""T2.1: Pub/Sub push 봉투를 받아 스텝을 전진시킨다.

Pub/Sub 는 본문을 base64 로 감싸 보낸다. 봉투 해석이 틀리면 엔드포인트는 200 을
돌려주는데 아무 일도 일어나지 않는다 — 조용히 실패하는 종류라 테스트로 고정한다.
"""

import base64
import json

from api.main import TickRequest


def envelope(data: dict | str | None = None, attributes: dict | None = None):
    message: dict = {}
    if data is not None:
        raw = data if isinstance(data, str) else json.dumps(data)
        message["data"] = base64.b64encode(raw.encode()).decode()
    if attributes is not None:
        message["attributes"] = attributes
    return TickRequest(message=message, subscription="projects/x/subscriptions/y")


def test_reads_run_id_from_json_payload():
    assert envelope({"run_id": "run-42"}).resolve_run_id() == "run-42"


def test_reads_run_id_from_attributes():
    assert envelope(None, {"run_id": "run-7"}).resolve_run_id() == "run-7"


def test_attributes_win_over_payload():
    req = envelope({"run_id": "from-body"}, {"run_id": "from-attrs"})
    assert req.resolve_run_id() == "from-attrs"


def test_accepts_bare_string_payload():
    assert envelope("run-bare").resolve_run_id() == "run-bare"


def test_direct_call_without_pubsub_envelope():
    assert TickRequest(run_id="run-direct").resolve_run_id() == "run-direct"


def test_falls_back_to_default_run():
    assert TickRequest().resolve_run_id() == "run-default"


def test_repeated_ticks_actually_advance_the_cursor(monkeypatch):
    """봉투 해석만 맞고 상태가 안 남으면 tick 은 200 을 주면서 아무 일도 안 한다.

    실제로 그랬다: `default_ledger()` 가 요청마다 새 인메모리 원장을 만들어
    커서가 계속 1 이었다.
    """
    from fastapi.testclient import TestClient

    from api.main import app
    from backstop.ledger import reset_default_ledger

    monkeypatch.setenv("BACKSTOP_OFFLINE", "1")
    reset_default_ledger()
    client = TestClient(app)

    cursors = [
        client.post("/tick", json={"run_id": "adv"}).json()["cursor"] for _ in range(3)
    ]
    assert cursors == [1, 2, 3]

    state = client.get("/runs/adv").json()
    assert state["cursor"] == 3
    assert state["effects"] == 3
    reset_default_ledger()
