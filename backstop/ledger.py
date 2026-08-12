"""원장 쓰기/읽기. 스키마는 README 의 표와 1:1 대응한다.

백엔드는 둘이다.
- `InMemoryLedger`: 테스트와 오프라인 모드. 네트워크 없음
- `FirestoreLedger`: 배포 경로

시간은 전부 주입된 `Clock` 에서 온다(R3). 이 모듈은 벽시계를 읽지 않는다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Protocol

from backstop.clock import Clock, SystemClock
from backstop.idempotency import canonicalize_args, idem_key

# runs.status
RUNNING = "running"
CRASHED = "crashed"
RESUMED = "resumed"
DONE = "done"

# events.kind
TOOL_CALL = "tool_call"
TOOL_RESULT = "tool_result"
IDEMPOTENT_SKIP = "idempotent_skip"
TICK = "tick"
ERROR = "error"


@dataclass(frozen=True)
class Event:
    run_id: str
    seq: int
    kind: str
    at: datetime
    tool_name: str | None = None
    args_canonical: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None
    span_id: str | None = None
    event_id: str | None = None

    def to_doc(self) -> dict[str, Any]:
        doc = asdict(self)
        doc.pop("event_id", None)
        return doc


@dataclass(frozen=True)
class Effect:
    run_id: str
    idem_key: str
    event_id: str
    target: str
    at: datetime
    # 차단된 재시도에 돌려줄 원래 결과. 관문 ①은 예외를 던지지 않고 이걸 반환한다 —
    # 에이전트는 중단되지 않고 계속 진행해야 한다.
    result: dict[str, Any] = field(default_factory=dict)
    effect_id: str | None = None

    def to_doc(self) -> dict[str, Any]:
        doc = asdict(self)
        doc.pop("effect_id", None)
        return doc


@dataclass(frozen=True)
class Run:
    run_id: str
    agent_version: str
    started_at: datetime
    last_tick_at: datetime
    status: str
    # 워크플로 스텝 위치. 재개는 여기서 이어간다. 이게 없으면 크래시 후 처음부터
    # 다시 돌아 중복이 대량 발생한다.
    cursor: int = 0

    def to_doc(self) -> dict[str, Any]:
        return asdict(self)


class Ledger(Protocol):
    def append_event(self, **kwargs) -> Event: ...
    def append_effect(self, **kwargs) -> Effect: ...
    def events(self, run_id: str) -> list[Event]: ...
    def effects(self, run_id: str) -> list[Effect]: ...
    def find_effect(self, run_id: str, key: str) -> Effect | None: ...
    def start_run(self, run_id: str, agent_version: str) -> Run: ...
    def get_run(self, run_id: str) -> Run | None: ...
    def save_run(self, run: Run) -> Run: ...


class InMemoryLedger:
    """프로세스 메모리 원장. 테스트·오프라인 재생용."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._events: list[Event] = []
        self._effects: list[Effect] = []
        self._seq: dict[str, int] = {}
        self._runs: dict[str, Run] = {}

    def _next_seq(self, run_id: str) -> int:
        self._seq[run_id] = self._seq.get(run_id, -1) + 1
        return self._seq[run_id]

    def append_event(
        self,
        run_id: str,
        kind: str,
        tool_name: str | None = None,
        args: dict[str, Any] | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> Event:
        event = Event(
            run_id=run_id,
            seq=self._next_seq(run_id),
            kind=kind,
            at=self._clock.now(),
            tool_name=tool_name,
            args_canonical=canonicalize_args(args or {}),
            trace_id=trace_id,
            span_id=span_id,
            event_id=f"ev-{len(self._events)}",
        )
        self._events.append(event)
        return event

    def append_effect(
        self,
        run_id: str,
        idem_key: str,
        event_id: str,
        target: str,
        result: dict[str, Any] | None = None,
    ) -> Effect:
        effect = Effect(
            run_id=run_id,
            idem_key=idem_key,
            event_id=event_id,
            target=target,
            at=self._clock.now(),
            result=result or {},
            effect_id=f"eff-{len(self._effects)}",
        )
        self._effects.append(effect)
        return effect

    def events(self, run_id: str) -> list[Event]:
        # seq 로 정렬한다. at 으로 정렬하지 않는다 — README 참조.
        return sorted(
            [e for e in self._events if e.run_id == run_id], key=lambda e: e.seq
        )

    def effects(self, run_id: str) -> list[Effect]:
        return [e for e in self._effects if e.run_id == run_id]

    def find_effect(self, run_id: str, key: str) -> Effect | None:
        for e in self._effects:
            if e.run_id == run_id and e.idem_key == key:
                return e
        return None

    def start_run(self, run_id: str, agent_version: str) -> Run:
        """이미 있으면 그대로 돌려준다 — 재개는 새 run 을 만들지 않는다."""
        existing = self._runs.get(run_id)
        if existing is not None:
            return existing
        now = self._clock.now()
        run = Run(
            run_id=run_id,
            agent_version=agent_version,
            started_at=now,
            last_tick_at=now,
            status=RUNNING,
            cursor=0,
        )
        self._runs[run_id] = run
        return run

    def get_run(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def save_run(self, run: Run) -> Run:
        self._runs[run.run_id] = run
        return run


class FirestoreLedger:
    """Firestore 원장. `effects` 는 append-only 다 — 수정·삭제 경로를 두지 않는다."""

    def __init__(self, project: str, clock: Clock | None = None) -> None:
        from google.cloud import firestore

        self._db = firestore.Client(project=project)
        self._clock = clock or SystemClock()
        self._seq: dict[str, int] = {}

    def _next_seq(self, run_id: str) -> int:
        if run_id not in self._seq:
            existing = list(
                self._db.collection("events")
                .where("run_id", "==", run_id)
                .order_by("seq", direction="DESCENDING")
                .limit(1)
                .stream()
            )
            self._seq[run_id] = existing[0].to_dict()["seq"] if existing else -1
        self._seq[run_id] += 1
        return self._seq[run_id]

    def append_event(
        self,
        run_id: str,
        kind: str,
        tool_name: str | None = None,
        args: dict[str, Any] | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> Event:
        event = Event(
            run_id=run_id,
            seq=self._next_seq(run_id),
            kind=kind,
            at=self._clock.now(),
            tool_name=tool_name,
            args_canonical=canonicalize_args(args or {}),
            trace_id=trace_id,
            span_id=span_id,
        )
        ref = self._db.collection("events").document()
        ref.set(event.to_doc())
        return Event(**{**event.to_doc(), "event_id": ref.id})

    def append_effect(
        self,
        run_id: str,
        idem_key: str,
        event_id: str,
        target: str,
        result: dict[str, Any] | None = None,
    ) -> Effect:
        effect = Effect(
            run_id=run_id,
            idem_key=idem_key,
            event_id=event_id,
            target=target,
            at=self._clock.now(),
            result=result or {},
        )
        ref = self._db.collection("effects").document()
        ref.set(effect.to_doc())
        return Effect(**{**effect.to_doc(), "effect_id": ref.id})

    def events(self, run_id: str) -> list[Event]:
        docs = (
            self._db.collection("events")
            .where("run_id", "==", run_id)
            .order_by("seq")
            .stream()
        )
        return [Event(**d.to_dict(), event_id=d.id) for d in docs]

    def effects(self, run_id: str) -> list[Effect]:
        docs = (
            self._db.collection("effects").where("run_id", "==", run_id).stream()
        )
        return [Effect(**d.to_dict(), effect_id=d.id) for d in docs]

    def find_effect(self, run_id: str, key: str) -> Effect | None:
        docs = list(
            self._db.collection("effects")
            .where("run_id", "==", run_id)
            .where("idem_key", "==", key)
            .limit(1)
            .stream()
        )
        return Effect(**docs[0].to_dict(), effect_id=docs[0].id) if docs else None

    def start_run(self, run_id: str, agent_version: str) -> Run:
        ref = self._db.collection("runs").document(run_id)
        snap = ref.get()
        if snap.exists:
            return Run(**snap.to_dict())
        now = self._clock.now()
        run = Run(
            run_id=run_id,
            agent_version=agent_version,
            started_at=now,
            last_tick_at=now,
            status=RUNNING,
            cursor=0,
        )
        ref.set(run.to_doc())
        return run

    def get_run(self, run_id: str) -> Run | None:
        snap = self._db.collection("runs").document(run_id).get()
        return Run(**snap.to_dict()) if snap.exists else None

    def save_run(self, run: Run) -> Run:
        self._db.collection("runs").document(run.run_id).set(run.to_doc())
        return run


_DEFAULT: Ledger | None = None


def default_ledger(clock: Clock | None = None) -> Ledger:
    """PROJECT_ID 가 있고 오프라인 모드가 아니면 Firestore, 아니면 메모리.

    R2: 환경변수 없이도 동작해야 한다. 기본값이 오프라인이다.

    **프로세스당 하나로 캐시한다.** 요청마다 새로 만들면 인메모리 모드에서 원장이
    매번 비어 있고, tick 은 200 을 돌려주면서 아무 것도 전진시키지 않는다 —
    조용히 실패한다. Firestore 모드에서도 클라이언트 재생성을 피한다.
    """
    global _DEFAULT
    import os

    if _DEFAULT is None:
        project = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        if project and not os.environ.get("BACKSTOP_OFFLINE"):
            _DEFAULT = FirestoreLedger(project=project, clock=clock)
        else:
            _DEFAULT = InMemoryLedger(clock=clock)
    return _DEFAULT


def reset_default_ledger() -> None:
    """테스트 격리용. 프로덕션 경로에서는 부르지 않는다."""
    global _DEFAULT
    _DEFAULT = None


def effect_key(tool_name: str, args: dict[str, Any], run_id: str) -> str:
    """부작용의 멱등성 키. run_scope 는 run_id 다 — 같은 실행 안에서의 중복을 막는다."""
    return idem_key(tool_name, args, run_id)
