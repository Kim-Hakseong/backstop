#!/usr/bin/env bash
# T0.4 — backstop-api를 Cloud Run에 배포한다.
#   ./scripts/deploy.sh
# 필요한 것: gcloud 인증 + PROJECT_ID. min-instances=0 (유휴 시 과금 0, CLAUDE.md §10).
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-backstop-api}"

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
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION}"

URL="$(gcloud run services describe "${SERVICE}" \
  --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"

echo
echo "URL: ${URL}"
echo "P0 게이트 확인:"
curl -fsS "${URL}/health" && echo
