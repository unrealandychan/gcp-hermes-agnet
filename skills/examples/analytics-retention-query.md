---
name: analytics-retention-query
description: "Query BigQuery for user retention rates by cohort"
agent_name: AnalyticsAgent
trigger: "When user asks for retention rate, cohort analysis, or user drop-off metrics"
tags: [analytics, bigquery, retention, cohort]
version: 1.0.0
author: hermes-seed
---

# Analytics: Retention Query

## When to Use
When the user asks about user retention, cohort drop-off, weekly/monthly active user trends,
or any question involving "how many users came back after X days/weeks".

## Steps
1. Ask the user which time window they want (weekly / monthly) and the signup cohort date range if not specified.
2. Identify the relevant BigQuery dataset and table — typically an `events` or `sessions` table.
3. Write a cohort-based retention SQL query:
   ```sql
   WITH cohort AS (
     SELECT user_id, DATE_TRUNC(first_seen, WEEK) AS cohort_week
     FROM `project.dataset.users`
   ),
   activity AS (
     SELECT user_id, DATE_TRUNC(event_date, WEEK) AS activity_week
     FROM `project.dataset.events`
   )
   SELECT
     c.cohort_week,
     DATE_DIFF(a.activity_week, c.cohort_week, WEEK) AS weeks_since_signup,
     COUNT(DISTINCT a.user_id) AS retained_users
   FROM cohort c
   JOIN activity a USING (user_id)
   GROUP BY 1, 2
   ORDER BY 1, 2
   ```
4. Execute via the BigQuery tool.
5. Return results as a table with % retention per cohort week.

## Example Query
> "Show me the retention rate for users who signed up in January, weekly breakdown"

## Pitfalls
- **Missing date range**: Always confirm the cohort date range before running — unbounded queries on large tables can be expensive.
- **Time zone**: Check whether the table stores UTC or local time; mismatches cause off-by-one cohort errors.
- **NULL user_id**: Filter out `user_id IS NOT NULL` to avoid skewing the cohort count.
