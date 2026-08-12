"""ADK 콜백 → 원장 (R1, R4).

`before_tool_callback` 과 `after_tool_callback` 이 원장이 만들어지는 유일한 지점이다.
에이전트 코드는 자기가 기록되고 있다는 걸 모른다 — 제약은 프롬프트가 아니라 실행
계층에 있다(CLAUDE.md §4).

T1.5 에서 이 `before_tool` 자리에 IdempotencyGuard 가 들어간다. ADK 는
before_tool_callback 이 dict 를 반환하면 도구 실행을 건너뛰고 그 dict 를 결과로
쓴다 — 그게 관문 ①의 차단 메커니즘이다.
"""

from __future__ import annotations

from typing import Any

from backstop.ledger import TOOL_CALL, TOOL_RESULT, Ledger, effect_key

# 부작용 대상 식별자를 뽑을 때 우선적으로 보는 필드
_TARGET_FIELDS = ("po_id", "message_id", "payment_id", "invoice_id", "id")


def target_of(tool_name: str, response: Any) -> str:
    """`erp.create_po#PO-8428` 형태의 사람이 읽는 식별자.

    분기 카드에 그대로 뜬다. 식별자를 못 찾으면 도구 이름만 쓴다.
    """
    if isinstance(response, dict):
        for f in _TARGET_FIELDS:
            if f in response and response[f] is not None:
                return f"{tool_name}#{response[f]}"
    return tool_name


class LedgerCallbacks:
    """한 run 에 대응하는 콜백 쌍."""

    def __init__(self, ledger: Ledger, run_id: str) -> None:
        self._ledger = ledger
        self._run_id = run_id
        # before 에서 만든 이벤트 id 를 after 로 넘긴다. 같은 도구를 연속 호출해도
        # 섞이지 않도록 ADK 의 function_call_id 로 구분한다.
        self._pending: dict[str, str] = {}

    def _slot(self, tool_name: str, context: Any) -> str:
        return f"{getattr(context, 'function_call_id', None) or ''}:{tool_name}"

    # 인자 이름은 ADK 호출 규약이다. ADK 는 키워드로 넘긴다:
    #   callback(tool=tool, args=function_args, tool_context=tool_context)
    #   callback(tool, args=..., tool_context=..., tool_response=...)
    # 이름을 바꾸면 TypeError 가 난다.
    def before_tool(self, tool: Any, args: dict[str, Any], tool_context: Any = None):
        event = self._ledger.append_event(
            run_id=self._run_id,
            kind=TOOL_CALL,
            tool_name=tool.name,
            args=args,
        )
        self._pending[self._slot(tool.name, tool_context)] = event.event_id or ""
        return None  # None = 도구를 정상 실행한다

    def after_tool(
        self,
        tool: Any,
        args: dict[str, Any],
        tool_context: Any = None,
        tool_response: Any = None,
    ):
        event = self._ledger.append_event(
            run_id=self._run_id,
            kind=TOOL_RESULT,
            tool_name=tool.name,
            args=args,
        )
        call_event_id = self._pending.pop(
            self._slot(tool.name, tool_context), event.event_id
        )

        # 여기까지 왔다는 건 도구가 실제로 실행됐다는 뜻이다 → 부작용을 기록한다.
        self._ledger.append_effect(
            run_id=self._run_id,
            idem_key=effect_key(tool.name, args, self._run_id),
            event_id=call_event_id or "",
            target=target_of(tool.name, tool_response),
        )
        return None  # None = 도구 결과를 그대로 쓴다
