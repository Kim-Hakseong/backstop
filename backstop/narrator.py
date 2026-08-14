"""Narrator — Gemini 3.5 Flash. **설명 전용.**

이 모듈이 하는 일은 이미 끝난 판정을 사람이 읽을 한 문장으로 옮기는 것뿐이다.
- 입력은 `Divergence` 하나, 출력은 `str` 하나다. 다른 시그니처를 쓰지 않는다.
- 판정(`kind`)을 읽기만 하고 바꾸지 않는다. 바꿀 수 있는 반환 경로가 없다.
- 모델이 죽든, 키가 없든, 한도를 넘든 판정은 그대로 유효하다.

`BACKSTOP_OFFLINE=1` 이거나 자격증명이 없으면 사전 저장 문장을 쓴다 —
심사위원이 API 키 없이 `make gate` 를 돌려도 같은 화면이 나와야 하기 때문이다.
"""

from __future__ import annotations

import dataclasses
import os

from backstop.divergence import DUPLICATE, MISSING, MUTATED, Divergence

# 재생 1회당 모델 호출 상한(docs/engineering-rules.md §9). 원장이 커져도 비용이 선형으로 늘지 않는다.
MAX_NARRATOR_CALLS = 5

MODEL = os.environ.get("BACKSTOP_MODEL", "gemini-3.5-flash")

_PROMPT = """You are writing one sentence for an engineering incident card.

A deployment gate compared a six-week execution ledger against a replay of the
same ledger under a new agent version. It already decided the verdict below.
Explain the consequence in one plain sentence, under 30 words. Do not restate
the field names. Do not give advice. Do not question the verdict.

verdict: {kind}
tool: {tool}
field that changed: {field}
value in the ledger: {past!r}
value on replay: {replay!r}
"""


def _offline_sentence(d: Divergence) -> str:
    """사전 저장 문장. 모델 없이도 카드가 채워진다."""
    if d.kind == DUPLICATE:
        return (
            f"{d.mismatch_field} changed from {d.past_value!r} to {d.replay_value!r}, "
            f"so the idempotency key no longer matches and the same "
            f"{d.tool_name} would be issued a second time."
        )
    if d.kind == MUTATED:
        return (
            f"The same {d.tool_name} target would be reached with a different "
            f"{d.mismatch_field} ({d.past_value!r} → {d.replay_value!r})."
        )
    if d.kind == MISSING:
        return (
            f"The new version never reaches this {d.tool_name} call, so work the "
            f"ledger recorded would silently stop happening."
        )
    return f"{d.kind} on {d.tool_name}."


def _use_offline() -> bool:
    if os.environ.get("BACKSTOP_OFFLINE"):
        return True
    return not (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("PROJECT_ID")
        or os.environ.get("GOOGLE_API_KEY")
    )


def narrate(divergence: Divergence) -> str:
    """분기 하나를 한 문장으로. 반환 타입은 `str` 이다 — 판정을 건드릴 수 없다."""
    if _use_offline():
        return _offline_sentence(divergence)

    try:
        from google import genai

        client = genai.Client(
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT")
            or os.environ.get("PROJECT_ID"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
        )
        response = client.models.generate_content(
            model=MODEL,
            contents=_PROMPT.format(
                kind=divergence.kind,
                tool=divergence.tool_name,
                field=divergence.mismatch_field,
                past=divergence.past_value,
                replay=divergence.replay_value,
            ),
        )
        text = (response.text or "").strip()
        return text or _offline_sentence(divergence)
    except Exception:
        # 모델이 어떤 이유로든 실패하면 사전 저장 문장으로 떨어진다.
        # 판정은 이미 끝났으므로 데모가 죽지 않는다.
        return _offline_sentence(divergence)


def narrate_all(divergences: list[Divergence]) -> list[Divergence]:
    """설명을 붙인 **복사본**을 돌려준다. 원본 판정은 불변이다.

    상한을 넘는 분기는 `narrative=None` 으로 남는다 — 판정에는 영향이 없다.
    """
    out: list[Divergence] = []
    used = 0
    for d in divergences:
        if used < MAX_NARRATOR_CALLS:
            out.append(dataclasses.replace(d, narrative=narrate(d)))
            used += 1
        else:
            out.append(d)
    return out


def calls_used(divergences: list[Divergence]) -> int:
    return sum(1 for d in divergences if d.narrative)
