---
name: hr-pto-balance-query
description: "Look up PTO balance and explain accrual policy for an employee"
agent_name: HRAgent
trigger: "When user asks about PTO balance, vacation days remaining, or leave accrual"
tags: [hr, pto, leave, policy]
version: 1.0.0
author: hermes-seed
---

# HR: PTO Balance Query

## When to Use
When a user asks how many PTO days they have left, how PTO accrues, or whether a specific
type of leave (sick, vacation, parental) counts against their balance.

## Steps
1. Look up the PTO policy in the HR knowledge base — confirm the accrual rate for the user's employment type (full-time / part-time / contractor).
2. If the user is asking about their specific balance: explain that real-time balances are in the HRIS system (provide the link from the knowledge base).
3. Explain the accrual policy clearly:
   - Accrual rate (e.g. 1.5 days/month)
   - Max carryover
   - Blackout periods (if any)
4. If the user has a leave request: confirm the request process (HRIS system link + manager approval requirement).
5. For edge cases (e.g. parental leave, bereavement): retrieve the specific policy section from the knowledge base and quote it directly.

## Example Query
> "How many vacation days do I have left this year? And can I carry them over?"

## Pitfalls
- **Don't invent numbers**: Never state a specific balance — always direct users to the HRIS system for real-time figures.
- **Leave type matters**: "PTO", "vacation", "sick leave", and "personal days" may be separate buckets — clarify which the user means.
