#!/usr/bin/env bash
# Idempotent deploy of AnnaDrishti to Cloud Run (asia-south1) via Cloud Build.
#
#   export GCP_PROJECT=my-project            # or: gcloud config set project my-project
#   export GEMINI_API_KEY=AIza...            # only needed the first time / when rotating
#   ./deploy/deploy.sh
#
# Optional env:
#   REGION=asia-south1  SERVICE=annadrishti  REPO=annadrishti  GEMINI_MODEL=gemini-2.5-flash
#   USE_VERTEX=1            use Vertex AI with the Cloud Run service account (no API key / secret)
#   ARTIFACTS_GCS_URI=gs://bucket/prefix   API downloads *.json from here at startup
#   ENABLE_EE=1             also enable the Earth Engine API
set -euo pipefail
cd "$(dirname "$0")/.."

REGION="${REGION:-asia-south1}"
SERVICE="${SERVICE:-annadrishti}"
REPO="${REPO:-annadrishti}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-2.5-flash}"
USE_VERTEX="${USE_VERTEX:-0}"
ARTIFACTS_GCS_URI="${ARTIFACTS_GCS_URI:-}"
PROJECT="${GCP_PROJECT:-${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}}"

[ -n "$PROJECT" ] && [ "$PROJECT" != "(unset)" ] || { echo "ERROR: set GCP_PROJECT or run 'gcloud config set project <id>'" >&2; exit 1; }
command -v gcloud >/dev/null || { echo "ERROR: gcloud not installed (see deploy/README_GCP.md)" >&2; exit 1; }
gcloud auth list --filter=status:ACTIVE --format='value(account)' | grep -q . \
  || { echo "ERROR: not logged in. Run: gcloud auth login" >&2; exit 1; }

echo "==> Project: $PROJECT  Region: $REGION  Service: $SERVICE"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"   # default Cloud Run + Cloud Build identity

echo "==> Enabling APIs (no-op if already enabled)"
APIS=(run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com)
[ "$USE_VERTEX" = "1" ] && APIS+=(aiplatform.googleapis.com)
[ "${ENABLE_EE:-0}" = "1" ] && APIS+=(earthengine.googleapis.com)
gcloud services enable "${APIS[@]}" --project "$PROJECT" 2>/dev/null \
  || echo "WARN: could not enable APIs (needs Service Usage Admin). Continuing; make sure they are already enabled in the console."

echo "==> Artifact Registry repo '$REPO'"
gcloud artifacts repositories describe "$REPO" --location "$REGION" --project "$PROJECT" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "$REPO" --repository-format=docker --location "$REGION" \
       --description="AnnaDrishti images" --project "$PROJECT"

bind() { # bind <role> : idempotent IAM binding for the runtime/build service account
  gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$RUNTIME_SA" \
    --role "$1" --condition=None --quiet >/dev/null
}
echo "==> Granting build/deploy roles to $RUNTIME_SA (idempotent)"
for r in roles/run.admin roles/iam.serviceAccountUser roles/artifactregistry.writer \
         roles/logging.logWriter roles/storage.objectViewer; do bind "$r"; done

if [ "$USE_VERTEX" = "1" ]; then
  echo "==> Vertex AI mode: granting roles/aiplatform.user, skipping Secret Manager"
  bind roles/aiplatform.user
else
  echo "==> Secret GEMINI_API_KEY"
  if ! gcloud secrets describe GEMINI_API_KEY --project "$PROJECT" >/dev/null 2>&1; then
    [ -n "${GEMINI_API_KEY:-}" ] || { echo "ERROR: secret missing and GEMINI_API_KEY env not set (or use USE_VERTEX=1)" >&2; exit 1; }
    printf '%s' "$GEMINI_API_KEY" | gcloud secrets create GEMINI_API_KEY --data-file=- \
      --replication-policy=automatic --project "$PROJECT"
  elif [ -n "${GEMINI_API_KEY:-}" ]; then
    current="$(gcloud secrets versions access latest --secret GEMINI_API_KEY --project "$PROJECT" 2>/dev/null || true)"
    if [ "$current" != "$GEMINI_API_KEY" ]; then
      echo "    key changed -> adding new secret version"
      printf '%s' "$GEMINI_API_KEY" | gcloud secrets versions add GEMINI_API_KEY --data-file=- --project "$PROJECT"
    fi
  fi
  gcloud secrets add-iam-policy-binding GEMINI_API_KEY --project "$PROJECT" \
    --member "serviceAccount:$RUNTIME_SA" --role roles/secretmanager.secretAccessor --quiet >/dev/null
fi

# Optional secret RATE_LIMIT_BYPASS_TOKEN (create it to let the pre-warm script skip per-IP limits):
#   printf '%s' "$(openssl rand -hex 24)" | gcloud secrets create RATE_LIMIT_BYPASS_TOKEN --data-file=- --replication-policy=automatic
HAVE_BYPASS_SECRET=0
if gcloud secrets describe RATE_LIMIT_BYPASS_TOKEN --project "$PROJECT" >/dev/null 2>&1; then
  HAVE_BYPASS_SECRET=1
  echo "==> Secret RATE_LIMIT_BYPASS_TOKEN found: granting access and passing it to the service"
  gcloud secrets add-iam-policy-binding RATE_LIMIT_BYPASS_TOKEN --project "$PROJECT" \
    --member "serviceAccount:$RUNTIME_SA" --role roles/secretmanager.secretAccessor --quiet >/dev/null
fi

if [ -n "$ARTIFACTS_GCS_URI" ]; then
  bucket="${ARTIFACTS_GCS_URI#gs://}"; bucket="${bucket%%/*}"
  echo "==> Bucket gs://$bucket (create if missing) + read access for the service"
  gsutil ls -b "gs://$bucket" >/dev/null 2>&1 || gsutil mb -l "$REGION" -p "$PROJECT" "gs://$bucket"
fi

TAG="$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d-%H%M%S)"
IMAGE="$REGION-docker.pkg.dev/$PROJECT/$REPO/app"
if [ "${LOCAL_BUILD:-0}" = "1" ]; then
  echo "==> LOCAL_BUILD=1: building the image on this machine (linux/amd64) and pushing to Artifact Registry"
  command -v docker >/dev/null || { echo "ERROR: docker not installed" >&2; exit 1; }
  gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet
  docker build --platform linux/amd64 -f deploy/Dockerfile -t "$IMAGE:$TAG" -t "$IMAGE:latest" .
  docker push "$IMAGE:$TAG" && docker push "$IMAGE:latest"
  ENVVARS="GEMINI_MODEL=$GEMINI_MODEL,VERTEX_LOCATION=${VERTEX_LOCATION:-global},XFF_POSITION=last"
  SECRET_LIST=""
  if [ "$USE_VERTEX" = "1" ]; then ENVVARS="$ENVVARS,USE_VERTEX=1,GOOGLE_CLOUD_PROJECT=$PROJECT"; else SECRET_LIST="GEMINI_API_KEY=GEMINI_API_KEY:latest"; fi
  [ "$HAVE_BYPASS_SECRET" = "1" ] && SECRET_LIST="${SECRET_LIST:+$SECRET_LIST,}RATE_LIMIT_BYPASS_TOKEN=RATE_LIMIT_BYPASS_TOKEN:latest"
  SECRETS=()
  [ -n "$SECRET_LIST" ] && SECRETS=(--set-secrets "$SECRET_LIST")
  [ -n "$ARTIFACTS_GCS_URI" ] && ENVVARS="$ENVVARS,ARTIFACTS_GCS_URI=$ARTIFACTS_GCS_URI"
  gcloud run deploy "$SERVICE" --image "$IMAGE:$TAG" --region "$REGION" --project "$PROJECT" --platform managed \
    --allow-unauthenticated --min-instances 0 --max-instances 5 --memory 1Gi --cpu 1 --concurrency 40 --timeout 120 \
    --port 8080 --set-env-vars "$ENVVARS" "${SECRETS[@]}"
else
  echo "==> Cloud Build (tag $TAG) - this takes ~5-8 minutes"
  gcloud builds submit . --project "$PROJECT" \
    --config deploy/cloudbuild.yaml --ignore-file deploy/gcloudignore \
    --substitutions "_REGION=$REGION,_REPO=$REPO,_SERVICE=$SERVICE,_TAG=$TAG,_GEMINI_MODEL=$GEMINI_MODEL,_USE_VERTEX=$USE_VERTEX,_ARTIFACTS_GCS_URI=$ARTIFACTS_GCS_URI"
fi

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format='value(status.url)')"
echo
echo "Deployed: $URL"
echo "Health:   $URL/api/health"
