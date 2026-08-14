#!/usr/bin/env bash
# T0.4 — backstop-api를 Cloud Run에 배포한다.
#   ./scripts/deploy.sh
# 필요한 것: gcloud 인증 + PROJECT_ID. min-instances=0 (유휴 시 과금 0, docs/engineering-rules.md §9).
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-backstop-api}"
# Cloud Run 리전과 모델 엔드포인트 위치는 별개다. Gemini 3.x는 리전 엔드포인트에
# 존재하지 않는다 — us-central1로 부르면 404가 난다. 반드시 global.
GENAI_LOCATION="${GENAI_LOCATION:-global}"
# /admin/kill 은 공개 URL 에 놓인 자살 버튼이다. 인증 시스템은 만들지 않되(§4),
# 지나가는 사람이 누르지 못하게 토큰 하나는 건다.
KILL_TOKEN="${KILL_TOKEN:-demo-kill-2026}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "PROJECT_ID가 없다. gcloud config set project <id> 또는 PROJECT_ID=<id> 를 지정한다." >&2
  exit 1
fi

echo "deploying ${SERVICE} to ${PROJECT_ID}/${REGION}"

gcloud run deploy "${SERVICE}" \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=3 \
  --memory=1Gi \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${GENAI_LOCATION},BACKSTOP_KILL_TOKEN=${KILL_TOKEN}"

URL="$(gcloud run services describe "${SERVICE}" \
  --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"

echo
echo "URL: ${URL}"
echo "P0 게이트 확인:"
curl -fsS "${URL}/health" && echo
