# LOG.md — Backstop 스프린트 로그

**기간**: 2026-08-12 ~ 2026-08-31 (19일, solo)
**내부 마감**: 2026-08-31 21:00 KST
**실제 마감**: 2026-09-01 09:00 KST (Aug 31 17:00 PDT)
**가용 시간 가정**: 하루 4~6시간 / 총 80~110시간

**현재 Phase**: P2 (P0·P1 게이트 08-12 통과. P1은 계획 대비 6일 선행)
**배포 URL**: https://backstop-api-911984605187.us-central1.run.app
**현재 잔여 크레딧**: 미확인 — 08-12 Cloud Build 1회 + Cloud Run + Vertex 호출 3회로 실사용은 $1 미만 추정. **콘솔에서 눈으로 확인 필요**(CLAUDE.md §10)

---

## Phase P0 — 배포 먼저 (08-12 ~ 08-14)
> 목표: 다른 어떤 코드보다 먼저 공개 URL을 만든다. 이게 안 되면 나머지는 전부 무의미하다.

### T0.1 GCP 프로젝트 + 크레딧
- 목표: 프로젝트 생성, $150 크레딧 폼 제출, Vertex AI / Cloud Run / Pub/Sub / Firestore API 활성화
- 완료 조건: `gcloud run services list`가 에러 없이 빈 목록을 반환한다
- 예상: 1h
- 실소요: 0.4h
- [x] 08-12. 프로젝트 `backstop-haku-2026`, 결제 연결(018E97-4DB4AA-E37287). API 6종 활성화(run/aiplatform/firestore/pubsub/cloudbuild/artifactregistry). Firestore 네이티브 DB 생성(nam5). **완료 조건 확인: `gcloud run services list` → "Listed 0 items." 종료 코드 0.**

### T0.2 리포 스캐폴드
- 목표: uv 프로젝트, `backstop/`·`subject_agent/`·`api/`·`tests/` 디렉터리, Makefile 6개 타깃(빈 껍데기 가능)
- 완료 조건: `make setup && make test`가 통과(테스트 0건이어도 됨)
- 예상: 1h / 실소요: 0.4h
- [x] 08-12. `make setup` (uv sync, py3.12) + `make test` 2건 통과. Makefile 7 타깃(setup/test/replay/gate/bench/deploy/demo). `tests/test_scaffold.py`가 패키지 import와 Makefile 타깃 존재를 검사한다.

### T0.3 ADK 최소 에이전트
- 목표: ADK로 도구 1개(`erp.create_po` 스텁)를 가진 에이전트. Gemini 3.5 Flash 연결
- 완료 조건: 로컬에서 에이전트가 도구를 1회 호출하고 결과를 반환한다
- 예상: 2.5h / 실소요: 1.1h
- [x] 08-12. **완료 조건 확인**: `scripts/smoke_agent.py` → `tool_call: create_po {'vendor_id': 'acme-corp', 'line_item': 'one laptop', 'amount_usd': 4200}` → `PO-8428` 반환. 도구 호출 1건. Gemini 3.5 Flash 라이브.
- 참고: `create_po`의 PO 번호는 인자 해시에서 파생된다. `vendor_id="acme-corp"` → PO-0382, `"ACME Corp"` → PO-3593. **T3.6 분기 시나리오의 씨앗이 이미 여기 있다.**

### T0.4 FastAPI 래핑 + Cloud Run 배포
- 목표: `api/main.py`에 `/health`, `/run` 두 엔드포인트. Cloud Run 배포(min-instances=0)
- 완료 조건: **공개 URL이 `/health`에 200을 반환한다**
- 예상: 2.5h / 실소요: 1.0h
- [x] 08-12. **완료 조건 확인: 공개 URL `/health` → HTTP 200.**
  - URL: https://backstop-api-911984605187.us-central1.run.app
  - `{"status":"ok","service":"backstop-api","model":"gemini-3.5-flash"}`
  - `/run`도 배포본에서 종단 확인: 도구 호출 1건 → PO-8428. Cloud Run 런타임 SA가 Vertex(global)에 도달한다.
  - min-instances=0, max-instances=3, allow-unauthenticated(로그인 없이 심사 가능)
- ⚠️ 이 태스크가 08-14까지 안 끝나면 전체 계획을 재검토한다

### T0.5 Firestore 쓰기 1건
- 목표: 도구 호출 결과를 Firestore `events`에 1건 쓴다
- 완료 조건: 콘솔에서 문서 1건이 눈에 보인다
- 예상: 1h
- 실소요: 0.3h
- [x] 08-12. **완료 조건 확인**: `events/irPeR3qP0k94DiMPWgiq` 기록됨. `kind=tool_call tool_name=erp.create_po at=2026-08-12 06:37:38+00:00`. 서버 타임스탬프 사용(R3 준수).

### T0.6 워크숍 시청 (고정 일정)
- 목표: 08-14 13:00 KST "Build a Long-Running Agent: Persistent Workflows with Google ADK" (멱등성 함정)
- 완료 조건: P1 설계에 반영할 항목을 Decision Log에 3줄 이상 적는다
- 예상: 1.5h
- [ ]

**P0 검증 게이트**: 공개 URL 200 + Firestore 문서 1건. 통과 시 `git tag p0-gate-passed`.

✅ **08-12 통과.** 공개 URL 200 + `events/irPeR3qP0k94DiMPWgiq`. 태그 `p0-gate-passed`.
계획(08-14) 대비 2일 빠르다. T0.6 워크숍은 08-14 고정 일정이라 미완으로 남는다 — 게이트 조건이 아니므로 P1을 막지 않는다.

---

## Phase P1 — 원장 (08-15 ~ 08-18)
> 목표: 에이전트가 하는 모든 일이 되감을 수 있는 형태로 남는다.

### T1.1 이벤트 스키마 확정
- 목표: `events`(무슨 일이 있었나) / `effects`(외부로 나간 부작용) / `runs`(실행 단위) 3개 컬렉션 스키마
- 완료 조건: 스키마 문서가 README에 표로 들어간다. 필드마다 "왜 필요한지" 한 줄
- 예상: 2h / 실소요: 0.5h
- [x] 08-12. README.md 생성. 컬렉션 4종 전 필드에 "왜 필요한가" 1줄. 추가로 **멱등성 키 정규화 규칙표**를 확정해 넣었다(T1.4의 입력). 시뮬레이션 원장 고지 + 3줄 재현 + `<TBD>` 수치 자리 포함.
- 확정 사항 2개: (1) 재생 순서는 `seq` 단독 근거, `at`는 정렬에 쓰지 않는다 — 동시 tick에서 타임스탬프 정렬은 결정론을 깬다. (2) `args_canonical`만 저장하고 원본 인자는 저장하지 않는다 — 두 벌이면 어느 쪽이 진실인지 모르게 된다.

### T1.2 clock.py — 시간 주입
- 목표: `datetime.now()` 직접 호출 제거. `Clock` 프로토콜 + `FrozenClock`
- 완료 조건: 6주 원장을 실시간 대기 없이 생성할 수 있다
- 예상: 1h / 실소요: 0.6h
- [x] 08-12. `backstop/clock.py` — `Clock` 프로토콜 + `SystemClock` + `FrozenClock`. **완료 조건 확인**: 6주(42일)를 1,008 tick으로 전진, 벽시계 소요 0.4ms.
- `tests/test_clock.py`가 R3를 저장소 전체에 강제한다. **정규식이 아니라 AST로 검사한다** — 정규식 버전은 `firestore_smoke.py` 독스트링의 "datetime.now()를 부르지 않는다"라는 **설명 문장**을 위반으로 오탐했다. 막으려는 건 텍스트가 아니라 호출이다. 가드 자체를 검사하는 테스트도 붙였다(실제 호출 3종은 잡고, 산문·`clock.now()`는 안 잡는지).
- `backstop/clock.py`만 벽시계를 읽는 유일한 예외로 허용 목록에 있다.

### T1.3 ADK 콜백 → 원장
- 목표: `before_tool_callback`/`after_tool_callback`에서 이벤트 기록
- 완료 조건: 에이전트 1회 실행 시 도구 호출 수만큼 `events` 문서가 생긴다
- 예상: 3h / 실소요: 1.4h
- [x] 08-12 (인메모리 검증 완료, Firestore 종단 확인은 인덱스 생성 대기). `backstop/ledger.py`(Event/Effect + InMemory/Firestore 백엔드) + `subject_agent/callbacks.py`. 테스트 13건.
- 🔴 **함정 1 — ADK는 콜백을 키워드로 부른다.** `callback(tool=, args=, tool_context=, tool_response=)`. 파라미터명을 `context`로 뒀더니 단위 테스트는 전부 통과하는데 라이브에서 `TypeError`가 났다. 위치 인자로만 테스트했기 때문이다. 호출 규약을 고정하는 테스트를 추가했다(`test_callbacks_accept_adk_keyword_calling_convention`). 출처: `google/adk/flows/llm_flows/functions.py:593`
- 🔴 **함정 2 — Firestore 복합 인덱스.** `where(run_id) + order_by(seq)`는 인덱스 없이는 `FailedPrecondition 400`이다. `firestore.indexes.json`을 커밋했다(events 2종 + effects 1종). 새 프로젝트에서 재현하려면 이게 필요하다.

### T1.4 멱등성 키 설계
- 목표: `(tool_name, canonical_args_hash, run_scope)` 조합. 정규화 규칙 문서화
- 완료 조건: 같은 의미의 호출이 인자 순서·공백 차이에도 같은 키를 낸다 (pytest)
- 예상: 2.5h / 실소요: 0.9h
- [x] 08-12. `backstop/idempotency.py` — `canonicalize_args` + `canonical_repr` + `idem_key`. 순수 모듈(네트워크·LLM·시계 없음). 테스트 15건.
- **완료 조건 확인**: P0에서 실제로 갈렸던 두 호출이 이제 같은 키를 낸다. 라이브(`amount_usd=4200`, 인자 순서 다름) vs 로컬(`4200.0`, `' acme-corp '`) → 둘 다 `cef2a86729c23d9b…`.
- 규칙: 인자 순서 무시 / 정수형 float→int / NFC+trim / None 필드 제거 / **리스트 순서는 유의미** / **bool≠int**(파이썬에서 bool이 int 서브클래스라 True와 1이 충돌할 뻔했다) / `vendor_id` 대소문자는 의도적으로 유의미.
- `CANON_VERSION` 도입. 규칙을 바꾸면 과거 키와 비교 불가라 버전을 올려야 한다.
- ⚠️ **순서 변경**: LOG 순서상 T1.3이 먼저지만 T1.4를 먼저 했다. T1.3이 `args_canonical`을 저장하는데, 정규화가 없으면 그 필드가 이름과 다른 내용(원본 인자)을 담게 된다. 플레이스홀더 위에 원장을 쌓지 않는다.
- ⚠️ 여기가 프로젝트의 심장이다. 대충 하면 P3에서 게이트가 의미 없어진다
- 🔴 **P0에서 이미 실물로 관측된 정규화 요구사항 — 숫자 타입.** 라이브 에이전트가 `amount_usd=4200`(int)을 보냈다. 로컬 테스트는 `4200.0`(float)였다. 해시가 갈린다: int → PO-8428, float → PO-9084. LLM은 같은 의미의 인자를 호출마다 다른 JSON 타입으로 보낸다. 정규화 규칙에 **숫자 타입 통일**을 넣지 않으면 관문 ①이 통과시키고 관문 ②가 false positive `DUPLICATE`를 낸다. 인자 순서·공백보다 이게 먼저다.

### T1.5 IdempotencyGuard (관문 ①)
- 목표: 같은 키의 부작용이 두 번 나가지 않게 차단. 차단 시 `idempotent_skip` 이벤트 기록
- 완료 조건: 같은 도구 호출 2회 → `effects` 1건 + `idempotent_skip` 1건
- 예상: 2.5h / 실소요: 1.0h
- [x] 08-12. **완료 조건 확인**: 같은 호출 2회 → `events=[tool_call, tool_result, idempotent_skip]`, `effects=1`, 스텁이 실제로 발행한 PO 1건. 2번째 호출은 이전 결과(PO-6255)를 그대로 돌려받는다.
- 차단은 **예외가 아니라 이전 결과 반환**이다. ADK는 `before_tool_callback`이 dict를 반환하면 도구를 건너뛰고 그 dict를 결과로 쓴다. 예외를 던지면 에이전트가 멈춰서 재개 시나리오가 성립하지 않는다.
- 🔴 **함정 3 (관문 ①을 무력화할 뻔한 것) — ADK는 도구를 건너뛰어도 `after_tool_callback`을 그대로 부른다** (`functions.py` Step 5는 Step 2의 단축과 무관하게 실행된다). after에서 무조건 부작용을 기록하면 **관문 ①이 막은 바로 그 중복이 원장에 남는다.** 차단된 슬롯을 표시해 after가 건너뛰게 했고, `test_after_callback_does_not_record_effect_for_blocked_call`이 이를 고정한다.
- 진실의 근거는 프로세스 메모리가 아니라 원장이다 → 새 프로세스(새 콜백 인스턴스)로 재개해도 중복이 막힌다(`test_resume_after_crash_does_not_duplicate`). P2 재개 시나리오의 축소판이 이미 통과한다.

### T1.6 test_idempotency.py
- 목표: 관문 ① 불변식 테스트 4건
- 완료 조건: `make test` 통과
- 예상: 1.5h / 실소요: (T1.4·T1.5에 포함)
- [x] 08-12. 요구는 4건인데 25건이 됐다 — `tests/test_idempotency.py` 15건(키 정규화) + `tests/test_guard.py` 10건(관문 ① 동작). `make test` 59건 통과.

### T1.7 OTel 스팬
- 목표: 콜백에서 스팬 열고 닫기. `trace_id`/`span_id`를 이벤트에 저장
- 완료 조건: 이벤트 문서에서 스팬 ID로 추론 체인을 역추적할 수 있다
- 예상: 2h / 실소요: 0.7h
- [x] 08-12. `backstop/otel.py` — `ToolSpans`. 스팬은 `before_tool`에서 열려 `after_tool`에서 닫힌다(두 콜백에 걸쳐 있어 `with` 불가, 수동 start/end). 테스트 6건.
- **완료 조건 확인 (Firestore 실물)**: `events/p11ooSoAX0DokSUPCxgH`(tool_call)와 `events/vWWURLXQardGvqG3zoNf`(tool_result)가 같은 `trace_id=d0342f5ca321f87d…`, `span_id=0bca83a4c38596af`를 공유한다. effect → event_id → span 경로가 성립한다 = 마커 카드의 `[trace ↗]` 링크 근거.
- 🔴 **함정 4 — TracerProvider가 없으면 OTel은 NonRecordingSpan을 주고 id가 전부 0이 된다.** 그러면 이벤트에 필드는 있는데 역참조가 불가능한 상태로 조용히 통과한다. `_ensure_provider()`가 SDK provider를 달고, `test_span_ids_are_real_not_zeros`가 0을 거부한다. **익스포터는 달지 않았다** — 필요한 건 실제 id 값이지 외부 전송이 아니다.
- 관문 ①이 차단한 호출도 스팬을 남긴다(`backstop.idempotent_skip=true` 속성). 막힌 호출이 감사에서 사라지면 안 된다.

**P1 검증 게이트**: 같은 호출 2회 → 부작용 1건. `make test` 통과. 태그 `p1-gate-passed`.

✅ **08-12 통과.** 같은 호출 2회 → `effects` 1건 + `idempotent_skip` 1건(`test_guard.py` 10건). `make test` 66건 통과. Firestore 종단 확인 완료. 태그 `p1-gate-passed`.
계획(08-18) 대비 6일 선행.

⚠️ **P2로 넘길 미해결 항목**: ADK가 기록하는 도구 이름이 `create_po`다(함수명). PRD·Design의 카드 예시는 `erp.create_po#PO-2291` 형태를 쓴다. 원장 **내부** 일관성은 유지되므로(키는 같은 이름으로 계산·비교된다) 게이트 정확성에는 영향이 없다. T2.5 시드 원장 생성에서 이름 규칙을 확정한다.

---

## Phase P2 — 비동기 + 크래시 (08-19 ~ 08-21)
> 목표: "몇 주간 백그라운드로 돈다"를 주장이 아니라 구조로 만든다.

### T2.1 Pub/Sub 토픽 + push 구독
- 목표: `agent.tick` 토픽 → Cloud Run push 엔드포인트
- 완료 조건: 메시지 발행 시 에이전트가 한 스텝 전진한다
- 예상: 3h / 실소요: 1.2h
- [x] 08-12. 토픽 `agent.tick` + push 구독 `agent-tick-push`(ack deadline 30s) → Cloud Run `/tick`.
- **완료 조건 확인**: `gcloud pubsub topics publish agent.tick --message '{"run_id":"p2-pubsub-01"}'` → `/runs/p2-pubsub-01`이 `cursor=0→1`, `events=2`, `effects=1`.
- Pub/Sub push 봉투는 base64다. 해석이 틀리면 엔드포인트가 200을 주면서 아무 일도 안 한다 — 조용히 실패하는 종류라 `tests/test_tick_endpoint.py`로 고정했다(attributes 우선, JSON payload, 평문, 직접 호출).
- 🔴 **함정 5 — `default_ledger()`가 요청마다 새 인메모리 원장을 만들었다.** 오프라인 모드에서 tick이 200을 돌려주는데 커서가 계속 1이었다. 프로세스당 캐시로 고쳤다.

### T2.2 워크플로 상태 영속화
- 목표: 6주 벤더 온보딩 워크플로를 스텝 단위로 쪼개고 상태를 Firestore `runs`에 저장
- 완료 조건: 프로세스를 껐다 켜도 다음 tick에서 이어서 진행된다
- 예상: 3.5h / 실소요: 1.0h
- [x] 08-12. `subject_agent/workflow.py` — 6주 12스텝 벤더 온보딩(주당 2스텝, 4주차에 `erp.create_po`, 5주차에 `payment.schedule_payment`). 커서는 `runs/{run_id}.cursor`.
- **완료 조건 확인**: `test_state_survives_a_new_runner_instance` — 새 `WorkflowRunner` 인스턴스(=새 프로세스)가 커서 2에서 이어받아 3으로 간다. 배포본에서도 tick 3회 → `cursor=3, events=6, effects=3`.
- **커서는 부작용 뒤에 전진한다.** 반대로 하면 크래시가 스텝을 건너뛴다.
- 스텝은 결정론적으로 실행되고 ADK와 **같은 `LedgerCallbacks`**를 통과한다. 스텝마다 LLM을 부르면 원장 1,000건에 비용·시간이 폭발한다(CLAUDE.md §10). 관문 ①과 원장 기록은 LLM 경로와 동일하다.
- 도구 3종(`erp.create_po`/`mail.send`/`payment.schedule_payment`). 5개 상한 안이다.

### T2.3 크래시 주입 경로
- 목표: `POST /admin/kill` — 실행 중간에 프로세스를 자살시킨다
- 완료 조건: 부작용 실행 직전에 죽일 수 있다 (가장 위험한 지점)
- 예상: 1.5h / 실소요: 0.5h
- [x] 08-12. `POST /admin/kill {"when":"before_effect"|"now"}`. 무장 시 다음 tick이 **관문 ①을 통과한 뒤, 도구 실행 직전에** `os._exit(137)`.
- `sys.exit`이 아니라 `os._exit`다. 예외를 던지면 FastAPI가 잡아 500을 돌려주고, 그러면 Pub/Sub이 **응답을 받아버린다**. 응답 없이 사라져야 재전달이 일어난다.
- 무장은 1회용이다. 안 그러면 재개 tick도 계속 죽어서 재개가 증명되지 않는다.
- 공개 URL에 자살 버튼을 두는 것이므로 `BACKSTOP_KILL_TOKEN` 헤더를 건다. 인증 시스템이 아니라 자물쇠 하나다(§4의 "인증 만들지 않는다"와 충돌하지 않는 최소 조치).

### T2.4 재개 검증
- 목표: 크래시 → Pub/Sub 재전달 → 재개 시 중복 부작용 0건
- 완료 조건: **10회 반복 실행에서 중복 0건.** 이 장면이 데모 2:30 클라이맥스다
- 예상: 3h
- [ ]

### T2.5 6주 시드 원장 생성 스크립트
- 목표: `scripts/seed_ledger.py` — FrozenClock으로 6주치 실행을 압축 생성
- 완료 조건: `fixtures/ledger_6w.jsonl` 생성. 이벤트 1,000건 이상, 부작용 40건 내외
- 예상: 3h
- [ ]

**P2 검증 게이트**: 크래시 후 재개 10회 반복 중복 0건 + 시드 원장 파일 존재. 태그 `p2-gate-passed`.

---

## Phase P3 — 재생 + 게이트 (08-22 ~ 08-25)
> 목표: 제품의 본체. 여기가 안 되면 프로젝트가 성립하지 않는다.

### T3.1 IntentCollector
- 목표: 도구 실행기를 no-op 수집기로 교체하는 실행 모드
- 완료 조건: 재생 모드에서 외부 HTTP 클라이언트 호출 0건
- 예상: 3h
- [ ]

### T3.2 test_replay_no_egress.py
- 목표: 재생 중 네트워크 호출이 발생하면 테스트 실패 (소켓 몽키패치)
- 완료 조건: 일부러 호출을 넣으면 테스트가 빨간불이 된다
- 예상: 1.5h
- [ ]

### T3.3 ReplayHarness
- 목표: 원장 이벤트를 순서대로 새 에이전트 버전에 재주입하고 의도 집합 수집
- 완료 조건: `make replay`가 시드 원장 전체를 처리하고 의도 목록을 출력한다
- 예상: 4h
- [ ]

### T3.4 DivergenceGate (관문 ②)
- 목표: 과거 부작용 집합 vs 재생 의도 집합 차집합. 순수 함수. 3종 분기 분류 — `DUPLICATE` / `MISSING` / `MUTATED`
- 완료 조건: 순수 함수, import에 네트워크/LLM 없음
- 예상: 3.5h
- [ ]

### T3.5 test_gate_is_pure.py + test_divergence.py
- 목표: 게이트 모듈의 import 그래프 검사 + 분기 분류 정확도 테스트
- 완료 조건: `divergence.py`가 `google.genai`/`vertexai`/`httpx`를 import하면 실패
- 예상: 2h
- [ ]

### T3.6 분기 시나리오 심기
- 목표: 프롬프트 v3에서 `vendor_id` 정규화를 바꿔 중복 3건이 나오는 시나리오를 의도적으로 만든다
- 완료 조건: `make gate`가 정확히 3건을 `DUPLICATE`로 잡고 종료 코드 1을 반환한다
- 예상: 2.5h
- [ ]

### T3.7 narrator.py
- 목표: Gemini 3.5 Flash로 분기 카드 설명 문장 생성. 호출 상한 5회 강제
- 완료 조건: 게이트 결과를 입력으로만 받고 판정을 바꿀 수 없음(반환 타입 `str`)
- 예상: 2h
- [ ]

### T3.8 오프라인 모드
- 목표: `BACKSTOP_OFFLINE=1`이면 Narrator 없이 사전 저장 문장 사용
- 완료 조건: API 키 없는 환경에서 `make replay`가 동일 분기 결과를 낸다
- 예상: 1.5h
- [ ]

### T3.9 make bench
- 목표: 이벤트 수 / 재생 소요(초) / LLM 호출 수 / 차단 건수 출력
- 완료 조건: 4개 숫자가 나온다. 이 숫자를 @SUBMISSION.md와 @Design.md에 반영
- 예상: 1h
- [ ]

**P3 검증 게이트**: `make gate`가 분기 3건을 잡고 종료 코드 1. API 키 없이 재현 가능. 태그 `p3-gate-passed`.

---

## Phase P4 — 콘솔 (08-26 ~ 08-27)
> 목표: 30초 룰 화면 하나. 다른 페이지는 만들지 않는다.

### T4.1 타임라인 컴포넌트
- 목표: 6주 가로 바 + 이벤트 점 밀도 렌더링. @Design.md 규격 준수
- 완료 조건: 1,284개 점이 60fps로 스크럽된다 (Canvas 사용)
- 예상: 4h
- [ ]

### T4.2 분기 마커 + 카드
- 목표: 붉은 마커 3개. 클릭 시 카드(effect id / 원본 시점 / 재생 의도 / 키 불일치 사유 / OTel 링크)
- 완료 조건: 데모 0:30~1:30 장면이 화면에서 재현된다
- 예상: 3h
- [ ]

### T4.3 상단 카운터
- 목표: `LLM calls during replay` / `external calls during replay: 0` / `DEPLOY BLOCKED` 배너
- 완료 조건: 30초 룰 첫 화면 완성
- 예상: 2h
- [ ]

### T4.4 콘솔 Cloud Run 배포
- 목표: Next.js를 Cloud Run에 배포, 공개 URL 확보
- 완료 조건: URL 접속 시 시드 원장 기반 타임라인이 바로 보인다(로그인 없음)
- 예상: 2h
- [ ]

**P4 검증 게이트**: 공개 URL에서 30초 룰 화면이 로그인 없이 보인다. 태그 `p4-gate-passed`.

---

## Phase P5 — 제출물 (08-28 ~ 08-29)

### T5.1 아키텍처 다이어그램
- 목표: PRD Section 3의 텍스트 다이어그램을 이미지로. 필수 기술 3종 라벨 명시
- 완료 조건: PNG/SVG 파일. 영상 1:30 구간에 그대로 삽입 가능
- 예상: 2h
- [ ]
- ⚠️ 필수 제출물이다. 빼먹으면 감점이 아니라 요건 미충족

### T5.2 README
- 목표: 3줄 재현 + 스키마 표 + "시뮬레이션 원장" 고지 + `make bench` 실측 수치
- 완료 조건: 처음 보는 사람이 3분 안에 `make replay`를 성공시킨다
- 예상: 2h
- [ ]

### T5.3 Devpost writeup 5섹션
- 목표: @SUBMISSION.md 초안을 실측 수치로 갱신해 Devpost에 붙여넣기
- 완료 조건: 플레이스홀더 0개
- 예상: 2h
- [ ]

### T5.4 영상 녹화
- 목표: 3분 이내, 컷 3개 이하, @PRD.md Section 4 스크립트 그대로
- 완료 조건: 공개 URL (YouTube 미등록 공개)
- 예상: 4h (재촬영 포함)
- [ ]
- ⚠️ **08-12 Overview 재확인 결과 원문은 "approximately 4-minute demo video proving backend runs on Google Cloud"다.** PRD·SUBMISSION은 3분으로 잡혀 있다. 3분은 4분 이하라 위반은 아니지만, 원문이 **"백엔드가 Google Cloud에서 돈다는 증명"**을 명시적으로 요구한다 — 현재 큐시트에는 배포 URL이 마지막 정지 화면에만 나온다. 라이브 Cloud Run 응답을 화면에 넣는 컷이 필요하다. T5.5에서 Rules 전문으로 최종 확인한다.
- ✅ **08-12 해소.** 3분 구조 유지. @SUBMISSION.md 큐시트에 `1:50–1:55` Cloud Run 콘솔 + 라이브 `.run.app` 호출 5초 컷 삽입(아키텍처 구간 25→20초에서 차용). 2:30–3:00 클라이맥스 불변. 촬영 실패 시 콘솔 요청 로그 화면으로 대체.

### T5.5 Rules 탭 재확인
- 목표: 상금 구조 / 심사 배점 / IP·오픈소스 조항을 직접 읽는다
- 완료 조건: @PRD.md Section 0의 "미공개" 항목이 채워지거나 여전히 미공개임이 확인된다
- 예상: 0.5h
- [ ]

**P5 검증 게이트**: 제출물 4종이 전부 파일/URL로 존재. 태그 `p5-gate-passed`.

---

## Phase P6 — 리허설 · 버퍼 (08-30 ~ 08-31 21:00)

### T6.1 데모 리허설 1회차
- 목표: 영상 없이 실제 시스템으로 스크립트 전 구간 실행
- 완료 조건: 3분 안에 끝난다. 안 되면 구간 하나를 잘라낸다
- 예상: 1.5h
- [ ]

### T6.2 폴백 검증
- 목표: API 키 제거 / 네트워크 차단 / Firestore 권한 회수 3가지 상황에서 `make replay` 동작 확인
- 완료 조건: 3가지 모두에서 오프라인 모드로 동일 결과
- 예상: 1.5h
- [ ]

### T6.3 데모 리허설 2회차 (타인 기준)
- 목표: 사전 지식 없는 사람 관점으로 영상 재시청. "30초에 뭘 봤나" 확인
- 완료 조건: 30초 지점에서 "무슨 문제를 푸는지" 설명 가능
- 예상: 1h
- [ ]

### T6.4 제출
- 목표: Devpost 제출 폼 작성, 트랙 선택(Fortified Enterprise Fleet), 4종 첨부
- 완료 조건: 제출 페이지에서 "Submitted" 상태 확인
- 예상: 1h
- [ ]
- ⚠️ 08-31 21:00 KST까지. 마지막 날 아침에 시작하지 않는다

### T6.5 데모 리허설 3회차 (제출 후)
- 목표: 제출된 URL로 심사위원 동선을 그대로 밟는다
- 완료 조건: 링크 4개 전부 로그인 없이 열린다
- 예상: 0.5h
- [ ]

### T6.6 (여유 시 only) Model Armor 연동
- 목표: subject-agent의 외부 입력 경로에 Model Armor를 붙이고 이벤트를 원장에 합류
- 완료 조건: Fleet 트랙 컴포넌트 1개 추가 충족
- 예상: 3h
- [ ]
- ⚠️ T6.1~T6.5가 전부 끝나기 전에는 손대지 않는다

---

## Kill Switch 체크포인트

| 날짜 | 조건 | 조치 |
|---|---|---|
| 08-14 | Cloud Run URL 200 실패 | 전체 계획 재검토. 배포 문제 해결이 최우선 |
| 08-18 | 원장 기록 불안정 | Pub/Sub 비동기 포기 → 동기 실행 + 원장. 재생/게이트는 유지 |
| 08-21 | 크래시 재개 불안정 | 데모 클라이맥스를 "관문 ② 차단 장면"으로 교체 |
| 08-25 | 게이트 미완성 | 원장 + 타임라인 시각화만으로 축소 제출. 미제출보다 낫다 |
| 08-27 | 콘솔 미완성 | 터미널 TUI + 정적 SVG 타임라인으로 대체 |
| 08-29 | 영상 미완성 | 화면 녹화 + 자막만. 나레이션 포기 |

---

## Decision Log

| 날짜 | 결정 | 이유 | 되돌릴 조건 |
|---|---|---|---|
| 08-12 | 트랙: Fortified Enterprise Fleet | 제출 밀도가 가장 낮을 트랙이고 "수 주 비동기 컨텍스트" 요구가 우리 각도와 정확히 겹침 | 08-20까지 Fleet 요구 3개 중 2개 미충족 시 Taskmaster로 변경 |
| 08-12 | 모델: Gemini 3.5 Flash 단일 | 게이트에 LLM이 없으므로 Pro 불필요. 크레딧 방어 | Narrator 문장 품질이 데모에 못 쓸 수준일 때만 |
| 08-12 | Memory Bank / Agent Registry 제외 | 19일 solo 스코프에서 학습 비용 회수 불가 | P6에 12시간 이상 남으면 재검토 |
| 08-12 | UI 페이지 1개 원칙 | 코퍼스 기준 UI 폭에 시간 쓴 팀의 수상 사례 없음 | 없음 |
| 08-12 | Python 3.12 핀 (시스템은 3.14) | ADK/Firestore 클라이언트의 검증된 런타임. 3.14는 휠 미비 위험 | ADK가 3.12를 떨어뜨릴 때 |
| 08-12 | P0 기반 의존성 5종 일괄 설치 (google-adk 2.6.3 / google-cloud-firestore / fastapi+uvicorn / opentelemetry-sdk) | PRD Section 3 스택 그대로. "Phase당 1개" 규칙은 이 기준선 **이후**의 추가에 적용한다 | 없음 |
| 08-12 | ADK는 2.6.3 (PRD 작성 시 가정은 1.x) | uv가 해석한 최신. 콜백 시그니처를 1.x 기억이 아니라 설치본에서 직접 확인해 쓴다 | 콜백 API가 P1을 막을 때 1.x로 핀 |
| 08-12 | pytest `pythonpath=["."]` | 리포를 설치형 패키지로 만들지 않고 루트 import 유지. `package=false` | 없음 |
| 08-12 | **`GOOGLE_CLOUD_LOCATION=global` 고정** | Gemini 3.x는 리전 엔드포인트에 없다. us-central1/us-east5/europe-west4 전부 404 NOT_FOUND. 비리전(global) 엔드포인트에서만 200. 리전엔 2.5 계열만 있다 — **2.5를 쓰면 "Gemini 3.5 이상" 필수 요건 위반이라 실격 사유가 된다** | Google이 3.x를 리전에 배포할 때 |
| 08-12 | Cloud Run 리전(us-central1)과 모델 위치(global)를 분리 | 같은 변수로 묶으면 배포본이 조용히 404를 낸다. `deploy.sh`에서 `GENAI_LOCATION`을 별도 변수로 뺐다 | 없음 |
| 08-12 | 모델은 `gemini-3.5-flash` 유지 (3.6-flash도 접근 가능) | 3.6-flash가 출력 토큰이 더 싸지만($7.5 vs $9/1M) PRD·SUBMISSION 전반이 3.5로 서술돼 있고 Narrator 호출 상한이 5회라 비용차가 무의미하다 | Narrator 품질 미달 시 |

---

## Changelog

| 날짜 | Phase | 변경 |
|---|---|---|
| 08-12 | P0 | LOG.md 초안 작성. 스프린트 시작 |
| 08-12 | P0 | Hour 0. T0.2 완료. T0.3/T0.4/T0.5는 코드·스크립트 완료 후 인증 대기. gcloud SDK 설치. 커밋 3건 |
| 08-12 | P0 | **P0 게이트 통과.** T0.1/T0.3/T0.4/T0.5 완료. Cloud Run 공개 URL 200. Gemini 3.x 리전 미서빙 발견 → global 엔드포인트로 고정. 현재 Phase를 P1로 갱신 |
| 08-12 | P1 | **P1 게이트 통과.** T1.1~T1.7 전부 완료. 원장·멱등성 키·관문 ①·OTel 스팬. 테스트 66건. ADK 콜백 함정 3개(키워드 호출 규약 / 건너뛴 호출에도 after 실행 / 스팬 id 0) 문서화. 현재 Phase를 P2로 갱신 |

---

## 일일 기록 템플릿

```
### 08-XX
- 실작업 시간:
- 완료 태스크:
- 막힌 곳:
- 잔여 크레딧: $
- 내일 첫 작업:
```
