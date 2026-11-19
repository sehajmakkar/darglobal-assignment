#!/usr/bin/env bash
# Deploy the app to Google Cloud Run (D-028).
#
#   GCP_PROJECT=my-project scripts/deploy_cloudrun.sh
#
# Cloud Build builds the Dockerfile from the uploaded source (.gcloudignore keeps private
# docs, notes, .env and raw data out of the upload), pushes the image to Artifact Registry
# and rolls out a new Cloud Run revision. Settings are env vars, never baked into the image.
set -euo pipefail

: "${GCP_PROJECT:?set GCP_PROJECT to your Google Cloud project id}"
REGION="${GCP_REGION:-europe-west1}"
SERVICE="${CLOUD_RUN_SERVICE:-dgbot}"

cd "$(dirname "$0")/.."

gcloud run deploy "$SERVICE" \
  --project "$GCP_PROJECT" \
  --region "$REGION" \
  --source . \
  --port 7860 \
  --cpu 1 \
  --memory 1Gi \
  --cpu-boost \
  --min-instances 0 \
  --max-instances 2 \
  --concurrency 40 \
  --timeout 300 \
  --set-env-vars DGBOT_ENV=prod \
  --allow-unauthenticated \
  --quiet

gcloud run services describe "$SERVICE" --project "$GCP_PROJECT" --region "$REGION" \
  --format 'value(status.url)'
