"""R8 관문 ①: 실행 시점 중복 차단.

완료 조건(T1.5): 같은 도구 호출 2회 → `effects` 1건 + `idempotent_skip` 1건.

주의할 함정이 하나 있다. ADK 는 `before_tool_callback` 이 dict 를 반환해 도구 실행을
건너뛰어도 `after_tool_callback` 은 **그대로 호출한다**
(google/adk/flows/llm_flows/functions.py Step 5). after 쪽에서 무조건 부작용을
기록하면, 관문 ①이 막은 바로 그 중복이 원장에 남는다. 아래 테스트가 그걸 막는다.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from backstop.clock import FrozenClock
from backstop.ledger import IDEMPOTENT_SKIP, TOOL_CALL, InMemoryLedger
from subject_agent.callbacks import LedgerCallbacks

TOOL = SimpleNamespace(name="erp.create_po")
ARGS = {"vendor_id": "acme-corp", "amount_usd": 4200}
RESPONSE = {"po_id": "PO-8428"}


def make(run_id="run-1"):
    ledger = InMemoryLedger(clock=FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc)))
    return ledger, LedgerCallbacks(ledger, run_id)


def call(cb, args=ARGS, slot="fc-1", response=RESPONSE):
    """ADK 의 호출 순서를 그대로 흉내낸다. before 가 dict 를 반환해도 after 는 불린다."""
    ctx = SimpleNamespace(function_call_id=slot)
    short_circuit = cb.before_tool(tool=TOOL, args=args, tool_context=ctx)
    actual = short_circuit if short_circuit is not None else response
    cb.after_tool(tool=TOOL, args=args, tool_context=ctx, tool_response=actual)
    return short_circuit


def test_duplicate_call_produces_exactly_one_effect():
    """T1.5 완료 조건의 앞쪽 절반."""
    ledger, cb = make()
    call(cb, slot="fc-1")
    call(cb, slot="fc-2")

    assert len(ledger.effects("run-1")) == 1


def test_duplicate_call_records_idempotent_skip():
    """완료 조건의 뒤쪽 절반. 관문 ①이 일했다는 증거가 원장에 남아야 한다(R1)."""
    ledger, cb = make()
    call(cb, slot="fc-1")
    call(cb, slot="fc-2")

    skips = [e for e in ledger.events("run-1") if e.kind == IDEMPOTENT_SKIP]
    assert len(skips) == 1
    assert skips[0].tool_name == "erp.create_po"


def test_duplicate_call_is_short_circuited_with_prior_result():
    """차단은 예외가 아니라 이전 결과 반환이다. 에이전트는 계속 진행할 수 있어야 한다."""
    ledger, cb = make()
    call(cb, slot="fc-1")
    blocked = call(cb, slot="fc-2")

    assert isinstance(blocked, dict)
    assert blocked["po_id"] == "PO-8428"


def test_after_callback_does_not_record_effect_for_blocked_call():
    """ADK 는 건너뛴 호출에도 after_tool 을 부른다. 여기서 부작용을 남기면 안 된다."""
    ledger, cb = make()
    call(cb, slot="fc-1")
    before = len(ledger.effects("run-1"))
    call(cb, slot="fc-2")

    assert len(ledger.effects("run-1")) == before


def test_blocked_call_does_not_emit_tool_call_event():
    """차단된 호출은 tool_call 이 아니라 idempotent_skip 으로 기록된다."""
    ledger, cb = make()
    call(cb, slot="fc-1")
    call(cb, slot="fc-2")

    kinds = [e.kind for e in ledger.events("run-1")]
    assert kinds.count(TOOL_CALL) == 1
    assert kinds.count(IDEMPOTENT_SKIP) == 1


def test_ten_repeats_still_produce_one_effect():
    """P2 재개 시나리오의 축소판. 10회 반복에서 중복 0건(T2.4)."""
    ledger, cb = make()
    for i in range(10):
        call(cb, slot=f"fc-{i}")

    assert len(ledger.effects("run-1")) == 1
    assert len([e for e in ledger.events("run-1") if e.kind == IDEMPOTENT_SKIP]) == 9


def test_semantically_identical_args_are_blocked():
    """정규화가 관문 ①에 실제로 걸려 있는지. int/float·공백·순서 차이."""
    ledger, cb = make()
    call(cb, args={"vendor_id": "acme-corp", "amount_usd": 4200}, slot="fc-1")
    call(cb, args={"amount_usd": 4200.0, "vendor_id": " acme-corp "}, slot="fc-2")

    assert len(ledger.effects("run-1")) == 1


def test_different_args_are_not_blocked():
    ledger, cb = make()
    call(cb, args={"vendor_id": "acme-corp", "amount_usd": 4200}, slot="fc-1")
    call(cb, args={"vendor_id": "acme-corp", "amount_usd": 9999}, slot="fc-2")

    assert len(ledger.effects("run-1")) == 2


def test_guard_is_scoped_to_the_run():
    """다른 run 의 같은 호출은 막지 않는다. run_scope 가 키에 들어 있기 때문이다."""
    ledger = InMemoryLedger(clock=FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc)))
    a = LedgerCallbacks(ledger, "run-a")
    b = LedgerCallbacks(ledger, "run-b")
    call(a, slot="fc-1")
    call(b, slot="fc-1")

    assert len(ledger.effects("run-a")) == 1
    assert len(ledger.effects("run-b")) == 1


def test_resume_after_crash_does_not_duplicate():
    """크래시 재개 시나리오: 새 콜백 객체(새 프로세스)라도 원장이 진실의 근거다."""
    ledger = InMemoryLedger(clock=FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc)))
    first = LedgerCallbacks(ledger, "run-1")
    call(first, slot="fc-1")

    # 프로세스가 죽고 재개된다. 인메모리 상태는 사라지고 원장만 남는다.
    resumed = LedgerCallbacks(ledger, "run-1")
    call(resumed, slot="fc-1")

    assert len(ledger.effects("run-1")) == 1
