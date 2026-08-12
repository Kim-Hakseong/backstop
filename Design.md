# Design.md — Backstop 비주얼 가이드

**목표**: 심사위원이 갤러리 썸네일 목록에서 스크롤하다가 **채팅 UI가 아닌 유일한 이미지**에서 멈추게 한다.
**범위**: Hero / Demo / CTA 3개 화면만. 다른 화면은 만들지 않는다.
**성격**: 계기판(instrument panel)이지 대시보드가 아니다. 장식 0, 데이터 밀도 최대.

---

## 1. Visual Foundation

### 1.1 컬러 팔레트

**Base (어두운 계기판)**
| 토큰 | HEX | 용도 |
|---|---|---|
| `--bg` | `#0A0C10` | 페이지 배경 |
| `--surface` | `#12151C` | 카드·패널 |
| `--surface-2` | `#191D26` | 카드 내부 중첩 |
| `--border` | `#232937` | 1px 경계선 |
| `--border-strong` | `#323A4D` | 포커스·활성 경계선 |

**Text**
| 토큰 | HEX | 용도 |
|---|---|---|
| `--fg` | `#E8EBF2` | 주요 텍스트 |
| `--fg-muted` | `#8A93A6` | 보조 텍스트·축 라벨 |
| `--fg-dim` | `#5A6274` | 비활성·타임스탬프 |

**Semantic (의미가 있을 때만 색을 쓴다)**
| 토큰 | HEX | 용도 |
|---|---|---|
| `--pass` | `#3DDC97` | 통과·멱등 스킵·테스트 그린 |
| `--block` | `#FF4D4D` | `DUPLICATE` 분기 · DEPLOY BLOCKED |
| `--warn` | `#F5A524` | `MUTATED` 분기 |
| `--info` | `#4C8DFF` | `MISSING` 분기 · 재생 진행 바 |
| `--inert` | `#3A4152` | 정상 이벤트 점 (타임라인 대부분) |

**규칙**
- 그라데이션 금지. 그림자는 카드 1단계만(`0 1px 0 rgba(255,255,255,0.03) inset`).
- 컬러는 상태 표현에만 쓴다. 브랜드 강조용 색칠 금지.
- 화면의 92% 이상이 `--bg` / `--inert` / `--fg-muted`여야 한다. 붉은 마커 3개가 눈에 꽂히는 이유는 나머지가 전부 무채색이기 때문이다.

### 1.2 타이포그래피

| 역할 | 폰트 | 크기 / 행간 / 자간 |
|---|---|---|
| UI 텍스트 | **Inter** (400/500/600) | 14px / 20px / -0.01em |
| 숫자·ID·로그·코드 | **IBM Plex Mono** (400/500) | 13px / 20px / 0 |
| 히어로 수치 | IBM Plex Mono 500 | 48px / 52px / -0.02em, tabular-nums |
| 섹션 라벨 | Inter 600 | 11px / 16px / 0.08em, uppercase |
| 카드 제목 | Inter 600 | 15px / 22px |

**규칙**: 모든 숫자는 모노스페이스에 `font-variant-numeric: tabular-nums`. 재생 중 숫자가 바뀔 때 폭이 흔들리면 신뢰가 깨진다.

### 1.3 스페이싱 · 라디우스

- 4px 그리드. 사용 값: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64
- 라디우스: 카드 8px, 배지·칩 4px, 버튼 6px. 원형 금지(로딩 스피너 제외)
- 컨테이너 최대폭 1440px, 좌우 패딩 32px
- 타임라인은 컨테이너 폭을 꽉 채운다 — 이 화면에서 여백은 낭비다

### 1.4 모션

- 재생 진행: 왼→오른쪽 채움, `linear`. 이징 금지. **실제 처리 속도를 그대로 반영한다.** 실측 11초면 화면도 11초다. 가짜 애니메이션 금지
- 분기 마커 등장: 100ms `opacity 0→1`. 튀거나 흔들리지 않는다
- 호버: 120ms `ease-out`, 배경만 `--surface-2`로
- `DEPLOY BLOCKED` 배너: 애니메이션 없이 즉시 표시. 깜빡임 금지

---

## 2. Screen 1 — Hero (30초 룰 화면)

이 화면 하나가 데모 0:00~0:30과 Devpost 썸네일을 동시에 담당한다.

```
┌──────────────────────────────────────────────────────────────────────┐
│  BACKSTOP                                    subject-agent · v3.1.0  │  ← 40px 바
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  LLM CALLS DURING REPLAY   EXTERNAL CALLS   EVENTS      REPLAY TIME   │
│         3                        0           1,284         11.4s      │  ← 48px mono
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │  ← 타임라인 180px
│  │        │        │        │        │        │        │            │
│  Week 1   Week 2   Week 3   Week 4   Week 5   Week 6                 │
│                                   ▲▲▲                                │
│                          3 duplicate side effects                    │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│  ███ DEPLOY BLOCKED — 3 DUPLICATE SIDE EFFECTS                       │  ← 56px, --block
└──────────────────────────────────────────────────────────────────────┘
```

### 규격
- **타임라인**: `<canvas>` 렌더링. 1,284개 점을 DOM으로 그리지 않는다. 점 반지름 1.5px, 색 `--inert`, 밀도가 높은 구간은 자연스럽게 겹쳐 밝아진다
- **부작용 점**: 반지름 3px, 색 `--fg-muted` — 일반 이벤트보다 밝다
- **분기 마커**: 세로 막대 폭 3px, 높이 타임라인 전체, 색 `--block`, 상단에 삼각형 6px
- **주 구분선**: 1px `--border`, 라벨 `--fg-dim` 11px
- **히어로 수치 4개**: 라벨은 uppercase 11px `--fg-muted`, 값은 48px mono `--fg`. `EXTERNAL CALLS 0`만 값 색이 `--pass`
- **BLOCKED 배너**: 배경 `--block` 12% 알파, 좌측 4px 실선 `--block`, 텍스트 `--block` 600 15px uppercase

### 썸네일 크롭
Devpost 썸네일(1200×630)은 타임라인 + BLOCKED 배너만 잘라 쓴다. 로고·사람·아이콘·그라데이션 없음. 화면에 텍스트는 `DEPLOY BLOCKED — 3 DUPLICATE SIDE EFFECTS` 한 줄뿐.

---

## 3. Screen 2 — Demo (분기 카드)

붉은 마커를 클릭하면 타임라인 아래에 카드가 펼쳐진다. 페이지 이동 없음.

```
┌─ DIVERGENCE 1 / 3 ────────────────────────────── DUPLICATE ─┐
│                                                              │
│  EFFECT      erp.create_po#PO-2291                           │
│  ORIGINAL    Week 4 · Day 2 · 09:14:07Z      [trace ↗]       │
│  REPLAY      intent: NEW  (not matched to any past effect)    │
│                                                              │
│  IDEMPOTENCY KEY                                             │
│    past    a3f1c9…  vendor_id="acme-corp"                    │
│    replay  7b20e4…  vendor_id="ACME Corp"      ← mismatch    │
│                                                              │
│  ─────────────────────────────────────────────────────────   │
│  prompt v3 changed vendor_id normalization; the same          │
│  purchase order would be issued a second time.                │
│                                          — generated summary  │
└──────────────────────────────────────────────────────────────┘
```

### 규격
- 카드 배경 `--surface`, 경계선 1px `--border`, 좌측 3px 실선은 분기 종류 색(`DUPLICATE`=`--block`, `MUTATED`=`--warn`, `MISSING`=`--info`)
- 우상단 배지: 4px 라디우스, 배경은 해당 색 15% 알파, 텍스트는 해당 색 500 11px uppercase
- 필드 라벨: uppercase 11px `--fg-muted`, 고정 폭 96px 좌측 정렬
- 값: IBM Plex Mono 13px `--fg`
- **키 비교 블록**: `--surface-2` 배경, 불일치 부분만 `--block` 텍스트 + `← mismatch` 표시
- **LLM 생성 문장**: 카드 최하단, `--fg-dim` 13px, 우측에 `— generated summary` 캡션. **이 텍스트는 절대 주역이 아니다.** 크기·색·위치로 보조임을 명확히 한다 (PRD Section 8의 AI Slop 리스크 대응)
- `[trace ↗]`: OTel 스팬 뷰어 링크. `--info` 텍스트, 밑줄 없음

### 상태 표시 (재생 중)
타임라인 위에 1px `--info` 세로선이 왼→오른쪽으로 이동. 좌하단에 mono 12px로 진행 카운터 `847 / 1,284`. 스피너 금지 — 숫자가 진행 표시다.

---

## 4. Screen 3 — CTA (게이트 결과 · 재현 안내)

Hero 최하단에 붙는 밴드. 별도 페이지가 아니다.

```
┌──────────────────────────────────────────────────────────────────────┐
│  REPRODUCE THIS                                                      │
│                                                                      │
│    $ git clone github.com/<user>/backstop                            │
│    $ make setup                                                      │
│    $ make replay          # no API key required                      │
│                                                                      │
│  ledger: fixtures/ledger_6w.jsonl  ·  6 weeks, simulated run         │
│  exit code 1 = deploy blocked                                        │
│                                                                      │
│  [ View architecture diagram ]   [ Source ]   [ 3-min demo ]         │
└──────────────────────────────────────────────────────────────────────┘
```

### 규격
- 코드 블록: `--surface-2` 배경, IBM Plex Mono 13px, 프롬프트 `$`는 `--fg-dim`, 명령은 `--fg`, 주석은 `--pass`
- `simulated run` 고지: `--warn` 12px. **숨기지 않는다.** 코퍼스가 확인한 약점 선언 패턴이자 정직성 신호
- 버튼 3개: 배경 없음, 1px `--border` 경계선, 텍스트 `--fg` 14px, 호버 시 경계선만 `--border-strong`. 채워진 CTA 버튼 없음 — 이 제품은 가입을 유도하지 않는다

---

## 5. 컴포넌트 패턴

### 5.1 `<StatTile>`
라벨(11px uppercase `--fg-muted`) + 값(48px mono). 값이 0이고 그게 좋은 뜻이면 `--pass`, 나쁜 뜻이면 `--block`. 그 외 `--fg`. 아이콘 없음.

### 5.2 `<Timeline>`
- Props: `events[]`, `effects[]`, `divergences[]`, `weeks`, `playhead`
- Canvas 단일 레이어. 리사이즈 시 devicePixelRatio 반영
- 클릭 히트 테스트는 x좌표 ±4px 내 가장 가까운 divergence
- 1,284개 점 렌더링이 16ms를 넘기면 점을 샘플링하지 말고 **오프스크린 캔버스에 1회 그려 캐시**한다. 샘플링은 데이터 왜곡이다

### 5.3 `<DivergenceCard>`
좌측 3px 색 막대 + 배지 + 필드 리스트 + 키 비교 + 생성 문장. 최대 높이 없음, 스크롤 없음. 카드가 길면 필드를 줄인다.

### 5.4 `<KeyDiff>`
2행 mono 비교. 다른 부분만 `--block`. diff 알고리즘 불필요 — 필드 단위 비교로 충분하다.

### 5.5 `<Banner>`
`variant`: `blocked` | `passed`. `passed`일 때 텍스트 `DEPLOY ALLOWED — 0 DUPLICATE SIDE EFFECTS`, 색 `--pass`. 데모에서는 `blocked`만 쓰지만 통과 상태도 구현해 둔다 — 게이트가 항상 빨간불이면 심사위원이 하드코딩을 의심한다.

### 5.6 금지 컴포넌트
모달, 토스트, 사이드바, 탭, 드롭다운, 아바타, 로고 마크, 히어로 일러스트, 로딩 스피너, 스켈레톤. 화면이 1개인데 내비게이션이 필요할 이유가 없다.

---

## 6. 접근성 · 실무 체크

- 텍스트 대비: `--fg`/`--bg` = 약 15:1, `--fg-muted`/`--bg` = 약 5.4:1 — 둘 다 WCAG AA 통과
- **색맹 대응**: 분기 종류를 색으로만 구분하지 않는다. 배지에 항상 `DUPLICATE`/`MUTATED`/`MISSING` 텍스트를 붙인다
- 영상 촬영 시 브라우저 확대 125%, 북마크바 숨김, 다크 테마 고정
- 폰트는 self-host. CDN 로드 실패로 데모 영상에 시스템 폰트가 뜨면 즉시 티가 난다

---

## 7. 아키텍처 다이어그램 비주얼 규격 (필수 제출물)

다이어그램은 코드가 아니라 **제출물**이다. 심사위원이 5초 안에 필수 기술 3종을 확인할 수 있어야 한다.

- 캔버스 1600×900, 배경 `--bg`, 여백 64px
- 박스: 라디우스 8px, 배경 `--surface`, 경계선 1px `--border`, 제목 Inter 600 15px, 부제 Inter 400 12px `--fg-muted`
- **필수 기술 라벨은 배지로 분리 표기**: `Gemini 3.5 Flash` / `Google ADK` / `Cloud Run` / `Pub/Sub` / `Firestore` — 배경 `--info` 15% 알파, 텍스트 `--info` mono 11px
- 화살표: 1px `--border-strong`, 화살촉 4px. 곡선 금지, 직교 라우팅만
- **관문 ①·② 는 붉은 세로 막대**(3px `--block`)로 그리고 라벨 `GATE ①` / `GATE ②`
- 재생 경로는 점선(4/4) `--info`, 라벨 `replay: no egress`
- 하단 각주 한 줄 mono 11px `--fg-dim`: `LLM is called only inside Narrator — the gate is pure set arithmetic.`
- 로고 이미지·클립아트·구름 모양 금지. Google 제품 아이콘은 쓰지 않고 텍스트 배지로 통일한다(브랜드 가이드 위반 위험 회피)

**제작 도구**: Excalidraw 또는 draw.io로 그린 뒤 PNG 2x 내보내기. 손그림 스타일(Excalidraw 기본값)은 끈다 — 계기판 톤과 충돌한다.

## 8. 레퍼런스 (실재 URL만)

| 무엇을 참고하나 | URL |
|---|---|
| Inter 폰트 · 메트릭 | https://rsms.me/inter/ |
| IBM Plex Mono | https://github.com/IBM/plex |
| 어두운 계기판 UI의 색 단계 설계 | https://www.radix-ui.com/colors |
| 저채도 다크 인터페이스 밀도 | https://vercel.com/geist/colors |
| 컴포넌트 기본형 (직접 쓰진 않고 구조 참고) | https://ui.shadcn.com |
| Tailwind 색 커스터마이징 | https://tailwindcss.com/docs/colors |
| ADK 소스 (콜백 시그니처 확인용) | https://github.com/google/adk-python |
| Google Cloud 무료 티어 | https://cloud.google.com/free |

> 위 URL 외에 "참고했다"고 적을 링크를 만들어내지 않는다.

---

## 9. 구현 순서 (P4, 총 11h)

1. 토큰 정의 (CSS 변수 1파일) — 0.5h
2. `<StatTile>` 4개 + 상단 바 — 1.5h
3. `<Timeline>` Canvas 렌더링 — 4h
4. 분기 마커 + 히트 테스트 — 1.5h
5. `<DivergenceCard>` + `<KeyDiff>` — 2h
6. `<Banner>` + CTA 밴드 — 1h
7. 촬영 세팅 확인 (확대율·폰트 로딩) — 0.5h

시간이 부족하면 5번을 정적 텍스트로 낮추고 3번을 지킨다. **타임라인이 이 프로젝트의 얼굴이다.**
