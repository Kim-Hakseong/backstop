"""T1.3: 콜백이 원장을 만든다.

ADK 런너를 띄우지 않고 콜백을 직접 호출한다 — 콜백의 계약만 검증하면 되고,
네트워크 없이 돌아야 하기 때문이다. 라이브 종단 확인은 scripts/smoke_agent.py 가 한다.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from backstop.clock import FrozenClock
from backstop.ledger import (
    IDEMPOTENT_SKIP,
    TOOL_CALL,
    TOOL_RESULT,
    InMemoryLedger,
    effect_key,
)
from subject_agent.callbacks import LedgerCallbacks, target_of

TOOL = SimpleNamespace(name="erp.create_po")
CTX = SimpleNamespace(function_call_id="fc-1")
ARGS = {"vendor_id": "acme-corp", "amount_usd": 4200}
RESPONSE = {"po_id": "PO-8428", "vendor_id": "acme-corp"}


def make(run_id="run-1"):
    ledger = InMemoryLedger(clock=FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc)))
    return ledger, LedgerCallbacks(ledger, run_id)


def test_one_tool_call_produces_call_and_result_events():
    ledger, cb = make()
    cb.before_tool(TOOL, ARGS, CTX)
    cb.after_tool(TOOL, ARGS, CTX, RESPONSE)

    kinds = [e.kind for e in ledger.events("run-1")]
    assert kinds == [TOOL_CALL, TOOL_RESULT]


def test_event_count_matches_tool_call_count():
    """T1.3 완료 조건: 도구 호출 수만큼 이벤트가 생긴다."""
    ledger, cb = make()
    for i in range(3):
        ctx = SimpleNamespace(function_call_id=f"fc-{i}")
        cb.before_tool(TOOL, {**ARGS, "line_item": f"item-{i}"}, ctx)
        cb.after_tool(TOOL, {**ARGS, "line_item": f"item-{i}"}, ctx, RESPONSE)

    events = ledger.events("run-1")
    assert len([e for e in events if e.kind == TOOL_CALL]) == 3
    assert len(events) == 6


def test_seq_is_monotonic_and_dense():
    ledger, cb = make()
    for i in range(3):
        ctx = SimpleNamespace(function_call_id=f"fc-{i}")
        cb.before_tool(TOOL, ARGS, ctx)
        cb.after_tool(TOOL, ARGS, ctx, RESPONSE)

    assert [e.seq for e in ledger.events("run-1")] == [0, 1, 2, 3, 4, 5]


def test_effect_is_recorded_with_idempotency_key():
    ledger, cb = make()
    cb.before_tool(TOOL, ARGS, CTX)
    cb.after_tool(TOOL, ARGS, CTX, RESPONSE)

    effects = ledger.effects("run-1")
    assert len(effects) == 1
    assert effects[0].idem_key == effect_key("erp.create_po", ARGS, "run-1")
    assert effects[0].target == "erp.create_po#PO-8428"


def test_effect_links_back_to_its_tool_call_event():
    ledger, cb = make()
    cb.before_tool(TOOL, ARGS, CTX)
    cb.after_tool(TOOL, ARGS, CTX, RESPONSE)

    call_event = ledger.events("run-1")[0]
    assert ledger.effects("run-1")[0].event_id == call_event.event_id


def test_stored_args_are_canonicalized():
    """`args_canonical` 은 이름값을 해야 한다. 원본 인자를 담으면 안 된다."""
    ledger, cb = make()
    cb.before_tool(TOOL, {"vendor_id": "  acme-corp ", "amount_usd": 4200.0}, CTX)

    stored = ledger.events("run-1")[0].args_canonical
    assert stored == {"vendor_id": "acme-corp", "amount_usd": 4200}


def test_runs_are_isolated():
    ledger = InMemoryLedger(clock=FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc)))
    a = LedgerCallbacks(ledger, "run-a")
    b = LedgerCallbacks(ledger, "run-b")
    a.before_tool(TOOL, ARGS, CTX)
    b.before_tool(TOOL, ARGS, CTX)

    assert len(ledger.events("run-a")) == 1
    assert len(ledger.events("run-b")) == 1
    assert ledger.events("run-a")[0].seq == 0
    assert ledger.events("run-b")[0].seq == 0


def test_events_are_ordered_by_seq_not_insertion():
    ledger = InMemoryLedger(clock=FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc)))
    ledger.append_event(run_id="r", kind=TOOL_CALL)
    ledger.append_event(run_id="r", kind=TOOL_RESULT)
    assert [e.seq for e in ledger.events("r")] == [0, 1]


def test_ledger_uses_injected_clock():
    """R3: 원장의 시각은 주입된 시계에서 온다."""
    clock = FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc))
    ledger = InMemoryLedger(clock=clock)
    first = ledger.append_event(run_id="r", kind=TOOL_CALL)
    clock.advance(days=7)
    second = ledger.append_event(run_id="r", kind=TOOL_CALL)

    assert (second.at - first.at).days == 7


def test_find_effect_locates_by_key():
    ledger, cb = make()
    cb.before_tool(TOOL, ARGS, CTX)
    cb.after_tool(TOOL, ARGS, CTX, RESPONSE)

    key = effect_key("erp.create_po", ARGS, "run-1")
    assert ledger.find_effect("run-1", key) is not None
    assert ledger.find_effect("run-1", "nope") is None
    assert ledger.find_effect("other-run", key) is None


def test_target_falls_back_to_tool_name():
    assert target_of("mail.send", {"status": "sent"}) == "mail.send"
    assert target_of("mail.send", None) == "mail.send"
    assert target_of("erp.create_po", {"po_id": "PO-1"}) == "erp.create_po#PO-1"


def test_callbacks_accept_adk_keyword_calling_convention():
    """ADK 는 콜백을 키워드로 부른다. 이걸 위치 인자로만 테스트하면 라이브에서 터진다.

    실제로 터졌다: `TypeError: before_tool() got an unexpected keyword argument
    'tool_context'`. 단위 테스트는 전부 통과한 상태였다. 호출 규약을 여기 고정한다.
    호출 형태 출처: google/adk/flows/llm_flows/functions.py
    """
    ledger, cb = make()
    cb.before_tool(tool=TOOL, args=ARGS, tool_context=CTX)
    cb.after_tool(TOOL, args=ARGS, tool_context=CTX, tool_response=RESPONSE)

    assert [e.kind for e in ledger.events("run-1")] == [TOOL_CALL, TOOL_RESULT]
    assert len(ledger.effects("run-1")) == 1


def test_idempotent_skip_kind_exists_for_gate_one():
    """관문 ①이 일했다는 증거가 될 kind. T1.5 에서 쓴다."""
    ledger = InMemoryLedger(clock=FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc)))
    ledger.append_event(run_id="r", kind=IDEMPOTENT_SKIP, tool_name="erp.create_po")
    assert ledger.events("r")[0].kind == "idempotent_skip"
