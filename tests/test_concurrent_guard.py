"""R8: 동시 실행에서도 부작용은 한 번만 나간다.

이 파일은 **실제로 새어나간 버그**를 고정한다. Pub/Sub 가 tick 3건을 동시에 밀어넣자
같은 스텝이 두 워커에서 동시에 실행됐고, 원장에 같은 부작용이 2건 남았다
(`mail.send#MSG-CA2473` ×2). 원인은 관문 ①이 "조회 후 실행 후 기록"이었기 때문이다.
두 워커가 모두 "기록 없음"을 보고 둘 다 지나갔다.

지금은 실행 **전에** 키를 선점한다. 선점이 원자적이라 한쪽만 이긴다.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from backstop.clock import FrozenClock
from backstop.ledger import COMMITTED, PENDING, InMemoryLedger
from subject_agent.callbacks import LedgerCallbacks

TOOL = SimpleNamespace(name="mail.send")
ARGS = {"to": "ap@acme.example", "subject": "Documents received", "body": "thanks"}
RESPONSE = {"message_id": "MSG-CA2473"}


def test_two_workers_racing_on_the_same_step_produce_one_effect():
    """동시 tick 2건. 실행 순서를 인터리브해 실제 경합을 흉내낸다."""
    ledger = InMemoryLedger(clock=FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc)))
    worker_a = LedgerCallbacks(ledger, "run-1")
    worker_b = LedgerCallbacks(ledger, "run-1")

    ctx_a = SimpleNamespace(function_call_id="a")
    ctx_b = SimpleNamespace(function_call_id="b")

    # 둘 다 도구를 실행하기 전에 before 를 통과하려 시도한다 — 이게 경합 창이다
    a_short = worker_a.before_tool(tool=TOOL, args=ARGS, tool_context=ctx_a)
    b_short = worker_b.before_tool(tool=TOOL, args=ARGS, tool_context=ctx_b)

    # 정확히 한쪽만 실행 허가를 받아야 한다
    assert [a_short, b_short].count(None) == 1

    worker_a.after_tool(
        tool=TOOL, args=ARGS, tool_context=ctx_a, tool_response=a_short or RESPONSE
    )
    worker_b.after_tool(
        tool=TOOL, args=ARGS, tool_context=ctx_b, tool_response=b_short or RESPONSE
    )

    assert len(ledger.effects("run-1")) == 1


def test_ten_racing_workers_produce_one_effect():
    ledger = InMemoryLedger(clock=FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc)))
    workers = [LedgerCallbacks(ledger, "run-1") for _ in range(10)]
    contexts = [SimpleNamespace(function_call_id=f"w{i}") for i in range(10)]

    shorts = [
        w.before_tool(tool=TOOL, args=ARGS, tool_context=c)
        for w, c in zip(workers, contexts)
    ]
    assert shorts.count(None) == 1, "정확히 한 워커만 실행해야 한다"

    for w, c, s in zip(workers, contexts, shorts):
        w.after_tool(tool=TOOL, args=ARGS, tool_context=c, tool_response=s or RESPONSE)

    assert len(ledger.effects("run-1")) == 1


def test_claim_is_pending_until_the_tool_finishes():
    """선점 직후에는 pending 이다. 확정 전 상태가 '나간 부작용'으로 세어지면 안 된다."""
    ledger = InMemoryLedger(clock=FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc)))
    cb = LedgerCallbacks(ledger, "run-1")
    ctx = SimpleNamespace(function_call_id="a")

    cb.before_tool(tool=TOOL, args=ARGS, tool_context=ctx)

    assert ledger.all_effects("run-1")[0].status == PENDING
    assert ledger.effects("run-1") == []  # 아직 나가지 않았다

    cb.after_tool(tool=TOOL, args=ARGS, tool_context=ctx, tool_response=RESPONSE)

    assert ledger.all_effects("run-1")[0].status == COMMITTED
    assert len(ledger.effects("run-1")) == 1


def test_loser_receives_the_winners_result_once_committed():
    ledger = InMemoryLedger(clock=FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc)))
    winner = LedgerCallbacks(ledger, "run-1")
    ctx_w = SimpleNamespace(function_call_id="w")
    winner.before_tool(tool=TOOL, args=ARGS, tool_context=ctx_w)
    winner.after_tool(
        tool=TOOL, args=ARGS, tool_context=ctx_w, tool_response=RESPONSE
    )

    loser = LedgerCallbacks(ledger, "run-1")
    blocked = loser.before_tool(
        tool=TOOL, args=ARGS, tool_context=SimpleNamespace(function_call_id="l")
    )

    assert blocked is not None
    assert blocked["message_id"] == "MSG-CA2473"
