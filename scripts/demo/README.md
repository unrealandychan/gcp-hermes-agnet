# Hermes Agent PoC — Demo Data & Showcase

This directory contains everything needed to seed realistic demo data and
exercise every feature of the Hermes Agent platform.

---

## Directory Layout

```
scripts/demo/
├── README.md                   ← you are here
├── seed_bigquery.py            ← create and populate BigQuery tables
├── seed_knowledge_base.py      ← upload docs + skills to RAG corpora
├── showcase.sh                 ← 40+ curl examples covering all features
├── e2e_test.py                 ← async Python end-to-end test suite
└── sample_docs/
    ├── hr_policy.txt           ← Acme HR Policy Handbook
    ├── it_vpn_runbook.txt      ← VPN setup & troubleshooting runbook
    ├── it_incident_response.txt← Incident response playbook (P0–P3)
    ├── dev_deployment_guide.txt← CI/CD deploy & rollback guide
    └── onboarding_checklist.txt← New hire onboarding checklist
```

---

## Quickstart

### 1. Seed BigQuery

```bash
cd hermes-gcp
python scripts/demo/seed_bigquery.py
```

Creates dataset `hermes_demo` with 5 tables:

| Table | Rows | Description |
|---|---|---|
| `employees` | 25 | Acme staff across 6 departments |
| `it_incidents` | 15 | Nov 2025 – May 2026, P0–P3 |
| `sales_performance` | 144 | Monthly revenue by region × product |
| `pto_requests` | 20 | Approved / pending leave requests |
| `project_tracker` | 10 | Cross-team projects with status |

### 2. Seed RAG Knowledge Base

First ensure the RAG corpora exist (run once):
```bash
python scripts/setup_rag.py
```

Then upload demo documents and pre-seeded skills:
```bash
python scripts/demo/seed_knowledge_base.py
```

### 3. Run the Showcase

```bash
# Ensure the gateway is running first:
uvicorn gateway.main:app --port 8080 --reload

# In another terminal:
chmod +x scripts/demo/showcase.sh

# Run all sections:
./scripts/demo/showcase.sh

# Run a specific section:
./scripts/demo/showcase.sh hr          # HR agent scenarios
./scripts/demo/showcase.sh it          # IT Helpdesk scenarios
./scripts/demo/showcase.sh dev         # Developer agent scenarios
./scripts/demo/showcase.sh analytics   # BigQuery analytics
./scripts/demo/showcase.sh tasks       # Long-running async tasks
./scripts/demo/showcase.sh scheduler   # Self-scheduling (Cloud Scheduler)
./scripts/demo/showcase.sh workspace   # Gmail / Calendar / Drive
./scripts/demo/showcase.sh connectors  # Telegram / Slack / Teams webhooks
./scripts/demo/showcase.sh multiturn   # Multi-turn conversation with sessions
```

### 4. Run the E2E Test Suite

```bash
pip install httpx
python scripts/demo/e2e_test.py
```

By default tests against `http://localhost:8080`. Override with:
```bash
GATEWAY_URL=https://hermes-gateway-xxxxx.run.app python scripts/demo/e2e_test.py
```

### 5. Cloud Smoke Test (read-only)

Quick pass/fail probe to verify deployed cloud runtime is reachable from local.
This script is read-only: it only performs chat/query calls and never creates or updates resources.

```bash
# Auto mode:
# - if GATEWAY_URL is set -> gateway mode
# - otherwise -> sdk mode
python scripts/demo/cloud_smoke_test.py
```

Gateway mode (no GCP credentials required if your gateway accepts your provided token/api key):

```bash
GATEWAY_URL=https://your-gateway-url.run.app \
GOOGLE_ID_TOKEN="$(gcloud auth print-identity-token)" \
python scripts/demo/cloud_smoke_test.py --mode gateway
```

SDK mode (requires ADC/GCP credentials + existing REASONING_ENGINE_RESOURCE_NAME):

```bash
GCP_PROJECT_ID=your-project \
GCP_LOCATION=us-central1 \
REASONING_ENGINE_RESOURCE_NAME=projects/your-project/locations/us-central1/reasoningEngines/1234567890 \
python scripts/demo/cloud_smoke_test.py --mode sdk
```

---

## Demo Data Details

### Company: Acme Corporation (acmecorp.com)

**Key employees:**

| Name | Email | Role |
|---|---|---|
| Alice Chen | alice.chen@acmecorp.com | Senior Software Engineer (L5) |
| Bob Kim | bob.kim@acmecorp.com | Engineering Manager (L7) |
| Carol Davis | carol.davis@acmecorp.com | VP of Engineering (L9) |
| Frank Garcia | frank.garcia@acmecorp.com | Staff Engineer (L6) |
| Henry Brown | henry.brown@acmecorp.com | DevOps Engineer (L5) |
| Noah Anderson | noah.anderson@acmecorp.com | HR Business Partner (L5) |
| Olivia Harris | olivia.harris@acmecorp.com | Head of HR (L8) |
| James Taylor | james.taylor@acmecorp.com | Sales Director (L7) |
| Xavier Green | xavier.green@acmecorp.com | IT Sysadmin (L4) |
| Yara Adams | yara.adams@acmecorp.com | IT Manager (L7) |

**Open IT incidents:**

| ID | Severity | Title | Assignee |
|---|---|---|---|
| INC-013 | P2 | Analytics dashboard 24h stale data | alice.chen |
| INC-014 | P1 | Phishing campaign targeting employees | xavier.green |
| INC-015 | P3 | Emma Wilson cannot access Confluence | xavier.green |

**Active projects:**

| ID | Name | Owner | Completion |
|---|---|---|---|
| PRJ-001 | Hermes AI Agent Platform | bob.kim | 70% |
| PRJ-002 | CRM Data Migration | mia.thompson | 55% |
| PRJ-007 | ISO 27001 Certification | frank.garcia | 65% |

---

## Sample BigQuery Queries

```sql
-- Headcount by department
SELECT department, COUNT(*) AS headcount
FROM hermes_demo.employees
GROUP BY department
ORDER BY headcount DESC;

-- Open and in-progress incidents
SELECT incident_id, severity, title, status, assignee
FROM hermes_demo.it_incidents
WHERE status IN ('Open', 'In Progress')
ORDER BY severity;

-- Q1 2025 revenue by region
SELECT region, SUM(revenue_usd) AS total_revenue,
       ROUND(SUM(revenue_usd) / SUM(quota_usd) * 100, 1) AS attainment_pct
FROM hermes_demo.sales_performance
WHERE month BETWEEN '2025-01-01' AND '2025-03-31'
GROUP BY region
ORDER BY total_revenue DESC;

-- Pending PTO requests
SELECT r.request_id, e.full_name, r.start_date, r.end_date, r.days, r.reason
FROM hermes_demo.pto_requests r
JOIN hermes_demo.employees e ON r.employee_id = e.employee_id
WHERE r.status = 'Pending'
ORDER BY r.start_date;

-- P2 incident SLA compliance (resolve < 480 mins = 1 business day)
SELECT
  COUNT(*) AS total_p2,
  COUNTIF(resolution_mins <= 480) AS within_sla,
  ROUND(COUNTIF(resolution_mins <= 480) / COUNT(*) * 100, 1) AS sla_pct
FROM hermes_demo.it_incidents
WHERE severity = 'P2' AND resolution_mins IS NOT NULL;
```

---

## Environment Variables

The scripts respect the same `.env` as the gateway:

```dotenv
GCP_PROJECT_ID=hermes-agent-prod
GCP_LOCATION=us-central1
KNOWLEDGE_CORPUS_NAME=projects/.../locations/.../ragCorpora/...
SKILLS_CORPUS_NAME=projects/.../locations/.../ragCorpora/...
GATEWAY_URL=http://localhost:8080      # for showcase.sh / e2e_test.py
GOOGLE_ID_TOKEN=...                   # optional, falls back to gcloud auth
TIMEOUT_TASK_POLL=120                 # seconds to wait for async tasks
```
