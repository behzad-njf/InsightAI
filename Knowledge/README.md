# Knowledge base

Put your organization's reference documents here so InsightAI can answer **policy, help, security, and product** questions without SQL.

## Supported formats

| Format | Extensions |
|--------|------------|
| Markdown | `.md`, `.markdown` |
| Plain text | `.txt` |
| PDF | `.pdf` (requires `pip install 'insightai[rag]'`) |

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
