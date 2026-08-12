"""R4: 모든 도구 호출은 스팬을 남기고, 원장에서 역참조 가능해야 한다."""

from datetime import datetime, timezone
from types import SimpleNamespace

from backstop.clock import FrozenClock
from backstop.ledger import IDEMPOTENT_SKIP, TOOL_CALL, InMemoryLedger
from backstop.otel import ToolSpans
from subject_agent.callbacks import LedgerCallbacks

TOOL = SimpleNamespace(name="erp.create_po")
ARGS = {"vendor_id": "acme-corp", "amount_usd": 4200}
RESPONSE = {"po_id": "PO-8428"}


def make(run_id="run-1"):
    ledger = InMemoryLedger(clock=FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc)))
    return ledger, LedgerCallbacks(ledger, run_id)


def call(cb, args=ARGS, slot="fc-1", response=RESPONSE):
    ctx = SimpleNamespace(function_call_id=slot)
    sc = cb.before_tool(tool=TOOL, args=args, tool_context=ctx)
    cb.after_tool(
        tool=TOOL, args=args, tool_context=ctx, tool_response=sc or response
    )
    return sc


def test_span_ids_are_real_not_zeros():
    """provider 가 없으면 OTel 은 id 를 전부 0 으로 준다. 그러면 역참조가 불가능하다."""
    spans = ToolSpans()
    trace_id, span_id = spans.start("slot", "erp.create_po")

    assert trace_id and span_id
    assert len(trace_id) == 32 and len(span_id) == 16
    assert set(trace_id) != {"0"}
    assert int(span_id, 16) != 0


def test_events_carry_span_ids():
    ledger, cb = make()
    call(cb)

    for event in ledger.events("run-1"):
        assert event.trace_id, f"{event.kind} has no trace_id"
        assert event.span_id, f"{event.kind} has no span_id"


def test_call_and_result_share_one_span():
    """도구 호출 하나가 스팬 하나다. tool_call 과 tool_result 는 같은 스팬에 속한다."""
    ledger, cb = make()
    call(cb)

    events = ledger.events("run-1")
    assert len({e.span_id for e in events}) == 1
    assert len({e.trace_id for e in events}) == 1


def test_separate_tool_calls_get_separate_spans():
    ledger, cb = make()
    call(cb, args={**ARGS, "line_item": "a"}, slot="fc-1")
    call(cb, args={**ARGS, "line_item": "b"}, slot="fc-2")

    span_ids = {e.span_id for e in ledger.events("run-1")}
    assert len(span_ids) == 2


def test_blocked_call_also_leaves_a_span():
    """관문 ①이 막은 호출도 감사 대상이다. 스팬 없이 사라지면 안 된다."""
    ledger, cb = make()
    call(cb, slot="fc-1")
    call(cb, slot="fc-2")

    skip = [e for e in ledger.events("run-1") if e.kind == IDEMPOTENT_SKIP][0]
    assert skip.trace_id and skip.span_id


def test_effect_is_traceable_back_to_its_span():
    """마커 카드의 [trace ↗] 링크가 성립하는지: effect → event → span."""
    ledger, cb = make()
    call(cb)

    effect = ledger.effects("run-1")[0]
    event = [e for e in ledger.events("run-1") if e.event_id == effect.event_id][0]
    assert event.kind == TOOL_CALL
    assert event.span_id
