"""6주 벤더 온보딩 워크플로 (감사 검체).

스텝 하나 = tick 하나. 커서는 Firestore `runs.cursor` 에 남으므로 프로세스가 죽어도
다음 tick 이 이어간다.

**왜 스텝마다 LLM 을 부르지 않는가**: 원장이 1,000건 규모여야 6주를 증명할 수 있는데
스텝마다 모델을 부르면 비용과 시간이 스프린트를 잡아먹는다(CLAUDE.md §10 — Gemini 는
Narrator 에서만). 스텝은 결정론적으로 실행되고, **ADK 가 부르는 것과 똑같은
`LedgerCallbacks`** 를 통과한다. 관문 ①과 원장 기록은 LLM 경로와 동일하다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable

from backstop.clock import Clock, SystemClock
from backstop.ledger import (
    COMMITTED,
    DONE,
    RESUMED,
    RUNNING,
    Ledger,
    Run,
    effect_key,
)
from subject_agent.callbacks import LedgerCallbacks
from subject_agent.tools import erp, mail, payment

TOOLS: dict[str, Callable[..., dict]] = {
    "erp.create_po": erp.create_po,
    "mail.send": mail.send,
    "payment.schedule_payment": payment.schedule_payment,
}


@dataclass(frozen=True)
class Step:
    name: str
    week: int
    tool: str
    args: Callable[[dict[str, Any]], dict[str, Any]]


def _po_args(ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "vendor_id": ctx["vendor_id"],
        "amount_usd": ctx["amount_usd"],
        "line_item": ctx["line_item"],
    }


# 6주 · 12스텝. 주당 2스텝이고, 부작용이 나가는 스텝은 매주 최소 1개다.
STEPS: list[Step] = [
    Step("intro_email", 1, "mail.send", lambda c: {
        "to": c["contact"], "subject": "Vendor onboarding kickoff",
        "body": f"Welcome {c['vendor_id']}.",
    }),
    Step("request_documents", 1, "mail.send", lambda c: {
        "to": c["contact"], "subject": "Compliance documents required",
        "body": "Please return the W-9 and insurance certificate.",
    }),
    Step("acknowledge_documents", 2, "mail.send", lambda c: {
        "to": c["contact"], "subject": "Documents received",
        "body": "Thanks, we are reviewing.",
    }),
    Step("compliance_review", 2, "mail.send", lambda c: {
        "to": "compliance@acme.example", "subject": f"Review {c['vendor_id']}",
        "body": "Vendor packet ready for review.",
    }),
    Step("negotiate_terms", 3, "mail.send", lambda c: {
        "to": c["contact"], "subject": "Proposed terms",
        "body": "Net 30, volume tier 2.",
    }),
    Step("terms_agreed", 3, "mail.send", lambda c: {
        "to": c["contact"], "subject": "Terms agreed",
        "body": "Countersigned copy attached.",
    }),
    # 4주차: 부작용이 가장 위험해지는 구간. 데모의 붉은 마커가 여기 선다.
    Step("create_purchase_order", 4, "erp.create_po", _po_args),
    Step("po_confirmation", 4, "mail.send", lambda c: {
        "to": c["contact"], "subject": "PO issued",
        "body": "Purchase order issued.",
    }),
    Step("schedule_first_payment", 5, "payment.schedule_payment", lambda c: {
        "vendor_id": c["vendor_id"], "amount_usd": c["amount_usd"],
        "due_date": c["due_date"],
    }),
    Step("payment_notice", 5, "mail.send", lambda c: {
        "to": c["contact"], "subject": "Payment scheduled",
        "body": "First payment scheduled.",
    }),
    Step("delivery_check", 6, "mail.send", lambda c: {
        "to": c["contact"], "subject": "Delivery confirmation",
        "body": "Please confirm delivery.",
    }),
    Step("close_onboarding", 6, "mail.send", lambda c: {
        "to": "ops@acme.example", "subject": f"Onboarding complete {c['vendor_id']}",
        "body": "Vendor is active.",
    }),
]


def context_for(vendor_id: str) -> dict[str, Any]:
    return {
        "vendor_id": vendor_id,
        "contact": f"ap@{vendor_id}.example",
        "amount_usd": 4200,
        "line_item": "one laptop",
        "due_date": "2026-09-15",
    }


def default_context(vendor_id: str = "acme-corp") -> dict[str, Any]:
    return context_for(vendor_id)


def _display_vendor(vendor_id: str) -> str:
    """"acme-corp" → "ACME Corp".

    v3 에서 들어간 표시용 정규화. 사람이 읽기 좋으라고 넣은 변경이고, 기능적으로는
    같은 벤더를 가리킨다. **그런데 멱등성 키가 이 문자열 위에서 계산된다.**
    """
    head, _, tail = vendor_id.partition("-")
    return f"{head.upper()} {tail.title()}".strip()


# 에이전트 버전별 인자 변형. v1 이 과거 원장을 만든 버전이다.
#
# v3 는 `erp.create_po` 에 넘기는 vendor_id 표기만 바꾼다. 메일 본문·수신자는
# 건드리지 않는다 — 실제 프롬프트 수정이 대개 이런 모양이기 때문이다.
AGENT_VERSIONS: dict[str, dict[str, Any]] = {
    "v1": {},
    "v3": {
        "erp.create_po": lambda args: {
            **args,
            "vendor_id": _display_vendor(args["vendor_id"]),
        }
    },
}


def apply_version(version: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    transform = AGENT_VERSIONS.get(version, {}).get(tool)
    return transform(args) if transform else args


class _Tool:
    """ADK BaseTool 의 최소 대역. 콜백은 `.name` 만 본다."""

    def __init__(self, name: str) -> None:
        self.name = name


class WorkflowRunner:
    def __init__(
        self,
        ledger: Ledger,
        run_id: str,
        agent_version: str = "v1",
        context: dict[str, Any] | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._ledger = ledger
        self._run_id = run_id
        self._version = agent_version
        self._ctx = context or default_context()
        self._clock = clock or SystemClock()
        self._callbacks = LedgerCallbacks(ledger, run_id)

    def start(self) -> Run:
        return self._ledger.start_run(self._run_id, self._version)

    def tick(self, before_effect: Callable[[Step], None] | None = None) -> Run:
        """스텝 하나를 전진시킨다. 이미 끝났으면 아무 것도 하지 않는다.

        `before_effect` 는 크래시 주입 지점이다(T2.3). 부작용이 나가기 **직전**,
        관문 ①을 통과한 뒤에 불린다 — 가장 위험한 지점이다.
        """
        run = self._ledger.get_run(self._run_id) or self.start()
        if run.cursor >= len(STEPS):
            return self._ledger.save_run(replace(run, status=DONE))

        step = STEPS[run.cursor]
        tool = _Tool(step.tool)
        args = step.args(self._ctx)
        ctx = _CallContext(f"{self._run_id}:{run.cursor}")

        short_circuit = self._callbacks.before_tool(
            tool=tool, args=args, tool_context=ctx
        )
        if short_circuit is None:
            if before_effect is not None:
                before_effect(step)  # ← 여기서 죽으면 부작용은 아직 안 나갔다
            response = TOOLS[step.tool](**args)
        else:
            response = short_circuit

        self._callbacks.after_tool(
            tool=tool, args=args, tool_context=ctx, tool_response=response
        )

        # 이 스텝의 부작용이 **확정**됐을 때만 커서를 전진시킨다.
        #
        # 차단에는 두 종류가 있고 의미가 다르다:
        #   - committed 를 만나 차단됨 → 이미 끝난 일이다. 전진해야 한다.
        #   - lease 안의 pending 을 만나 차단됨 → 다른 워커가 실행 중이거나, 방금
        #     죽은 워커의 흔적이다. 아직 안 끝났다. **전진하면 스텝이 통째로 사라진다.**
        #
        # 실제로 그렇게 사라졌다: 크래시 후 재전달이 lease(25s) 안에 도착하자
        # 재시도가 중복으로 오인돼 건너뛰어졌고, 커서만 올라가 워크플로가
        # "완료"됐다. 부작용 12건 중 11건만 나간 채로.
        key = effect_key(step.tool, args, self._run_id)
        settled = self._ledger.find_effect(self._run_id, key)
        if settled is None or settled.status != COMMITTED:
            return run  # 커서 유지 → 다음 tick 이 같은 스텝을 다시 시도한다

        advanced = replace(
            run,
            cursor=run.cursor + 1,
            last_tick_at=self._clock.now(),
            status=DONE if run.cursor + 1 >= len(STEPS) else RUNNING,
        )
        return self._ledger.save_run(advanced)

    def resume(self) -> Run:
        run = self._ledger.get_run(self._run_id)
        if run is None:
            return self.start()
        return self._ledger.save_run(replace(run, status=RESUMED))

    def run_to_completion(self, max_ticks: int = 100) -> Run:
        run = self.start()
        for _ in range(max_ticks):
            run = self.tick()
            if run.status == DONE:
                break
        return run


class _CallContext:
    """ADK ToolContext 의 최소 대역."""

    def __init__(self, function_call_id: str) -> None:
        self.function_call_id = function_call_id
