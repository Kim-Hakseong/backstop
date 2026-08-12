"""Backstop CLI. `make replay` / `make gate` / `make bench` / `make demo` 의 본체.

API 키 없이 동작해야 한다(R2). 기본 경로에 네트워크가 없다.
"""

from __future__ import annotations

import argparse
import sys
import time

from backstop.divergence import DUPLICATE, compute, counts, exit_code, is_blocked
from backstop.replay import ReplayHarness

FIXTURE = "fixtures/ledger_6w.jsonl"
LEDGER_VERSION = "v1"  # 원장을 만든 버전
CANDIDATE_VERSION = "v3"  # 배포하려는 버전

DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
OFF = "\033[0m"


def _harness(args) -> ReplayHarness:
    return ReplayHarness.from_fixture(args.fixture)


def cmd_replay(args) -> int:
    result = _harness(args).replay(version=args.version)
    print(f"ledger        {args.fixture}")
    print(f"version       {args.version}")
    print(f"runs          {result.runs}")
    print(f"events in ledger {result.events_read}")
    print(f"steps replayed   {len(result.intents)}")
    print(f"past effects     {len(result.past_effects)}")
    print(f"replay time   {result.seconds * 1000:.1f} ms")
    print(f"{GREEN}external calls during replay   {result.external_calls}{OFF}")
    print(f"{GREEN}LLM calls during replay        {result.llm_calls}{OFF}")
    return 0


def cmd_gate(args) -> int:
    harness = _harness(args)
    result = harness.replay(version=args.version)
    divergences = compute(result.past_effects, result.intents)
    tally = counts(divergences)

    if args.narrate:
        from backstop.narrator import narrate_all

        divergences = narrate_all(divergences)

    print(f"replaying {result.events_read} events from {args.fixture}")
    print(f"  {LEDGER_VERSION} (ledger)  ->  {args.version} (candidate)")
    print(f"  {len(result.past_effects)} past effects vs {len(result.intents)} replay intents")
    print(f"  external calls: {result.external_calls}   replay time: {result.seconds * 1000:.1f} ms")
    print()

    for i, d in enumerate(divergences, 1):
        colour = RED if d.kind == DUPLICATE else YELLOW
        print(f"{colour}[{d.kind}]{OFF} {d.run_id} step {d.step_index} · {d.tool_name}")
        if d.target:
            print(f"    effect     {d.target}")
        if d.mismatch_field:
            print(f"    field      {d.mismatch_field}")
            print(f"    past       {d.past_value!r}  key={(d.past_key or '')[:12]}…")
            print(f"    replay     {d.replay_value!r}  key={(d.replay_key or '')[:12]}…")
        if d.narrative:
            print(f"    {DIM}{d.narrative}{OFF}")
        print()

    print(
        f"DUPLICATE {tally['DUPLICATE']}   MISSING {tally['MISSING']}   "
        f"MUTATED {tally['MUTATED']}"
    )

    if is_blocked(divergences):
        print(
            f"\n{RED}DEPLOY BLOCKED — {tally['DUPLICATE']} DUPLICATE SIDE "
            f"EFFECT(S){OFF}"
        )
    else:
        print(f"\n{GREEN}DEPLOY ALLOWED — 0 DUPLICATE SIDE EFFECTS{OFF}")

    return exit_code(divergences)


def cmd_bench(args) -> int:
    # 파일 로딩까지 포함해 잰다. "6주치를 재생하는 데 얼마나 걸리나"가 질문이므로
    # 원장을 읽는 시간을 빼면 답이 아니다.
    timings = []
    for _ in range(args.repeat):
        started = time.perf_counter()
        harness = ReplayHarness.from_fixture(args.fixture)
        result = harness.replay(version=args.version)
        divergences = compute(result.past_effects, result.intents)
        timings.append(time.perf_counter() - started)

    tally = counts(divergences)
    best = min(timings)

    print("backstop bench")
    print(f"  ledger                    {args.fixture}")
    print(f"  weeks                     6")
    print(f"  runs                      {result.runs}")
    print(f"  events in ledger          {result.events_read}")
    print(f"  steps replayed            {len(result.intents)}")
    print(f"  past effects compared     {len(result.past_effects)}")
    print(f"  load+replay+gate (best)   {best * 1000:.1f} ms  of {args.repeat} runs")
    print(f"  external calls            {result.external_calls}")
    print(f"  LLM calls                 {result.llm_calls}")
    print(f"  DUPLICATE blocked         {tally['DUPLICATE']}")
    print(f"  MISSING                   {tally['MISSING']}")
    print(f"  MUTATED                   {tally['MUTATED']}")
    print(f"  exit code                 {exit_code(divergences)}")
    return 0


def cmd_demo(args) -> int:
    """오프라인 크래시·재개 시연. 클라우드 없이 관문 ①을 보여준다."""
    from datetime import datetime, timezone

    from backstop.clock import FrozenClock
    from backstop.ledger import IDEMPOTENT_SKIP, PENDING_LEASE_SECONDS, InMemoryLedger
    from subject_agent.workflow import STEPS, WorkflowRunner

    class Crash(Exception):
        pass

    clock = FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc))
    ledger = InMemoryLedger(clock=clock)
    wf = WorkflowRunner(ledger, "demo-run", "v1", clock=clock)
    wf.start()

    print("running 6-week onboarding workflow, crashing before a side effect\n")
    for _ in range(4):
        clock.advance(hours=6)
        run = wf.tick()
    print(f"  step {run.cursor}: {STEPS[run.cursor - 1].name}  effects={len(ledger.effects('demo-run'))}")

    print(f"  {RED}crash injected before the side effect of step {run.cursor}{OFF}")
    try:
        wf.tick(before_effect=lambda step: (_ for _ in ()).throw(Crash()))
    except Crash:
        pass
    print(f"  after crash: effects={len(ledger.effects('demo-run'))} (nothing went out)")

    clock.advance(seconds=PENDING_LEASE_SECONDS + 5)
    run = wf.tick()
    print(f"  resumed:     step {run.cursor} completed, effects={len(ledger.effects('demo-run'))}")

    while run.status != "done":
        clock.advance(hours=6)
        run = wf.tick()

    effects = ledger.effects("demo-run")
    skips = [e for e in ledger.events("demo-run") if e.kind == IDEMPOTENT_SKIP]
    unique = {e.idem_key for e in effects}

    print()
    print(f"  steps            {len(STEPS)}")
    print(f"  effects          {len(effects)}")
    print(f"  unique keys      {len(unique)}")
    print(f"  idempotent skips {len(skips)}")
    print()
    ok = len(effects) == len(unique) == len(STEPS)
    print(f"{GREEN if ok else RED}duplicate side effects after crash+resume: "
          f"{len(effects) - len(unique)}{OFF}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backstop")
    parser.add_argument("--fixture", default=FIXTURE)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_replay = sub.add_parser("replay", help="시드 원장을 재생하고 의도를 수집한다")
    p_replay.add_argument("--version", default=CANDIDATE_VERSION)
    p_replay.set_defaults(func=cmd_replay)

    p_gate = sub.add_parser("gate", help="재생 + 분기 게이트. 중복 시 exit 1")
    p_gate.add_argument("--version", default=CANDIDATE_VERSION)
    p_gate.add_argument("--narrate", action="store_true", help="Gemini 설명문 생성")
    p_gate.set_defaults(func=cmd_gate)

    p_bench = sub.add_parser("bench", help="실측 수치 출력")
    p_bench.add_argument("--version", default=CANDIDATE_VERSION)
    p_bench.add_argument("--repeat", type=int, default=5)
    p_bench.set_defaults(func=cmd_bench)

    p_demo = sub.add_parser("demo", help="오프라인 크래시·재개 시연")
    p_demo.set_defaults(func=cmd_demo)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
