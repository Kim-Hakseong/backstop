"""OTel 스팬 생성 (R4).

Fleet 트랙의 "추론 감사 가능성" 요구에 대응한다. 도구 호출마다 스팬을 열고 닫고,
그 `trace_id`/`span_id` 를 원장 이벤트에 박아 UI 마커 카드에서 역참조할 수 있게 한다.

스팬은 `before_tool` 에서 열려 `after_tool` 에서 닫힌다 — 두 콜백에 걸쳐 있으므로
`with` 문을 쓸 수 없고 수동으로 start/end 한다.
"""

from __future__ import annotations

from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

_INVALID = 0


def _ensure_provider() -> None:
    """TracerProvider 가 없으면 SDK 것을 단다.

    익스포터는 달지 않는다. 우리가 필요한 건 **실제 id 값**이지 외부 전송이 아니다.
    provider 가 없으면 OTel 은 NonRecordingSpan 을 주고 id 가 전부 0 이 되어
    역참조가 불가능해진다.
    """
    current = trace.get_tracer_provider()
    if not isinstance(current, TracerProvider):
        trace.set_tracer_provider(TracerProvider())


def _ids(span: Any) -> tuple[str | None, str | None]:
    ctx = span.get_span_context()
    if ctx.trace_id == _INVALID or ctx.span_id == _INVALID:
        return None, None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


class ToolSpans:
    """도구 호출 슬롯별 스팬 보관소."""

    def __init__(self, tracer_name: str = "backstop") -> None:
        _ensure_provider()
        self._tracer = trace.get_tracer(tracer_name)
        self._open: dict[str, Any] = {}

    def start(self, slot: str, tool_name: str) -> tuple[str | None, str | None]:
        span = self._tracer.start_span(f"tool:{tool_name}")
        span.set_attribute("backstop.tool", tool_name)
        self._open[slot] = span
        return _ids(span)

    def end(
        self, slot: str, *, blocked: bool = False
    ) -> tuple[str | None, str | None]:
        span = self._open.pop(slot, None)
        if span is None:
            return None, None
        # 관문 ①이 막았다는 사실 자체가 감사 대상이다.
        span.set_attribute("backstop.idempotent_skip", blocked)
        ids = _ids(span)
        span.end()
        return ids
