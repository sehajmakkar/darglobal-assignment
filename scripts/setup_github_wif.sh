#!/usr/bin/env bash
# One-time setup: let GitHub Actions deploy to Cloud Run without a long-lived key (D-052).
#
#   GCP_PROJECT=my-project GITHUB_REPO=owner/repo scripts/setup_github_wif.sh
#
# Creates:
# - Workload Identity pool `github` + OIDC provider `github-repo` that trusts tokens only
#   from GITHUB_REPO on refs/heads/main;
# - service account `dgbot-deployer` with only what scripts/deploy_cloudrun.sh needs:
#   Cloud Run admin (deploy + public access), Cloud Build editor, service-usage consumer,
#   storage admin on the Cloud Build source bucket only, and "act as" on the runtime and
#   build service accounts.
# Prints the two values to store as GitHub repository variables. Safe to re-run.
set -euo pipefail

: "${GCP_PROJECT:?set GCP_PROJECT}"
: "${GITHUB_REPO:?set GITHUB_REPO, e.g. owner/repo}"
NUMBER="$(gcloud projects describe "$GCP_PROJECT" --format 'value(projectNumber)')"
DEPLOYER="dgbot-deployer@${GCP_PROJECT}.iam.gserviceaccount.com"
POOL="projects/${NUMBER}/locations/global/workloadIdentityPools/github"

exists() { "$@" >/dev/null 2>&1; }

gcloud services enable sts.googleapis.com iamcredentials.googleapis.com --project "$GCP_PROJECT"

exists gcloud iam workload-identity-pools describe github --location global --project "$GCP_PROJECT" ||
  gcloud iam workload-identity-pools create github --location global --project "$GCP_PROJECT" \
    --display-name "GitHub Actions"

exists gcloud iam workload-identity-pools providers describe github-repo --location global \
  --workload-identity-pool github --project "$GCP_PROJECT" ||
  gcloud iam workload-identity-pools providers create-oidc github-repo --location global \
    --workload-identity-pool github --project "$GCP_PROJECT" \
    --display-name "GitHub repo, main branch" \
    --issuer-uri https://token.actions.githubusercontent.com \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition "assertion.repository == '${GITHUB_REPO}' && assertion.ref == 'refs/heads/main'"

exists gcloud iam service-accounts describe "$DEPLOYER" --project "$GCP_PROJECT" ||
  gcloud iam service-accounts create dgbot-deployer --project "$GCP_PROJECT" \
    --display-name "dgbot deploys from GitHub Actions (WIF)"

for role in roles/run.admin roles/cloudbuild.builds.editor roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" --member "serviceAccount:${DEPLOYER}" \
    --role "$role" --condition None --format none
done
gcloud storage buckets add-iam-policy-binding "gs://${GCP_PROJECT}_cloudbuild" \
  --member "serviceAccount:${DEPLOYER}" --role roles/storage.admin --format none
for sa in "dgbot-runtime@${GCP_PROJECT}.iam.gserviceaccount.com" \
  "${NUMBER}-compute@developer.gserviceaccount.com"; do
  gcloud iam service-accounts add-iam-policy-binding "$sa" --project "$GCP_PROJECT" \
    --member "serviceAccount:${DEPLOYER}" --role roles/iam.serviceAccountUser --format none
done
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER" --project "$GCP_PROJECT" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/${POOL}/attribute.repository/${GITHUB_REPO}" \
  --format none

echo
echo "Set these as GitHub repository variables (Settings → Secrets and variables → Actions → Variables):"
echo "  GCP_PROJECT              = ${GCP_PROJECT}"
echo "  GCP_WIF_PROVIDER         = ${POOL}/providers/github-repo"
echo "  GCP_DEPLOY_SERVICE_ACCOUNT = ${DEPLOYER}"
