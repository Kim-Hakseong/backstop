"""R5 불변식: 재생 중 외부 호출은 0건이다.

Fleet 트랙의 "프로덕션 데이터 안전 취급" 요구가 이 파일 하나에 걸려 있다.
재생은 과거 원장을 새 버전에 먹이는 일이므로, 실수로 도구가 진짜 실행되면
**감사 도구가 감사 대상을 오염시킨다.** 6주 전 발주가 오늘 다시 나간다.

소켓을 몽키패치해서 강제한다. 재생 중 소켓이 열리면 테스트가 실패한다.
"""

import socket

import pytest

from backstop.replay import IntentCollector, ReplayHarness
from subject_agent.tools import erp, mail, payment


@pytest.fixture
def no_network(monkeypatch):
    """소켓 연결을 전부 막는다. 재생이 네트워크를 건드리면 여기서 터진다."""
    opened: list = []

    def forbidden(*args, **kwargs):
        opened.append(args)
        raise AssertionError(
            "재생 중 네트워크 연결이 시도됐다. ReplayHarness 가 도구를 실제로 "
            "실행하고 있다 — R5 위반."
        )

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    return opened


@pytest.fixture
def clean_stubs():
    """스텁의 부작용 기록을 비운다. 재생 후 늘어나면 실행된 것이다."""
    erp.ISSUED_POS.clear()
    mail.SENT.clear()
    payment.SCHEDULED.clear()
    yield
    erp.ISSUED_POS.clear()
    mail.SENT.clear()
    payment.SCHEDULED.clear()


def test_replay_opens_no_sockets(no_network, clean_stubs, tmp_path):
    harness = ReplayHarness.from_fixture("fixtures/ledger_6w.jsonl")
    result = harness.replay(version="v1")

    assert result.intents, "재생이 아무 의도도 수집하지 못했다 — 검증이 무의미해진다"
    assert no_network == []


def test_replay_executes_no_tools(no_network, clean_stubs):
    """소켓을 안 여는 것만으로는 부족하다. 스텁은 네트워크 없이도 부작용을 남긴다."""
    harness = ReplayHarness.from_fixture("fixtures/ledger_6w.jsonl")
    harness.replay(version="v1")

    assert erp.ISSUED_POS == []
    assert mail.SENT == []
    assert payment.SCHEDULED == []


def test_intent_collector_records_instead_of_calling():
    collector = IntentCollector(run_id="run-1")
    response = collector("erp.create_po", {"vendor_id": "acme-corp", "amount_usd": 4200})

    assert len(collector.intents) == 1
    assert collector.intents[0].tool_name == "erp.create_po"
    assert isinstance(response, dict)  # 워크플로가 계속 진행할 수 있어야 한다
    assert erp.ISSUED_POS == []


def test_intent_collector_canonicalizes_args():
    collector = IntentCollector(run_id="run-1")
    collector("erp.create_po", {"vendor_id": " acme-corp ", "amount_usd": 4200.0})

    assert collector.intents[0].args_canonical == {
        "vendor_id": "acme-corp",
        "amount_usd": 4200,
    }


def test_intent_keys_match_the_execution_path_keys():
    """재생 의도의 키는 실행 경로가 만드는 키와 같은 함수로 계산돼야 한다.

    다른 함수로 계산하면 게이트가 비교하는 두 집합이 애초에 다른 공간에 있게 된다.
    """
    from backstop.ledger import effect_key

    args = {"vendor_id": "acme-corp", "amount_usd": 4200}
    collector = IntentCollector(run_id="run-9")
    collector("erp.create_po", args)

    assert collector.intents[0].idem_key == effect_key("erp.create_po", args, "run-9")
