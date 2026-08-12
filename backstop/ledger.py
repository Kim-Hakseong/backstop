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
    effect_id: str | None = None

    def to_doc(self) -> dict[str, Any]:
        doc = asdict(self)
        doc.pop("effect_id", None)
        return doc


class Ledger(Protocol):
    def append_event(self, **kwargs) -> Event: ...
    def append_effect(self, **kwargs) -> Effect: ...
    def events(self, run_id: str) -> list[Event]: ...
    def effects(self, run_id: str) -> list[Effect]: ...
    def find_effect(self, run_id: str, key: str) -> Effect | None: ...


class InMemoryLedger:
    """프로세스 메모리 원장. 테스트·오프라인 재생용."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._events: list[Event] = []
        self._effects: list[Effect] = []
        self._seq: dict[str, int] = {}

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
        self, run_id: str, idem_key: str, event_id: str, target: str
    ) -> Effect:
        effect = Effect(
            run_id=run_id,
            idem_key=idem_key,
            event_id=event_id,
            target=target,
            at=self._clock.now(),
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
        self, run_id: str, idem_key: str, event_id: str, target: str
    ) -> Effect:
        effect = Effect(
            run_id=run_id,
            idem_key=idem_key,
            event_id=event_id,
            target=target,
            at=self._clock.now(),
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


def effect_key(tool_name: str, args: dict[str, Any], run_id: str) -> str:
    """부작용의 멱등성 키. run_scope 는 run_id 다 — 같은 실행 안에서의 중복을 막는다."""
    return idem_key(tool_name, args, run_id)
