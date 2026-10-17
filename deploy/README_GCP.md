# Deploying AnnaDrishti to Google Cloud (no DevOps experience needed)

You end up with one public HTTPS URL on **Cloud Run** (region `asia-south1`, Mumbai) serving the API and the website.

## 0. What you need
- A Google account and a Google Cloud **project with billing enabled** (billing: console.cloud.google.com/billing, link it to the project; Cloud Run needs it even though idle cost is ~0).
- A Gemini API key from https://aistudio.google.com/apikey **or** use Vertex AI (see "Vertex instead of API key").

## 1. Install gcloud on macOS
```bash
brew install --cask google-cloud-sdk        # or: curl https://sdk.cloud.google.com | bash
gcloud --version
gcloud auth login                            # opens a browser
gcloud config set project YOUR_PROJECT_ID    # find it at console.cloud.google.com (project picker)
```

## 2. Deploy
```bash
cd climate-informed-food-security-optimisation-project
export GEMINI_API_KEY="AIza..."              # stored in Secret Manager, never in the image
./deploy/deploy.sh
```
The script is safe to re-run. It: enables the APIs (Cloud Run, Cloud Build, Artifact Registry, Secret Manager), creates
the Docker repo `annadrishti`, stores the key as secret `GEMINI_API_KEY`, grants the needed roles to the default
service account, builds the image in the cloud (~5-8 min; you do not need Docker locally) and deploys service
`annadrishti` (1 GiB, min-instances 0, max 5, public). It prints the URL; open `URL/api/health` to check.
If a step fails with a permission error you are probably not an Owner of the project, ask the project owner to run it.

Useful overrides: `REGION=...`, `GEMINI_MODEL=gemini-3-...` (any model id), `GCP_PROJECT=...`.

### Vertex instead of API key
`USE_VERTEX=1 ./deploy/deploy.sh` enables Vertex AI, grants the service account `roles/aiplatform.user`, skips the secret.
Check the model you choose is available in `asia-south1` (otherwise set `VERTEX_LOCATION`/redeploy with another region such as `us-central1`).


### Deploying with a service-account key (no browser login)
If you created a project service account (roles listed in docs/PLAN.md "GCP access") and saved its key in the project folder:
```bash
gcloud auth activate-service-account --key-file=./aibuildercup-511905-0689c9d7ac44.json
gcloud config set project aibuildercup-511905
export GEMINI_API_KEY="AIza..."      # or USE_VERTEX=1 to use Gemini through Vertex AI with the project's own credentials
./deploy/deploy.sh
```
The key file is git/docker/gcloud-ignored. The SA needs the APIs enabled first (Vertex AI, Cloud Run, Cloud Build, Artifact Registry, Secret Manager, Cloud Scheduler, IAM, Resource Manager, Earth Engine, BigQuery, Storage); a *Service Usage Consumer* role cannot enable them, so enable once in the console or grant *Service Usage Admin*.

## 3. Updating the data (artifacts) without rebuilding
Option A (simple): re-run `./deploy/deploy.sh` after regenerating `artifacts/` (image is rebuilt with new files).

Option B (fast, no rebuild): keep artifacts in a Cloud Storage bucket; the API downloads every `*.json` (incl. `timeseries/`) at startup.
```bash
export ARTIFACTS_GCS_URI=gs://YOUR_PROJECT-annadrishti-artifacts/v1     # deploy.sh creates the bucket if missing
./deploy/deploy.sh                                                     # one time, sets the env var
gsutil -m rsync -r -x '.*\.parquet$|.*_cache.*' artifacts gs://YOUR_PROJECT-annadrishti-artifacts/v1
gcloud run services update annadrishti --region asia-south1 --update-env-vars REFRESHED=$(date +%s)   # restarts instances
```
(Only `*.json` are fetched. Cached advisories are keyed by model/scenario, delete `_advisory_cache.json` if you regenerate data and want fresh text.)

## 4. Custom domain (optional)
```bash
gcloud beta run domain-mappings create --service annadrishti --domain annadrishti.example.org --region asia-south1
```
Then add the DNS records it prints. (Not all regions support domain mappings; alternative: a global external HTTPS load balancer.)

## 5. Cost
Idle: about $0 (min-instances 0). Typical demo month: **under $5**: Artifact Registry storage (~$0.10/GB-month),
Secret Manager (~$0.06), Cloud Build (first 2,500 build-minutes/month free with the default machine; this config uses a larger machine, so ~$0.02/min after the free tier),
Cloud Run (free tier 2M requests, 180k vCPU-s) plus Gemini tokens (cents for a demo; advisories are cached).
Set a budget alert: console.cloud.google.com/billing/budgets.

## 6. Logs, rollback
```bash
gcloud run services logs read annadrishti --region asia-south1 --limit 100
gcloud run revisions list --service annadrishti --region asia-south1
gcloud run services update-traffic annadrishti --region asia-south1 --to-revisions REVISION_NAME=100   # rollback
gcloud run services update-traffic annadrishti --region asia-south1 --to-latest                         # roll forward
```

## 7. Run the same image locally
`GEMINI_API_KEY=... ./deploy/run_local_docker.sh` (or `MOCK_LLM=1`), then http://localhost:8080.

## 8. Alternatives
**GKE Autopilot (5 lines):**
```bash
gcloud container clusters create-auto annadrishti --region asia-south1
gcloud container clusters get-credentials annadrishti --region asia-south1
kubectl create deployment annadrishti --image asia-south1-docker.pkg.dev/PROJECT/annadrishti/app:latest --port 8080
kubectl set env deployment/annadrishti GEMINI_API_KEY=...   # prefer a Secret in production
kubectl expose deployment annadrishti --type LoadBalancer --port 80 --target-port 8080
```
More moving parts and a ~$70+/month cluster fee, only worth it if you need it.

**Firebase Hosting (static only):** hosts just the React build, no Gemini endpoints, so the AI features need the API
elsewhere (Cloud Run), proxied with a `rewrites` entry (`{"source": "/api/**", "run": {"serviceId": "annadrishti", "region": "asia-south1"}}`).
`cd web && pnpm build && firebase init hosting && firebase deploy` (public dir `dist`, SPA rewrite to `/index.html`).

### If Cloud Build fails (or you prefer building locally)
```bash
LOCAL_BUILD=1 GEMINI_API_KEY=... ./deploy/deploy.sh
```
Builds the image on your machine (Docker required, linux/amd64), pushes it to Artifact Registry and deploys the same way.
