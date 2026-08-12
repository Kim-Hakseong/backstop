"""재생 하네스 (R5).

과거 원장을 새 에이전트 버전에 다시 먹이고, **나가려 했던 의도만** 수집한다.
도구 실행기는 `IntentCollector` 로 교체되므로 외부로 나가는 호출은 0건이다.
`tests/test_replay_no_egress.py` 가 소켓 몽키패치로 이를 강제한다.

이 모듈은 네트워크도 LLM 도 쓰지 않는다. 원장 파일 하나만 읽는다 —
심사위원이 API 키 없이 `make replay` 만 쳐도 같은 결과가 나와야 하기 때문이다.
"""

from __future__ import annotations

import json
import pathlib
import time
from dataclasses import dataclass, field
from typing import Any

from backstop.idempotency import canonicalize_args
from backstop.ledger import effect_key
from subject_agent.workflow import STEPS, apply_version, context_for


@dataclass(frozen=True)
class Intent:
    """재생이 수집한 '나가려 했던 부작용'. 실제로는 나가지 않았다."""

    run_id: str
    step_index: int
    step_name: str
    tool_name: str
    args_canonical: dict[str, Any]
    idem_key: str


@dataclass(frozen=True)
class PastEffect:
    """원장에 기록된, 실제로 나갔던 부작용."""

    run_id: str
    step_index: int
    tool_name: str
    args_canonical: dict[str, Any]
    idem_key: str
    target: str


@dataclass
class ReplayResult:
    intents: list[Intent] = field(default_factory=list)
    past_effects: list[PastEffect] = field(default_factory=list)
    events_read: int = 0
    runs: int = 0
    seconds: float = 0.0
    external_calls: int = 0  # 항상 0. 화면에 띄우는 숫자다.
    llm_calls: int = 0  # 재생 경로에는 모델이 없다


class IntentCollector:
    """도구 실행기 자리에 들어가는 수집기.

    호출되면 기록만 하고 합성 응답을 돌려준다. 워크플로는 자기가 도구를 부른다고
    믿지만 아무 것도 나가지 않는다.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.intents: list[Intent] = []
        self._step_index = 0
        self._step_name = ""

    def bind_step(self, index: int, name: str) -> None:
        self._step_index = index
        self._step_name = name

    def __call__(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        canon = canonicalize_args(args)
        self.intents.append(
            Intent(
                run_id=self.run_id,
                step_index=self._step_index,
                step_name=self._step_name,
                tool_name=tool_name,
                args_canonical=canon,
                # 실행 경로와 **같은 함수**로 키를 만든다. 다른 함수로 만들면
                # 게이트가 비교하는 두 집합이 애초에 다른 공간에 있게 된다.
                idem_key=effect_key(tool_name, args, self.run_id),
            )
        )
        # 합성 응답. 워크플로가 다음 스텝으로 진행할 수 있을 만큼만 준다.
        return {"replayed": True, "tool": tool_name}


class ReplayHarness:
    def __init__(self, runs: list[dict], events: list[dict], effects: list[dict]) -> None:
        self._runs = runs
        self._events = events
        self._effects = effects

    @classmethod
    def from_fixture(cls, path: str | pathlib.Path) -> ReplayHarness:
        runs, events, effects = [], [], []
        bucket = {"run": runs, "event": events, "effect": effects}
        for line in pathlib.Path(path).read_text().splitlines():
            if not line.strip():
                continue
            doc = json.loads(line)
            bucket[doc.pop("type")].append(doc)
        return cls(runs, events, effects)

    def past(self) -> list[PastEffect]:
        """원장의 부작용을 스텝 순서로 복원한다.

        effect → event_id → event 로 인자를 되찾는다. `effects` 는 인자를 저장하지
        않기 때문이다(스키마상 진실의 근거는 `events.args_canonical` 하나다).
        """
        events_by_id = {e["event_id"]: e for e in self._events if e.get("event_id")}
        per_run: dict[str, list[tuple[int, dict]]] = {}
        for eff in self._effects:
            ev = events_by_id.get(eff.get("event_id"))
            seq = ev["seq"] if ev else 0
            per_run.setdefault(eff["run_id"], []).append((seq, eff))

        out: list[PastEffect] = []
        for run_id, items in per_run.items():
            for index, (seq, eff) in enumerate(sorted(items, key=lambda x: x[0])):
                ev = events_by_id.get(eff.get("event_id")) or {}
                out.append(
                    PastEffect(
                        run_id=run_id,
                        step_index=index,
                        tool_name=ev.get("tool_name") or eff["target"].split("#")[0],
                        args_canonical=ev.get("args_canonical", {}),
                        idem_key=eff["idem_key"],
                        target=eff["target"],
                    )
                )
        return out

    def replay(self, version: str = "v1") -> ReplayResult:
        """원장이 기록한 만큼의 스텝을 새 버전으로 다시 통과시킨다.

        각 run 이 실제로 어디까지 갔는지(`cursor`)를 원장에서 읽어 그만큼만 재생한다.
        과거에 일어나지 않은 일을 상상해서 만들지 않는다.
        """
        started = time.perf_counter()
        result = ReplayResult()

        for run in self._runs:
            run_id = run["run_id"]
            vendor_id = run_id.replace("onboard-", "")
            collector = IntentCollector(run_id)
            ctx = context_for(vendor_id)

            for index in range(min(run.get("cursor", 0), len(STEPS))):
                step = STEPS[index]
                collector.bind_step(index, step.name)
                args = apply_version(version, step.tool, step.args(ctx))
                collector(step.tool, args)

            result.intents.extend(collector.intents)
            result.runs += 1

        result.past_effects = self.past()
        result.events_read = len(self._events)
        result.seconds = time.perf_counter() - started
        return result
