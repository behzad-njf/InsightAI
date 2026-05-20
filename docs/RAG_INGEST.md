# RAG document ingestion (Phase 10.2)

The `insightai-ingest` CLI chunks documents, generates embeddings, and writes a **local JSONL index** for Phase 10.3 (pgvector) to load later.

## Supported sources

| Type | Extensions | Notes |
|------|------------|--------|
| Markdown | `.md`, `.markdown` | Split on `#` headings, then size windows |
| Plain text | `.txt` | Size windows with overlap |
| PDF | `.pdf` | Requires `pip install 'insightai[rag]'` (pypdf) |

## Quick start

```bash
pip install -e ".[dev]"

# Offline / CI-friendly (deterministic local embeddings)
INSIGHTAI_EMBEDDING_PROVIDER=local insightai-ingest \
  --input docs/ \
  --output data/rag_index/chunks.jsonl

# Production embeddings (OpenAI)
INSIGHTAI_EMBEDDING_PROVIDER=openai \
OPENAI_API_KEY=sk-... \
insightai-ingest -i ./policies -o data/rag_index/chunks.jsonl
```

## Output layout

```text
data/rag_index/
  chunks.jsonl    # one IngestedChunkRecord per line (text + embedding vector)
  manifest.json # provider, model, dimensions, source file list, chunk settings
```

## Useful flags

```bash
insightai-ingest --help

# Preview chunking without API calls or file writes
insightai-ingest -i docs/ --dry-run

# Tune chunking
insightai-ingest -i docs/ -o out.jsonl --chunk-size 1200 --chunk-overlap 150

# Single file, non-recursive directory scan
insightai-ingest -i readme.md -o out.jsonl
insightai-ingest -i docs/ --no-recursive
```

## Environment variables

See [.env.example](../.env.example) — embedding and RAG chunk settings use the `INSIGHTAI_` prefix:

- `INSIGHTAI_EMBEDDING_PROVIDER` — `local` | `openai`
- `INSIGHTAI_RAG_CHUNK_SIZE` — default `800`
- `INSIGHTAI_RAG_CHUNK_OVERLAP` — default `100`
- `INSIGHTAI_RAG_DEFAULT_INDEX_PATH` — default output path

## Load into pgvector (Phase 10.3)

After ingest, load the JSONL index into PostgreSQL with the **`insightai-rag-load`** CLI:

```bash
pip install -e ".[rag]"   # pgvector Python package + pypdf

# Postgres with pgvector (docker-compose uses pgvector/pgvector:pg16)
INSIGHTAI_RAG_DATABASE_URL=postgresql+psycopg2://insightai:insightai@localhost:5432/insightai \
insightai-rag-load --index data/rag_index/chunks.jsonl

# Tests / offline without Postgres
INSIGHTAI_RAG_VECTOR_BACKEND=memory insightai-rag-load -i data/rag_index/chunks.jsonl
```

| Flag | Purpose |
|------|---------|
| `--index` / `-i` | Path to `chunks.jsonl` (default: `INSIGHTAI_RAG_DEFAULT_INDEX_PATH`) |
| `--backend` | `pgvector` (default) or `memory` |
| `--no-clear` | Upsert without truncating the table first |

The loader reads `manifest.json` beside the JSONL file, ensures the `vector` extension and `rag_document_chunks` table (configurable), builds an HNSW cosine index, and upserts all rows.

### Vector settings

- `INSIGHTAI_RAG_VECTOR_BACKEND` — `pgvector` | `memory`
- `INSIGHTAI_RAG_DATABASE_URL` — writer Postgres URL (falls back to `DB_USER` / `DB_PASSWORD` on PostgreSQL)
- `INSIGHTAI_RAG_VECTOR_TABLE` — table name (default `rag_document_chunks`)
- `INSIGHTAI_RAG_SEARCH_TOP_K` — default retrieval `top_k` for future query path (10.4+)

## Hybrid routing (Phase 10.4)

Enable on the API with:

```bash
INSIGHTAI_RAG_ENABLED=true
INSIGHTAI_RAG_VECTOR_BACKEND=memory   # or pgvector after insightai-rag-load
```

`POST /api/v1/chat` and `POST /api/v1/ask` then:

| Route | Behavior |
|-------|----------|
| `sql` | Schema → SQL → execute → answer (default when signals are ambiguous) |
| `rag` | Embed question → vector search → document answer (no SQL) |
| `both` | SQL pipeline + retrieved excerpts merged into the answer prompt |

Optional request field `route` forces `sql` | `rag` | `both`. Responses include `route` and `sources` (RAG citations).

Classifier: `INSIGHTAI_RAG_ROUTER_MODE=heuristic` (keyword-based). Empty index fallback: `INSIGHTAI_RAG_FALLBACK_TO_SQL_ON_EMPTY_INDEX=true`.

## LangChain agent path (Phase 10.5)

Optional tool-calling agent instead of the heuristic hybrid router:

```bash
pip install -e ".[langchain]"
INSIGHTAI_RAG_ENABLED=true
INSIGHTAI_LANGCHAIN_AGENT_ENABLED=true
INSIGHTAI_RAG_VECTOR_BACKEND=memory
```

The agent exposes two tools to the LLM:

| Tool | Purpose |
|------|---------|
| `search_documents` | Vector search over ingested policies / help text |
| `run_sql_analytics` | Read-only SQL generate → execute (same safety as the main pipeline) |

Responses use `route: "agent"`. Chat streaming emits `routing` then `done` (no token streaming from the agent yet).

Set `INSIGHTAI_AI_FRAMEWORK=langchain` to register LangChain as the framework adapter (LLM calls still delegate to Groq/OpenAI providers).

## Combined answers with citations (Phase 10.6)

**BOTH** and **RAG** routes attach document sources to the API response:

| Field | Meaning |
|-------|---------|
| `route` | `sql`, `rag`, `both`, or `agent` |
| `sources` | Retrieved chunks with `citation_index` (1-based) |
| `citations` | Indices referenced in the answer text |
| `include_source_excerpts` | Chat request flag to include chunk `excerpt` text |

BOTH answers use dedicated prompts in `prompts/hybrid/` so the LLM merges SQL rows and document excerpts in one JSON response with `source_citations`.

Example chat request:

```json
{
  "question": "Per policy, how many classrooms are on campus?",
  "route": "both",
  "include_source_excerpts": true
}
```
