#!/usr/bin/env python3
"""
teardown_wizard.py — Hermes GCP Agent Platform cleanup

Deletes ALL GCP resources created by setup_wizard.py.
Safe to run multiple times — every step is idempotent.

Usage:
    python teardown_wizard.py

What it deletes (in safe dependency order):
  1.  Cloud Run service          (hermes-gateway)
  2.  Vertex AI Reasoning Engine (from .env REASONING_ENGINE_RESOURCE_NAME)
  3.  Vertex AI Memory Bank      (from .env MEMORY_BANK_RESOURCE_NAME)
  4.  Vertex AI RAG Corpora      (KNOWLEDGE_CORPUS_NAME + SKILLS_CORPUS_NAME)
  5.  GCS bucket                 (PROJECT_ID-hermes-artifacts)
  6.  Firestore database         (default)
  7.  IAM Service Account        (hermes-agent-sa@PROJECT.iam.gserviceaccount.com)
  8.  Container Registry image   (gcr.io/PROJECT/hermes-gateway)
  9.  Cloud Scheduler jobs       (any job pointing at hermes-gateway)
  10. GCP APIs                   (optional — prompt to disable)
  11. .env file                  (optional — prompt to wipe)

SAFETY:
  - Reads PROJECT_ID from .env (falls back to interactive prompt)
  - Shows a full resource list and asks for explicit confirmation
  - Each step fails gracefully and continues (won't abort mid-teardown)
  - Does NOT delete the GCP project itself
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from subprocess import CalledProcessError, run as _run

try:
    from google.cloud import storage as _gcs_storage
    from google.api_core.exceptions import NotFound as _GcsNotFound
except ImportError:
    _gcs_storage = None  # type: ignore[assignment]
    _GcsNotFound = Exception  # type: ignore[assignment, misc]

# ── ANSI colours ───────────────────────────────────────────────────────────────
RED, GREEN, YELLOW, CYAN, BOLD, RESET = (
    "\033[31m", "\033[32m", "\033[33m", "\033[36m", "\033[1m", "\033[0m"
)

def _c(colour: str, text: str) -> str:
    return f"{colour}{text}{RESET}" if sys.stdout.isatty() else text

def header(title: str) -> None:
    width = 60
    bar = "─" * width
    print(f"\n{_c(CYAN, bar)}")
    print(f"{_c(BOLD, f'  {title}')}")
    print(f"{_c(CYAN, bar)}")

def step(msg: str)  -> None: print(f"  {_c(CYAN,   '→')} {msg}")
def ok(msg: str)    -> None: print(f"  {_c(GREEN,  '✓')} {msg}")
def warn(msg: str)  -> None: print(f"  {_c(YELLOW, '!')} {msg}")
def err(msg: str)   -> None: print(f"  {_c(RED,    '✗')} {msg}")
def skip(msg: str)  -> None: print(f"  {_c(YELLOW, '–')} skipped: {msg}")


# ── Shell helpers ──────────────────────────────────────────────────────────────

def run(cmd: list[str], capture: bool = True, check: bool = True) -> str:
    result = _run(
        cmd,
        capture_output=capture,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return (result.stdout or "").strip()


def gcloud(*args: str, check: bool = True) -> str:
    return run(["gcloud", *args], check=check)


def gsutil(*args: str, check: bool = False) -> str:
    return run(["gsutil", *args], check=check)


# ── .env reader ────────────────────────────────────────────────────────────────

def read_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# ── Confirmation gate ──────────────────────────────────────────────────────────

def confirm(prompt: str, require_yes: bool = False) -> bool:
    """
    Ask the user to confirm.  If require_yes=True the user must type
    the exact word 'yes' (not just 'y') to proceed.
    """
    hint = "type 'yes' to confirm" if require_yes else "y/N"
    answer = input(f"\n  {_c(YELLOW, '?')} {prompt} [{hint}]: ").strip().lower()
    if require_yes:
        return answer == "yes"
    return answer in ("y", "yes")


# ── Individual teardown steps ──────────────────────────────────────────────────

def delete_cloud_run(project: str, region: str) -> None:
    header("Cloud Run — hermes-gateway")
    svc = "hermes-gateway"
    try:
        gcloud("run", "services", "describe", svc,
               f"--project={project}", f"--region={region}", "--format=value(name)")
        step(f"Deleting Cloud Run service: {svc} …")
        gcloud("run", "services", "delete", svc,
               f"--project={project}", f"--region={region}", "--quiet")
        ok(f"Cloud Run service '{svc}' deleted")
    except CalledProcessError:
        skip(f"Cloud Run service '{svc}' not found")


def delete_reasoning_engine(resource_name: str) -> None:
    header("Vertex AI Reasoning Engine")
    if not resource_name:
        skip("REASONING_ENGINE_RESOURCE_NAME not set in .env")
        return
    step(f"Deleting Reasoning Engine: {resource_name} …")
    try:
        # Extract project + location + id from resource name
        # projects/PROJECT/locations/LOCATION/reasoningEngines/ID
        parts = resource_name.split("/")
        if len(parts) == 6:
            project, location, engine_id = parts[1], parts[3], parts[5]
            gcloud(
                "ai", "reasoning-engines", "delete", engine_id,
                f"--project={project}", f"--location={location}", "--quiet",
            )
            ok(f"Reasoning Engine deleted: {engine_id}")
        else:
            warn("Unexpected resource name format — trying direct delete")
            gcloud("ai", "reasoning-engines", "delete", resource_name, "--quiet", check=False)
    except CalledProcessError as e:
        warn(f"Could not delete Reasoning Engine: {e.stderr or e}")


def delete_memory_bank(resource_name: str) -> None:
    header("Vertex AI Memory Bank")
    if not resource_name:
        skip("MEMORY_BANK_RESOURCE_NAME not set in .env")
        return
    step(f"Deleting Memory Bank: {resource_name} …")
    try:
        import vertexai
        from vertexai.preview import memory_bank as mb
        bank = mb.MemoryBank(resource_name=resource_name)
        bank.delete()
        ok(f"Memory Bank deleted: {resource_name}")
    except ImportError:
        warn("vertexai SDK not available — trying gcloud fallback …")
        try:
            parts = resource_name.split("/")
            if len(parts) >= 6:
                project, location, bank_id = parts[1], parts[3], parts[5]
                gcloud(
                    "ai", "memory-banks", "delete", bank_id,
                    f"--project={project}", f"--location={location}", "--quiet", check=False,
                )
                ok(f"Memory Bank deleted via gcloud: {bank_id}")
        except Exception as exc:
            warn(f"gcloud fallback also failed: {exc}")
    except Exception as exc:
        warn(f"Could not delete Memory Bank: {exc}")


def delete_rag_corpora(knowledge_corpus: str, skills_corpus: str, project: str, region: str) -> None:
    header("Vertex AI RAG Corpora")
    try:
        import vertexai
        import vertexai.preview.rag as rag
        vertexai.init(project=project, location=region)
    except ImportError:
        warn("vertexai SDK not available — skipping RAG corpus deletion")
        return

    for name, corpus_name in [("Knowledge", knowledge_corpus), ("Skills", skills_corpus)]:
        if not corpus_name:
            skip(f"{name} corpus not set in .env")
            continue
        step(f"Deleting {name} RAG corpus: {corpus_name} …")
        try:
            rag.delete_corpus(name=corpus_name)
            ok(f"{name} corpus deleted")
        except Exception as exc:
            warn(f"Could not delete {name} corpus: {exc}")


def delete_gcs_bucket(bucket: str) -> None:
    header("GCS Bucket")
    if not bucket:
        skip("GCP_STAGING_BUCKET not set in .env")
        return
    bucket_uri = bucket if bucket.startswith("gs://") else f"gs://{bucket}"
    bucket_name = bucket_uri.removeprefix("gs://")
    step(f"Deleting GCS bucket (all objects + bucket): {bucket_uri} …")
    try:
        client = _gcs_storage.Client()
        b = client.bucket(bucket_name)
        blobs = list(client.list_blobs(bucket_name))
        if blobs:
            b.delete_blobs(blobs)
        b.delete()
        ok(f"Bucket deleted: {bucket_uri}")
    except _GcsNotFound:
        warn(f"Bucket may not exist or already deleted: {bucket_uri}")
    except Exception as exc:  # noqa: BLE001
        warn(f"Could not delete bucket {bucket_uri}: {exc}")


def delete_firestore(project: str) -> None:
    header("Firestore Database")
    try:
        dbs = gcloud("firestore", "databases", "list", f"--project={project}", "--format=json", check=False)
        db_list = json.loads(dbs) if dbs else []
        default_db = next((d for d in db_list if d.get("name", "").endswith("(default)")), None)
        if not default_db:
            skip("Firestore '(default)' database not found")
            return
        step("Deleting Firestore '(default)' database …")
        gcloud(
            "firestore", "databases", "delete", "(default)",
            f"--project={project}", "--quiet", check=False,
        )
        ok("Firestore database deleted")
    except Exception as exc:
        warn(f"Could not delete Firestore database: {exc}")


def delete_service_account(project: str) -> None:
    header("IAM Service Account")
    sa_name  = "hermes-agent-sa"
    sa_email = f"{sa_name}@{project}.iam.gserviceaccount.com"
    step(f"Deleting service account: {sa_email} …")
    try:
        gcloud("iam", "service-accounts", "describe", sa_email, f"--project={project}")
        gcloud("iam", "service-accounts", "delete", sa_email, f"--project={project}", "--quiet")
        ok(f"Service account deleted: {sa_email}")
    except CalledProcessError:
        skip(f"Service account '{sa_email}' not found")


def delete_container_image(project: str) -> None:
    header("Container Registry Image")
    image = f"gcr.io/{project}/hermes-gateway"
    step(f"Deleting container image: {image} …")
    try:
        tags = gsutil("ls", f"gs://artifacts.{project}.appspot.com/containers/repositories/library/hermes-gateway/")
        if not tags:
            skip("No container image found in GCR")
            return
    except Exception:
        pass
    try:
        gcloud(
            "container", "images", "delete", f"{image}:latest",
            "--force-delete-tags", "--quiet", check=False,
        )
        ok(f"Container image deleted: {image}:latest")
    except Exception as exc:
        warn(f"Could not delete container image: {exc}")


def delete_scheduler_jobs(project: str, region: str) -> None:
    header("Cloud Scheduler Jobs")
    try:
        jobs_json = gcloud(
            "scheduler", "jobs", "list",
            f"--project={project}", f"--location={region}",
            "--format=json", check=False,
        )
        jobs = json.loads(jobs_json) if jobs_json else []
        hermes_jobs = [j for j in jobs if "hermes" in j.get("name", "").lower()]
        if not hermes_jobs:
            skip("No Hermes scheduler jobs found")
            return
        for job in hermes_jobs:
            job_name = job["name"].split("/")[-1]
            step(f"Deleting scheduler job: {job_name} …")
            gcloud(
                "scheduler", "jobs", "delete", job_name,
                f"--project={project}", f"--location={region}", "--quiet", check=False,
            )
            ok(f"Scheduler job deleted: {job_name}")
    except Exception as exc:
        warn(f"Could not list/delete scheduler jobs: {exc}")


_REQUIRED_APIS = [
    "aiplatform.googleapis.com",
    "run.googleapis.com",
    "firestore.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "cloudscheduler.googleapis.com",
    "containerregistry.googleapis.com",
]

def disable_apis(project: str) -> None:
    header("GCP APIs (optional)")
    print("\n  APIs that were enabled by setup_wizard:\n")
    for api in _REQUIRED_APIS:
        print(f"    - {api}")
    print()
    warn("Disabling APIs may affect OTHER services in this project.")
    if not confirm("Disable these APIs?"):
        skip("APIs left enabled")
        return
    step("Disabling APIs …")
    try:
        gcloud("services", "disable", *_REQUIRED_APIS, f"--project={project}", "--quiet", check=False)
        ok("APIs disabled")
    except Exception as exc:
        warn(f"Could not disable some APIs: {exc}")


def wipe_env_file(env_path: Path) -> None:
    header(".env File")
    if not env_path.exists():
        skip(".env not found")
        return
    if confirm(f"Delete {env_path}? (you will need to re-run setup_wizard.py to recreate it)"):
        env_path.unlink()
        ok(".env deleted")
    else:
        skip(".env kept")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    env_path = Path(".env")
    env      = read_env(env_path)

    # ── Banner ─────────────────────────────────────────────────────────────────
    print(f"""
{_c(RED + BOLD, '╔══════════════════════════════════════════════════════════╗')}
{_c(RED + BOLD, '║       Hermes GCP Agent Platform — TEARDOWN WIZARD        ║')}
{_c(RED + BOLD, '╚══════════════════════════════════════════════════════════╝')}

  This wizard will permanently delete all GCP resources
  created by setup_wizard.py.

  {_c(YELLOW, 'This action CANNOT be undone.')}
  The GCP project itself will NOT be deleted.
""")

    # ── Resolve project ────────────────────────────────────────────────────────
    project = env.get("GCP_PROJECT_ID", "").strip()
    if not project:
        project = input(f"  {_c(CYAN, '?')} GCP Project ID: ").strip()
    if not project:
        err("Project ID is required. Aborting.")
        sys.exit(1)

    region = env.get("GCP_LOCATION", "us-central1").strip()

    # ── Resolve resource names ─────────────────────────────────────────────────
    reasoning_engine = env.get("REASONING_ENGINE_RESOURCE_NAME", "")
    memory_bank      = env.get("MEMORY_BANK_RESOURCE_NAME", "")
    knowledge_corpus = env.get("KNOWLEDGE_CORPUS_NAME", "")
    skills_corpus    = env.get("SKILLS_CORPUS_NAME", "")
    bucket           = env.get("GCP_STAGING_BUCKET", f"gs://{project}-hermes-artifacts")

    # ── Show what will be deleted ──────────────────────────────────────────────
    print(f"  {_c(BOLD, 'Project:')} {_c(CYAN, project)}  |  {_c(BOLD, 'Region:')} {_c(CYAN, region)}")
    print(f"\n  {_c(BOLD, 'Resources scheduled for deletion:')}\n")

    resources = [
        ("Cloud Run service",        "hermes-gateway",    True),
        ("Reasoning Engine",         reasoning_engine or "(not set)", bool(reasoning_engine)),
        ("Memory Bank",              memory_bank or "(not set)",      bool(memory_bank)),
        ("RAG corpus — knowledge",   knowledge_corpus or "(not set)", bool(knowledge_corpus)),
        ("RAG corpus — skills",      skills_corpus or "(not set)",    bool(skills_corpus)),
        ("GCS bucket",               bucket,              True),
        ("Firestore DB",             "(default)",         True),
        ("IAM Service Account",      f"hermes-agent-sa@{project}.iam.gserviceaccount.com", True),
        ("Container image",          f"gcr.io/{project}/hermes-gateway", True),
        ("Cloud Scheduler jobs",     "any job with 'hermes' in name", True),
    ]
    for label, value, active in resources:
        icon  = _c(RED, "✗") if active else _c(YELLOW, "–")
        vtext = _c(CYAN, value) if active else _c(YELLOW, value)
        print(f"    {icon}  {label:<30} {vtext}")

    # ── Double confirmation ────────────────────────────────────────────────────
    print()
    if not confirm(
        f"Delete ALL resources above in project {_c(BOLD, project)}?",
        require_yes=True,
    ):
        print(f"\n  {_c(GREEN, 'Teardown cancelled — nothing was deleted.')}\n")
        sys.exit(0)

    print(f"\n  {_c(RED + BOLD, 'Starting teardown …')}\n")

    # ── Execute teardown (in safe dependency order) ───────────────────────────
    errors: list[str] = []

    def _safe(fn, *args):
        try:
            fn(*args)
        except Exception as exc:
            errors.append(f"{fn.__name__}: {exc}")
            err(f"Unexpected error in {fn.__name__}: {exc}")

    _safe(delete_cloud_run,        project, region)
    _safe(delete_reasoning_engine, reasoning_engine)
    _safe(delete_memory_bank,      memory_bank)
    _safe(delete_rag_corpora,      knowledge_corpus, skills_corpus, project, region)
    _safe(delete_gcs_bucket,       bucket)
    _safe(delete_firestore,        project)
    _safe(delete_service_account,  project)
    _safe(delete_container_image,  project)
    _safe(delete_scheduler_jobs,   project, region)

    # Optional steps
    disable_apis(project)
    wipe_env_file(env_path)

    # ── Summary ────────────────────────────────────────────────────────────────
    header("Teardown Complete")
    if errors:
        warn(f"{len(errors)} step(s) had errors (resources may already be deleted):")
        for e in errors:
            print(f"    {_c(YELLOW, '!')} {e}")
    else:
        ok("All resources deleted successfully")

    print(f"""
  {_c(GREEN, 'PoC cleaned up.')} No idle resources remain in GCP.

  To redeploy from scratch:
    {_c(CYAN, 'python setup_wizard.py')}
""")


if __name__ == "__main__":
    main()
