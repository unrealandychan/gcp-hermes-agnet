#!/usr/bin/env python3
"""
setup_wizard.py — Hermes GCP Agent Platform interactive setup

Run once to go from zero → running agent:

    python setup_wizard.py

What it does:
  1. Pre-flight: checks gcloud, Python, Node, billing
  2. Asks 3 questions (project ID, region, deploy target)
  3. Enables GCP APIs, creates bucket + SA + Firestore
  4. Creates RAG corpora, writes resource names into .env
  5. Deploys agent to Vertex AI Reasoning Engine
  6. Deploys gateway to Cloud Run  (optional)
  7. Prints a single curl command to test everything works

Requirements: gcloud CLI authenticated as project owner.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

# ── Colours ──────────────────────────────────────────────────────────────────
RESET = "\033[0m"
BOLD  = "\033[1m"
GREEN = "\033[32m"
YELLOW= "\033[33m"
CYAN  = "\033[36m"
RED   = "\033[31m"
DIM   = "\033[2m"

def _c(colour: str, text: str) -> str:
    return f"{colour}{text}{RESET}"

def ok(msg: str)     -> None: print(_c(GREEN,  f"  ✓ {msg}"))
def warn(msg: str)   -> None: print(_c(YELLOW, f"  ⚠ {msg}"))
def err(msg: str)    -> None: print(_c(RED,    f"  ✗ {msg}"))
def step(msg: str)   -> None: print(_c(CYAN,   f"\n▶ {msg}"))
def header(msg: str) -> None:
    print(_c(BOLD + CYAN, f"\n{'═'*60}\n  {msg}\n{'═'*60}"))
def dim(msg: str)    -> None: print(_c(DIM, f"    {msg}"))


# ── Helpers ───────────────────────────────────────────────────────────────────
def run(
    cmd: list[str],
    capture: bool = True,
    check: bool = True,
    env: dict | None = None,
) -> subprocess.CompletedProcess:
    merged_env = {**os.environ, **(env or {})}
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=check,
        env=merged_env,
    )


def gcloud(*args: str, capture: bool = True, check: bool = True) -> str:
    result = run(["gcloud", *args], capture=capture, check=check)
    return result.stdout.strip()


def ask(question: str, default: str = "") -> str:
    prompt = f"\n  {_c(BOLD, question)}"
    if default:
        prompt += f"  {_c(DIM, f'[{default}]')}"
    prompt += "\n  › "
    while True:
        answer = input(prompt).strip()
        if answer:
            return answer
        if default:
            return default
        print("  (required — please enter a value)")


def ask_yn(question: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    prompt = f"\n  {_c(BOLD, question)}  {_c(DIM, f'[{hint}]')}\n  › "
    answer = input(prompt).strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def write_env(path: Path, key: str, value: str) -> None:
    """Upsert KEY=value in an .env file."""
    text = path.read_text() if path.exists() else ""
    pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.MULTILINE)
    new_line = f"{key}={value}"
    if pattern.search(text):
        text = pattern.sub(new_line, text)
    else:
        text = text.rstrip("\n") + f"\n{new_line}\n"
    path.write_text(text)


def read_env_value(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith(key + "="):
            value = line[len(key) + 1:].strip()
            # Strip inline comments and ignore placeholder values
            if "#" in value:
                value = value[:value.index("#")].strip()
            return value
    return ""


# ── Pre-flight checks ─────────────────────────────────────────────────────────
def preflight() -> None:
    header("Pre-flight checks")
    errors: list[str] = []

    # Python version
    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 11):
        ok(f"Python {major}.{minor}")
    else:
        err(f"Python {major}.{minor} — need 3.11+")
        errors.append("Upgrade Python to 3.11+")

    # gcloud CLI
    if shutil.which("gcloud"):
        try:
            account = gcloud("config", "get-value", "account")
            ok(f"gcloud authenticated as {account}")
        except subprocess.CalledProcessError:
            err("gcloud not authenticated")
            errors.append("Run: gcloud auth login")
    else:
        err("gcloud CLI not found")
        errors.append("Install gcloud: https://cloud.google.com/sdk/docs/install")

    # Node.js (optional — only needed for web UI)
    if shutil.which("node"):
        node_ver = run(["node", "--version"]).stdout.strip().lstrip("v")
        major_node = int(node_ver.split(".")[0])
        if major_node >= 18:
            ok(f"Node.js v{node_ver}")
        else:
            warn(f"Node.js v{node_ver} — recommend v20+ for Web UI")
    else:
        warn("Node.js not found — Web UI won't be available (gateway + API still work)")

    # Docker (optional — needed for Cloud Run deploy)
    if shutil.which("docker"):
        ok("Docker found")
    else:
        warn("Docker not found — Cloud Run deploy will be skipped")

    if errors:
        print()
        for e in errors:
            err(e)
        print()
        sys.exit(1)


# ── Configuration wizard ──────────────────────────────────────────────────────
def gather_config(env_path: Path) -> dict[str, str]:
    header("Configuration")
    print(textwrap.dedent("""
    Answer 3 questions and the wizard handles the rest.
    Press Enter to accept the default value shown in [brackets].
    """))

    existing_project = read_env_value(env_path, "GCP_PROJECT_ID") or ""
    project_id = ask(
        "GCP Project ID  (must already exist with billing enabled)",
        default=existing_project or "my-hermes-project",
    )

    existing_region = read_env_value(env_path, "GCP_LOCATION") or ""
    region = ask(
        "GCP Region",
        default=existing_region or "us-central1",
    )

    print(textwrap.dedent(f"""
    {_c(BOLD, 'Deploy target')}
      {_c(GREEN, '1')}  Local only   — gateway runs on your machine (fastest, no Cloud Run needed)
      {_c(GREEN, '2')}  Cloud Run    — deploy gateway to production Cloud Run (requires Docker)
    """))
    target_input = ask("Choose deploy target", default="1")
    deploy_cloud_run = target_input.strip() == "2"

    want_demo_data = ask_yn(
        "Seed demo data? (sample BigQuery tables + knowledge docs for testing)",
        default=True,
    )

    bucket = f"gs://{project_id}-hermes-artifacts"

    return {
        "project_id": project_id,
        "region": region,
        "bucket": bucket,
        "deploy_cloud_run": deploy_cloud_run,
        "want_demo_data": want_demo_data,
    }


# ── GCP bootstrap ─────────────────────────────────────────────────────────────
_REQUIRED_APIS = [
    "aiplatform.googleapis.com",
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "secretmanager.googleapis.com",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "iam.googleapis.com",
    "firestore.googleapis.com",
    "cloudscheduler.googleapis.com",
    "modelarmor.googleapis.com",
    "cloudtrace.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "vectorsearch.googleapis.com",
]

_SA_ROLES = [
    "roles/aiplatform.user",
    "roles/bigquery.dataViewer",
    "roles/bigquery.jobUser",
    "roles/storage.objectAdmin",
    "roles/secretmanager.secretAccessor",
    "roles/logging.logWriter",
    "roles/datastore.user",
    "roles/cloudscheduler.admin",
    "roles/run.invoker",
]


def bootstrap_gcp(cfg: dict[str, str]) -> None:
    project   = cfg["project_id"]
    region    = cfg["region"]
    bucket    = cfg["bucket"]
    sa_name   = "hermes-agent-sa"
    sa_email  = f"{sa_name}@{project}.iam.gserviceaccount.com"

    header("GCP Bootstrap")

    # ── Set project ──────────────────────────────────────────────────────────
    step("Setting active project")
    gcloud("config", "set", "project", project)
    ok(f"Active project: {project}")

    # ── Enable APIs ──────────────────────────────────────────────────────────
    step("Enabling required APIs (this can take ~2 min on first run)")
    gcloud("services", "enable", *_REQUIRED_APIS, f"--project={project}")
    ok(f"Enabled {len(_REQUIRED_APIS)} APIs")

    # ── GCS bucket ──────────────────────────────────────────────────────────
    step(f"Creating staging bucket {bucket}")
    bucket_name = bucket.removeprefix("gs://")
    try:
        run(["gsutil", "ls", "-b", bucket], check=True)
        ok("Bucket already exists — skipping")
    except subprocess.CalledProcessError:
        run(["gsutil", "mb", "-p", project, "-l", region, bucket], check=True)
        run(["gsutil", "versioning", "set", "on", bucket], check=True)
        ok(f"Created {bucket}")

    # ── Service account ──────────────────────────────────────────────────────
    step(f"Creating service account {sa_email}")
    try:
        gcloud("iam", "service-accounts", "describe", sa_email, f"--project={project}")
        ok("Service account already exists — skipping")
    except subprocess.CalledProcessError:
        gcloud(
            "iam", "service-accounts", "create", sa_name,
            "--display-name=Hermes Agent Service Account",
            f"--project={project}",
        )
        ok(f"Created {sa_email}")

    # ── IAM roles ────────────────────────────────────────────────────────────
    step("Granting IAM roles")
    for role in _SA_ROLES:
        gcloud(
            "projects", "add-iam-policy-binding", project,
            f"--member=serviceAccount:{sa_email}",
            f"--role={role}",
            "--condition=None",
            "--quiet",
        )
    ok(f"Granted {len(_SA_ROLES)} roles to {sa_email}")

    # ── Firestore ────────────────────────────────────────────────────────────
    step("Creating Firestore database (native mode)")
    dbs_json = gcloud("firestore", "databases", "list", f"--project={project}", "--format=json", check=False)
    try:
        dbs = json.loads(dbs_json) if dbs_json else []
        has_native = any(d.get("type") == "FIRESTORE_NATIVE" for d in dbs)
    except (json.JSONDecodeError, TypeError):
        has_native = False

    if has_native:
        ok("Firestore database already exists — skipping")
    else:
        gcloud(
            "firestore", "databases", "create",
            f"--location={region}",
            f"--project={project}",
        )
        ok("Firestore database created")


# ── RAG corpora ───────────────────────────────────────────────────────────────
def setup_rag(cfg: dict[str, str], env_path: Path) -> None:
    header("RAG Corpora")

    existing_knowledge = read_env_value(env_path, "KNOWLEDGE_CORPUS_NAME")
    existing_skills    = read_env_value(env_path, "SKILLS_CORPUS_NAME")
    if existing_knowledge and existing_skills:
        ok("RAG corpora already configured in .env — skipping")
        return

    step("Creating RAG corpora via Vertex AI")
    try:
        import vertexai
        from vertexai.preview import rag
    except ImportError:
        warn("vertexai not installed — running: pip install google-cloud-aiplatform[agent_engines,adk]>=1.112")
        run([sys.executable, "-m", "pip", "install",
             "google-cloud-aiplatform[agent_engines,adk]>=1.112"], capture=False)
        import vertexai
        from vertexai.preview import rag

    vertexai.init(project=cfg["project_id"], location=cfg["region"])
    embedding_config = rag.EmbeddingModelConfig(
        publisher_model="publishers/google/models/text-embedding-004"
    )

    # Switch to Serverless mode first (required for new projects in us-central1)
    try:
        rag_cfg_name = f"projects/{cfg['project_id']}/locations/{cfg['region']}/ragEngineConfig"
        rag.rag_data.update_rag_engine_config(rag_engine_config=rag.RagEngineConfig(
            name=rag_cfg_name,
            rag_managed_db_config=rag.RagManagedDbConfig(mode=rag.Serverless()),
        ))
    except Exception:  # noqa: BLE001
        pass  # non-fatal — may already be serverless or API unavailable

    def _create(display_name: str, description: str) -> str:
        corpus = rag.create_corpus(
            display_name=display_name,
            description=description,
            embedding_model_config=embedding_config,
        )
        return corpus.name

    if not existing_knowledge:
        knowledge_name = _create(
            "hermes-knowledge-corpus",
            "Enterprise knowledge base: runbooks, policies, schemas, documentation.",
        )
        write_env(env_path, "KNOWLEDGE_CORPUS_NAME", knowledge_name)
        ok(f"Knowledge corpus: {knowledge_name}")
    else:
        ok(f"Knowledge corpus already set: {existing_knowledge}")

    if not existing_skills:
        skills_name = _create(
            "hermes-skills-corpus",
            "Self-generated agent skills and learned procedures.",
        )
        write_env(env_path, "SKILLS_CORPUS_NAME", skills_name)
        ok(f"Skills corpus: {skills_name}")
    else:
        ok(f"Skills corpus already set: {existing_skills}")


# ── Deploy to Vertex AI Agent Runtime ────────────────────────────────────────
def deploy_agent(cfg: dict[str, str], env_path: Path) -> str:
    header("Deploy Agent to Vertex AI Reasoning Engine")

    existing = read_env_value(env_path, "REASONING_ENGINE_RESOURCE_NAME")
    if existing:
        print(f"\n  ℹ️  Existing engine found: {existing}")
        print("  [u] Update existing engine (redeploy ~5–10 min)")
        print("  [s] Skip (keep current engine)")
        choice = input("  Choice [u/S]: ").strip().lower()
        if choice == "u":
            step("Updating existing Reasoning Engine …")
            result = run(
                [sys.executable, "scripts/deploy.py", "--update", existing],
                capture=True,
                check=True,
            )
            ok(f"Agent updated: {existing}")
            return existing
        else:
            ok(f"Agent already deployed: {existing}")
            return existing

    step("Deploying agent (this takes ~5–10 min on first run) …")
    result = run(
        [sys.executable, "scripts/deploy.py"],
        capture=True,
        check=True,
    )
    # Parse resource name from output
    match = re.search(r"REASONING_ENGINE_RESOURCE_NAME=(\S+)", result.stdout + result.stderr)
    if not match:
        err("Could not parse REASONING_ENGINE_RESOURCE_NAME from deploy output.")
        err("Output was:")
        print(result.stdout[-2000:])
        sys.exit(1)

    resource_name = match.group(1)
    write_env(env_path, "REASONING_ENGINE_RESOURCE_NAME", resource_name)
    ok(f"Agent deployed: {resource_name}")
    return resource_name


# ── Demo data seed ────────────────────────────────────────────────────────────
def seed_demo_data(cfg: dict[str, str]) -> None:
    header("Seeding Demo Data")
    scripts = [
        Path("scripts/demo/seed_bigquery.py"),
        Path("scripts/demo/seed_knowledge_base.py"),
    ]
    for script in scripts:
        if script.exists():
            step(f"Running {script}")
            run([sys.executable, str(script)], capture=False, check=False)
            ok(f"Done: {script.name}")
        else:
            warn(f"{script} not found — skipping")


def setup_memory_bank(cfg: dict[str, str], env_path: Path) -> None:
    header("VertexAiMemoryBank")

    existing = read_env_value(env_path, "MEMORY_BANK_RESOURCE_NAME")
    if existing:
        ok(f"MemoryBank already configured: {existing}")
        return

    step("Creating VertexAiMemoryBank resource …")
    try:
        import vertexai
        vertexai.init(project=cfg["project_id"], location=cfg["region"])
        from memory.memory_bank import create_memory_bank
        resource_name = create_memory_bank(
            project=cfg["project_id"],
            location=cfg["region"],
        )
        write_env(env_path, "MEMORY_BANK_RESOURCE_NAME", resource_name)
        ok(f"MemoryBank created: {resource_name}")
    except Exception as exc:  # noqa: BLE001
        warn(f"VertexAiMemoryBank unavailable ({exc})")
        step("Falling back: creating RAG corpus as memory bank …")
        try:
            import vertexai
            from vertexai.preview import rag
            vertexai.init(project=cfg["project_id"], location=cfg["region"])
            embedding_config = rag.EmbeddingModelConfig(
                publisher_model="publishers/google/models/text-embedding-004",
            )
            corpus = rag.create_corpus(
                display_name="hermes-memory-bank",
                description="Per-user long-term memory for Hermes (RAG corpus fallback).",
                embedding_model_config=embedding_config,
            )
            write_env(env_path, "MEMORY_BANK_RESOURCE_NAME", corpus.name)
            ok(f"Memory bank corpus created: {corpus.name}")
        except Exception as exc2:  # noqa: BLE001
            warn(f"Memory bank creation failed ({exc2}) — continuing without it.")
            warn("Long-term user memory will be disabled. Re-run wizard to retry.")


# ── Cloud Run deploy ──────────────────────────────────────────────────────────
def deploy_cloud_run(cfg: dict[str, str], env_path: Path) -> str | None:
    if not shutil.which("docker"):
        warn("Docker not found — skipping Cloud Run deploy")
        return None

    header("Deploy Gateway to Cloud Run")
    project   = cfg["project_id"]
    region    = cfg["region"]
    image_tag = f"gcr.io/{project}/hermes-gateway:latest"
    svc_name  = "hermes-gateway"

    step(f"Building Docker image: {image_tag}")
    run(["docker", "build", "-f", "Dockerfile.gateway", "-t", image_tag, "."], capture=False, check=True)
    ok("Image built")

    step("Pushing to Container Registry")
    run(["docker", "push", image_tag], capture=False, check=True)
    ok("Image pushed")

    step(f"Deploying Cloud Run service: {svc_name}")
    env_vars = ",".join(
        f"{k}={v}"
        for k, v in {
            "GCP_PROJECT_ID":                   cfg["project_id"],
            "GCP_LOCATION":                     cfg["region"],
            "REASONING_ENGINE_RESOURCE_NAME":   read_env_value(env_path, "REASONING_ENGINE_RESOURCE_NAME"),
            "KNOWLEDGE_CORPUS_NAME":            read_env_value(env_path, "KNOWLEDGE_CORPUS_NAME"),
            "SKILLS_CORPUS_NAME":               read_env_value(env_path, "SKILLS_CORPUS_NAME"),
        }.items()
        if v
    )
    url_out = gcloud(
        "run", "deploy", svc_name,
        f"--image={image_tag}",
        f"--region={region}",
        f"--project={project}",
        "--platform=managed",
        "--allow-unauthenticated",
        f"--set-env-vars={env_vars}",
        "--format=value(status.url)",
    )
    service_url = url_out.strip()
    write_env(env_path, "CLOUD_RUN_URL", service_url)
    ok(f"Gateway live at: {service_url}")
    return service_url


# ── Local gateway start helper ────────────────────────────────────────────────
def install_python_deps() -> None:
    req = Path("requirements.txt")
    if not req.exists():
        return
    step("Installing Python dependencies")
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], capture=False, check=True)
    ok("Dependencies installed")


# ── Final summary ─────────────────────────────────────────────────────────────
def print_summary(cfg: dict[str, Any], gateway_url: str | None, env_path: Path) -> None:
    header("🎉 Setup complete!")

    reasoning = read_env_value(env_path, "REASONING_ENGINE_RESOURCE_NAME")
    local_url = "http://localhost:8080"
    url = gateway_url or local_url

    print(textwrap.dedent(f"""
  {_c(BOLD, 'Your Hermes Agent is ready.')}

  {_c(CYAN, '── Start the gateway locally ──')}
  source .env && uvicorn gateway.main:app --reload --port 8080

  {_c(CYAN, '── Test it with curl ──')}
  curl -X POST {url}/chat \\
    -H "Content-Type: application/json" \\
    -d '{{"message": "Hello! What can you help me with?"}}'

  {_c(CYAN, '── Web UI (optional) ──')}
  cd ui && cp .env.local.example .env.local
  # Edit ui/.env.local: set NEXT_PUBLIC_GATEWAY_URL={url}
  npm install && npm run dev
  # Open http://localhost:3000

  {_c(CYAN, '── Add your own agents (no Python needed) ──')}
  Edit agents.yaml — add an entry, restart gateway.

  {_c(CYAN, '── Add your own skills ──')}
  cp skills/TEMPLATE.md skills/my-skill.md
  # Fill in the YAML frontmatter, restart gateway.

  {_c(CYAN, '── Useful files ──')}
  .env                    ← all your config (auto-filled by this wizard)
  agents.yaml             ← add/remove agents here
  skills/                 ← add skills here
  AGENTS.md               ← contributor guide
  RELEASE_NOTES.md        ← changelog
    """))


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    os.chdir(Path(__file__).parent)
    env_path = Path(".env")

    # Ensure .env exists
    if not env_path.exists():
        example = Path(".env.example")
        if example.exists():
            shutil.copy(example, env_path)
        else:
            env_path.touch()

    header("Hermes GCP Agent Platform — Setup Wizard")
    print(textwrap.dedent("""
  This wizard sets up everything from scratch in 3 questions.
  It is safe to re-run — all steps are idempotent.
    """))

    preflight()
    cfg = gather_config(env_path)

    # Write base config into .env immediately
    write_env(env_path, "GCP_PROJECT_ID",      cfg["project_id"])
    write_env(env_path, "GCP_LOCATION",         cfg["region"])
    write_env(env_path, "GCP_STAGING_BUCKET",   cfg["bucket"])

    print(f"\n  {_c(BOLD, 'Summary:')}")
    print(f"  Project  : {_c(GREEN, cfg['project_id'])}")
    print(f"  Region   : {_c(GREEN, cfg['region'])}")
    print(f"  Target   : {_c(GREEN, 'Cloud Run' if cfg['deploy_cloud_run'] else 'Local')}")
    print(f"  Demo data: {_c(GREEN, 'Yes' if cfg['want_demo_data'] else 'No')}")

    if not ask_yn("\nProceed?", default=True):
        print("  Aborted.")
        sys.exit(0)

    bootstrap_gcp(cfg)

    install_python_deps()

    setup_rag(cfg, env_path)

    # ── VertexAiMemoryBank ──────────────────────────────────────────────────
    setup_memory_bank(cfg, env_path)

    deploy_agent(cfg, env_path)

    if cfg["want_demo_data"]:
        seed_demo_data(cfg)

    gateway_url: str | None = None
    if cfg["deploy_cloud_run"]:
        gateway_url = deploy_cloud_run(cfg, env_path)

    print_summary(cfg, gateway_url, env_path)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(_c(YELLOW, "\n\n  Interrupted. Re-run at any time — all steps are idempotent."))
        sys.exit(130)
