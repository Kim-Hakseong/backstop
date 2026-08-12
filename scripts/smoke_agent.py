"""T0.3 완료 조건 확인: 에이전트가 도구를 1회 호출하고 결과를 반환한다.

    uv run python scripts/smoke_agent.py

Vertex AI 자격증명이 필요하다. 종료 코드 0 = 도구 호출 1건 이상 관측.
"""

import asyncio
import sys

from google.adk.runners import InMemoryRunner
from google.genai import types

from subject_agent.agent import build_agent
from subject_agent.tools.erp import ISSUED_POS

PROMPT = "Raise a purchase order for vendor acme-corp, 4200 USD, one laptop."


async def main() -> int:
    runner = InMemoryRunner(agent=build_agent(), app_name="backstop-smoke")
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

    print(f"\ntool calls: {tool_calls} | effects recorded: {len(ISSUED_POS)}")
    return 0 if tool_calls >= 1 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
