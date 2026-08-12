"""backstop-api. P0에서는 /health와 /run 두 개만 둔다.

/replay, /gate, /timeline, /admin/kill은 P2~P3에서 붙는다(CLAUDE.md §5).
"""

import base64
import json
import os

from fastapi import FastAPI
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel

from backstop.ledger import default_ledger
from subject_agent.agent import build_agent
from subject_agent.workflow import STEPS, WorkflowRunner

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


class TickRequest(BaseModel):
    """Pub/Sub push 봉투 또는 직접 호출 둘 다 받는다."""

    message: dict | None = None
    subscription: str | None = None
    run_id: str | None = None

    def resolve_run_id(self) -> str:
        # Pub/Sub push: {"message": {"data": <base64>, "attributes": {...}}}
        if self.message:
            attrs = self.message.get("attributes") or {}
            if attrs.get("run_id"):
                return attrs["run_id"]
            data = self.message.get("data")
            if data:
                decoded = base64.b64decode(data).decode("utf-8").strip()
                try:
                    return json.loads(decoded)["run_id"]
                except (json.JSONDecodeError, KeyError, TypeError):
                    return decoded
        return self.run_id or "run-default"


@app.get("/health")
def health() -> dict:
    """Cloud Run 공개 URL이 200을 반환하는지 — P0 검증 게이트 그 자체."""
    return {
        "status": "ok",
        "service": "backstop-api",
        "model": os.environ.get("BACKSTOP_MODEL", "gemini-3.5-flash"),
    }


@app.post("/tick")
def tick(req: TickRequest) -> dict:
    """Pub/Sub `agent.tick` push 대상. 메시지 1건 = 워크플로 1스텝.

    비동기 장기 실행이 주장이 아니라 구조가 되는 지점이다. 커서는 Firestore 에
    남으므로 이 프로세스가 죽어도 다음 메시지가 이어간다.
    """
    run_id = req.resolve_run_id()
    wf = WorkflowRunner(default_ledger(), run_id)
    run = wf.tick()
    return {
        "run_id": run_id,
        "cursor": run.cursor,
        "status": run.status,
        "total_steps": len(STEPS),
        "step": STEPS[run.cursor - 1].name if 0 < run.cursor <= len(STEPS) else None,
    }


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    ledger = default_ledger()
    run = ledger.get_run(run_id)
    if run is None:
        return {"run_id": run_id, "status": "not_found"}
    return {
        "run_id": run.run_id,
        "cursor": run.cursor,
        "status": run.status,
        "agent_version": run.agent_version,
        "events": len(ledger.events(run_id)),
        "effects": len(ledger.effects(run_id)),
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
