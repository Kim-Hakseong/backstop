# 내 목소리로 영어 말하기 (cross-lingual voice cloning)

한국어로 10~15초 녹음하면, 그 목소리로 **영어** 문장을 만들어 줍니다.
영어를 직접 녹음할 필요가 없고, 학습(파인튜닝)도 하지 않습니다.

CPU만으로 돕니다. 이 저장소를 만든 샌드박스(vCPU 4개, GPU 없음)에서
실시간 대비 1~2배 속도로 생성됐습니다.

---

## 왜 이 조합인가

목소리 복제 모델은 사실상 전부 Hugging Face에만 올라가 있습니다. XTTS-v2,
OpenVoice, Chatterbox, F5-TTS 모두 그렇습니다. 그런데 사내·클라우드 네트워크에서
`huggingface.co`가 막혀 있는 경우가 흔하고, 이 툴킷을 만든 환경도 그랬습니다.

그래서 **PyPI + GitHub 릴리스만으로** 완결되는 조합을 골랐습니다.

| 항목 | 선택 | 이유 |
|---|---|---|
| 모델 | ZipVoice-distill (zh-en) | 제로샷 복제, 123M로 작고 CPU에서 실시간급 |
| 런타임 | `sherpa-onnx` (ONNX Runtime) | PyPI 설치, torch·CUDA 불필요 |
| 가중치 | k2-fsa/sherpa-onnx GitHub 릴리스 | HF 없이 받을 수 있음 |
| 라이선스 | Apache-2.0 (ZipVoice, sherpa-onnx) | 상업적 사용 가능 |

XTTS-v2가 음질은 더 좋지만 Coqui Public Model License라 **비상업용**입니다.
상업 서비스를 염두에 둔다면 이쪽이 안전합니다.

---

## 쓰는 법

```bash
./voice/bootstrap.sh                      # 모델 600MB + 패키지 (최초 1회)
source voice/.venv/bin/activate

# 1. voice/record_script_ko.md 를 읽고 녹음 → my_voice.m4a
python voice/prep_reference.py my_voice.m4a

# 2. 샘플 일괄 생성
python voice/synthesize.py

# 한 문장만
python voice/synthesize.py --text "Ship it before the meeting."
```

결과는 `voice/out/samples/` 에 wav로 떨어지고 `manifest.json`이 같이 생깁니다.

만들 문장은 `voice/samples.json`에서 바꾸면 됩니다.

### 자주 쓰는 옵션

| 옵션 | 기본 | 설명 |
|---|---|---|
| `--steps` | 8 | flow-matching 단계. 4는 빠르고 16은 매끄럽습니다 |
| `--speed` | 1.0 | 1.1이면 조금 빠르게 |
| `--prompt-text` | samples.json | 실제로 읽은 한국어 문장 |
| `--prompt-romaja` | 자동 | 로마자를 직접 지정 |
| `--threads` | CPU 코어 수 | |

---

## 파이프라인

```
녹음 (한국어, 10~15초)
   │
   ├─ prep_reference.py ── 모노 / 24kHz / 무음 제거 / 라우드니스 정규화
   │                       + 길이·클리핑·노이즈 플로어 경고
   │
   └─ 대본(한글) ── romanize.py ── 로마자
                                      │
                    영어 문장 ────────┴──→ ZipVoice ──→ 내 목소리의 영어 wav
```

---

## 알아두면 좋은 함정

이 세 가지 때문에 처음에 파이프라인이 조용히 망가집니다. 전부 실제로 밟았습니다.

**1. 대본을 한글 그대로 넣으면 프로세스가 죽습니다.**
ZipVoice의 토크나이저는 espeak(영어) + 중국어 lexicon 조합입니다. 한글은 어느
쪽에도 안 걸려서 음절 단위로 통째로 버려집니다. 프롬프트 토큰 수가 0이 되면
길이 예측기가 5분짜리 오디오를 만들려 하고, 어텐션 행렬 33GB를 할당하려다
OOM으로 죽습니다. → `romanize.py`가 자동으로 처리합니다.

**2. 배포된 모델에 `lexicon.txt`가 없고, 음절을 통째로 넣으면 중국어가 전멸합니다.**
`pinyin.raw`만 들어있는데 두 번째 컬럼이 로그 확률이라 lexicon 로더가 그걸
발음기호로 읽습니다. 더 중요한 건 **토큰 사전이 음절 단위가 아니라는 점**입니다.
`ong4`, `in1` 같은 성조 붙은 운모와 낱글자만 있어서 重는 `zhong4`가 아니라
`z h ong4`입니다. 통음절로 넣으면 모든 한자가 OOV로 조용히 사라지고, 결과는
0.07초짜리 잡음입니다. → `build_lexicon.py`가 tokens.txt를 보고 쪼갭니다.

**3. 대본과 실제 녹음이 다르면 모든 샘플의 속도가 틀어집니다.**
모델은 `프롬프트 오디오 길이 ÷ 프롬프트 토큰 수`로 발화 속도를 추정합니다.
읽은 문장을 그대로 넘기세요.

**4. 중국어 외의 언어는 전부 영어로 읽힙니다.**
`matcha-tts-lexicon.cc`가 espeak 음성을 `en-us`로 하드코딩합니다. 언어 인자가
없습니다. 그래서 이 체크포인트로 진짜 되는 건 **중국어와 영어뿐**입니다.
한국어·일본어는 한자/가나가 OOV라 로마자로 바꿔 넘기고, 프랑스어·독일어는
철자를 영어 규칙으로 읽습니다 — 전부 근사치입니다. 다국어가 목적이면
XTTS-v2(17개 언어)나 Chatterbox Multilingual(23개 언어, MIT)로 가야 하고,
둘 다 Hugging Face에 있습니다.

---

## demo/

`demo/`의 파일은 **사람 목소리가 아닙니다.** 파이프라인이 도는지 확인하려고
한국어 TTS(`vits-mimic3-ko_KO-kss_low`)로 만든 대역 음성입니다.

- `stand_in_reference_ko.wav` — 한국어 레퍼런스 9초
- `stand_in_en_intro.wav`, `stand_in_en_pitch.wav` — 같은 목소리의 영어

레퍼런스와 결과를 나란히 들어보면 음색이 옮겨간 게 들립니다.
본인 목소리로 바꾸면 품질은 훨씬 올라갑니다. 합성 음성은 레퍼런스로선
조건이 나쁜 편입니다.

---

## 목소리는 본인 것만

레퍼런스로 쓸 수 있는 건 **본인 목소리이거나, 명시적으로 동의를 받은 목소리**뿐입니다.
남의 목소리를 복제해 그 사람이 말한 것처럼 쓰는 건 한국 형법상 명예훼손·사기,
EU AI Act의 딥페이크 고지 의무, 미국 여러 주의 퍼블리시티권에 걸립니다.
공개 배포한다면 합성 음성이라는 표시를 넣으세요.

`voice/out/`, `voice/models/`, `voice/.venv/`는 gitignore되어 있습니다.
녹음 원본을 커밋하지 마세요.
