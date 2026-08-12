"""T2.4: 크래시 → Pub/Sub 재전달 → 재개. 중복 부작용 0건을 10회 반복 검증한다.

    PROJECT_ID=backstop-haku-2026 uv run python scripts/crash_demo.py --rounds 10

한 라운드의 흐름:
  1. tick 을 몇 번 밀어 워크플로를 진행시킨다
  2. `/admin/kill` 로 다음 tick 의 **부작용 직전** 크래시를 무장한다
  3. tick 을 민다 → 인스턴스가 응답 없이 죽는다 → Pub/Sub 이 ack 을 못 받는다
  4. 재전달을 기다린다(ack deadline 30s). 선점 리스(25s)가 만료돼 재선점이 허용된다
  5. 남은 tick 을 밀어 워크플로를 끝낸다
  6. 검증: 확정된 부작용의 idem_key 가 전부 유일한가

종료 코드 0 = 전 라운드에서 중복 0건.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter

import urllib.error
import urllib.request

from google.cloud import firestore


def publish(topic: str, project: str, run_id: str) -> None:
    subprocess.run(
        [
            "gcloud", "pubsub", "topics", "publish", topic,
            f"--message={json.dumps({'run_id': run_id})}",
            f"--project={project}",
        ],
        check=True,
        capture_output=True,
    )


def post(url: str, payload: dict, headers: dict | None = None, timeout: int = 90):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        # 크래시를 유도한 요청은 응답이 없는 게 정상이다.
        return {"crashed": True, "detail": str(exc)}


def get(url: str, timeout: int = 60) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def duplicates(db: firestore.Client, run_id: str) -> tuple[int, list[str], int]:
    docs = [
        d.to_dict()
        for d in db.collection("effects").where("run_id", "==", run_id).stream()
    ]
    committed = [d for d in docs if d.get("status") == "committed"]
    counts = Counter(d["idem_key"] for d in committed)
    dupes = [k for k, n in counts.items() if n > 1]
    return len(committed), dupes, len(docs) - len(committed)


def advance(args, run_id: str, steps: int) -> dict:
    """스텝을 순차로 전진시킨다. 응답을 기다린 뒤 다음을 보낸다.

    동시에 밀면 안 된다 — 여러 tick 이 같은 커서를 노리고 하나만 이긴다(나머지는
    관문 ①이 정상적으로 막는다). 그러면 워크플로가 진행되지 않아 크래시 시나리오를
    검증할 수 없다. 동시성 자체는 test_concurrent_guard.py 가 따로 검증한다.
    """
    state: dict = {}
    for _ in range(steps):
        state = post(f"{args.url}/tick", {"run_id": run_id})
        if state.get("status") == "done":
            break
    return state


def run_round(args, db, index: int) -> dict:
    run_id = f"{args.prefix}-{index}"
    print(f"\n=== round {index}: {run_id} ===", flush=True)

    # 1) 순차 tick 으로 워크플로를 절반쯤 진행시킨다
    advance(args, run_id, 5)
    state = get(f"{args.url}/runs/{run_id}")
    print(f"  before crash : cursor={state.get('cursor')} effects={state.get('effects')}")

    # 2) 다음 tick 의 부작용 직전 크래시를 무장한다
    armed = post(
        f"{args.url}/admin/kill",
        {"when": "before_effect"},
        {"X-Backstop-Kill": args.kill_token},
    )
    print(f"  armed        : {armed}")

    # 3) 크래시는 **Pub/Sub 로** 유발한다. ack 을 못 받은 메시지가 재전달돼야
    #    재개가 자동으로 일어나기 때문이다. HTTP 로 죽이면 재전달이 없다.
    publish(args.topic, args.project, run_id)
    print(f"  crash published, waiting {args.redeliver}s for redelivery", flush=True)
    time.sleep(args.redeliver)

    mid = get(f"{args.url}/runs/{run_id}")
    print(f"  after resume : cursor={mid.get('cursor')} effects={mid.get('effects')}")

    # 4) 남은 스텝을 순차로 끝낸다
    advance(args, run_id, 12)
    state = get(f"{args.url}/runs/{run_id}")
    total, dupes, pending = duplicates(db, run_id)
    print(
        f"  final        : cursor={state.get('cursor')}/{12} "
        f"committed={total} pending={pending} duplicates={len(dupes)}"
    )
    if dupes:
        print(f"  DUPLICATE KEYS: {dupes}")

    return {
        "run_id": run_id,
        "cursor": state.get("cursor"),
        "committed": total,
        "duplicates": len(dupes),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="https://backstop-api-5nohynuexa-uc.a.run.app")
    p.add_argument("--project", default="backstop-haku-2026")
    p.add_argument("--topic", default="agent.tick")
    p.add_argument("--kill-token", default="demo-kill-2026")
    p.add_argument("--rounds", type=int, default=10)
    p.add_argument("--prefix", default="crash")
    p.add_argument("--settle", type=int, default=12, help="tick 처리 대기(초)")
    p.add_argument("--redeliver", type=int, default=45, help="재전달 대기(초)")
    args = p.parse_args()

    db = firestore.Client(project=args.project)
    results = [run_round(args, db, i) for i in range(1, args.rounds + 1)]

    total_dupes = sum(r["duplicates"] for r in results)
    finished = sum(1 for r in results if r["cursor"] == 12)

    print("\n" + "=" * 60)
    print(f"rounds              : {len(results)}")
    print(f"completed workflows : {finished}/{len(results)}")
    print(f"duplicate effects   : {total_dupes}")
    print("=" * 60)
    print("T2.4:", "PASS" if total_dupes == 0 else "FAIL")
    return 0 if total_dupes == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
