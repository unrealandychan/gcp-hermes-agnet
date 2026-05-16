#!/usr/bin/env python3
"""
scripts/demo/seed_bigquery.py

Creates the `hermes_demo` BigQuery dataset and seeds it with realistic sample
data for all Acme Corporation demo scenarios.

Tables created:
  hermes_demo.employees          — 25 Acme staff members
  hermes_demo.it_incidents       — 15 IT support incidents (Nov 2025 – May 2026)
  hermes_demo.sales_performance  — Monthly revenue by region × product (2025–2026)
  hermes_demo.pto_requests       — 20 PTO requests with approval status
  hermes_demo.project_tracker    — 10 engineering/cross-team projects

Usage:
    cd hermes-gcp
    python scripts/demo/seed_bigquery.py

Requirements:
    pip install google-cloud-bigquery
    gcloud auth application-default login
"""
from __future__ import annotations

import os
import sys

# Allow running from any directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from google.cloud import bigquery

DATASET = "hermes_demo"


def get_client() -> bigquery.Client:
    try:
        from config import get_settings  # noqa: PLC0415
        settings = get_settings()
        project = settings.gcp_project_id
    except Exception:  # noqa: BLE001
        project = os.environ.get("GCP_PROJECT_ID", "hermes-agent-prod")
    return bigquery.Client(project=project)


def ensure_dataset(client: bigquery.Client) -> None:
    dataset_ref = bigquery.DatasetReference(client.project, DATASET)
    try:
        client.get_dataset(dataset_ref)
        print(f"  Dataset {DATASET} already exists.")
    except Exception:  # noqa: BLE001
        ds = bigquery.Dataset(dataset_ref)
        ds.location = "US"
        ds.description = "Hermes PoC demo data — Acme Corporation"
        client.create_dataset(ds)
        print(f"  Created dataset {DATASET}.")


# ── Employees ──────────────────────────────────────────────────────────────────

EMPLOYEES_SCHEMA = [
    bigquery.SchemaField("employee_id", "STRING"),
    bigquery.SchemaField("full_name", "STRING"),
    bigquery.SchemaField("email", "STRING"),
    bigquery.SchemaField("department", "STRING"),
    bigquery.SchemaField("title", "STRING"),
    bigquery.SchemaField("manager_email", "STRING"),
    bigquery.SchemaField("start_date", "DATE"),
    bigquery.SchemaField("location", "STRING"),
    bigquery.SchemaField("level", "STRING"),
]

EMPLOYEES = [
    ("EMP001", "Alice Chen",      "alice.chen@acmecorp.com",    "Engineering", "Senior Software Engineer",   "bob.kim@acmecorp.com",       "2021-03-15", "San Francisco", "L5"),
    ("EMP002", "Bob Kim",         "bob.kim@acmecorp.com",       "Engineering", "Engineering Manager",        "carol.davis@acmecorp.com",   "2019-07-01", "San Francisco", "L7"),
    ("EMP003", "Carol Davis",     "carol.davis@acmecorp.com",   "Engineering", "VP of Engineering",          None,                         "2018-01-10", "San Francisco", "L9"),
    ("EMP004", "David Park",      "david.park@acmecorp.com",    "Engineering", "Software Engineer",          "bob.kim@acmecorp.com",       "2022-08-22", "Remote",        "L4"),
    ("EMP005", "Emma Wilson",     "emma.wilson@acmecorp.com",   "Engineering", "Senior Software Engineer",   "bob.kim@acmecorp.com",       "2020-11-01", "Seattle",       "L5"),
    ("EMP006", "Frank Garcia",    "frank.garcia@acmecorp.com",  "Engineering", "Staff Engineer",             "carol.davis@acmecorp.com",   "2017-05-15", "San Francisco", "L6"),
    ("EMP007", "Grace Lee",       "grace.lee@acmecorp.com",     "Engineering", "Software Engineer",          "bob.kim@acmecorp.com",       "2023-02-06", "New York",      "L3"),
    ("EMP008", "Henry Brown",     "henry.brown@acmecorp.com",   "Engineering", "DevOps Engineer",            "bob.kim@acmecorp.com",       "2021-09-13", "San Francisco", "L5"),
    ("EMP009", "Iris Martinez",   "iris.martinez@acmecorp.com", "Sales",       "Account Executive",          "james.taylor@acmecorp.com",  "2021-01-18", "Chicago",       "L4"),
    ("EMP010", "James Taylor",    "james.taylor@acmecorp.com",  "Sales",       "Sales Director",             "karen.white@acmecorp.com",   "2019-04-22", "Chicago",       "L7"),
    ("EMP011", "Karen White",     "karen.white@acmecorp.com",   "Sales",       "VP of Sales",                None,                         "2016-09-01", "Chicago",       "L9"),
    ("EMP012", "Liam Johnson",    "liam.johnson@acmecorp.com",  "Sales",       "Sales Development Rep",      "james.taylor@acmecorp.com",  "2023-06-12", "Remote",        "L2"),
    ("EMP013", "Mia Thompson",    "mia.thompson@acmecorp.com",  "Sales",       "Enterprise Account Manager", "james.taylor@acmecorp.com",  "2020-03-09", "Boston",        "L5"),
    ("EMP014", "Noah Anderson",   "noah.anderson@acmecorp.com", "HR",          "HR Business Partner",        "olivia.harris@acmecorp.com", "2020-07-20", "San Francisco", "L5"),
    ("EMP015", "Olivia Harris",   "olivia.harris@acmecorp.com", "HR",          "Head of HR",                 None,                         "2017-11-01", "San Francisco", "L8"),
    ("EMP016", "Peter Clark",     "peter.clark@acmecorp.com",   "HR",          "Recruiter",                  "olivia.harris@acmecorp.com", "2022-04-04", "Remote",        "L3"),
    ("EMP017", "Quinn Robinson",  "quinn.robinson@acmecorp.com","Marketing",   "Content Marketing Manager",  "rachel.lewis@acmecorp.com",  "2021-06-28", "New York",      "L5"),
    ("EMP018", "Rachel Lewis",    "rachel.lewis@acmecorp.com",  "Marketing",   "VP of Marketing",            None,                         "2018-08-15", "New York",      "L9"),
    ("EMP019", "Sam Walker",      "sam.walker@acmecorp.com",    "Marketing",   "Growth Marketing Specialist","rachel.lewis@acmecorp.com",  "2022-10-17", "Remote",        "L3"),
    ("EMP020", "Tina Young",      "tina.young@acmecorp.com",    "Marketing",   "Brand Designer",             "rachel.lewis@acmecorp.com",  "2023-01-30", "San Francisco", "L3"),
    ("EMP021", "Uma Scott",       "uma.scott@acmecorp.com",     "Finance",     "Senior Financial Analyst",   "victor.king@acmecorp.com",   "2020-02-10", "San Francisco", "L5"),
    ("EMP022", "Victor King",     "victor.king@acmecorp.com",   "Finance",     "CFO",                        None,                         "2015-03-01", "San Francisco", "L10"),
    ("EMP023", "Wendy Hill",      "wendy.hill@acmecorp.com",    "Finance",     "Financial Controller",       "victor.king@acmecorp.com",   "2018-07-16", "San Francisco", "L7"),
    ("EMP024", "Xavier Green",    "xavier.green@acmecorp.com",  "IT",          "IT Systems Administrator",   "yara.adams@acmecorp.com",    "2019-12-02", "San Francisco", "L4"),
    ("EMP025", "Yara Adams",      "yara.adams@acmecorp.com",    "IT",          "IT Manager",                 None,                         "2017-06-19", "San Francisco", "L7"),
]


# ── IT Incidents ───────────────────────────────────────────────────────────────

INCIDENTS_SCHEMA = [
    bigquery.SchemaField("incident_id",      "STRING"),
    bigquery.SchemaField("reported_date",    "DATE"),
    bigquery.SchemaField("severity",         "STRING"),
    bigquery.SchemaField("category",         "STRING"),
    bigquery.SchemaField("title",            "STRING"),
    bigquery.SchemaField("status",           "STRING"),
    bigquery.SchemaField("assignee",         "STRING"),
    bigquery.SchemaField("resolution_mins",  "INTEGER"),
    bigquery.SchemaField("resolution_notes", "STRING"),
]

IT_INCIDENTS = [
    ("INC-001","2025-11-05","P0","Network",  "Production API gateway down — 100% traffic loss","Resolved",   "xavier.green@acmecorp.com",  45,   "Misconfigured LB rule after routine maintenance"),
    ("INC-002","2025-11-12","P1","Security", "Suspicious login attempts on 3 employee accounts","Resolved",  "xavier.green@acmecorp.com",  120,  "Forced MFA re-enrolment; 2 accounts locked"),
    ("INC-003","2025-12-01","P2","Access",   "10 employees cannot access Salesforce after SSO update","Resolved","xavier.green@acmecorp.com",90, "SSO attribute mapping corrected in Okta"),
    ("INC-004","2025-12-15","P3","Hardware", "Laptop screen cracked — David Park","Resolved",               "xavier.green@acmecorp.com",  2880, "Replacement laptop ordered and delivered"),
    ("INC-005","2026-01-07","P2","Network",  "VPN intermittent disconnections for remote employees","Resolved","xavier.green@acmecorp.com", 240,  "VPN gateway upgraded to new firmware"),
    ("INC-006","2026-01-22","P1","Software", "CI/CD pipeline broken — no deployments possible","Resolved",  "henry.brown@acmecorp.com",   180,  "GitHub Actions runner Docker socket permissions"),
    ("INC-007","2026-02-03","P3","Access",   "Grace Lee cannot access prod read-only dashboard","Resolved",  "xavier.green@acmecorp.com",  480,  "IAM role missing from new hire provisioning template"),
    ("INC-008","2026-02-18","P2","Software", "Slack integration sending duplicate notifications to #alerts","Resolved","alice.chen@acmecorp.com",60,"Webhook registered twice in setup script"),
    ("INC-009","2026-03-04","P0","Security", "CVE-2026-1234 vulnerability in production container image","Resolved","frank.garcia@acmecorp.com",30,"Hotfix deployed with patched base image"),
    ("INC-010","2026-03-15","P2","Access",   "5 new Sales hires missing CRM access after batch onboarding","Resolved","xavier.green@acmecorp.com",360,"Onboarding script had wrong department filter"),
    ("INC-011","2026-04-01","P1","Network",  "Video conferencing degraded — New York office","Resolved",    "xavier.green@acmecorp.com",  720,  "ISP bandwidth upgrade ticket submitted and resolved"),
    ("INC-012","2026-04-20","P3","Hardware", "Finance floor printer offline","Resolved",                    "xavier.green@acmecorp.com",  1440, "Driver update required after OS patch"),
    ("INC-013","2026-05-02","P2","Software", "Analytics dashboard showing 24-hour stale data","In Progress","alice.chen@acmecorp.com",    None, "Investigating BigQuery scheduled query failure"),
    ("INC-014","2026-05-10","P1","Security", "Phishing email campaign targeting 3 employees","In Progress", "xavier.green@acmecorp.com",  None, "Email quarantined; investigating sender domain"),
    ("INC-015","2026-05-14","P3","Access",   "Emma Wilson cannot access Confluence space","Open",           "xavier.green@acmecorp.com",  None, "Awaiting space admin approval"),
]


# ── Sales Performance ──────────────────────────────────────────────────────────

SALES_SCHEMA = [
    bigquery.SchemaField("month",          "DATE"),
    bigquery.SchemaField("region",         "STRING"),
    bigquery.SchemaField("product",        "STRING"),
    bigquery.SchemaField("revenue_usd",    "FLOAT"),
    bigquery.SchemaField("deals_closed",   "INTEGER"),
    bigquery.SchemaField("quota_usd",      "FLOAT"),
]


def generate_sales_data() -> list[tuple]:
    """Generate 12 months × 4 regions × 3 products of sales data."""
    import random  # noqa: PLC0415
    random.seed(42)

    regions = ["North America", "EMEA", "APAC", "LATAM"]
    products = ["Enterprise License", "Professional Services", "Support Contract"]

    # Base monthly revenue by region × product
    base = {
        ("North America", "Enterprise License"):   450_000,
        ("North America", "Professional Services"): 120_000,
        ("North America", "Support Contract"):      80_000,
        ("EMEA",          "Enterprise License"):   280_000,
        ("EMEA",          "Professional Services"):  90_000,
        ("EMEA",          "Support Contract"):       60_000,
        ("APAC",          "Enterprise License"):   180_000,
        ("APAC",          "Professional Services"):  50_000,
        ("APAC",          "Support Contract"):       35_000,
        ("LATAM",         "Enterprise License"):    60_000,
        ("LATAM",         "Professional Services"):  20_000,
        ("LATAM",         "Support Contract"):       15_000,
    }
    quota_multiplier = 1.1  # quota is 10% above base

    rows = []
    for month_num in range(1, 13):
        year = 2025 if month_num <= 12 else 2026
        actual_month = month_num if month_num <= 12 else month_num - 12
        month_str = f"{'2025' if month_num <= 6 else '2025'}-{actual_month:02d}-01"
        # Recalculate: Jan 2025 to Dec 2025, then Jan-May 2026
        if month_num <= 12:
            year = 2025
            month_str = f"{year}-{month_num:02d}-01"

        for region in regions:
            for product in products:
                b = base[(region, product)]
                # Add seasonal trend (Q4 bump) and random noise
                seasonal = 1.0 + (0.25 if month_num in (10, 11, 12) else 0.0)
                growth = 1.0 + (month_num - 1) * 0.015  # 1.5% monthly growth
                revenue = b * seasonal * growth * random.uniform(0.88, 1.12)
                quota = b * quota_multiplier * seasonal
                deals = max(1, int(revenue / (b * 0.15) + random.uniform(-2, 2)))
                rows.append((month_str, region, product, round(revenue, 2), deals, round(quota, 2)))

    return rows


# ── PTO Requests ───────────────────────────────────────────────────────────────

PTO_SCHEMA = [
    bigquery.SchemaField("request_id",    "STRING"),
    bigquery.SchemaField("employee_id",   "STRING"),
    bigquery.SchemaField("employee_email","STRING"),
    bigquery.SchemaField("start_date",    "DATE"),
    bigquery.SchemaField("end_date",      "DATE"),
    bigquery.SchemaField("days",          "INTEGER"),
    bigquery.SchemaField("status",        "STRING"),
    bigquery.SchemaField("reason",        "STRING"),
    bigquery.SchemaField("approved_by",   "STRING"),
]

PTO_REQUESTS = [
    ("PTO-001","EMP001","alice.chen@acmecorp.com",    "2026-01-06","2026-01-09",4,"Approved","New Year break","noah.anderson@acmecorp.com"),
    ("PTO-002","EMP004","david.park@acmecorp.com",    "2026-01-19","2026-01-23",5,"Approved","Family vacation","noah.anderson@acmecorp.com"),
    ("PTO-003","EMP007","grace.lee@acmecorp.com",     "2026-02-09","2026-02-13",5,"Approved","Winter holiday","noah.anderson@acmecorp.com"),
    ("PTO-004","EMP009","iris.martinez@acmecorp.com", "2026-02-16","2026-02-20",5,"Approved","Personal travel","noah.anderson@acmecorp.com"),
    ("PTO-005","EMP005","emma.wilson@acmecorp.com",   "2026-02-23","2026-02-27",5,"Approved","Ski trip","noah.anderson@acmecorp.com"),
    ("PTO-006","EMP012","liam.johnson@acmecorp.com",  "2026-03-02","2026-03-06",5,"Approved","Spring break","noah.anderson@acmecorp.com"),
    ("PTO-007","EMP017","quinn.robinson@acmecorp.com","2026-03-09","2026-03-13",5,"Approved","Conference (personal)","noah.anderson@acmecorp.com"),
    ("PTO-008","EMP008","henry.brown@acmecorp.com",   "2026-03-23","2026-03-27",5,"Approved","Vacation","noah.anderson@acmecorp.com"),
    ("PTO-009","EMP013","mia.thompson@acmecorp.com",  "2026-04-06","2026-04-10",5,"Approved","Spring vacation","noah.anderson@acmecorp.com"),
    ("PTO-010","EMP016","peter.clark@acmecorp.com",   "2026-04-13","2026-04-17",5,"Approved","Family event","noah.anderson@acmecorp.com"),
    ("PTO-011","EMP019","sam.walker@acmecorp.com",    "2026-04-20","2026-04-24",5,"Approved","Travel","noah.anderson@acmecorp.com"),
    ("PTO-012","EMP001","alice.chen@acmecorp.com",    "2026-05-04","2026-05-08",5,"Approved","Wedding","noah.anderson@acmecorp.com"),
    ("PTO-013","EMP004","david.park@acmecorp.com",    "2026-05-18","2026-05-22",5,"Pending", "Graduation ceremony","noah.anderson@acmecorp.com"),
    ("PTO-014","EMP007","grace.lee@acmecorp.com",     "2026-06-01","2026-06-05",5,"Pending", "International trip","noah.anderson@acmecorp.com"),
    ("PTO-015","EMP020","tina.young@acmecorp.com",    "2026-06-08","2026-06-12",5,"Pending", "Beach vacation","noah.anderson@acmecorp.com"),
    ("PTO-016","EMP009","iris.martinez@acmecorp.com", "2026-07-06","2026-07-17",10,"Pending","Summer vacation","noah.anderson@acmecorp.com"),
    ("PTO-017","EMP002","bob.kim@acmecorp.com",       "2026-07-27","2026-07-31",5,"Pending", "Family holiday","noah.anderson@acmecorp.com"),
    ("PTO-018","EMP005","emma.wilson@acmecorp.com",   "2026-08-03","2026-08-14",10,"Pending","Sabbatical travel","noah.anderson@acmecorp.com"),
    ("PTO-019","EMP021","uma.scott@acmecorp.com",     "2025-12-22","2026-01-02",10,"Approved","Christmas holidays","noah.anderson@acmecorp.com"),
    ("PTO-020","EMP006","frank.garcia@acmecorp.com",  "2025-12-29","2026-01-02",5,"Approved", "Year-end break","noah.anderson@acmecorp.com"),
]


# ── Project Tracker ────────────────────────────────────────────────────────────

PROJECTS_SCHEMA = [
    bigquery.SchemaField("project_id",   "STRING"),
    bigquery.SchemaField("name",         "STRING"),
    bigquery.SchemaField("owner_email",  "STRING"),
    bigquery.SchemaField("department",   "STRING"),
    bigquery.SchemaField("status",       "STRING"),
    bigquery.SchemaField("priority",     "STRING"),
    bigquery.SchemaField("start_date",   "DATE"),
    bigquery.SchemaField("due_date",     "DATE"),
    bigquery.SchemaField("completion_pct","INTEGER"),
    bigquery.SchemaField("description",  "STRING"),
]

PROJECTS = [
    ("PRJ-001","Hermes AI Agent Platform",        "bob.kim@acmecorp.com",       "Engineering","In Progress","High",  "2026-01-01","2026-06-30",70, "Enterprise AI agent with multi-model LLM support and GCP integration"),
    ("PRJ-002","CRM Data Migration",              "mia.thompson@acmecorp.com",  "Sales",      "In Progress","High",  "2026-02-01","2026-05-31",55, "Migrate legacy CRM data to Salesforce with enriched account data"),
    ("PRJ-003","Employee Onboarding Automation",  "noah.anderson@acmecorp.com", "HR",         "In Progress","Medium","2026-01-15","2026-04-30",80, "Automate Day 1 provisioning (Okta, GitHub, Slack) via HR triggers"),
    ("PRJ-004","Analytics Dashboard v2",          "alice.chen@acmecorp.com",    "Engineering","In Progress","Medium","2026-02-15","2026-06-15",45, "Rebuild analytics dashboard with real-time BigQuery data"),
    ("PRJ-005","Zero-Trust Network Upgrade",      "yara.adams@acmecorp.com",    "IT",         "Planning",   "High",  "2026-05-01","2026-09-30",10, "Replace VPN with BeyondCorp zero-trust access for all internal tools"),
    ("PRJ-006","Q2 Marketing Campaign",           "quinn.robinson@acmecorp.com","Marketing",  "In Progress","Medium","2026-04-01","2026-06-30",60, "Demand-gen campaign targeting mid-market accounts in EMEA"),
    ("PRJ-007","ISO 27001 Certification",         "frank.garcia@acmecorp.com",  "Engineering","In Progress","High",  "2025-10-01","2026-07-31",65, "Security certification audit — GRC tooling and policy review"),
    ("PRJ-008","2026 Budget Planning Tool",       "uma.scott@acmecorp.com",     "Finance",    "Completed",  "Medium","2025-11-01","2026-02-28",100,"FY2026 budgeting spreadsheet + automated forecast model"),
    ("PRJ-009","Developer Platform Self-Service", "henry.brown@acmecorp.com",   "Engineering","Planning",   "Medium","2026-06-01","2026-10-31",5,  "Internal developer portal: service catalog, provisioning, docs"),
    ("PRJ-010","APAC Expansion Readiness",        "karen.white@acmecorp.com",   "Sales",      "Planning",   "High",  "2026-07-01","2026-12-31",0,  "GTM strategy and hiring plan for Singapore and Australia markets"),
]


# ── Seeding helpers ────────────────────────────────────────────────────────────


def seed_table(
    client: bigquery.Client,
    name: str,
    schema: list[bigquery.SchemaField],
    rows: list[tuple],
) -> None:
    table_id = f"{client.project}.{DATASET}.{name}"
    table = bigquery.Table(table_id, schema=schema)
    table.description = f"Hermes demo: {name}"

    # Drop and recreate for idempotent runs
    client.delete_table(table_id, not_found_ok=True)
    table = client.create_table(table)

    # Convert tuples to dicts
    field_names = [f.name for f in schema]
    dicts = [dict(zip(field_names, row)) for row in rows]

    errors = client.insert_rows_json(table, dicts)
    if errors:
        print(f"  ✗  {name}: {errors}")
    else:
        print(f"  ✓  {name}: {len(dicts)} rows inserted.")


def main() -> None:
    print("Connecting to BigQuery …")
    client = get_client()
    print(f"Project: {client.project}")

    print(f"\nEnsuring dataset '{DATASET}' …")
    ensure_dataset(client)

    print("\nSeeding tables …")
    seed_table(client, "employees",         EMPLOYEES_SCHEMA, EMPLOYEES)
    seed_table(client, "it_incidents",      INCIDENTS_SCHEMA, IT_INCIDENTS)
    seed_table(client, "sales_performance", SALES_SCHEMA,     generate_sales_data())
    seed_table(client, "pto_requests",      PTO_SCHEMA,       PTO_REQUESTS)
    seed_table(client, "project_tracker",   PROJECTS_SCHEMA,  PROJECTS)

    print("\nDone! Query your data:\n")
    print(f"  SELECT * FROM `{client.project}.{DATASET}.employees` LIMIT 5;")
    print("  SELECT department, COUNT(*) as headcount")
    print(f"    FROM `{client.project}.{DATASET}.employees`")
    print("    GROUP BY department ORDER BY headcount DESC;")
    print()


if __name__ == "__main__":
    main()
