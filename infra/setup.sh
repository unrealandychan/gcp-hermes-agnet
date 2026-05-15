#!/usr/bin/env bash
# infra/setup.sh
#
# One-time GCP project bootstrap for Hermes Agent Platform.
# Run this ONCE before deploying anything.
#
# Prerequisites:
#   - gcloud CLI authenticated with project owner permissions
#   - PROJECT_ID, LOCATION, STAGING_BUCKET set as env vars OR read from .env
#
# Usage:
#   source .env && bash infra/setup.sh
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-hermes-agent-prod}"
LOCATION="${GCP_LOCATION:-us-central1}"
STAGING_BUCKET="${GCP_STAGING_BUCKET:-gs://hermes-agent-artifacts}"
BUCKET_NAME="${STAGING_BUCKET#gs://}"

echo "==> Bootstrapping Hermes Agent Platform"
echo "    Project  : $PROJECT_ID"
echo "    Location : $LOCATION"
echo "    Bucket   : $STAGING_BUCKET"
echo ""

# ── 1. Set active project ──────────────────────────────────────────────────────
gcloud config set project "$PROJECT_ID"

# ── 2. Enable required APIs ────────────────────────────────────────────────────
echo "==> Enabling APIs …"
gcloud services enable \
  aiplatform.googleapis.com \
  bigquery.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  iam.googleapis.com \
  firestore.googleapis.com \
  cloudscheduler.googleapis.com \
  gmail.googleapis.com \
  calendar-json.googleapis.com \
  drive.googleapis.com \
  admin.googleapis.com \
  modelarmor.googleapis.com \
  cloudtrace.googleapis.com \
  --project="$PROJECT_ID"

# ── 3. Create staging bucket ────────────────────────────────────────────────────
echo "==> Creating staging bucket …"
if ! gsutil ls -b "$STAGING_BUCKET" &>/dev/null; then
  gsutil mb -p "$PROJECT_ID" -l "$LOCATION" "$STAGING_BUCKET"
  gsutil versioning set on "$STAGING_BUCKET"
  echo "    Created $STAGING_BUCKET"
else
  echo "    Bucket already exists — skipping."
fi

# ── 4. Create service account ──────────────────────────────────────────────────
SA_NAME="hermes-agent-sa"
SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

echo "==> Creating service account $SA_EMAIL …"
if ! gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT_ID" &>/dev/null; then
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="Hermes Agent Service Account" \
    --project="$PROJECT_ID"
fi

# ── 5. Grant IAM roles ─────────────────────────────────────────────────────────
echo "==> Granting IAM roles …"
for ROLE in \
  roles/aiplatform.user \
  roles/bigquery.dataViewer \
  roles/bigquery.jobUser \
  roles/storage.objectAdmin \
  roles/secretmanager.secretAccessor \
  roles/logging.logWriter \
  roles/datastore.user \
  roles/cloudscheduler.admin \
; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="$ROLE" \
    --condition=None \
    --quiet
done

# ── 6. Create .env from example if missing ────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> Created .env from .env.example — fill in the remaining values."
fi

echo ""
# ── Firestore native-mode database ───────────────────────────────────────────
echo "==> Creating Firestore database (native mode) …"
if ! gcloud firestore databases list --project="$PROJECT_ID" --format=json 2>/dev/null | python3 -c "import sys,json; dbs=json.load(sys.stdin); exit(0 if any(d.get('type')=='FIRESTORE_NATIVE' for d in dbs) else 1)" &>/dev/null; then
  gcloud firestore databases create \
    --location="$LOCATION" \
    --project="$PROJECT_ID"
  echo "    Firestore database created."
else
  echo "    Firestore database already exists — skipping."
fi

echo "==> Bootstrap complete. Next steps:"
echo "    1. python scripts/setup_rag.py       # create RAG corpora"
echo "    2. Fill KNOWLEDGE_CORPUS_NAME and SKILLS_CORPUS_NAME in .env"
echo "    3. python scripts/deploy.py           # deploy to Agent Runtime"
echo "    4. Fill REASONING_ENGINE_RESOURCE_NAME in .env"
echo "    5. docker build + gcloud run deploy   # deploy gateway"
