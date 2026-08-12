"""T2.5: 6주치 원장을 실시간 대기 없이 생성한다.

    uv run python scripts/seed_ledger.py --out fixtures/ledger_6w.jsonl

`FrozenClock` 으로 6주를 압축한다(R3). 네트워크도 API 키도 쓰지 않는다 —
심사위원이 그대로 재생할 수 있어야 하기 때문이다.

**이 원장은 시뮬레이션이다.** 실제 6주 운영 로그가 아니다. README·write-up·화면에
같은 문장을 적는다.

원장의 모양: 장기 실행 에이전트는 대부분의 시간에 아무 것도 하지 않는다. 그래서
이벤트의 대부분은 `tick` 이고, 도구 호출은 드문드문 박혀 있다. 부작용은 그보다 더 드물다.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import asdict
from datetime import datetime, timezone

from backstop.clock import FrozenClock
from backstop.ledger import TICK, InMemoryLedger
from subject_agent.workflow import STEPS, WorkflowRunner

START = datetime(2026, 7, 1, tzinfo=timezone.utc)
WEEKS = 6
HOURS = WEEKS * 7 * 24  # 1,008 시간

# 벤더 4곳. 3곳은 6주 안에 온보딩을 끝내고, 1곳은 아직 진행 중이다 —
# 6주 시점에 모든 게 딱 끝나 있는 원장이 오히려 비현실적이다.
VENDORS = [
    {"vendor_id": "acme-corp", "start_hour": 2, "steps": len(STEPS)},
    {"vendor_id": "globex-ltd", "start_hour": 80, "steps": len(STEPS)},
    {"vendor_id": "initech", "start_hour": 200, "steps": len(STEPS)},
    {"vendor_id": "umbrella-co", "start_hour": 640, "steps": 6},
]


def context_for(vendor_id: str) -> dict:
    return {
        "vendor_id": vendor_id,
        "contact": f"ap@{vendor_id}.example",
        "amount_usd": 4200,
        "line_item": "one laptop",
        "due_date": "2026-09-15",
    }


def build(out_path: pathlib.Path) -> dict:
    clock = FrozenClock(START)
    ledger = InMemoryLedger(clock=clock)

    runners = {}
    for v in VENDORS:
        run_id = f"onboard-{v['vendor_id']}"
        runners[run_id] = {
            "runner": WorkflowRunner(
                ledger, run_id, "v1", context=context_for(v["vendor_id"]), clock=clock
            ),
            "spec": v,
            "done": 0,
        }
        runners[run_id]["runner"].start()

    # 각 벤더의 스텝을 6주에 고르게 분산한다.
    schedule: dict[int, list[str]] = {}
    for run_id, entry in runners.items():
        spec = entry["spec"]
        span = HOURS - spec["start_hour"]
        gap = max(1, span // (spec["steps"] + 1))
        for i in range(spec["steps"]):
            hour = spec["start_hour"] + gap * (i + 1)
            schedule.setdefault(min(hour, HOURS - 1), []).append(run_id)

    for hour in range(HOURS):
        clock.advance(hours=1)
        # 에이전트는 매 시간 깨어난다. 대부분은 할 일이 없다.
        ledger.append_event(run_id="fleet", kind=TICK)

        for run_id in schedule.get(hour, []):
            runners[run_id]["runner"].tick()
            runners[run_id]["done"] += 1

    # 재전달로 같은 스텝이 다시 들어오는 상황. 관문 ①이 막은 흔적이 원장에 남는다.
    for run_id in ("onboard-acme-corp", "onboard-globex-ltd"):
        entry = runners[run_id]
        replayed = WorkflowRunner(
            ledger,
            run_id,
            "v1",
            context=context_for(entry["spec"]["vendor_id"]),
            clock=clock,
        )
        run = ledger.get_run(run_id)
        # 커서를 한 칸 되돌려 이미 끝낸 스텝을 다시 시도하게 만든다
        from dataclasses import replace as _replace

        ledger.save_run(_replace(run, cursor=max(0, run.cursor - 1)))
        replayed.tick()

    return dump(ledger, out_path, list(runners))


def dump(ledger: InMemoryLedger, out_path: pathlib.Path, run_ids: list[str]) -> dict:
    lines: list[str] = []

    all_runs = [ledger.get_run(r) for r in run_ids]
    for run in all_runs:
        lines.append(json.dumps({"type": "run", **serialize(asdict(run))}))

    event_count = 0
    for run_id in run_ids + ["fleet"]:
        for event in ledger.events(run_id):
            lines.append(json.dumps({"type": "event", **serialize(asdict(event))}))
            event_count += 1

    effect_count = 0
    for run_id in run_ids:
        for effect in ledger.effects(run_id):
            lines.append(json.dumps({"type": "effect", **serialize(asdict(effect))}))
            effect_count += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")

    skips = sum(
        1
        for r in run_ids
        for e in ledger.events(r)
        if e.kind == "idempotent_skip"
    )
    return {
        "runs": len(all_runs),
        "events": event_count,
        "effects": effect_count,
        "idempotent_skips": skips,
        "weeks": WEEKS,
        "bytes": out_path.stat().st_size,
    }


def serialize(doc: dict) -> dict:
    return {
        k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in doc.items()
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="fixtures/ledger_6w.jsonl")
    args = p.parse_args()

    stats = build(pathlib.Path(args.out))
    print(f"wrote {args.out}")
    for k, v in stats.items():
        print(f"  {k:18s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
