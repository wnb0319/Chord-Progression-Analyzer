#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-chord-progression-analyzer}"
REGION="${REGION:-asia-northeast3}"
SERVICE="${SERVICE:-chord-analyzer}"
REPO="${REPO:-chord-analyzer}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: '$1' 명령이 필요합니다." >&2
    exit 1
  }
}

need_cmd gcloud
need_cmd docker

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: git 저장소에서 실행하세요." >&2
  exit 1
fi

TAG="${TAG:-$(git rev-parse --short HEAD)}"
IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SERVICE}"
IMAGE="${IMAGE_BASE}:${TAG}"

echo "== Deploy target =="
echo "PROJECT_ID: $PROJECT_ID"
echo "REGION:     $REGION"
echo "SERVICE:    $SERVICE"
echo "REPO:       $REPO"
echo "IMAGE:      $IMAGE"
echo

echo "== 1) Ensure project selected =="
gcloud config set project "$PROJECT_ID" >/dev/null

echo "== 2) Ensure Artifact Registry repo exists =="
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Chord analyzer images" >/dev/null 2>&1 || true

echo "== 3) Configure docker auth for Artifact Registry =="
gcloud auth configure-docker "${REGION}-docker.pkg.dev" -q >/dev/null

echo "== 4) Build & push image (local Docker) =="
docker build -t "$IMAGE" .
docker push "$IMAGE"

echo "== 5) Deploy to Cloud Run (image deploy) =="

# 환경변수 전달 (보안상 스크립트에 하드코딩 금지)
# 필요 시 아래 환경변수를 export 하고 실행하세요:
# - SPOTIFY_CLIENT_ID
# - SPOTIFY_CLIENT_SECRET
# - (선택) GENIUS_ACCESS_TOKEN
ENV_ARGS=()
if [[ "${NO_ENV:-}" != "1" ]]; then
  if [[ -n "${SPOTIFY_CLIENT_ID:-}" && -n "${SPOTIFY_CLIENT_SECRET:-}" ]]; then
    ENV_VARS="SPOTIFY_CLIENT_ID=${SPOTIFY_CLIENT_ID},SPOTIFY_CLIENT_SECRET=${SPOTIFY_CLIENT_SECRET}"
    if [[ -n "${GENIUS_ACCESS_TOKEN:-}" ]]; then
      ENV_VARS="${ENV_VARS},GENIUS_ACCESS_TOKEN=${GENIUS_ACCESS_TOKEN}"
    fi
    ENV_ARGS+=(--set-env-vars "$ENV_VARS")
  else
    echo "WARN: SPOTIFY_CLIENT_ID/SECRET 환경변수가 없어 env vars 없이 배포합니다." >&2
    echo "      (원하면 export 후 다시 실행하세요.)" >&2
  fi
fi

gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --allow-unauthenticated \
  "${ENV_ARGS[@]}"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo
echo "✅ Done!"
echo "Service URL: $URL"

