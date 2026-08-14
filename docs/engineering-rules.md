# Engineering rules — Backstop

> **In English, briefly**: this file records the constraints this codebase was built under.
> The judging criteria are translated into rules that are enforceable in code (R1–R8), each
> with the test that enforces it. It also lists what we deliberately did *not* build, and why.
> The body is Korean, as written during the sprint. The rules themselves are visible in the
> code: `tests/test_gate_is_pure.py` (R6), `tests/test_replay_no_egress.py` (R5),
> `tests/test_clock.py` (R3), `tests/test_guard.py` and `tests/test_concurrent_guard.py` (R8).

관련 문서: [README.md](../README.md) · [LOG.md](../LOG.md) · [Design.md](../Design.md) · [SUBMISSION.md](../SUBMISSION.md)

---

## 1. 프로젝트 정의

**한 줄**: 장기 실행 ADK 에이전트의 실행 원장을 저장하고, 새 버전으로 되감아 재생해 중복 부작용을 배포 전에 차단하는 게이트.

**대회**: All Things Agentic Hackathon (Google / Devpost)
**트랙**: The Fortified Enterprise Fleet
**마감**: 2026-09-01 09:00 KST (내부 마감 08-31 21:00 KST)

**필수 기술 (빠지면 실격)**
- Gemini 3.5 이상 (Vertex AI 경유) — 우리는 `gemini-3.5-flash` (**global 엔드포인트**. 리전에서는 404)
- Google ADK (Python)
- Google Cloud 인프라 ≥1 — 우리는 Cloud Run + Pub/Sub + Firestore

**필수 제출물 4종**: 데모 영상 / 코드 저장소 / **아키텍처 다이어그램** / write-up

## 2. 심사 기준 → 코드 레벨 규칙

심사 배점(2026-08-12 Rules 확인): **Innovation & Operational Utility 40% / Architectural Discipline & Tech Stack 30% / Demo & Production Readiness 30%.**
아래 규칙은 그중 30% Architectural Discipline과 30% Demo & Production Readiness를 코드로 옮긴 것이다.

### R1. "말이 아니라 행동" → 모든 기능은 관측 가능한 부작용을 남긴다
- 새 기능을 추가할 때, 그 기능이 Firestore `events` 또는 `effects`에 무엇을 쓰는지 먼저 정의한다.
- 화면에만 존재하고 원장에 흔적이 없는 기능은 만들지 않는다.

### R2. "심사위원이 따라갈 수 있게" → 진입점은 항상 3줄 이하
- `make replay`, `make gate`, `make demo` 세 개로 재현된다.
- README 최상단 3줄로 재현 가능해야 한다. 환경변수 없이도 동작해야 한다(오프라인 모드 기본값).

### R3. "수 주 단위 비동기 컨텍스트" → 시간은 주입 가능해야 한다
- 코드 어디에서도 `datetime.now()`를 직접 호출하지 않는다. `clock.now()`를 통한다.
- 6주 원장 생성과 재생이 실시간을 기다리지 않고 동작해야 한다.
- **강제**: `tests/test_clock.py`가 AST로 저장소 전체를 검사한다. `backstop/clock.py`만 예외다.

### R4. "추론 감사 가능성" → 모든 도구 호출은 스팬을 남긴다
- `before_tool_callback` / `after_tool_callback`에서 OTel 스팬을 열고 닫는다.
- 스팬 ID는 원장 이벤트 문서에 `trace_id`, `span_id`로 저장한다. UI 마커 카드에서 역참조 가능해야 한다.
- **강제**: `tests/test_otel.py`가 id가 전부 0인 경우(NonRecordingSpan)를 거부한다.

### R5. "프로덕션 데이터 안전 취급" → 재생 중 외부 호출 0건
- `ReplayHarness` 활성 시 도구 실행기는 `IntentCollector`로 교체된다.
- **강제**: `tests/test_replay_no_egress.py`가 소켓을 몽키패치하고, 추가로 스텁의 부작용 리스트가 비어 있는지도 검사한다(우리 스텁은 네트워크 없이도 부작용을 남기기 때문).

### R6. 판정에는 LLM이 없다 (가장 중요)
- `backstop/divergence.py`는 순수 함수만 포함한다. 표준 라이브러리 밖 import가 없다.
- **강제**: `tests/test_gate_is_pure.py`가 AST로 직접 import를, `sys.modules` 차집합으로 전이 import를 검사한다. 금지 목록과 허용 목록 양방향이다.
- LLM은 `backstop/narrator.py`에서만 호출된다. Narrator는 게이트 결과를 **입력으로만** 받고, 결과를 바꿀 수 없다(반환 타입이 `str`).

### R7. 수치는 측정한 것만 쓴다
- README, write-up, 영상 자막의 모든 숫자는 `make bench` 출력에서 복사한다.
- 측정 전 숫자는 `<TBD>`로 남긴다. 추정치를 확정치처럼 쓰지 않는다.
- 이 규칙이 실제로 작동한 사례: 재생 시간 추정치 11.4초 → 실측 1.7ms. 이벤트 추정 1,284 → 실측 1,094.

### R8. 멱등성은 두 관문에서 검증한다
- 관문 ①: 실행 시점 `IdempotencyGuard` — 같은 키의 부작용은 두 번 나가지 않는다. **도구 실행 전에 키를 선점**하고, Firestore 문서 ID가 곧 멱등성 키다(유일성이 저장소 제약).
- 관문 ②: 배포 시점 `DivergenceGate` — 재생 의도 집합과 과거 부작용 집합의 차집합.
- 관문 하나가 죽어도 다른 하나가 잡아야 한다.
- **강제**: `tests/test_guard.py`, `tests/test_concurrent_guard.py`, `tests/test_divergence.py`.

## 3. 개발 원칙

1. **배포가 마지막이 아니라 처음이다.** 공개 URL이 200을 반환하기 전에는 다른 기능 코드를 쓰지 않는다.
2. 한 단계는 한 커밋 단위가 아니라 **한 검증 게이트 단위**다. [LOG.md](../LOG.md)의 게이트를 통과하지 못하면 다음 단계로 넘어가지 않는다.
3. 리팩터링보다 동작이 우선이다.
4. 테스트는 R3, R5, R6, R8 불변식에 집중한다. 커버리지 목표는 없다.
5. 의존성 추가 시 [LOG.md](../LOG.md) Decision Log에 이유를 적는다.

## 4. 만들지 않은 것 (그리고 이유)

- ❌ **프롬프트에 가드레일을 쓰지 않는다.** "중복 실행하지 마세요"류 문장은 데모에서 증명 불가다. 제약은 실행 계층에 넣는다.
- ❌ **모델 업그레이드로 문제를 풀지 않는다.** Flash로 안 되면 프롬프트가 아니라 출력 공간을 좁힌다(구조화 스키마 강제).
- ❌ **인증·결제·멀티테넌시·가입 플로우를 만들지 않는다.** 제품의 주장과 무관하다.
- ❌ **DB 스키마를 미리 완성하지 않는다.** Firestore 컬렉션 4개로 시작하고 필요할 때 필드를 붙인다.
- ❌ **subject-agent를 화려하게 만들지 않는다.** 감사 검체일 뿐이다. 도구 5개를 넘기지 않는다.
- ❌ **UI 페이지를 2개 이상 만들지 않는다.** 타임라인 화면 하나면 된다.
- ❌ **write-up을 매끈하게 쓰지 않는다.** 약점을 실명으로 쓴다.
- ❌ **Memory Bank / Agent Registry / Model Armor를 필수 경로에 넣지 않는다.** 학습 비용이 스프린트를 잡아먹는다.

## 5. 코드 구조

```
backstop/
  ledger.py        # Firestore 원장 쓰기/읽기. 이벤트·부작용 스키마
  idempotency.py   # 관문 ①의 키 계산. 정규화 규칙
  replay.py        # ReplayHarness. 도구 실행기를 IntentCollector로 교체
  divergence.py    # 관문 ②. 순수 함수만. 표준 라이브러리 외 import 금지
  narrator.py      # Gemini 3.5 Flash. 설명 문장 생성 전용
  clock.py         # 시간 주입 (R3). 벽시계를 읽는 유일한 파일
  otel.py          # 스팬 생성 (R4)
  cli.py           # make replay / gate / bench / demo / export
subject_agent/
  agent.py         # ADK 에이전트
  workflow.py      # 6주 벤더 온보딩 워크플로 (12스텝)
  tools/           # erp, mail, payment — 전부 스텁
  callbacks.py     # before/after_tool_callback → 원장 + 관문 ①
api/
  main.py          # FastAPI. /health, /tick, /runs, /admin/kill, /run
  static/          # 콘솔 1페이지 (정적)
fixtures/
  ledger_6w.jsonl  # 시드 원장 (커밋 대상)
tests/
Makefile
```

## 6. 검증 명령

```bash
make setup      # uv sync
make test       # pytest -q  (R3, R5, R6, R8 불변식)
make replay     # 시드 원장 재생. API 키 불필요 (BACKSTOP_OFFLINE=1)
make gate       # 재생 + 분기 게이트 + 종료 코드. CI에서 이걸 씀
make bench      # 이벤트 수 / 재생 소요 / LLM 호출 수 / 차단 건수 출력
make deploy     # Cloud Run 배포
make demo       # 크래시 주입 시나리오 (오프라인)
```

**커밋 전**: `make test && make gate`
**배포 전**: `make test && make gate && make replay`

## 7. 데이터 모델

컬렉션 4개(`runs` / `events` / `effects` / `divergences`)의 필드별 근거는 [README.md](../README.md#data-model-firestore)에 표로 정리돼 있다.

**불변 규칙**: `effects`는 append-only. 수정·삭제하지 않는다. 원장이 고쳐지면 재생의 의미가 사라진다.

## 8. 커밋 규칙

- 형식: `[P{n}] {동사} {대상}` — 예: `[P1] add idempotency guard to before_tool_callback`
- 단계 게이트 통과 시 태그: `git tag p1-gate-passed`
- 매 커밋에서 `make test` 통과. 실패 상태 커밋 금지.

## 9. 비용 관리

- Google Cloud 크레딧 $150. Cloud Run은 유휴 시 0으로 축소되게 설정한다(`min-instances=0`).
- Gemini 호출은 Narrator에서만. 재생 1회당 호출 상한을 코드로 강제한다(`MAX_NARRATOR_CALLS=5`).
- 크레딧 소진 리스크가 보이면 즉시 오프라인 모드로 개발을 계속한다. 개발 중 LLM은 필요 없다.
