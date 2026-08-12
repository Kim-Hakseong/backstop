"""관문 ② — 분기 게이트 (R6).

**이 모듈에 LLM 은 없다.** 판정은 집합 연산이고 순수 함수다. 네트워크도, 모델도,
시계도, 파일도 쓰지 않는다. 표준 라이브러리 밖으로 나가는 import 가 하나도 없다 —
`tests/test_gate_is_pure.py` 가 import 그래프를 직접 검사한다.

Gemini 는 `backstop/narrator.py` 에서만 호출되고, 이미 끝난 판정을 문장으로 옮길 뿐
결과를 바꿀 수 없다.

입력은 덕 타이핑된 두 시퀀스다(과거 부작용 / 재생 의도). `backstop.replay` 를
import 하지 않는다 — 게이트가 재생 구현에 묶이면 순수성을 잃는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol

DUPLICATE = "DUPLICATE"
MISSING = "MISSING"
MUTATED = "MUTATED"

# 도구별 '식별 필드' — 어떤 외부 객체를 건드리는지 결정하는 인자들.
#
# 이 목록이 DUPLICATE 와 MUTATED 를 가른다.
#   식별 필드가 달라졌다  → 다른 객체가 새로 생긴다      → DUPLICATE
#   식별 필드는 같고 값만 → 같은 객체를 다르게 건드린다  → MUTATED
#
# 모델링 선택이며 임의적이지 않다: "이 인자가 바뀌면 외부 세계에 새 물건이
# 하나 더 생기는가?" 라는 질문에 예/아니오로 답한 결과다.
IDENTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "erp.create_po": ("vendor_id", "line_item"),
    "mail.send": ("to", "subject"),
    "payment.schedule_payment": ("vendor_id", "due_date"),
}


class _Effectish(Protocol):
    run_id: str
    step_index: int
    tool_name: str
    args_canonical: dict[str, Any]
    idem_key: str


@dataclass(frozen=True)
class Divergence:
    run_id: str
    kind: str
    tool_name: str
    step_index: int
    past_key: str | None
    replay_key: str | None
    mismatch_field: str | None
    past_value: Any = None
    replay_value: Any = None
    target: str = ""
    # Narrator 출력이 들어갈 자리. **None 이어도 판정은 유효하다.**
    narrative: str | None = None


def _mismatched_fields(past: dict, replay: dict) -> list[str]:
    return sorted(
        k for k in set(past) | set(replay) if past.get(k) != replay.get(k)
    )


def classify(past: _Effectish, replay: _Effectish) -> Divergence | None:
    """같은 스텝의 과거 부작용과 재생 의도를 비교한다. 같으면 None."""
    if past.idem_key == replay.idem_key:
        return None  # 키가 같다 → 관문 ①이 재실행을 막는다 → 분기 없음

    fields = _mismatched_fields(past.args_canonical, replay.args_canonical)
    identity = IDENTITY_FIELDS.get(past.tool_name, ())
    identity_changed = [f for f in fields if f in identity]

    field = (identity_changed or fields or [None])[0]
    return Divergence(
        run_id=past.run_id,
        kind=DUPLICATE if identity_changed else MUTATED,
        tool_name=past.tool_name,
        step_index=past.step_index,
        past_key=past.idem_key,
        replay_key=replay.idem_key,
        mismatch_field=field,
        past_value=past.args_canonical.get(field) if field else None,
        replay_value=replay.args_canonical.get(field) if field else None,
        target=getattr(past, "target", ""),
    )


def compute(
    past_effects: Iterable[_Effectish], intents: Iterable[_Effectish]
) -> list[Divergence]:
    """과거 부작용 집합과 재생 의도 집합의 차집합.

    (run_id, step_index) 로 짝을 맞춘다. 짝이 있으면 키를 비교하고, 과거에만
    있으면 MISSING 이다.
    """
    by_step = {(i.run_id, i.step_index): i for i in intents}
    out: list[Divergence] = []

    for past in past_effects:
        replay = by_step.get((past.run_id, past.step_index))
        if replay is None:
            out.append(
                Divergence(
                    run_id=past.run_id,
                    kind=MISSING,
                    tool_name=past.tool_name,
                    step_index=past.step_index,
                    past_key=past.idem_key,
                    replay_key=None,
                    mismatch_field=None,
                    target=getattr(past, "target", ""),
                )
            )
            continue
        found = classify(past, replay)
        if found is not None:
            out.append(found)

    return sorted(out, key=lambda d: (d.run_id, d.step_index))


def counts(divergences: Iterable[Divergence]) -> dict[str, int]:
    tally = {DUPLICATE: 0, MISSING: 0, MUTATED: 0}
    for d in divergences:
        tally[d.kind] = tally.get(d.kind, 0) + 1
    return tally


def is_blocked(divergences: Iterable[Divergence]) -> bool:
    """DUPLICATE 가 하나라도 있으면 배포를 막는다.

    MISSING·MUTATED 는 보고하되 막지 않는다. 중복 부작용만이 되돌릴 수 없는
    실제 피해(같은 발주가 두 번, 같은 결제가 두 번)를 만들기 때문이다.
    """
    return any(d.kind == DUPLICATE for d in divergences)


def exit_code(divergences: Iterable[Divergence]) -> int:
    return 1 if is_blocked(divergences) else 0
