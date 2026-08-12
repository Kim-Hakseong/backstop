"""backstop-api. P0에서는 /health와 /run 두 개만 둔다.

/replay, /gate, /timeline, /admin/kill은 P2~P3에서 붙는다(CLAUDE.md §5).
"""

import base64
import json
import os

from fastapi import FastAPI, Header, HTTPException
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


class KillRequest(BaseModel):
    # "before_effect" = 다음 tick 의 부작용 직전에 죽는다 (가장 위험한 지점)
    # "now"           = 즉시 죽는다
    when: str = "before_effect"


# 다음 tick 에서 자살할지 여부. 프로세스가 죽으면 같이 사라진다 — 그게 정상이다.
_ARMED_CRASH = {"value": False}


def _suicide(reason: str) -> None:
    """프로세스를 즉시 죽인다.

    `sys.exit` 이 아니라 `os._exit` 다. 예외는 FastAPI 가 잡아 500 을 돌려주고,
    그러면 Pub/Sub 은 ack 을 받지 못한 게 아니라 **응답을 받아버린다**.
    부작용 직전의 진짜 크래시를 재현하려면 응답 없이 사라져야 한다.
    """
    print(f"[backstop] simulated crash: {reason}", flush=True)
    os._exit(137)


@app.post("/admin/kill")
def admin_kill(req: KillRequest, x_backstop_kill: str | None = Header(default=None)):
    """크래시 주입 (T2.3). 데모 2:30 장면의 트리거.

    BACKSTOP_KILL_TOKEN 이 설정돼 있으면 헤더로 같은 값을 줘야 한다. 인증 시스템이
    아니라, 공개 URL 에 놓인 자살 버튼을 지나가는 사람이 누르지 못하게 하는 자물쇠다.
    """
    expected = os.environ.get("BACKSTOP_KILL_TOKEN")
    if expected and x_backstop_kill != expected:
        raise HTTPException(status_code=403, detail="bad kill token")

    if req.when == "now":
        _suicide("immediate")

    _ARMED_CRASH["value"] = True
    return {"armed": True, "when": "before_effect"}


@app.post("/tick")
def tick(req: TickRequest) -> dict:
    """Pub/Sub `agent.tick` push 대상. 메시지 1건 = 워크플로 1스텝.

    비동기 장기 실행이 주장이 아니라 구조가 되는 지점이다. 커서는 Firestore 에
    남으므로 이 프로세스가 죽어도 다음 메시지가 이어간다.
    """
    run_id = req.resolve_run_id()
    wf = WorkflowRunner(default_ledger(), run_id)

    def crash_if_armed(step) -> None:
        if _ARMED_CRASH["value"]:
            _ARMED_CRASH["value"] = False
            _suicide(f"before effect of step '{step.name}' (run {run_id})")

    run = wf.tick(before_effect=crash_if_armed)
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
