"""R3 불변식: 시간은 주입 가능해야 한다.

두 가지를 강제한다.
1. FrozenClock 으로 6주를 실시간 대기 없이 전진시킬 수 있다.
2. `clock.py` 를 제외한 어느 모듈도 `datetime.now()` 를 직접 부르지 않는다.
   2번이 깨지면 6주 원장 생성이 실시간을 기다리게 되고 재생이 결정론을 잃는다.
"""

import ast
import pathlib
from datetime import datetime, timezone

import pytest

from backstop.clock import Clock, FrozenClock, SystemClock

REPO = pathlib.Path(__file__).resolve().parents[1]
SCANNED_DIRS = ("backstop", "subject_agent", "api", "scripts")
ALLOWED = {"backstop/clock.py"}


def _wall_clock_calls(source: str) -> list[str]:
    """AST 로 실제 호출만 찾는다.

    정규식은 독스트링의 'datetime.now()를 부르지 않는다' 같은 **설명 문장**을 위반으로
    오탐한다. 반대로 주석 처리된 코드를 위반으로 세기도 한다. 우리가 막으려는 건
    텍스트가 아니라 호출이므로 AST 로 본다.
    """
    hits: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        dotted = ast.unparse(node.func)
        receiver, _, attr = dotted.rpartition(".")
        if attr in ("now", "utcnow") and receiver.split(".")[-1] == "datetime":
            hits.append(dotted)
        elif attr == "time" and receiver.split(".")[-1] == "time":
            hits.append(dotted)
    return hits


def test_frozen_clock_spans_six_weeks_without_waiting():
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    clock = FrozenClock(start)

    assert clock.now() == start
    for _ in range(6 * 7):
        clock.advance(days=1)

    assert (clock.now() - start).days == 42


def test_frozen_clock_is_stable_between_advances():
    clock = FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc))
    assert clock.now() == clock.now()


def test_system_clock_is_timezone_aware():
    assert SystemClock().now().tzinfo is not None


def test_clocks_satisfy_the_protocol():
    assert isinstance(FrozenClock(datetime(2026, 7, 1, tzinfo=timezone.utc)), Clock)
    assert isinstance(SystemClock(), Clock)


def test_detector_catches_real_calls_and_ignores_prose():
    """가드 자체의 가드. 이게 무력화되면 R3 위반이 조용히 통과한다."""
    assert _wall_clock_calls("import datetime\ndatetime.datetime.now()")
    assert _wall_clock_calls("from datetime import datetime\ndatetime.now()")
    assert _wall_clock_calls("import time\ntime.time()")
    # 산문과 정상 사용은 잡지 않는다
    assert not _wall_clock_calls('"""datetime.now() 를 부르지 않는다."""')
    assert not _wall_clock_calls("clock.now()")
    assert not _wall_clock_calls("self._clock.now()")


@pytest.mark.parametrize(
    "path",
    [
        p
        for d in SCANNED_DIRS
        for p in (REPO / d).rglob("*.py")
        if "__pycache__" not in str(p)
    ],
    ids=lambda p: str(p.relative_to(REPO)),
)
def test_no_direct_wall_clock_calls(path: pathlib.Path):
    rel = path.relative_to(REPO).as_posix()
    if rel in ALLOWED:
        return
    hits = _wall_clock_calls(path.read_text())
    assert not hits, f"{rel} calls wall clock directly: {hits}. Use clock.now()."
