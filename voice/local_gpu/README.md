# 로컬 GPU에서 Chatterbox 돌리기 (Ubuntu + RTX 3060)

Polly 기계 음성을 당신 목소리로 교체하는 전체 과정입니다.

> **검증 안 됨.** 이 파일들은 Hugging Face에 접속할 수 없는 환경에서 작성했습니다.
> 실행해본 적이 없습니다. Chatterbox 호출 시그니처는 최신 모델 카드와 대조하세요.

## 0. 왜 로컬 GPU인가

3060 12GB면 Chatterbox(백본 0.5B + s3gen)가 **여유롭게** 들어갑니다. VRAM
4~6GB 수준이라 best-of-8도 부담이 없습니다. 이 저장소의 CPU 파이프라인에서
best-of-6에 CPU 398초가 들었던 작업이 몇 초로 끝납니다.

영어 나레이션이므로 **다국어 모델이 아니라 영어 전용 체크포인트**를 쓰세요.
다국어는 23개 언어에 용량을 분산해서 영어 품질이 오히려 떨어집니다.
`--multilingual` 플래그를 빼면 영어 전용입니다.

## 1. 환경 (Ubuntu)

```bash
sudo apt install -y ffmpeg
curl -LsSf https://astral.sh/uv/install.sh | sh

uv venv --python 3.11 && source .venv/bin/activate
uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
uv pip install chatterbox-tts speechbrain soundfile numpy
python -c "import torch; print(torch.cuda.get_device_name(0))"
```

CUDA 휠을 먼저 깔아야 합니다. `chatterbox-tts`를 먼저 설치하면 CPU 전용
torch가 끌려와서 GPU를 못 씁니다.

가중치는 공개돼 있어 HF 토큰이 필요 없습니다. 첫 실행 때 `~/.cache/huggingface`로
약 3GB 내려받습니다.

## 2. 레퍼런스 녹음

`voice/record_script_ko.md`의 한국어 3문장을 **10~15초** 녹음하세요.
한국어로 읽어도 영어가 당신 목소리로 나옵니다.

측정으로 확인된 것이니 그대로 따르시면 됩니다.

- **길게 녹음해도 소용없습니다.** 4초와 18.6초의 화자 유사도 평균이
  0.458~0.518로 같았습니다.
- **조용한 곳이 길이보다 중요합니다.** 차 안에서 녹음한 것을 디노이즈했을 때
  (노이즈 플로어 -15dB → -62dB) 체감 품질이 가장 크게 올랐습니다.
- **여러 번 뽑아 고르는 게 가장 크게 작동합니다.** 같은 설정 3회가
  0.74 / 0.32 / 0.32로 나왔습니다. 한 번은 본인, 두 번은 남입니다.

## 3. 기존 영상의 나레이션 타이밍 추출

이게 핵심입니다. 영상이 Polly 음성에 맞춰 이미 편집돼 있으면, 길이가 다른
새 음성을 넣는 순간 그 뒤 전부가 어긋납니다.

```bash
python polly_timings.py intro.mp4 > timings.json
```

발화 구간의 시작 시각과 길이가 JSON으로 나옵니다. 각 구간의 `text`에
해당 영어 문장을 채우고, `prompt_text`에 실제로 녹음한 한국어 문장을 넣으세요.

무음 기준으로 자르므로 문장 단위와 정확히 일치하지 않습니다. 임계값을
조정하거나(`--threshold -45dB`) 손으로 병합하세요.

## 4. 생성

```bash
python run_chatterbox.py \
  --reference my_voice.m4a \
  --script timings.json \
  --takes 8 \
  --match-duration \
  --out-dir out
```

`--match-duration`이 각 구간을 `seconds` 값에 맞춰 WSOLA로 늘리거나 줄입니다.
피치는 보존됩니다. 1.25배를 넘는 보정이 필요하면 경고가 뜨는데, 그건 **문장을
짧게 고쳐 쓰라는 신호**입니다. 그 이상 늘리면 아티팩트가 들립니다.

출력 마지막에 유사도가 가장 낮은 구간을 알려줍니다. 그 구간만 `--takes 16`으로
다시 뽑으세요.

## 5. 맥미니로 전송

```bash
scp -r out/*.wav <맥미니-테일스케일-이름>:~/narration/
```

Tailscale 이름으로 바로 붙습니다. `~/.ssh/config`에 넣어두면 편합니다.

```
Host macmini
    HostName <테일스케일-이름>
    User <사용자명>
```

## 6. 영상에 교체

구간별 wav가 `start` 시각과 함께 나와 있으니, 편집 프로그램에서 Polly 오디오
트랙을 끄고 각 wav를 그 시각에 놓으면 됩니다.

ffmpeg로 트랙을 합성할 경우:

```bash
# manifest.json의 start 값으로 각 구간을 지연시켜 한 트랙으로 합성
ffmpeg -i intro.mp4 -i narration.wav \
  -map 0:v -map 1:a -c:v copy -shortest intro_myvoice.mp4
```

## 알아둘 것

- **워터마크.** Chatterbox는 출력에 Resemble AI의 PerTh 워터마크를 심습니다.
  들리지 않지만 탐지 가능합니다. MIT 라이선스라 해커톤 출품에 문제는 없지만,
  합성 음성이라는 사실은 밝히는 쪽이 안전합니다.
- **해커톤 심사 기준.** 출품 규정에 AI 생성물 고지 의무가 있는지 확인하세요.
  "본인 목소리를 복제한 합성 음성"은 보통 문제가 되지 않지만, 명시해두면
  분쟁 여지가 없습니다.
