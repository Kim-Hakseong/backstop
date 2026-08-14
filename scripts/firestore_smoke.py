"""T0.5 완료 조건 확인: Firestore `events`에 문서 1건을 쓴다.

    PROJECT_ID=<id> uv run python scripts/firestore_smoke.py

여기서 쓰는 필드는 docs/engineering-rules.md §7의 `events` 스키마 부분집합이다. 정식 쓰기 경로는
P1의 backstop/ledger.py가 맡는다 — 이 스크립트는 연결과 권한만 증명한다.
시간은 서버 타임스탬프로 남긴다. datetime.now()를 부르지 않는다(R3).
"""

import os
import sys

from google.cloud import firestore


def main() -> int:
    project = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        print("PROJECT_ID가 없다.", file=sys.stderr)
        return 1

    db = firestore.Client(project=project)
    doc = {
        "run_id": "p0-smoke",
        "seq": 0,
        "kind": "tool_call",
        "tool_name": "erp.create_po",
        "args_canonical": {"vendor_id": "acme-corp", "amount_usd": 4200.0},
        "at": firestore.SERVER_TIMESTAMP,
    }
    ref = db.collection("events").document()
    ref.set(doc)

    written = ref.get().to_dict()
    print(f"wrote events/{ref.id}")
    print(f"  kind={written['kind']} tool_name={written['tool_name']} at={written['at']}")
    print("\n콘솔에서 확인: "
          f"https://console.cloud.google.com/firestore/databases/-default-/data/panel/events?project={project}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
