"""T0.3 완료 조건 확인: 에이전트가 도구를 1회 호출하고 결과를 반환한다.

    uv run python scripts/smoke_agent.py

Vertex AI 자격증명이 필요하다. 종료 코드 0 = 도구 호출 1건 이상 관측.
"""

import asyncio
import os
import sys

from google.adk.runners import InMemoryRunner
from google.genai import types

from backstop.ledger import TOOL_CALL, FirestoreLedger, InMemoryLedger
from subject_agent.agent import build_agent
from subject_agent.tools.erp import ISSUED_POS

PROMPT = "Raise a purchase order for vendor acme-corp, 4200 USD, one laptop."
RUN_ID = os.environ.get("RUN_ID", "smoke-run")


def build_ledger():
    """PROJECT_ID 가 있으면 Firestore, 없으면 메모리. 오프라인에서도 돌아야 한다."""
    project = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project and not os.environ.get("BACKSTOP_OFFLINE"):
        print(f"ledger: Firestore ({project})")
        return FirestoreLedger(project=project)
    print("ledger: in-memory")
    return InMemoryLedger()


async def main() -> int:
    ledger = build_ledger()
    runner = InMemoryRunner(
        agent=build_agent(ledger=ledger, run_id=RUN_ID), app_name="backstop-smoke"
    )
    session = await runner.session_service.create_session(
        app_name="backstop-smoke", user_id="p0"
    )
    tool_calls = 0
    async for event in runner.run_async(
        user_id="p0",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=PROMPT)]),
    ):
        for part in (event.content.parts if event.content else []) or []:
            if part.function_call:
                tool_calls += 1
                print(f"tool_call: {part.function_call.name} {dict(part.function_call.args)}")
            elif part.text:
                print(f"text: {part.text.strip()}")

    events = ledger.events(RUN_ID)
    effects = ledger.effects(RUN_ID)
    call_events = [e for e in events if e.kind == TOOL_CALL]

    print(f"\ntool calls observed : {tool_calls}")
    print(f"ledger tool_call events: {len(call_events)}")
    print(f"ledger events (total)  : {len(events)}")
    print(f"ledger effects         : {len(effects)}")
    for e in effects:
        print(f"  effect {e.target}  key={e.idem_key[:16]}…")
    print(f"stub side effects      : {len(ISSUED_POS)}")

    # T1.3 완료 조건: 도구 호출 수만큼 tool_call 이벤트가 원장에 있다.
    ok = tool_calls >= 1 and len(call_events) == tool_calls
    print(f"\nT1.3 condition (tool calls == tool_call events): {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
