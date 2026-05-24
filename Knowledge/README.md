# Knowledge base

Put your organization's reference documents here for **domain-specific guidance**.

- **RAG / chat** — policy, help, security, and product answers without SQL.
- **SQL generation** — when `INSIGHTAI_SQL_KNOWLEDGE_CONTEXT_ENABLED=true`, matching chunks are injected into the SQL prompt (table names still come from your schema markdown, not from `prompts/sql_generation/`).

Examples (keep product-specific table and API details here, not in generic prompts):

- **`sql_never_guess_schema.md`** — **never invent columns**; use `schema/database_schema.md` + other Knowledge files first
- `classroom_roster_queries.md` — who is in a classroom
- `classroom_enrollment_counts.md` — per-classroom / top-N counts via `school_classroomchild` (not `general_post_classrooms`)
- `classroom_observations.md` — observation counts/lists via `school_observation` (not annual verification)
- `student_activity_feedback.md` — activity feedback per student via `school_studentactivityfeedback`
- `student_incident_reports.md` — incident reports: `school_behavioral` + incident-type activity feedback
- `student_queries.md` — students by `Student` role, oldest/youngest by `accounts_user.birthday`
- `student_example_questions.md` — 100 sample questions for testing chat/SQL/RAG
- `student_status_reference.md` — `student_status` enum codes → Active, Inactive, Withdrawn, etc.
- `campus_name_matching.md` — always `school_school.title LIKE '%keyword%'`; strip “campus” from user text
- `campus_student_counts.md` — classroom counts via `school_childschool` + `school_school.title` (not `cp.campus_id`)

**Future global learning from errors:** [BRAIN_PHASES.md](../BRAIN_PHASES.md) (Phase B+). **Now (Phase A):** keep fixing patterns here + weekly audit → new/updated `.md` → `insightai-knowledge-sync --force`.

## Supported formats


| Format     | Extensions                                       |
| ---------- | ------------------------------------------------ |
| Markdown   | `.md`, `.markdown`                               |
| Plain text | `.txt`                                           |
| PDF        | `.pdf` (requires `pip install 'insightai[rag]'`) |


## Layout

Use subfolders if you like — ingestion scans **recursively**:

```text
Knowledge/
  README.md              # this file (optional in index)
  about_the_system.md    # what InsightAI is for
  security/
    data_handling.md
  help/
    faq.txt
```

## How it gets loaded

When RAG is enabled (`INSIGHTAI_RAG_ENABLED=true`), the API **ingests this folder on startup** and loads embeddings into the vector store (see `INSIGHTAI_RAG_SYNC_KNOWLEDGE_ON_STARTUP`).

Manual refresh:

```bash
insightai-knowledge-sync
# or: insightai-ingest -i Knowledge -o data/rag_index/chunks.jsonl && insightai-rag-load
```

## Example questions

After startup sync, you can ask:

- "What is this system for?"
- "What is our data retention policy?"
- "How do I get help with enrollment reports?"

Analytical questions (counts, trends) still use the **SQL** path unless you force `route: "both"`.