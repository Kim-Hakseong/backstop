"""시간 주입 (R3).

이 파일은 저장소에서 벽시계를 직접 읽는 **유일한** 곳이다. 다른 모듈은 `Clock` 을
주입받아 `clock.now()` 를 부른다. `tests/test_clock.py` 가 이 규칙을 강제한다.

이유: 6주치 원장을 실시간으로 기다리며 만들 수는 없고, 재생이 결정론적이려면 재생
시각이 실행 시각에 의존해서는 안 된다.
"""

from __future__ import annotations

import datetime as _datetime
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """실제 벽시계. 프로덕션 실행 경로에서만 쓴다."""

    def now(self) -> datetime:
        return _datetime.datetime.now(timezone.utc)


class FrozenClock:
    """명시적으로 전진시키기 전까지 멈춰 있는 시계.

    시드 원장 생성(T2.5)과 재생에서 쓴다. 6주를 42번의 advance 로 통과한다.
    """

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("FrozenClock requires a timezone-aware datetime")
        self._t = start

    def now(self) -> datetime:
        return self._t

    def advance(self, **kwargs) -> datetime:
        """timedelta 인자(days, hours, minutes, seconds...)로 전진시킨다."""
        self._t += timedelta(**kwargs)
        return self._t
