#!/usr/bin/env env bash
# =============================================================================
# scripts/demo/showcase.sh
#
# Comprehensive showcase of every Hermes Agent PoC feature.
# Covers: HR, IT Helpdesk, Developer, Analytics, Long-running Tasks,
#         Self-scheduling, Google Workspace, Telegram/Slack/Teams webhooks.
#
# Prerequisites:
#   1. Gateway running: uvicorn gateway.main:app --port 8080
#      OR set GATEWAY_URL to your deployed Cloud Run URL.
#   2. Demo data seeded:
#        python scripts/demo/seed_bigquery.py
#        python scripts/demo/seed_knowledge_base.py
#   3. Authenticated: gcloud auth application-default login
#
# Usage:
#   chmod +x scripts/demo/showcase.sh
#   ./scripts/demo/showcase.sh          # run all sections
#   ./scripts/demo/showcase.sh hr       # run only HR section
#   ./scripts/demo/showcase.sh task     # run only long-running task section
# =============================================================================
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8080}"
SECTION="${1:-all}"

# ── Colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

header()  { echo -e "\n${BOLD}${CYAN}══ $1 ══${RESET}"; }
step()    { echo -e "${YELLOW}▶ $1${RESET}"; }
ok()      { echo -e "${GREEN}✓ $1${RESET}"; }
err()     { echo -e "${RED}✗ $1${RESET}"; }
sep()     { echo -e "${CYAN}──────────────────────────────────────────${RESET}"; }

# ── Auth token ─────────────────────────────────────────────────────────────────
get_token() {
  # For local dev: use gcloud identity token (works with any Google account).
  # For production: replace with your actual Google ID token source.
  if command -v gcloud &>/dev/null; then
    gcloud auth print-identity-token 2>/dev/null || echo "DUMMY_TOKEN_FOR_LOCAL_DEV"
  else
    echo "${GOOGLE_ID_TOKEN:-DUMMY_TOKEN_FOR_LOCAL_DEV}"
  fi
}

TOKEN=$(get_token)
AUTH="Authorization: Bearer ${TOKEN}"

# ── Helper: chat request ───────────────────────────────────────────────────────
# Usage: chat "your message here"  [session_id]
chat() {
  local message="$1"
  local session_id="${2:-}"
  local body

  if [[ -n "$session_id" ]]; then
    body=$(jq -n --arg m "$message" --arg s "$session_id" \
      '{"message": $m, "session_id": $s}')
  else
    body=$(jq -n --arg m "$message" '{"message": $m}')
  fi

  # SSE stream — collect all "text" events and print them
  curl -s -N -X POST "${GATEWAY_URL}/chat" \
    -H "$AUTH" \
    -H "Content-Type: application/json" \
    -d "$body" \
    | grep '^data:' \
    | sed 's/^data: //' \
    | python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        ev = json.loads(line)
        if ev.get('type') == 'text' and ev.get('content'):
            print(ev['content'])
        elif ev.get('type') == 'done':
            break
    except Exception:
        pass
" 2>/dev/null || echo "(no response — is the gateway running?)"
}

# ── Helper: submit task (async) ────────────────────────────────────────────────
submit_task() {
  local description="$1"
  local context="${2:-{}}"
  curl -s -X POST "${GATEWAY_URL}/tasks" \
    -H "$AUTH" \
    -H "Content-Type: application/json" \
    -d "{\"task\": \"${description}\", \"context\": ${context}}" \
    | python3 -m json.tool
}

# ── Helper: poll task ──────────────────────────────────────────────────────────
poll_task() {
  local task_id="$1"
  local max_polls="${2:-12}"
  local interval="${3:-5}"
  local i=0
  echo "Polling task ${task_id} (max ${max_polls}×${interval}s) …"
  while [[ $i -lt $max_polls ]]; do
    result=$(curl -s "${GATEWAY_URL}/tasks/${task_id}" -H "$AUTH")
    status=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))")
    echo "  [$(( i * interval ))s] status=${status}"
    if [[ "$status" == "done" || "$status" == "failed" || "$status" == "cancelled" ]]; then
      echo "$result" | python3 -m json.tool
      return 0
    fi
    sleep "$interval"
    (( i++ ))
  done
  echo "  Task still running after $(( max_polls * interval ))s — use GET /tasks/${task_id} to continue polling."
}

# =============================================================================
# SECTION: HEALTH CHECK
# =============================================================================
run_health() {
  header "HEALTH CHECK"
  step "Gateway health"
  curl -s "${GATEWAY_URL}/health" | python3 -m json.tool 2>/dev/null || \
    echo "  (No /health endpoint — check if gateway is running)"
  ok "Gateway at ${GATEWAY_URL}"
}

# =============================================================================
# SECTION: HR AGENT
# =============================================================================
run_hr() {
  header "HR AGENT — Policy, PTO & Benefits"
  sep

  step "1. PTO policy query"
  chat "How many PTO days do I get per year at Acme, and what's the rollover policy?"
  sep

  step "2. PTO balance (requires BigQuery seed data)"
  chat "How many PTO days has alice.chen@acmecorp.com used so far this year? Query the hermes_demo.pto_requests table."
  sep

  step "3. Benefits overview"
  chat "What health insurance plans does Acme offer and how much do employees pay?"
  sep

  step "4. 401k matching"
  chat "How does the 401k match work at Acme? What's the vesting schedule?"
  sep

  step "5. Parental leave"
  chat "I'm expecting a baby. What is Acme's parental leave policy for primary and secondary caregivers?"
  sep

  step "6. Performance review calendar"
  chat "When is the next annual performance review? What does the rating scale look like?"
  sep

  step "7. Remote work policy for a senior employee"
  chat "I'm a Level 6 Staff Engineer. How many days a week can I work from home?"
  sep

  step "8. Schedule an onboarding session (requires Calendar + Workspace setup)"
  chat "Schedule an onboarding orientation for a new hire, Jordan Patel (jordan.patel@acmecorp.com), who starts on Monday May 18 2026. Set it for 2 PM – 3 PM and invite Noah Anderson."
  sep

  step "9. Send offer letter reminder"
  chat "Send an email to peter.clark@acmecorp.com reminding him to schedule the final interview with candidate #C-4421 by Friday."
  sep

  step "10. Expense reimbursement"
  chat "An employee spent \$750 on a conference. Do they need VP approval to submit the expense?"
}

# =============================================================================
# SECTION: IT HELPDESK AGENT
# =============================================================================
run_it() {
  header "IT HELPDESK AGENT — Incidents, Access & Runbooks"
  sep

  step "1. VPN not working"
  chat "I installed Cisco AnyConnect but when I try to connect I get an Authentication Failed error. What should I do?"
  sep

  step "2. VPN disconnects frequently (macOS)"
  chat "I'm on macOS Sonoma and my VPN keeps disconnecting every few minutes. How do I fix it?"
  sep

  step "3. Look up open incidents (requires BigQuery seed data)"
  chat "How many IT incidents are currently open or in progress? Show me the details."
  sep

  step "4. P0 incident response"
  chat "EMERGENCY: The production API gateway just went down — all users are getting 503 errors. What do I do?"
  sep

  step "5. New employee access request"
  chat "A new engineer, Grace Kim, started today but has no GitHub access. Can you walk me through the access request process?"
  sep

  step "6. Incident statistics (BigQuery)"
  chat "How many P0 and P1 incidents did we have in 2025 vs 2026 so far? Which category is most common?"
  sep

  step "7. Average resolution time by severity"
  chat "What is the average incident resolution time in minutes for each severity level (P0–P3)? Use the hermes_demo.it_incidents table."
  sep

  step "8. Schedule maintenance window (Calendar)"
  chat "Schedule a maintenance window called 'VPN Gateway Upgrade' on Saturday May 16 2026 from 2 AM to 4 AM UTC. Invite xavier.green@acmecorp.com and yara.adams@acmecorp.com."
  sep

  step "9. Send incident notification email"
  chat "The Slack integration (INC-008) was resolved. Send a resolution email to alice.chen@acmecorp.com with a summary."
  sep

  step "10. Find IT runbook in Drive"
  chat "Search Google Drive for runbooks related to 'incident response' and summarise what you find."
}

# =============================================================================
# SECTION: DEVELOPER AGENT
# =============================================================================
run_dev() {
  header "DEVELOPER AGENT — Code, Infrastructure & CI/CD"
  sep

  step "1. How to deploy to production"
  chat "What is the process for deploying a new release to production at Acme?"
  sep

  step "2. Rollback procedure"
  chat "The latest deployment is causing errors. Walk me through rolling back to the previous Cloud Run revision."
  sep

  step "3. Local development setup"
  chat "I just joined as a backend engineer. How do I set up my local development environment for the Hermes gateway?"
  sep

  step "4. Emergency hotfix deploy"
  chat "We have a critical bug in production. Give me the exact commands to build, push, and deploy a hotfix Docker image."
  sep

  step "5. Architecture question"
  chat "How does the Hermes agent handle long-running tasks? What is the LoopAgent and how does it work?"
  sep

  step "6. CI/CD pipeline stages"
  chat "What checks run on every PR? What additional steps happen when merging to main?"
  sep

  step "7. Feature flag check"
  chat "Is the ENABLE_WORKSPACE_TOOLS feature flag currently enabled? How do I toggle it?"
  sep

  step "8. Find architecture docs in Drive"
  chat "Search Google Drive for architecture documents or design specs for the Hermes platform."
}

# =============================================================================
# SECTION: ANALYTICS AGENT (BigQuery)
# =============================================================================
run_analytics() {
  header "ANALYTICS AGENT — BigQuery Queries"
  sep

  step "1. Headcount by department"
  chat "How many employees does Acme have in each department? Use hermes_demo.employees."
  sep

  step "2. Sales performance Q1 2025"
  chat "Show me total revenue by region for Q1 2025 (January–March). Use hermes_demo.sales_performance."
  sep

  step "3. Top performing product"
  chat "Which product generated the most revenue in 2025 overall? Compare across all regions."
  sep

  step "4. Sales quota attainment"
  chat "What is the overall quota attainment percentage for North America in 2025? Use hermes_demo.sales_performance."
  sep

  step "5. Employee tenure analysis"
  chat "How many employees have been at Acme for more than 5 years? Show names and departments."
  sep

  step "6. PTO request trends"
  chat "What month has the most approved PTO requests in 2026? Query hermes_demo.pto_requests."
  sep

  step "7. Incident resolution SLA compliance"
  chat "For P2 incidents (SLA = resolve within 1 business day = 480 mins), what percentage were resolved within SLA in 2026? Use hermes_demo.it_incidents."
  sep

  step "8. Revenue growth"
  chat "Calculate month-over-month revenue growth for North America Enterprise License throughout 2025. Use hermes_demo.sales_performance."
  sep

  step "9. Project status summary"
  chat "How many projects are In Progress, Completed, or Planning? Show average completion percentage by status."
  sep

  step "10. Cross-department query"
  chat "For each department, show the headcount, number of open PTO requests, and number of open IT incidents involving their employees."
}

# =============================================================================
# SECTION: LONG-RUNNING TASKS (LoopAgent)
# =============================================================================
run_tasks() {
  header "LONG-RUNNING TASKS — ReAct LoopAgent"
  sep

  step "1. Submit: monthly HR report"
  TASK_ID=$(curl -s -X POST "${GATEWAY_URL}/tasks" \
    -H "$AUTH" \
    -H "Content-Type: application/json" \
    -d '{
      "task": "Generate a complete monthly HR report for May 2026. Include: (1) headcount by department, (2) PTO requests submitted and approved this month, (3) any open IT incidents affecting staff, (4) list of projects at risk (completion < 30%). Format as a structured report with sections and tables. Store the final result as a text summary.",
      "context": {"report_month": "2026-05", "requester": "olivia.harris@acmecorp.com"}
    }' | python3 -c "import sys,json; print(json.load(sys.stdin).get('task_id',''))")
  ok "Submitted HR Report Task: ${TASK_ID}"
  sep

  step "2. Poll HR report task (60 second window)"
  [[ -n "${TASK_ID}" ]] && poll_task "${TASK_ID}" 6 10
  sep

  step "3. Submit: sales analysis + email report"
  SALES_TASK=$(curl -s -X POST "${GATEWAY_URL}/tasks" \
    -H "$AUTH" \
    -H "Content-Type: application/json" \
    -d '{
      "task": "Analyse Q1 2026 (January–March) sales performance for all regions and products. Calculate: (1) total revenue per region, (2) quota attainment percentage, (3) top 3 deals by value. Then send a formatted summary email to james.taylor@acmecorp.com and karen.white@acmecorp.com with subject Q1 2026 Sales Report.",
      "context": {"quarter": "Q1-2026"}
    }' | python3 -c "import sys,json; print(json.load(sys.stdin).get('task_id',''))")
  ok "Submitted Sales Report Task: ${SALES_TASK}"
  sep

  step "4. Submit: onboard new employee (end-to-end)"
  ONBOARD_TASK=$(curl -s -X POST "${GATEWAY_URL}/tasks" \
    -H "$AUTH" \
    -H "Content-Type: application/json" \
    -d '{
      "task": "Onboard new employee Jordan Patel (jordan.patel@acmecorp.com), Senior Software Engineer, joining Engineering team under Bob Kim (bob.kim@acmecorp.com), starting Monday May 18 2026, based in New York. Steps: (1) Send welcome email to Jordan, (2) Send manager prep email to Bob, (3) Schedule Day-1 HR orientation for May 18 at 2 PM ET (invite Jordan + Noah Anderson), (4) Schedule first 1:1 with Bob for May 19 at 10 AM ET, (5) Create calendar event Welcome Lunch with the team on May 18 noon ET.",
      "context": {"new_hire": "Jordan Patel", "start_date": "2026-05-18"}
    }' | python3 -c "import sys,json; print(json.load(sys.stdin).get('task_id',''))")
  ok "Submitted Onboarding Task: ${ONBOARD_TASK}"
  sep

  step "5. List all my tasks"
  curl -s "${GATEWAY_URL}/tasks" -H "$AUTH" | python3 -m json.tool
  sep

  step "6. Submit: incident audit report"
  AUDIT_TASK=$(curl -s -X POST "${GATEWAY_URL}/tasks" \
    -H "$AUTH" \
    -H "Content-Type: application/json" \
    -d '{
      "task": "Produce an IT incident audit report for the last 6 months (Nov 2025 – May 2026). For each severity level: count incidents, average resolution time, SLA compliance rate (P0=1h, P1=4h, P2=1day, P3=3days). Identify the top 3 recurring incident categories. Write the report and save it to GCS as gs://hermes-agent-artifacts/reports/incident-audit-2026-05.txt",
      "context": {"period": "2025-11 to 2026-05", "save_to_gcs": "true"}
    }' | python3 -c "import sys,json; print(json.load(sys.stdin).get('task_id',''))")
  ok "Submitted Incident Audit Task: ${AUDIT_TASK}"
}

# =============================================================================
# SECTION: SELF-SCHEDULING (Cloud Scheduler)
# =============================================================================
run_scheduler() {
  header "SELF-SCHEDULING — Agent creates Cloud Scheduler jobs"
  sep

  step "1. Schedule weekly sales report (every Monday 9 AM)"
  chat "Schedule a task to run every Monday at 9 AM UTC: generate the weekly sales report for the previous week and email it to karen.white@acmecorp.com. Use the job name weekly-sales-report."
  sep

  step "2. Schedule daily IT incident check (every morning)"
  chat "Create a recurring task that runs every weekday at 8 AM UTC: check if there are any open P0 or P1 incidents and send a status email to yara.adams@acmecorp.com. Job name: daily-incident-check."
  sep

  step "3. Schedule monthly HR report (1st of each month)"
  chat "Schedule a monthly HR headcount and PTO report to be generated on the 1st of every month at 6 AM UTC and sent to olivia.harris@acmecorp.com. Job name: monthly-hr-report."
  sep

  step "4. List all scheduled tasks"
  chat "List all currently scheduled agent tasks for this project."
  sep

  step "5. One-time follow-up task"
  chat "I need you to check in on the CRM migration project (PRJ-002) in 3 days and send a status update to mia.thompson@acmecorp.com. Schedule it for May 18 2026 at 10 AM UTC. Job name: crm-migration-followup."
}

# =============================================================================
# SECTION: GOOGLE WORKSPACE (Gmail / Calendar / Drive)
# =============================================================================
run_workspace() {
  header "GOOGLE WORKSPACE — Gmail, Calendar, Drive"
  sep

  step "1. Search inbox for unread emails"
  chat "Search my inbox for unread emails from the last 3 days. Show subject, sender, and snippet."
  sep

  step "2. Read a specific email thread"
  chat "Search Gmail for emails with subject containing 'incident' from the last week and summarise them."
  sep

  step "3. Create a team meeting"
  chat "Schedule a team all-hands meeting called Q2 Engineering Review for May 20 2026 from 2 PM to 3:30 PM Pacific. Invite the entire engineering team: alice.chen, bob.kim, carol.davis, david.park, emma.wilson, frank.garcia, grace.lee, henry.brown (all @acmecorp.com). Add description: Q2 progress review and roadmap discussion."
  sep

  step "4. Check availability before scheduling"
  chat "Are alice.chen@acmecorp.com and bob.kim@acmecorp.com both free on May 19 2026 from 3 PM to 4 PM UTC? If yes, schedule a 1:1 between them."
  sep

  step "5. List upcoming calendar events"
  chat "List my calendar events for May 15–22 2026."
  sep

  step "6. Search Drive for HR documents"
  chat "Search Google Drive for documents related to performance reviews or the review process. Summarise what you find."
  sep

  step "7. Read a Drive file"
  chat "Find and read the employee onboarding checklist in Google Drive. List the Day 1 tasks."
  sep

  step "8. Send a formal email"
  chat "Send an email to liam.johnson@acmecorp.com with subject Your 30-Day Check-in and body: Hi Liam, It's been 30 days since you joined the Sales team. Please schedule a 30-min check-in with Noah Anderson (noah.anderson@acmecorp.com) by end of this week. Best, HR Team."
}

# =============================================================================
# SECTION: CONNECTOR WEBHOOKS (Telegram / Slack / Teams)
# =============================================================================
run_connectors() {
  header "CONNECTORS — Platform Webhook Payloads"
  sep

  step "Telegram webhook (simulated message)"
  echo "NOTE: Replace TELEGRAM_WEBHOOK_SECRET with your actual secret."
  curl -s -X POST "${GATEWAY_URL}/telegram/webhook" \
    -H "Content-Type: application/json" \
    -H "X-Telegram-Bot-Api-Secret-Token: ${TELEGRAM_WEBHOOK_SECRET:-demo-secret}" \
    -d '{
      "update_id": 100000001,
      "message": {
        "message_id": 42,
        "from": {"id": 12345678, "first_name": "Alice", "username": "alice_acme"},
        "chat": {"id": 12345678, "type": "private"},
        "date": 1747267200,
        "text": "How many PTO days do I have left?"
      }
    }' | python3 -m json.tool
  sep

  step "Slack slash command (simulated)"
  echo "NOTE: Replace SLACK_SIGNING_SECRET with a valid HMAC header for production."
  curl -s -X POST "${GATEWAY_URL}/slack/events" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -H "X-Slack-Signature: v0=demo_signature" \
    -H "X-Slack-Request-Timestamp: $(date +%s)" \
    -d "token=demo_token&team_id=T123&channel_id=C123&user_id=U456&user_name=alice.chen&text=What+is+the+VPN+server+address%3F&command=%2Fhermes"
  sep

  step "Microsoft Teams webhook (simulated activity)"
  curl -s -X POST "${GATEWAY_URL}/teams/messages" \
    -H "Content-Type: application/json" \
    -d '{
      "type": "message",
      "id": "1747267200000",
      "timestamp": "2026-05-15T10:00:00Z",
      "channelId": "msteams",
      "from": {"id": "29:1abc", "name": "Bob Kim"},
      "conversation": {"id": "19:demo@thread.tacv2"},
      "text": "How do I request VPN access for a new contractor?",
      "serviceUrl": "https://smba.trafficmanager.net/amer/"
    }' | python3 -m json.tool
}

# =============================================================================
# SECTION: MULTI-TURN CONVERSATION
# =============================================================================
run_multiturn() {
  header "MULTI-TURN CONVERSATION — Session Continuity"
  sep

  step "Start a conversation and continue it"
  echo "Starting first message …"
  # Capture session_id from first response
  FIRST=$(curl -s -N -X POST "${GATEWAY_URL}/chat" \
    -H "$AUTH" \
    -H "Content-Type: application/json" \
    -d '{"message": "My name is Alice Chen and I work in Engineering."}' \
    | grep '^data:' | sed 's/^data: //' | python3 -c "
import sys, json
session_id = ''
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        ev = json.loads(line)
        if ev.get('type') == 'done':
            session_id = ev.get('session_id','')
            break
    except: pass
print(session_id)
" 2>/dev/null)

  ok "Session ID: ${FIRST}"
  sep

  if [[ -n "${FIRST}" ]]; then
    step "Continue same session: follow-up question"
    chat "Given that context, how many PTO days do I have left this year if I've taken 12 days already?" "${FIRST}"
    sep

    step "Third turn: schedule PTO"
    chat "Great, can you schedule a PTO block for me: July 14–18, 2026 (5 days)? Send the calendar invite to noah.anderson@acmecorp.com for approval." "${FIRST}"
  fi
}

# =============================================================================
# MAIN DISPATCHER
# =============================================================================
echo -e "${BOLD}Hermes Agent PoC — Full Feature Showcase${RESET}"
echo -e "Gateway: ${CYAN}${GATEWAY_URL}${RESET}"
echo -e "Token:   ${CYAN}${TOKEN:0:20}…${RESET}"
echo ""

case "$SECTION" in
  health)     run_health ;;
  hr)         run_hr ;;
  it)         run_it ;;
  dev)        run_dev ;;
  analytics)  run_analytics ;;
  task|tasks) run_tasks ;;
  scheduler)  run_scheduler ;;
  workspace)  run_workspace ;;
  connectors) run_connectors ;;
  multiturn)  run_multiturn ;;
  all)
    run_health
    run_hr
    run_it
    run_dev
    run_analytics
    run_tasks
    run_scheduler
    run_workspace
    run_connectors
    run_multiturn
    ;;
  *)
    echo "Usage: $0 [health|hr|it|dev|analytics|tasks|scheduler|workspace|connectors|multiturn|all]"
    exit 1
    ;;
esac

echo -e "\n${GREEN}${BOLD}Showcase complete.${RESET}"
