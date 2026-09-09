# Hugging Face Space에 올리기

CPU 파이프라인의 한계는 언어입니다. ZipVoice 체크포인트는 중국어와 영어만
진짜로 하고, espeak 음성이 `en-us`로 하드코딩돼 있어 나머지는 전부 근사치입니다.
Chatterbox Multilingual은 23개 언어를 실제로 지원하고 MIT 라이선스라 상업
이용도 됩니다. 대신 GPU가 필요하고, 가중치가 Hugging Face에 있습니다.

`voice/hf_space/`의 세 파일을 그대로 Space에 올리면 됩니다.

> **검증 안 됨.** 이 파일들은 Hugging Face에 접속할 수 없는 환경에서 작성했습니다.
> 한 번도 실행해보지 않았습니다. 특히 Chatterbox 호출 시그니처와 `language_id`
> 코드는 최신 모델 카드와 대조하세요.

## 1. Space 만들기

huggingface.co/new-space 에서:

| 항목 | 값 |
|---|---|
| SDK | **Gradio** |
| Hardware | **ZeroGPU (Nvidia H200)** |
| Visibility | Private (처음엔 비공개 권장) |

ZeroGPU는 **Pro 구독에 포함**됩니다. 상시 점유가 아니라 요청이 올 때만 GPU를
빌리는 방식이라, 유휴 시간에 과금되지 않습니다.

## 2. 파일 올리기

```bash
git clone https://huggingface.co/spaces/<사용자명>/<스페이스명>
cp voice/hf_space/{app.py,requirements.txt,README.md} <스페이스명>/
cd <스페이스명> && git add -A && git commit -m "initial" && git push
```

`README.md`의 YAML 머리말이 Space 설정을 결정하므로 지우지 마세요.

빌드는 5~10분 걸립니다. 실패하면 Space의 Logs 탭에 이유가 나옵니다.

## 3. 쓰기

녹음 10~15초를 올리고, 언어를 고르고, 텍스트를 넣습니다. `voice/record_script_ko.md`의
문장을 그대로 쓰셔도 됩니다. Chatterbox는 프롬프트 대본을 요구하지 않아서
ZipVoice보다 준비가 간단합니다.

## CPU 파이프라인에서 가져간 것

측정으로 확인한 것들입니다. 자세한 숫자는 `voice/README.md`에 있습니다.

- **여러 번 뽑아서 고르기.** 이게 가장 크게 작동합니다. 같은 설정에서 같은
  문장이 화자 유사도 0.74 / 0.32 / 0.32로 나왔습니다. 한 번은 본인, 두 번은
  남입니다. `app.py`가 takes만큼 뽑아 ECAPA 임베딩으로 순위를 매깁니다.
  CPU에서 best-of-6이 398초였는데 GPU에서는 몇 초입니다.
- **녹음을 길게 하지 마세요.** 4초와 18.6초의 평균 유사도가 0.458~0.518로
  같았습니다. 회차 간 편차(최대 0.263)가 길이 차이보다 큽니다.
- **조용한 곳에서 녹음하세요.** 길이보다 이쪽이 훨씬 큽니다.

## 알아둘 것

- **워터마크.** Chatterbox는 출력에 Resemble AI의 PerTh 워터마크를 넣습니다.
  들리지는 않지만 탐지는 가능합니다. 상업 서비스에 쓸 계획이면 약관을 확인하세요.
- **ZeroGPU 할당량.** Pro에 일일 GPU 시간 한도가 있습니다. takes를 10으로
  올리면 그만큼 빨리 씁니다.
- **콜드 스타트.** 유휴 후 첫 요청은 모델 로딩까지 30초 이상 걸립니다.
- **비공개로 두세요.** 공개 Space에 목소리 복제 도구를 열어두면 남의 목소리를
  올리는 사람이 반드시 생깁니다.
