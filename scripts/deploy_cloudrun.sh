#!/usr/bin/env bash
# Build the image on Cloud Build and deploy it to Google Cloud Run (D-028, D-052).
#
#   GCP_PROJECT=my-project scripts/deploy_cloudrun.sh
#   GCP_PROJECT=my-project IMAGE_TAG=abc1234 SKIP_BUILD=1 scripts/deploy_cloudrun.sh   # redeploy a built image
#
# Used both by hand and by the GitHub Actions deploy job. Uploads the working tree
# (.gcloudignore keeps private docs, .env and raw data out), builds the Dockerfile, pushes
# the image to Artifact Registry and rolls out a new revision. The OpenRouter key comes
# from Secret Manager at runtime; it is never in the image or the build.
set -euo pipefail

: "${GCP_PROJECT:?set GCP_PROJECT to your Google Cloud project id}"
REGION="${GCP_REGION:-europe-west1}"
SERVICE="${CLOUD_RUN_SERVICE:-dgbot}"
REPO="${ARTIFACT_REPO:-cloud-run-source-deploy}"
RUNTIME_SA="${RUNTIME_SA:-dgbot-runtime@${GCP_PROJECT}.iam.gserviceaccount.com}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"

cd "$(dirname "$0")/.."

TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"
if [[ -z "${IMAGE_TAG:-}" && -n "$(git status --porcelain --untracked-files=no)" ]]; then
  TAG="${TAG}-dirty" # uncommitted tracked changes are uploaded too; don't pretend it's HEAD
fi
IMAGE="${REGION}-docker.pkg.dev/${GCP_PROJECT}/${REPO}/${SERVICE}:${TAG}"

# 1. Build. The image builds its search index (~3,100 passages on CPU), so a bigger VM
#    and a longer timeout than Cloud Build's 10-minute default. An explicit staging dir skips
#    gcloud's "list every bucket in the project" ownership check, so the CI deployer only
#    needs access to this one bucket (C-029).
if [[ -z "${SKIP_BUILD:-}" ]]; then
  gcloud builds submit . \
    --project "$GCP_PROJECT" \
    --tag "$IMAGE" \
    --gcs-source-staging-dir "gs://${GCP_PROJECT}_cloudbuild/source" \
    --machine-type e2-highcpu-8 \
    --timeout 3600s \
    --suppress-logs \
    --quiet
fi

# 2. Deploy. Loading the 1.2 GB embedding model peaks above 2 GiB on Cloud Run (C-027) → 4 GiB,
#    the most 1 vCPU allows. Bounded instances = bounded cost.
gcloud run deploy "$SERVICE" \
  --project "$GCP_PROJECT" \
  --region "$REGION" \
  --image "$IMAGE" \
  --service-account "$RUNTIME_SA" \
  --set-secrets OPENROUTER_API_KEY=openrouter-api-key:latest \
  --port 7860 \
  --cpu 1 \
  --memory 4Gi \
  --cpu-boost \
  --min-instances "$MIN_INSTANCES" \
  --max-instances 2 \
  --concurrency 40 \
  --timeout 300 \
  --set-env-vars DGBOT_ENV=prod \
  --allow-unauthenticated \
  --quiet

gcloud run services describe "$SERVICE" --project "$GCP_PROJECT" --region "$REGION" \
  --format 'value(status.url)'
