"""T2.1/T2.2: tick 이 스텝을 전진시키고, 상태가 원장에 남는다."""

from datetime import datetime, timezone

import pytest

from backstop.clock import FrozenClock
from backstop.ledger import (
    DONE,
    IDEMPOTENT_SKIP,
    PENDING_LEASE_SECONDS,
    RUNNING,
    InMemoryLedger,
)
from subject_agent.workflow import STEPS, WorkflowRunner


def make(run_id="run-1", version="v1"):
    clock = FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc))
    ledger = InMemoryLedger(clock=clock)
    return ledger, WorkflowRunner(ledger, run_id, version, clock=clock), clock


def test_tick_advances_cursor_by_one():
    ledger, wf, _ = make()
    wf.start()
    assert wf.tick().cursor == 1
    assert wf.tick().cursor == 2


def test_tick_records_events_in_the_ledger():
    ledger, wf, _ = make()
    wf.start()
    wf.tick()
    assert len(ledger.events("run-1")) > 0


def test_workflow_spans_six_weeks():
    assert {s.week for s in STEPS} == {1, 2, 3, 4, 5, 6}


def test_run_to_completion_marks_done():
    ledger, wf, _ = make()
    run = wf.run_to_completion()
    assert run.status == DONE
    assert run.cursor == len(STEPS)


def test_completed_run_produces_one_effect_per_step():
    ledger, wf, _ = make()
    wf.run_to_completion()
    assert len(ledger.effects("run-1")) == len(STEPS)


def test_state_survives_a_new_runner_instance():
    """T2.2 완료 조건: 프로세스를 껐다 켜도 다음 tick 이 이어간다."""
    ledger, wf, clock = make()
    wf.start()
    wf.tick()
    wf.tick()

    # 프로세스가 죽고 새로 뜬다. 원장만 남아 있다.
    revived = WorkflowRunner(ledger, "run-1", "v1", clock=clock)
    run = revived.tick()

    assert run.cursor == 3


def test_resume_does_not_restart_from_zero():
    ledger, wf, clock = make()
    wf.start()
    wf.tick()

    revived = WorkflowRunner(ledger, "run-1", "v1", clock=clock)
    assert revived.resume().cursor == 1


def test_start_is_idempotent():
    ledger, wf, _ = make()
    first = wf.start()
    wf.tick()
    again = wf.start()
    assert again.cursor == 1
    assert again.started_at == first.started_at


def test_last_tick_at_uses_injected_clock():
    ledger, wf, clock = make()
    wf.start()
    clock.advance(days=7)
    run = wf.tick()
    assert (run.last_tick_at - run.started_at).days == 7


def test_ticking_past_the_end_is_a_no_op():
    ledger, wf, _ = make()
    wf.run_to_completion()
    effects_before = len(ledger.effects("run-1"))

    run = wf.tick()
    assert run.status == DONE
    assert len(ledger.effects("run-1")) == effects_before


def test_crash_before_effect_leaves_no_effect():
    """T2.3 의 핵심: 부작용 직전에 죽으면 부작용은 나가지 않았어야 한다."""

    class Boom(Exception):
        pass

    ledger, wf, _ = make()
    wf.start()

    with pytest.raises(Boom):
        wf.tick(before_effect=lambda step: (_ for _ in ()).throw(Boom()))

    assert len(ledger.effects("run-1")) == 0
    # 커서도 전진하지 않았다 → 다음 tick 이 같은 스텝을 다시 시도한다
    assert ledger.get_run("run-1").cursor == 0


def test_retry_after_crash_completes_the_step():
    """크래시로 남은 선점(pending)은 리스가 만료되면 재선점된다.

    Pub/Sub 재전달은 ack deadline(30s) 뒤에 오므로 실제로 리스보다 늦다.
    """

    class Boom(Exception):
        pass

    ledger, wf, clock = make()
    wf.start()
    with pytest.raises(Boom):
        wf.tick(before_effect=lambda step: (_ for _ in ()).throw(Boom()))

    clock.advance(seconds=PENDING_LEASE_SECONDS + 5)  # 재전달까지 걸린 시간
    run = wf.tick()

    assert run.cursor == 1
    assert len(ledger.effects("run-1")) == 1


def test_blocked_by_pending_does_not_advance_the_cursor():
    """리스 안의 pending 에 막히면 스텝은 아직 안 끝난 것이다. 커서가 올라가면 안 된다.

    실제로 올라갔다: 크래시 재전달이 리스 안에 도착하자 재시도가 중복으로 오인됐고,
    커서만 전진해 워크플로가 부작용 1건을 빠뜨린 채 "완료"됐다.
    """

    class Boom(Exception):
        pass

    ledger, wf, clock = make()
    wf.start()
    with pytest.raises(Boom):
        wf.tick(before_effect=lambda step: (_ for _ in ()).throw(Boom()))

    clock.advance(seconds=1)  # 리스 안에서 재시도
    run = wf.tick()

    assert run.cursor == 0, "미완료 스텝을 건너뛰면 안 된다"
    assert len(ledger.effects("run-1")) == 0

    # 리스가 만료되면 같은 스텝이 정상적으로 끝난다
    clock.advance(seconds=PENDING_LEASE_SECONDS + 5)
    run = wf.tick()
    assert run.cursor == 1
    assert len(ledger.effects("run-1")) == 1


def test_committed_block_still_advances_the_cursor():
    """이미 확정된 부작용을 만난 차단은 '끝난 일'이므로 전진해야 한다."""
    ledger, wf, clock = make()
    wf.start()
    wf.tick()  # 스텝 0 완료

    # 커서를 되돌려 같은 스텝을 다시 시도하게 만든다 (재전달 흉내)
    from dataclasses import replace

    ledger.save_run(replace(ledger.get_run("run-1"), cursor=0))
    run = wf.tick()

    assert run.cursor == 1
    assert len(ledger.effects("run-1")) == 1  # 두 번 나가지 않았다


def test_workflow_completes_with_one_effect_per_step_after_a_crash():
    """크래시가 끼어도 최종 부작용 수는 스텝 수와 같아야 한다. 빠지지도 겹치지도 않는다."""

    class Boom(Exception):
        pass

    ledger, wf, clock = make()
    wf.start()
    wf.tick()
    with pytest.raises(Boom):
        wf.tick(before_effect=lambda step: (_ for _ in ()).throw(Boom()))

    for _ in range(40):
        clock.advance(seconds=PENDING_LEASE_SECONDS + 1)
        run = wf.tick()
        if run.status == DONE:
            break

    assert run.cursor == len(STEPS)
    assert len(ledger.effects("run-1")) == len(STEPS)


def test_retry_within_the_lease_is_blocked():
    """리스 안의 재시도는 '다른 워커가 실행 중'이라는 뜻이므로 막아야 한다.

    이걸 허용하면 Pub/Sub 동시 전달에서 부작용이 두 번 나간다 — 실제로 그렇게 샜다.
    """

    class Boom(Exception):
        pass

    ledger, wf, clock = make()
    wf.start()
    with pytest.raises(Boom):
        wf.tick(before_effect=lambda step: (_ for _ in ()).throw(Boom()))

    clock.advance(seconds=1)
    wf.tick()

    # 부작용은 나가지 않았고, 원장에는 차단 흔적이 남는다
    assert len(ledger.effects("run-1")) == 0
    assert any(e.kind == IDEMPOTENT_SKIP for e in ledger.events("run-1"))
