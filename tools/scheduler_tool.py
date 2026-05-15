"""
tools/scheduler_tool.py

Allows the Hermes agent to schedule tasks for itself using Cloud Scheduler.

The agent calls `schedule_agent_task(...)` to create a Cloud Scheduler job
that will POST back to the gateway's `/scheduler/trigger` endpoint at the
specified time/cron, causing a new task to be submitted automatically.

Use cases
─────────
- "Remind me to send the weekly report every Monday at 9 AM"
- "Check server health every 15 minutes for the next 2 hours"
- "Summarise my emails at 8 AM daily"

Auth
────
The Cloud Scheduler job uses an OIDC token (issued for the Hermes service
account) so the gateway `/scheduler/trigger` endpoint can verify the caller.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from google.adk.tools import FunctionTool

from config import get_settings

logger = logging.getLogger(__name__)

_SCHEDULER_PARENT_TEMPLATE = "projects/{project}/locations/{location}"
_JOB_NAME_TEMPLATE = "projects/{project}/locations/{location}/jobs/{job_name}"


@lru_cache(maxsize=1)
def _get_scheduler_client():
    from google.cloud import scheduler_v1  # noqa: PLC0415
    return scheduler_v1.CloudSchedulerClient()


# ── Tool function ──────────────────────────────────────────────────────────────


def schedule_agent_task(
    task_description: str,
    schedule: str,
    job_name: str,
    timezone: str = "UTC",
    description: str = "",
) -> dict:
    """
    Schedule this agent to run a task automatically at a future time or on a
    recurring schedule.

    Args:
        task_description: The task the agent should perform when triggered.
            Example: "Send a weekly sales report to the team."
        schedule: A cron expression OR a one-time RFC3339 datetime string.
            Cron examples:  "0 9 * * 1"  (every Monday at 9 AM)
                            "*/15 * * * *" (every 15 minutes)
                            "0 8 * * *"   (every day at 8 AM)
            One-time: use "cron" with a specific pattern for one-shot runs;
                      for truly one-off, create a job and delete it after it fires.
        job_name: A short lowercase identifier for this job.
            Example: "weekly-report" or "health-check-15m"
        timezone: IANA timezone for the schedule. Defaults to "UTC".
            Examples: "America/New_York", "Asia/Tokyo", "Europe/London"
        description: Optional human-readable description of why this job exists.

    Returns:
        dict with keys:
            - job_name: full resource name of the created/updated job
            - schedule: the cron expression used
            - status: "created" | "updated" | "error"
            - message: human-readable result
    """
    settings = get_settings()

    if not settings.gateway_url:
        return {
            "status": "error",
            "message": "GATEWAY_URL is not configured. Cannot create scheduler job.",
        }
    if not settings.scheduler_service_account:
        return {
            "status": "error",
            "message": "SCHEDULER_SERVICE_ACCOUNT is not configured.",
        }

    # Sanitise job name: lowercase alphanumeric and hyphens only
    safe_name = "".join(c if c.isalnum() or c == "-" else "-" for c in job_name.lower())
    safe_name = safe_name.strip("-")[:50] or "hermes-task"

    trigger_url = f"{settings.gateway_url.rstrip('/')}/scheduler/trigger"
    project = settings.gcp_project_id
    location = settings.scheduler_location

    import json  # noqa: PLC0415
    body = json.dumps({
        "task": task_description,
        "scheduled_by": "agent",
        "job_name": safe_name,
    }).encode()

    try:
        from google.cloud import scheduler_v1  # noqa: PLC0415
        from google.protobuf import duration_pb2  # noqa: PLC0415

        client = _get_scheduler_client()
        parent = _SCHEDULER_PARENT_TEMPLATE.format(project=project, location=location)
        full_job_name = _JOB_NAME_TEMPLATE.format(
            project=project, location=location, job_name=safe_name
        )

        job = scheduler_v1.Job(
            name=full_job_name,
            description=description or f"Hermes agent scheduled task: {task_description[:100]}",
            schedule=schedule,
            time_zone=timezone,
            http_target=scheduler_v1.HttpTarget(
                uri=trigger_url,
                http_method=scheduler_v1.HttpMethod.POST,
                body=body,
                headers={"Content-Type": "application/json"},
                oidc_token=scheduler_v1.OidcToken(
                    service_account_email=settings.scheduler_service_account,
                    audience=trigger_url,
                ),
            ),
            attempt_deadline=duration_pb2.Duration(seconds=1800),  # 30 min deadline
        )

        # Try update first; create if not found
        try:
            updated = client.update_job(job=job)
            return {
                "job_name": updated.name,
                "schedule": schedule,
                "status": "updated",
                "message": f"Job '{safe_name}' updated. Next run follows schedule: {schedule} ({timezone})",
            }
        except Exception:  # noqa: BLE001
            created = client.create_job(parent=parent, job=job)
            return {
                "job_name": created.name,
                "schedule": schedule,
                "status": "created",
                "message": f"Job '{safe_name}' created. Will trigger: {task_description[:80]} — Schedule: {schedule} ({timezone})",
            }

    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to create/update scheduler job '%s'.", safe_name)
        return {
            "status": "error",
            "message": f"Scheduler error: {exc}",
        }


def delete_scheduled_task(job_name: str) -> dict:
    """
    Delete a previously scheduled agent task.

    Args:
        job_name: The short job name used when creating the schedule (e.g. "weekly-report").

    Returns:
        dict with keys:
            - status: "deleted" | "not_found" | "error"
            - message: human-readable result
    """
    settings = get_settings()
    safe_name = "".join(c if c.isalnum() or c == "-" else "-" for c in job_name.lower()).strip("-")

    full_job_name = _JOB_NAME_TEMPLATE.format(
        project=settings.gcp_project_id,
        location=settings.scheduler_location,
        job_name=safe_name,
    )

    try:
        client = _get_scheduler_client()
        client.delete_job(name=full_job_name)
        return {"status": "deleted", "message": f"Scheduled job '{safe_name}' has been deleted."}
    except Exception as exc:  # noqa: BLE001
        err = str(exc).lower()
        if "not found" in err or "404" in err:
            return {"status": "not_found", "message": f"No job named '{safe_name}' found."}
        logger.exception("Failed to delete scheduler job '%s'.", safe_name)
        return {"status": "error", "message": f"Scheduler error: {exc}"}


def list_scheduled_tasks() -> dict:
    """
    List all agent-created Cloud Scheduler jobs for the current project.

    Returns:
        dict with key "jobs": list of {name, schedule, description, state, next_run}
    """
    settings = get_settings()
    parent = _SCHEDULER_PARENT_TEMPLATE.format(
        project=settings.gcp_project_id, location=settings.scheduler_location
    )
    try:
        client = _get_scheduler_client()
        jobs = []
        for job in client.list_jobs(parent=parent):
            jobs.append({
                "name": job.name.split("/")[-1],
                "schedule": job.schedule,
                "description": job.description,
                "state": str(job.state),
                "next_run": str(job.next_schedule_time) if job.next_schedule_time else None,
            })
        return {"jobs": jobs, "count": len(jobs)}
    except Exception as exc:  # noqa: BLE001
        return {"jobs": [], "error": str(exc)}


# ── ADK FunctionTool wrappers ──────────────────────────────────────────────────

schedule_task_tool = FunctionTool(schedule_agent_task)
delete_task_tool = FunctionTool(delete_scheduled_task)
list_tasks_tool = FunctionTool(list_scheduled_tasks)
