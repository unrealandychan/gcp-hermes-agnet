---
name: it-vpn-access-request
description: "Handle VPN access requests — verify identity, check policy, raise ticket"
agent_name: ITHelpdeskAgent
trigger: "When user requests VPN access, reports VPN issues, or asks about remote access setup"
tags: [it, vpn, access, helpdesk]
version: 1.0.0
author: hermes-seed
---

# IT Helpdesk: VPN Access Request

## When to Use
When a user requests new VPN access, cannot connect to VPN, or asks how to set up remote access.

## Steps
1. Confirm the user's employee ID and department (required for access policy check).
2. Check the IT runbook (RAG knowledge base) for the current VPN policy — specifically whether the user's role qualifies for VPN access.
3. If access is approved by policy:
   a. Raise an IT ticket with subject: `VPN Access Request — [Employee ID] — [Date]`
   b. Include the user's manager's email in the ticket (ask if unknown)
   c. Set ticket priority: Normal (urgent if production incident-related)
4. If access is NOT approved by policy:
   a. Explain which policy applies
   b. Provide the exception request form link from the runbook
5. Provide the user an ETA (standard SLA: 1 business day for new access).

## Example Query
> "I need VPN access to work from home, how do I get it set up?"

## Pitfalls
- **Contractor vs employee**: Contractor VPN access requires a separate approval chain — check the runbook for the contractor access policy specifically.
- **MFA required**: Always mention that MFA must be enrolled before VPN is provisioned. Users often skip this and then report the VPN "not working".
