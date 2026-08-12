"""Narrator 는 판정을 바꿀 수 없다 (R6, T3.7/T3.8).

제출물에 "LLM 은 아무것도 차단하지 않는다"고 쓴다. 그 문장의 근거가 이 파일이다.
"""

import dataclasses

from backstop.divergence import DUPLICATE, MISSING, MUTATED, Divergence, exit_code
from backstop.narrator import MAX_NARRATOR_CALLS, narrate, narrate_all


def make(kind=DUPLICATE, i=0):
    return Divergence(
        run_id=f"run-{i}",
        kind=kind,
        tool_name="erp.create_po",
        step_index=6,
        past_key="a" * 64,
        replay_key="b" * 64,
        mismatch_field="vendor_id",
        past_value="acme-corp",
        replay_value="ACME Corp",
        target="erp.create_po#PO-2291",
    )


def test_narrate_returns_a_string(monkeypatch):
    monkeypatch.setenv("BACKSTOP_OFFLINE", "1")
    assert isinstance(narrate(make()), str)


def test_offline_mode_needs_no_credentials(monkeypatch):
    monkeypatch.setenv("BACKSTOP_OFFLINE", "1")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("PROJECT_ID", raising=False)

    text = narrate(make())
    assert "acme-corp" in text and "ACME Corp" in text


def test_narration_does_not_change_the_verdict(monkeypatch):
    monkeypatch.setenv("BACKSTOP_OFFLINE", "1")
    before = [make(), make(MUTATED, 1), make(MISSING, 2)]
    after = narrate_all(before)

    assert [d.kind for d in after] == [d.kind for d in before]
    assert exit_code(after) == exit_code(before)


def test_narration_returns_copies_leaving_originals_untouched(monkeypatch):
    monkeypatch.setenv("BACKSTOP_OFFLINE", "1")
    original = make()
    (narrated,) = narrate_all([original])

    assert original.narrative is None
    assert narrated.narrative
    assert dataclasses.replace(narrated, narrative=None) == original


def test_call_cap_is_enforced(monkeypatch):
    """원장이 커져도 모델 호출이 선형으로 늘지 않아야 한다."""
    monkeypatch.setenv("BACKSTOP_OFFLINE", "1")
    many = [make(i=i) for i in range(20)]
    out = narrate_all(many)

    assert sum(1 for d in out if d.narrative) == MAX_NARRATOR_CALLS
    assert len(out) == len(many)


def test_divergences_beyond_the_cap_keep_their_verdict(monkeypatch):
    monkeypatch.setenv("BACKSTOP_OFFLINE", "1")
    out = narrate_all([make(i=i) for i in range(20)])

    uncovered = [d for d in out if d.narrative is None]
    assert uncovered
    assert all(d.kind == DUPLICATE for d in uncovered)
    assert exit_code(out) == 1


def test_model_failure_falls_back_without_breaking(monkeypatch):
    """모델이 터져도 카드가 비지 않고 판정도 살아 있어야 한다."""
    monkeypatch.delenv("BACKSTOP_OFFLINE", raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "no-such-project")

    def explode(*a, **k):
        raise RuntimeError("vertex is down")

    import backstop.narrator as narrator

    monkeypatch.setattr(narrator, "_use_offline", lambda: False)
    monkeypatch.setitem(__import__("sys").modules, "google.genai", None)

    text = narrator.narrate(make())
    assert isinstance(text, str) and text


def test_every_kind_has_a_sentence(monkeypatch):
    monkeypatch.setenv("BACKSTOP_OFFLINE", "1")
    for kind in (DUPLICATE, MUTATED, MISSING):
        assert narrate(make(kind)).strip()
