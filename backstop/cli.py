"""Backstop CLI. `make replay` / `make gate` / `make bench` / `make demo` 의 본체.

API 키 없이 동작해야 한다(R2). 기본 경로에 네트워크가 없다.
"""

from __future__ import annotations

import argparse
import pathlib
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


def cmd_export(args) -> int:
    """콘솔이 읽을 JSON 을 만든다.

    화면은 이 파일 하나만 읽는다 — API 가 죽어도, 네트워크가 없어도 콘솔이 뜬다.
    데모 무결성이 부산물이 아니라 요구사항이다(PRD 2-3).
    """
    import json
    from datetime import datetime

    from backstop.narrator import narrate_all

    harness = ReplayHarness.from_fixture(args.fixture)

    def instants(docs: list[dict]) -> list[str]:
        return [d["at"] for d in docs if d.get("at")]

    stamps = sorted(instants(harness._events))
    start = datetime.fromisoformat(stamps[0])
    end = datetime.fromisoformat(stamps[-1])
    span = max((end - start).total_seconds(), 1.0)

    def position(iso: str) -> float:
        return (datetime.fromisoformat(iso) - start).total_seconds() / span

    payload: dict = {
        "ledger": args.fixture,
        "simulated": True,
        "weeks": 6,
        "start": stamps[0],
        "end": stamps[-1],
        "events": [
            {"t": round(position(e["at"]), 6), "kind": e["kind"]}
            for e in harness._events
            if e.get("at")
        ],
        "effects": [
            {"t": round(position(e["at"]), 6), "target": e["target"]}
            for e in harness._effects
            if e.get("at") and e.get("status", "committed") == "committed"
        ],
        "versions": {},
    }

    effect_at = {e["idem_key"]: e.get("at") for e in harness._effects}

    for version in (args.candidate, args.baseline):
        # `make bench` 와 **같은 정의**로 잰다: 원장 로드 + 재생 + 판정, 5회 중 최속.
        # 화면과 README 에 다른 숫자가 뜨면 어느 쪽도 못 믿게 된다(R7).
        timings = []
        for _ in range(5):
            started = time.perf_counter()
            fresh = ReplayHarness.from_fixture(args.fixture)
            result = fresh.replay(version=version)
            divergences = compute(result.past_effects, result.intents)
            timings.append(time.perf_counter() - started)

        divergences = narrate_all(divergences)
        tally = counts(divergences)
        payload["versions"][version] = {
            "stats": {
                "events": result.events_read,
                "steps_replayed": len(result.intents),
                "past_effects": len(result.past_effects),
                "replay_ms": round(min(timings) * 1000, 2),
                "external_calls": result.external_calls,
                "llm_calls": result.llm_calls,
            },
            "counts": tally,
            "blocked": is_blocked(divergences),
            "divergences": [
                {
                    "run_id": d.run_id,
                    "kind": d.kind,
                    "tool_name": d.tool_name,
                    "step_index": d.step_index,
                    "target": d.target,
                    "mismatch_field": d.mismatch_field,
                    "past_value": d.past_value,
                    "replay_value": d.replay_value,
                    "past_key": d.past_key,
                    "replay_key": d.replay_key,
                    "narrative": d.narrative,
                    "t": round(position(effect_at[d.past_key]), 6)
                    if d.past_key and effect_at.get(d.past_key)
                    else None,
                }
                for d in divergences
            ],
        }

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print(f"wrote {out}  ({out.stat().st_size:,} bytes)")
    print(f"  events {len(payload['events'])}  effects {len(payload['effects'])}")
    for v, block in payload["versions"].items():
        print(f"  {v}: {block['counts']}  blocked={block['blocked']}")
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

    p_export = sub.add_parser("export", help="콘솔이 읽을 JSON 생성")
    p_export.add_argument("--out", default="api/static/gate.json")
    p_export.add_argument("--candidate", default=CANDIDATE_VERSION)
    p_export.add_argument("--baseline", default=LEDGER_VERSION)
    p_export.set_defaults(func=cmd_export)

    p_demo = sub.add_parser("demo", help="오프라인 크래시·재개 시연")
    p_demo.set_defaults(func=cmd_demo)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
