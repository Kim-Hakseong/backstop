"""콘솔이 읽는 `gate.json` 이 코드와 어긋나지 않게 막는다.

이 파일은 커밋된 산출물이라 조용히 낡을 수 있다. 게이트를 고쳤는데 화면은 옛날 결과를
보여주는 상황 — 데모에서 가장 창피한 종류의 사고다. 여기서 잡는다.
"""

import json
import pathlib

import pytest

from backstop.divergence import compute, counts, is_blocked
from backstop.replay import ReplayHarness

REPO = pathlib.Path(__file__).resolve().parents[1]
EXPORT = REPO / "api" / "static" / "gate.json"
FIXTURE = REPO / "fixtures" / "ledger_6w.jsonl"


@pytest.fixture(scope="module")
def payload():
    if not EXPORT.exists():
        pytest.skip("gate.json not generated yet")
    return json.loads(EXPORT.read_text())


def recompute(version: str):
    harness = ReplayHarness.from_fixture(FIXTURE)
    result = harness.replay(version=version)
    return result, compute(result.past_effects, result.intents)


@pytest.mark.parametrize("version", ["v1", "v3"])
def test_export_matches_a_fresh_gate_run(payload, version):
    result, divergences = recompute(version)
    block = payload["versions"][version]

    assert block["counts"] == counts(divergences)
    assert block["blocked"] == is_blocked(divergences)
    assert block["stats"]["events"] == result.events_read
    assert block["stats"]["steps_replayed"] == len(result.intents)


def test_export_carries_the_demo_scenario(payload):
    """v3 는 막히고 v1 은 통과한다 — 데모 0:50–1:10 대조군의 근거."""
    assert payload["versions"]["v3"]["blocked"] is True
    assert payload["versions"]["v3"]["counts"]["DUPLICATE"] == 3
    assert payload["versions"]["v1"]["blocked"] is False
    assert payload["versions"]["v1"]["counts"]["DUPLICATE"] == 0


def test_timeline_points_are_normalised(payload):
    assert len(payload["events"]) == 1094
    assert len(payload["effects"]) == 42
    assert all(0.0 <= e["t"] <= 1.0 for e in payload["events"])
    assert all(0.0 <= e["t"] <= 1.0 for e in payload["effects"])


def test_divergence_markers_have_a_position(payload):
    """마커에 위치가 없으면 타임라인에 안 그려지고 클릭도 안 된다."""
    for d in payload["versions"]["v3"]["divergences"]:
        assert d["t"] is not None
        assert 0.0 <= d["t"] <= 1.0


def test_markers_land_in_week_four(payload):
    """데모 서사가 '4주차'다. 위치가 어긋나면 대본과 화면이 따로 논다."""
    for d in payload["versions"]["v3"]["divergences"]:
        week = d["t"] * 6
        assert 3.0 <= week <= 5.0, f"{d['run_id']} at week {week:.1f}"


def test_simulated_ledger_is_declared(payload):
    """'이 원장은 시뮬레이션' 고지는 제출 요건이다."""
    assert payload["simulated"] is True


def test_console_html_states_the_simulation_notice():
    html = (REPO / "api" / "static" / "index.html").read_text()
    assert "simulated run" in html


def test_replay_time_is_reported_consistently(payload):
    """화면 숫자와 `make bench` 숫자가 다르면 어느 쪽도 못 믿게 된다(R7)."""
    for version in ("v1", "v3"):
        ms = payload["versions"][version]["stats"]["replay_ms"]
        assert 0 < ms < 100, f"{version} replay_ms={ms} — bench 정의와 어긋난다"
