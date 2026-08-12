# Backstop

**Replay your agent's last six weeks before you ship the next one.**

Backstop 은 장기 실행 에이전트의 실행 원장을 저장하고, 새 에이전트 버전으로 그 원장을
되감아 재생해서 **이 버전이었다면 과거에 중복 실행했을 부작용**을 배포 전에 계산한다.
중복이 1건이라도 나오면 종료 코드 1을 반환하고 배포가 막힌다.

```bash
make setup     # uv sync
make replay    # 시드 원장 재생. API 키 불필요
make gate      # 재생 + 분기 게이트. 중복 발견 시 exit 1
```

> ⚠️ **이 저장소의 6주 원장은 시뮬레이션으로 생성됐다.** 실제 6주간 운영한 로그가 아니라
> `FrozenClock` 으로 압축 생성한 것이다(`fixtures/ledger_6w.jsonl`). 이벤트 분포와 실패율은
> 우리가 정한 값이며, 실제 운영 트래픽의 지저분함을 담고 있지 않다.

**Backstop 에서 LLM 은 아무것도 차단하지 않는다.** 판정은 집합 연산이고 순수 함수이며
단위 테스트가 붙어 있다. Gemini 는 분기 카드의 설명 한 문장에만 쓰인다.

**구현 현황 (08-12, P3 완료)**: 원장 · 관문 ① · Pub/Sub 비동기 실행 · 크래시 재개 ·
재생 하네스 · 관문 ②까지 동작한다. `make replay` / `make gate` / `make bench` /
`make demo` 전부 API 키 없이 돈다.

배포 URL: https://backstop-api-911984605187.us-central1.run.app/health

---

## 데이터 모델 (Firestore)

컬렉션 4개. 필드는 필요할 때 붙인다.

### `runs/{run_id}` — 실행 단위

| 필드 | 타입 | 왜 필요한가 |
|---|---|---|
| `agent_version` | str | 게이트 비교의 축. "어느 버전의 원장을 어느 버전으로 재생하는가"가 전부 이 필드에서 갈린다 |
| `started_at` | ts | 6주 타임라인의 왼쪽 끝. `clock.now()` 산출값 |
| `last_tick_at` | ts | 비동기 실행이 어디서 멈췄는지. 크래시 판정의 근거 |
| `status` | enum | `running｜crashed｜resumed｜done`. 재개 시나리오가 원장에 남아야 데모 2:30 구간이 증명된다 |
| `cursor` | int | 워크플로 스텝 위치. 재개 시 여기서 이어간다. 이게 없으면 크래시 후 처음부터 다시 돌아 중복이 대량 발생한다 |

### `events/{event_id}` — 무슨 일이 있었나 (재생 입력)

| 필드 | 타입 | 왜 필요한가 |
|---|---|---|
| `run_id` | str | 어느 실행에 속하는가 |
| `seq` | int | **재생 순서를 결정하는 유일한 근거.** 타임스탬프로 정렬하지 않는다 — 동시 tick 에서 순서가 흔들리면 재생이 결정론을 잃는다 |
| `kind` | enum | `tool_call｜tool_result｜idempotent_skip｜tick｜error`. `idempotent_skip` 이 관문 ①이 실제로 일했다는 증거다 |
| `tool_name` | str | 재생 시 어떤 도구 의도로 복원할지 |
| `args_canonical` | map | **정규화된 인자.** 원본 인자는 저장하지 않는다 — 원본을 남기면 키 계산이 두 벌이 되고 어느 쪽이 진실인지 모르게 된다 |
| `trace_id` | str | R4. UI 마커 카드에서 추론 체인 역참조 |
| `span_id` | str | R4. 같은 목적 |
| `at` | ts | 타임라인 x좌표. **정렬 근거가 아니다** (`seq` 가 한다) |

### `effects/{effect_id}` — 실제로 외부로 나간 부작용 (게이트 비교 대상)

| 필드 | 타입 | 왜 필요한가 |
|---|---|---|
| `idem_key` | str (인덱스) | `(tool_name, args_hash, run_scope)` 해시. 관문 ①의 차단 기준이자 관문 ②의 차집합 원소 |
| `event_id` | str | 어느 이벤트가 이 부작용을 냈는가 |
| `run_id` | str | 어느 실행에서 나갔는가 |
| `target` | str | 사람이 읽는 식별자. 예: `erp.create_po#PO-2291`. 분기 카드에 그대로 뜬다 |
| `at` | ts | 원본 시점. 카드의 `ORIGINAL Week 4 · Day 2` 표시 |

**불변 규칙**: `effects` 는 append-only. 수정·삭제하지 않는다. 원장이 고쳐지면 재생의 의미가 사라진다.

### `divergences/{div_id}` — 게이트 산출물

| 필드 | 타입 | 왜 필요한가 |
|---|---|---|
| `run_id` | str | 어느 원장을 재생한 결과인가 |
| `replay_of_version` | str | 재생된 원장의 버전 |
| `against_version` | str | 배포하려는 새 버전 |
| `kind` | enum | `DUPLICATE｜MISSING｜MUTATED`. `DUPLICATE` 만 배포를 막는다 |
| `past_key` | str | 과거 부작용의 멱등성 키 |
| `replay_key` | str | 재생 의도의 멱등성 키 |
| `mismatch_field` | str | 어느 필드가 갈렸는가. 카드의 `← mismatch` 표시 |
| `narrative` | str, nullable | Narrator 출력. **null 이어도 판정은 유효하다** — LLM 이 죽어도 게이트는 동작한다 |

---

## 멱등성 키 정규화 규칙

키는 `sha256(tool_name | canonical_args | run_scope)` 다. `canonical_args` 는 아래 규칙을
통과한 뒤에 직렬화된다. **이 규칙이 흔들리면 게이트 전체가 무의미해진다.**

| 규칙 | 이유 |
|---|---|
| 키 정렬 | 인자 순서 차이가 키를 바꾸면 안 된다 |
| 숫자 타입 통일 (int/float → 단일 표현) | **실측 근거 있음.** 라이브 Gemini 가 같은 의미의 인자를 `4200`(int)으로 보냈고 로컬은 `4200.0`(float)였다. 해시가 갈렸다 (PO-8428 vs PO-9084). LLM 은 호출마다 JSON 숫자 타입을 다르게 낸다 |
| 문자열 trim + 유니코드 NFC | 공백·정규화 차이 흡수 |
| null 필드 제거 | 모델이 선택 인자를 명시적 null 로 채우기도, 생략하기도 한다 |

`vendor_id` 대소문자는 **정규화하지 않는다.** `"acme-corp"` 와 `"ACME Corp"` 는 다른 키다.
이건 버그가 아니라 데모가 재현하는 실제 실패 모드다 — 프롬프트 변경이 정규화를 바꾸면
게이트가 `DUPLICATE` 를 낸다. 한계는 write-up 에 실명으로 적는다.

---

## 필수 기술

| 요건 | 사용 |
|---|---|
| Gemini 3.5 이상 | `gemini-3.5-flash` (Vertex AI, **global 엔드포인트**) |
| Google 에이전트 프레임워크 | Google ADK (Python) |
| Google Cloud 인프라 | Cloud Run · Pub/Sub · Firestore |

> Gemini 3.x 는 리전 엔드포인트(`us-central1` 등)에서 404 를 반환한다. 비리전 `global`
> 엔드포인트에서만 서빙된다. Cloud Run 리전과는 별개의 값이다.

## 측정 수치

아래는 전부 `make bench` 출력에서 그대로 옮긴 실측값이다 (2026-08-12, M4 macOS, 오프라인).

| 항목 | 값 |
|---|---|
| 기간 | 6주 |
| 실행(run) 수 | 4 |
| 원장 이벤트 수 | 1,094 |
| 재생한 스텝 수 | 42 |
| 비교한 과거 부작용 수 | 42 |
| **원장 로드 + 재생 + 게이트 소요** | **1.7 ms** (5회 중 최속) |
| 재생 중 외부 호출 수 | **0** |
| 재생 중 LLM 호출 수 | **0** |
| 차단된 중복 부작용 | **3** (`DUPLICATE`) |
| 종료 코드 | 1 |

**LLM 호출에 대해 정확히**: 재생과 판정 경로의 모델 호출은 **0회**다. `--narrate` 를 켜면
분기 3건의 설명 문장을 만드는 데 **3회** 호출된다(상한 5회). 그 문장이 없어도 판정과
종료 코드는 똑같다.

```
$ make gate
DUPLICATE 3   MISSING 0   MUTATED 0
DEPLOY BLOCKED — 3 DUPLICATE SIDE EFFECT(S)
```

**종료 코드에 대해 정확히**: 게이트 명령 자체는 차단 시 **1**, 통과 시 **0** 을 반환한다.
`make gate` 로 감싸면 GNU make 규칙에 따라 실패한 레시피가 **2** 로 보고된다(make 는 항상 2다).
CI 는 "0 이 아니면 차단"으로 보면 되고, 정확한 코드가 필요하면 명령을 직접 부른다.

```
$ uv run python -m backstop.cli gate ; echo "exit=$?"
DEPLOY BLOCKED — 3 DUPLICATE SIDE EFFECT(S)
exit=1

$ uv run python -m backstop.cli gate --version v1 ; echo "exit=$?"   # 원장을 만든 버전 그대로
DEPLOY ALLOWED — 0 DUPLICATE SIDE EFFECTS
exit=0
```

두 번째 명령이 중요하다. 게이트가 **항상** 빨간불이면 하드코딩과 구분되지 않는다.
원장을 만든 버전(v1)을 그대로 재생하면 분기는 0건이고 배포가 통과한다.
