"""backstop-api. P0에서는 /health와 /run 두 개만 둔다.

/replay, /gate, /timeline, /admin/kill은 P2~P3에서 붙는다(CLAUDE.md §5).
"""

import os

from fastapi import FastAPI
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel

from subject_agent.agent import build_agent

app = FastAPI(title="backstop-api")

APP_NAME = "backstop"
_runner: InMemoryRunner | None = None


def get_runner() -> InMemoryRunner:
    global _runner
    if _runner is None:
        _runner = InMemoryRunner(agent=build_agent(), app_name=APP_NAME)
    return _runner


class RunRequest(BaseModel):
    prompt: str
    user_id: str = "p0"


@app.get("/health")
def health() -> dict:
    """Cloud Run 공개 URL이 200을 반환하는지 — P0 검증 게이트 그 자체."""
    return {
        "status": "ok",
        "service": "backstop-api",
        "model": os.environ.get("BACKSTOP_MODEL", "gemini-3.5-flash"),
    }


@app.post("/run")
async def run(req: RunRequest) -> dict:
    runner = get_runner()
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=req.user_id
    )
    tool_calls: list[dict] = []
    texts: list[str] = []
    async for event in runner.run_async(
        user_id=req.user_id,
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=req.prompt)]),
    ):
        for part in (event.content.parts if event.content else []) or []:
            if part.function_call:
                tool_calls.append(
                    {"name": part.function_call.name, "args": dict(part.function_call.args)}
                )
            elif part.text:
                texts.append(part.text.strip())

    return {"tool_calls": tool_calls, "text": "\n".join(t for t in texts if t)}
