#!/usr/bin/env python3
"""
scripts/demo/seed_knowledge_base.py

Uploads demo documents and sample skills into the Hermes RAG corpora.

Uploads to:
  hermes-knowledge-corpus — HR policies, IT runbooks, developer guides, onboarding
  hermes-skills-corpus    — Pre-seeded example skills (agent-learned procedures)

Usage:
    cd hermes-gcp
    python scripts/demo/seed_knowledge_base.py

The corpus resource names are read from .env (KNOWLEDGE_CORPUS_NAME, SKILLS_CORPUS_NAME).
Run scripts/setup_rag.py first if the corpora do not yet exist.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import vertexai
from vertexai.preview import rag

DOCS_DIR = Path(__file__).parent / "sample_docs"

# ── Knowledge-base documents ───────────────────────────────────────────────────
# Each entry: (filename, display_name, description)
KNOWLEDGE_DOCS = [
    (
        "hr_policy.txt",
        "Acme HR Policy Handbook v4.2",
        "PTO, remote work, benefits, performance reviews, expense reimbursement",
    ),
    (
        "it_vpn_runbook.txt",
        "IT Runbook: VPN Access Setup & Troubleshooting",
        "Cisco AnyConnect install, configuration, troubleshooting, escalation",
    ),
    (
        "it_incident_response.txt",
        "IT Incident Response Playbook",
        "Severity levels P0–P3, response SLAs, communication templates, escalation",
    ),
    (
        "dev_deployment_guide.txt",
        "Developer Guide: Deployment Process",
        "CI/CD pipeline, environments, manual deploy, rollback, feature flags",
    ),
    (
        "onboarding_checklist.txt",
        "New Employee Onboarding Checklist",
        "Day 1 setup, Week 1 tasks, benefits enrollment, system access requests",
    ),
]

# ── Pre-seeded skills ──────────────────────────────────────────────────────────
# These simulate procedures the agent has already learned from previous interactions.
SKILLS = [
    {
        "name": "check_pto_balance",
        "content": """SKILL: Check Employee PTO Balance
Trigger: When an employee asks how many PTO days they have left.
Procedure:
1. Query BigQuery: SELECT employee_id, start_date, level FROM hermes_demo.employees WHERE email = '<user_email>'
2. Calculate years of tenure from start_date to today.
3. Determine annual entitlement: 0-2 years = 20 days, 2-5 years = 25 days, 5+ years = 30 days.
4. Query PTO requests: SELECT SUM(days) FROM hermes_demo.pto_requests WHERE employee_email = '<email>' AND EXTRACT(YEAR FROM start_date) = EXTRACT(YEAR FROM CURRENT_DATE()) AND status IN ('Approved', 'Pending')
5. Remaining = annual_entitlement - days_used
6. Reply with: balance, entitlement basis, and any pending requests.
Learned from: 47 similar interactions. Last updated: 2026-05-01.""",
    },
    {
        "name": "reset_vpn_access",
        "content": """SKILL: Reset / Re-provision VPN Access
Trigger: Employee says "I can't connect to VPN" or "VPN is not working".
Procedure:
1. Ask the employee to confirm their OS and AnyConnect version.
2. Direct to vpn.acmecorp.com for the latest AnyConnect download.
3. Check if the issue is auth (Okta MFA) or connectivity (split-tunnel/DNS).
4. For auth issues: direct to okta.acmecorp.com to re-verify MFA enrollment.
5. For connectivity: provide DNS flush commands for their OS.
6. If unresolved after 3 steps, create a P2 ticket: escalate to xavier.green@acmecorp.com with subject "VPN reset — <employee name>".
Learned from: 32 similar interactions. Last updated: 2026-04-15.""",
    },
    {
        "name": "create_incident_ticket",
        "content": """SKILL: Create IT Incident Ticket
Trigger: Someone reports a system issue or outage.
Procedure:
1. Assess severity: P0 (full outage), P1 (major degradation), P2 (partial impact), P3 (minor issue).
2. Assign incident ID: INC-<next number> (query hermes_demo.it_incidents for MAX incident_id).
3. For P0/P1: immediately post to Slack #incidents channel and page on-call (+1-415-555-0100).
4. For P2/P3: create a helpdesk.acmecorp.com ticket and assign to xavier.green@acmecorp.com.
5. Acknowledge the reporter: "I've logged incident <ID> with severity <P?>. ETA for first response: <per SLA>."
Learned from: 28 similar interactions. Last updated: 2026-03-20.""",
    },
    {
        "name": "onboard_new_employee",
        "content": """SKILL: New Employee Onboarding Flow
Trigger: HR asks to onboard a new employee starting on a specific date.
Procedure:
1. Collect: full name, email, department, title, manager email, start date, location (remote/office).
2. Create calendar event: "Welcome — <name> first day" for start_date at 9 AM, invite manager + noah.anderson@acmecorp.com.
3. Create calendar event: "HR Orientation — <name>" for start_date at 2 PM, invite new hire + noah.anderson@acmecorp.com.
4. Send welcome email to new hire from noah.anderson@acmecorp.com with subject "Welcome to Acme, <name>!" using onboarding_checklist.txt template.
5. Send manager prep email: "Action required: <name> starts <date>" listing laptop order, system access requests needed.
6. Insert new row into hermes_demo.employees (if available).
Learned from: 15 similar interactions. Last updated: 2026-05-01.""",
    },
    {
        "name": "generate_sales_report",
        "content": """SKILL: Generate Sales Performance Report
Trigger: Manager asks for sales summary, quota attainment, or revenue by region/product.
Procedure:
1. Query: SELECT region, product, SUM(revenue_usd) as total_revenue, SUM(deals_closed) as total_deals, SUM(quota_usd) as total_quota, ROUND(SUM(revenue_usd)/SUM(quota_usd)*100,1) as attainment_pct FROM hermes_demo.sales_performance WHERE month >= '<start>' AND month <= '<end>' GROUP BY region, product ORDER BY total_revenue DESC
2. Format results as a markdown table with columns: Region, Product, Revenue, Deals, Quota, Attainment %.
3. Add a summary paragraph: top-performing region, best product, overall attainment.
4. If asked to send the report: use send_email tool to james.taylor@acmecorp.com and karen.white@acmecorp.com.
Learned from: 22 similar interactions. Last updated: 2026-04-28.""",
    },
]


def get_settings():
    try:
        from config import get_settings as _gs  # noqa: PLC0415
        return _gs()
    except Exception:  # noqa: BLE001
        class _FakeSettings:  # noqa: B024
            gcp_project_id = os.environ.get("GCP_PROJECT_ID", "hermes-agent-prod")
            gcp_location = os.environ.get("GCP_LOCATION", "asia-southeast1")
            knowledge_corpus_name = os.environ.get("KNOWLEDGE_CORPUS_NAME", "")
            skills_corpus_name = os.environ.get("SKILLS_CORPUS_NAME", "")
        return _FakeSettings()


def upload_doc(corpus_name: str, file_path: Path, display_name: str, description: str) -> None:
    """Upload a local text file to a RAG corpus."""
    print(f"  Uploading: {display_name} …", end=" ", flush=True)
    try:
        rag.upload_file(
            corpus_name=corpus_name,
            path=str(file_path),
            display_name=display_name,
            description=description,
        )
        print("✓")
    except Exception as exc:  # noqa: BLE001
        print(f"✗  {exc}")


def upload_skill(corpus_name: str, skill: dict) -> None:
    """Write a skill to a temp file and upload it to the skills corpus."""
    print(f"  Uploading skill: {skill['name']} …", end=" ", flush=True)
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", prefix=f"skill_{skill['name']}_", delete=False
        ) as f:
            f.write(skill["content"])
            tmp_path = f.name

        rag.upload_file(
            corpus_name=corpus_name,
            path=tmp_path,
            display_name=f"Skill: {skill['name']}",
            description=f"Pre-seeded agent skill: {skill['name']}",
        )
        os.unlink(tmp_path)
        print("✓")
    except Exception as exc:  # noqa: BLE001
        print(f"✗  {exc}")


def main() -> None:
    settings = get_settings()

    if not settings.knowledge_corpus_name:
        print("ERROR: KNOWLEDGE_CORPUS_NAME is not set in .env")
        print("Run: python scripts/setup_rag.py  first.")
        sys.exit(1)
    if not settings.skills_corpus_name:
        print("ERROR: SKILLS_CORPUS_NAME is not set in .env")
        print("Run: python scripts/setup_rag.py  first.")
        sys.exit(1)

    vertexai.init(project=settings.gcp_project_id, location=settings.gcp_location)

    print(f"Knowledge corpus: {settings.knowledge_corpus_name}")
    print(f"Skills corpus:    {settings.skills_corpus_name}")
    print()

    # ── Upload knowledge documents ─────────────────────────────────────────────
    print("Uploading knowledge base documents …")
    for filename, display_name, description in KNOWLEDGE_DOCS:
        file_path = DOCS_DIR / filename
        if not file_path.exists():
            print(f"  SKIP: {filename} not found at {file_path}")
            continue
        upload_doc(settings.knowledge_corpus_name, file_path, display_name, description)
        time.sleep(1)  # avoid rate limiting

    # ── Upload pre-seeded skills ───────────────────────────────────────────────
    print("\nSeeding agent skills …")
    for skill in SKILLS:
        upload_skill(settings.skills_corpus_name, skill)
        time.sleep(1)

    print("""
Done! The knowledge base and skills corpus are ready.

Test with:
  curl -s -X POST http://localhost:8080/chat \\
    -H "Authorization: Bearer $(gcloud auth print-identity-token)" \\
    -H "Content-Type: application/json" \\
    -d '{"message": "How many PTO days do I get per year?"}' | jq
""")


if __name__ == "__main__":
    main()
