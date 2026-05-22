# Education vertical — semantic starter pack

> **Example only** — not loaded automatically. Copy entries into:
>
> - [`../trusted_metrics.yaml`](../trusted_metrics.yaml)
> - [`../example_queries.yaml`](../example_queries.yaml)

## Files

| File | Contents |
|------|----------|
| [`trusted_metrics.yaml`](trusted_metrics.yaml) | `active_student_count`, campus/classroom aggregates |
| [`example_queries.yaml`](example_queries.yaml) | Classroom headcount, campus count, incident UNION patterns |

All samples use **placeholder names** (`Example` classroom, `Campus A` campus) — rename to match your `school_classroom.classroom_name` and `school_school.title` values.

## Quick start

```bash
# Validate SQL in the example pack (parse only)
insightai-semantic-validate --path config/semantic/examples/education

# After copying into active config, test matching
insightai-semantic-test-match \
  --path config/semantic \
  --question "How many kids are in the Example classroom?"

# Enable in .env
# INSIGHTAI_SEMANTIC_ENABLED=true
```

## Copy workflow

1. Merge `metrics:` / `example_queries:` blocks from the files above into the parent YAML (or replace empty `[]` lists).
2. Replace `Example` / `Campus A` with real names from your database.
3. Run `insightai-semantic-validate --path config/semantic`.
4. Set `INSIGHTAI_SEMANTIC_ENABLED=true` and restart the API.

## Alignment with Knowledge/

These assets mirror patterns in:

- [Knowledge/classroom_enrollment_counts.md](../../../Knowledge/classroom_enrollment_counts.md)
- [Knowledge/campus_student_counts.md](../../../Knowledge/campus_student_counts.md)
- [Knowledge/student_incident_reports.md](../../../Knowledge/student_incident_reports.md)

**Knowledge/** = narrative RAG rules. **config/semantic/** = approved SQL the matcher can return without an LLM.
