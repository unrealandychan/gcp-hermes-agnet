---
name: your-skill-name
description: "One sentence: what this skill does"
agent_name: AnalyticsAgent   # Which agent uses this skill (AnalyticsAgent / ITHelpdeskAgent / HRAgent / DeveloperAgent)
trigger: "When the user asks about X, Y, or Z — one sentence describing the trigger condition"
tags: [tag1, tag2]           # Used for search/retrieval
version: 1.0.0
author: your-name
---

# Skill Name

## When to Use
Describe the exact situation where this skill should be applied.
Be specific — vague triggers cause the agent to apply this skill in the wrong context.

## Steps
1. First, do this: [specific action]
2. Then, do this: [specific action with tool name if applicable, e.g. "Use BigQuery tool to run..."]
3. Format the result as: [expected output format]
4. Confirm with the user if: [condition where confirmation is needed]

## Example Query
> "Show me the retention rate for users who signed up in January"

## Pitfalls
- **Pitfall 1**: [what can go wrong and how to handle it]
- **Pitfall 2**: [another edge case]

## Notes
Any additional context the agent should know when applying this skill.
