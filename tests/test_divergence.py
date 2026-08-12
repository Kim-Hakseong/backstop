"""관문 ②의 분류 정확도.

게이트가 틀리면 두 방향으로 제품이 죽는다.
- 거짓 음성: 중복을 놓친다 → 배포가 통과하고 발주가 두 번 나간다
- 거짓 양성: 멀쩡한 배포를 막는다 → 아무도 게이트를 안 쓰게 된다
"""

from dataclasses import dataclass
from typing import Any

from backstop.divergence import (
    DUPLICATE,
    MISSING,
    MUTATED,
    compute,
    counts,
    exit_code,
    is_blocked,
)


@dataclass
class Rec:
    """PastEffect / Intent 양쪽 역할을 하는 최소 레코드 (게이트는 덕 타이핑이다)."""

    idem_key: str
    args_canonical: dict[str, Any]
    run_id: str = "run-1"
    step_index: int = 0
    tool_name: str = "erp.create_po"
    target: str = "erp.create_po#PO-2291"


PAST_ARGS = {"vendor_id": "acme-corp", "line_item": "one laptop", "amount_usd": 4200}


def test_identical_keys_produce_no_divergence():
    past = [Rec("k1", PAST_ARGS)]
    intents = [Rec("k1", PAST_ARGS)]
    assert compute(past, intents) == []


def test_identity_field_change_is_a_duplicate():
    """vendor_id 가 바뀌면 같은 발주가 새 PO 로 한 번 더 나간다."""
    past = [Rec("k1", PAST_ARGS)]
    intents = [Rec("k2", {**PAST_ARGS, "vendor_id": "ACME Corp"})]

    (d,) = compute(past, intents)
    assert d.kind == DUPLICATE
    assert d.mismatch_field == "vendor_id"
    assert d.past_value == "acme-corp"
    assert d.replay_value == "ACME Corp"


def test_non_identity_field_change_is_mutated():
    """금액만 달라졌다면 같은 대상에 다른 값이다 — 새 물건이 생기지는 않는다."""
    past = [Rec("k1", PAST_ARGS)]
    intents = [Rec("k2", {**PAST_ARGS, "amount_usd": 9999})]

    (d,) = compute(past, intents)
    assert d.kind == MUTATED
    assert d.mismatch_field == "amount_usd"


def test_absent_intent_is_missing():
    past = [Rec("k1", PAST_ARGS)]
    (d,) = compute(past, [])
    assert d.kind == MISSING
    assert d.replay_key is None


def test_only_duplicates_block_deployment():
    assert is_blocked([]) is False
    assert exit_code([]) == 0

    mutated = compute([Rec("k1", PAST_ARGS)], [Rec("k2", {**PAST_ARGS, "amount_usd": 1})])
    assert is_blocked(mutated) is False
    assert exit_code(mutated) == 0

    missing = compute([Rec("k1", PAST_ARGS)], [])
    assert is_blocked(missing) is False

    dup = compute([Rec("k1", PAST_ARGS)], [Rec("k2", {**PAST_ARGS, "vendor_id": "X"})])
    assert is_blocked(dup) is True
    assert exit_code(dup) == 1


def test_steps_are_matched_by_run_and_position():
    """다른 run 의 같은 스텝을 짝지으면 안 된다."""
    past = [
        Rec("k1", PAST_ARGS, run_id="run-a", step_index=0),
        Rec("k2", PAST_ARGS, run_id="run-b", step_index=0),
    ]
    intents = [
        Rec("k1", PAST_ARGS, run_id="run-a", step_index=0),
        Rec("zz", {**PAST_ARGS, "vendor_id": "Other"}, run_id="run-b", step_index=0),
    ]
    (d,) = compute(past, intents)
    assert d.run_id == "run-b"


def test_mail_identity_is_recipient_and_subject():
    past = [Rec("k1", {"to": "a@x.example", "subject": "PO issued", "body": "hi"},
                tool_name="mail.send")]
    intents = [Rec("k2", {"to": "b@x.example", "subject": "PO issued", "body": "hi"},
                   tool_name="mail.send")]
    (d,) = compute(past, intents)
    assert d.kind == DUPLICATE  # 다른 사람에게 같은 메일이 또 나간다

    intents_body = [Rec("k3", {"to": "a@x.example", "subject": "PO issued", "body": "yo"},
                        tool_name="mail.send")]
    (d2,) = compute(past, intents_body)
    assert d2.kind == MUTATED  # 같은 수신자·제목, 본문만 다름


def test_counts_tallies_each_kind():
    past = [
        Rec("k1", PAST_ARGS, step_index=0),
        Rec("k2", PAST_ARGS, step_index=1),
        Rec("k3", PAST_ARGS, step_index=2),
    ]
    intents = [
        Rec("x1", {**PAST_ARGS, "vendor_id": "A"}, step_index=0),
        Rec("x2", {**PAST_ARGS, "amount_usd": 5}, step_index=1),
    ]
    tally = counts(compute(past, intents))
    assert tally == {DUPLICATE: 1, MUTATED: 1, MISSING: 1}


def test_result_is_deterministic_and_sorted():
    past = [Rec("k1", PAST_ARGS, run_id="b", step_index=1),
            Rec("k2", PAST_ARGS, run_id="a", step_index=0)]
    intents = [Rec("z1", {**PAST_ARGS, "vendor_id": "X"}, run_id="b", step_index=1),
               Rec("z2", {**PAST_ARGS, "vendor_id": "Y"}, run_id="a", step_index=0)]
    result = compute(past, intents)
    assert [d.run_id for d in result] == ["a", "b"]
    assert compute(past, intents) == result


def test_narrative_defaults_to_none_and_verdict_stands_without_it():
    """Narrator 가 죽어도 판정은 유효해야 한다."""
    (d,) = compute([Rec("k1", PAST_ARGS)], [Rec("k2", {**PAST_ARGS, "vendor_id": "X"})])
    assert d.narrative is None
    assert d.kind == DUPLICATE
    assert exit_code([d]) == 1
