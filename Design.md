# Design.md — Backstop 비주얼 가이드

**목표**: 심사위원이 갤러리 썸네일 목록에서 스크롤하다가 **채팅 UI가 아닌 유일한 이미지**에서 멈추게 한다.
**범위**: Hero / Demo / CTA 3개 화면만. 다른 화면은 만들지 않는다.
**성격**: 계기판(instrument panel)이지 대시보드가 아니다. 장식 0, 데이터 밀도 최대.

---

## 1. Visual Foundation

### 1.1 컬러 팔레트 — 2테마 토큰

색은 `api/static/theme.css`의 CSS 변수 한 곳에서만 정의한다. 화면·캔버스 어디서도 hex를
하드코딩하지 않는다 — 캔버스에 박아뒀다가 테마를 바꾸면 타임라인만 옛 색으로 남는다.

**의미는 두 테마에서 동일하다: 따뜻한 색 = 차단, 차가운 색 = 통과.**
색이 바뀌어도 "붉은 쪽이 나쁜 것"이라는 규칙은 유지된다.

| 토큰 | dark (sunset) | light (pastel) | 의미 |
|---|---|---|---|
| `--bg` | `#0B0A0F` | `#F3F3F5` | 페이지 배경 |
| `--surface` | `#15131B` | `#FFFFFF` | 카드·배너 |
| `--surface-2` | `#1D1A24` | `#F6F6F8` | 코드블록 |
| `--border` | `#2A2533` | `#E6E6EA` | 1px 경계선 |
| `--fg` | `#F6F0EA` | `#15151A` | 주요 텍스트 |
| `--fg-muted` | `#9C90A2` | `#6E6E78` | 보조 텍스트 |
| `--fg-dim` | `#6C6376` | `#9A9AA5` | 비활성 |
| `--inert` | `#4E4660` | `#C7C7D0` | 타임라인 일반 이벤트 점 |
| **`--block` / `--block-2`** | `#FF4D2E` → `#FFA033` | `#EE4B2B` → `#FBB27E` | **`DUPLICATE` · 배포 차단** |
| `--pass` / `--pass-2` | `#4FA8FF` → `#7FD4FF` | `#2FA46A` → `#8BD48E` | 통과 · 좋은 뜻의 0 |
| `--warn` / `--warn-2` | `#FFB020` → `#FFD36B` | `#E39A12` → `#F5C851` | `MUTATED` |
| `--info` / `--info-2` | `#5B8DEF` → `#8FB8FF` | `#5B4FE0` → `#7EC8E3` | `MISSING` |

의미색은 전부 **쌍**이다. 단색이 아니라 `linear-gradient(120deg, --x, --x-2)`로 쓰인다 —
배지, 초점 숫자, 바뀐 값, 카드 블룸, 타임라인 마커가 같은 그라데이션 언어를 공유한다.

**`--sky`**: 페이지 상단에 깔리는 일몰/파스텔 워시(`radial-gradient`, 고정 위치, 높이 62vh).
다크는 하늘색→주황→진홍, 라이트는 분홍→노랑→하늘. **데이터를 덮지 않을 만큼만 옅게.**

### 1.1-a 테마 전환

- 우측 상단 원형 버튼. 다크일 때 **달**, 라이트일 때 **해** 픽토그램(inline SVG, 외부 아이콘 폰트 없음).
- 선택은 `localStorage['backstop-theme']`에 남는다.
- **기본값은 라이트다.**
- **시스템 설정(`prefers-color-scheme`)은 보지 않는다.** 코드에 그 분기가 없다.
  보는 사람 기기 설정에 따라 첫 화면이 달라지면 영상·썸네일과 실물이 어긋나기 때문이다.
  저장된 선택이 없으면 언제나 라이트로 시작한다.
- `?theme=light` / `?theme=dark`로 고정할 수 있다. **촬영할 때는 어느 쪽이든 명시적으로 붙인다** —
  촬영 기기에 남아 있던 `localStorage` 값 때문에 의도와 다른 테마로 찍히는 걸 막는다.
- 테마를 바꾸면 캔버스를 다시 그린다(`draw()`), 색을 CSS 토큰에서 읽어오기 때문이다.

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
- 라디우스: 카드 16px, 코드블록 12px, 배지·버튼은 pill(999px). 카드가 커질수록 라디우스도 커진다
- 컨테이너 최대폭 1440px, 좌우 패딩 32px
- 타임라인은 컨테이너 폭을 꽉 채운다 — 이 화면에서 여백은 낭비다

### 1.4 모션

- **재생 진행 애니메이션은 없다.** 실측 1.7ms이므로 화면도 즉시 끝난다. 가짜로 늦추지 않는다. 속도는 애니메이션이 아니라 `REPLAY TIME` 타일의 숫자가 말한다 (§3 결정 참조)
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
│         0                        0           1,094         1.7ms     │  ← 48px mono
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
- **타임라인**: `<canvas>` 렌더링. 1,094개 점을 DOM으로 그리지 않는다. 점 반지름 1.5px, 색 `--inert`, 밀도가 높은 구간은 자연스럽게 겹쳐 밝아진다
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

### 상태 표시 (재생 중) — 없음

**결정 (08-12): 진행 표시를 만들지 않는다.** 실측 재생은 1.7ms다. 진행 바·플레이헤드·
스텝 카운터는 전부 1프레임 안에 끝나므로 존재 이유가 없고, 눈에 보이게 하려면 가짜로
늦추는 수밖에 없다. 그건 이 파일의 모션 규칙 위반이다.

화면은 **결과 상태 두 개**만 가진다: 비어 있음 → 완료. 중간 상태가 없다.
"얼마나 빨랐나"는 애니메이션이 아니라 `REPLAY TIME 1.7ms` 타일이 말한다.

대신 이 자리에 **대조군**을 놓는다. 게이트를 v3(후보)와 v1(원장을 만든 버전) 두 번 돌려
`DEPLOY BLOCKED` 와 `DEPLOY ALLOWED` 를 나란히 보여준다. 배포 게이트 데모에서 심사위원이
가장 먼저 의심하는 건 "항상 빨간불 아니냐"이고, 진행 바는 그 의심에 아무 답도 못 하지만
대조군은 정확히 답한다. `<Banner>` 의 `passed` 변형(§5.5)이 이래서 필요하다.

---

## 4. Screen 3 — CTA (게이트 결과 · 재현 안내)

Hero 최하단에 붙는 밴드. 별도 페이지가 아니다.

```
┌──────────────────────────────────────────────────────────────────────┐
│  REPRODUCE THIS                                                      │
│                                                                      │
│    $ git clone github.com/Kim-Hakseong/backstop                      │
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
- 1,094개 점 렌더링이 16ms를 넘기면 점을 샘플링하지 말고 **오프스크린 캔버스에 1회 그려 캐시**한다. 샘플링은 데이터 왜곡이다

### 5.3 `<DivergenceCard>` — 벤토 그리드

**같은 직사각형을 세로로 쌓지 않는다.** 3개가 세로로 반복되면 그 자체가 기성품처럼 읽힌다.
`repeat(auto-fit, minmax(360px, 1fr))` 그리드로 가로에 나란히 놓는다.

카드 안의 위계는 하나뿐이다 — **무엇이 바뀌었나**.

```
┌──────────────────────────────────┐
│ 01 / 03              (DUPLICATE) │  ← idx는 dim, 배지는 pill
│                                  │
│ VENDOR_ID CHANGED                │  ← 10px uppercase
│ acme-corp                        │  ← 19px, --fg-dim, 취소선
│ ACME Corp                        │  ← 26px, 판정색. 이게 주인공이다
│                                  │
│ erp.create_po#PO-8428            │  ← 12.5px mono
│ onboard-acme-corp · step 6 · w4  │  ← --fg-dim
│                                  │
│ 7c55f8257… → 83720c34b…          │  ← surface-2 pill, 뒤쪽만 판정색
│                                  │
│ 생성 문장                          │  ← --fg-dim 12.5px, 맨 아래 고정
│ GENERATED SUMMARY                │
└──────────────────────────────────┘
```

라벨 열(96px 고정폭 `EFFECT / RUN / REPLAY`)은 없앴다. 같은 라벨을 카드마다 3번씩 반복하면
정보가 아니라 서식이 된다. 값만 남기고 위계로 구분한다.

### 5.5-a `<Banner>` 규격 (개정)
배너도 평평한 사각형이 아니라 **초점 숫자**를 가진다: 좌측에 판정 문구 + 보조 한 줄,
우측에 44px mono 숫자(차단 건수). 카드와 같은 블룸을 쓴다. `passed`면 색만 `--pass`로 바뀌고
숫자는 0이 된다.

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
