# InsightAI demo apps

Simple clients to test a **running** InsightAI API.

## 1. Command line (recommended)

```bash
# Terminal 1 — API
source .venv/bin/activate
uvicorn insightai.main:create_app --factory --reload

# Terminal 2 — ask a question
python scripts/ask.py "How many active classrooms are there?"
python scripts/ask.py --stream "How many students per classroom?"
python scripts/ask.py --include-sql "List classroom names"
python scripts/ask.py   # interactive mode
```

If API auth is enabled:

```bash
export INSIGHTAI_API_KEY=your-key
python scripts/ask.py "Your question"
```

Options: `--api-url`, `--timeout` (default 300s), `--stream`, `--include-sql`.

## 2. Browser UI

```bash
# Terminal 1 — API (development enables CORS for the demo UI)
uvicorn insightai.main:create_app --factory --reload

# Terminal 2 — static UI
python apps/serve_demo.py
```

Open http://127.0.0.1:8765 — ChatGPT-style UI with **New chat**, sidebar history (stored in the browser), and server **sessions** (`POST /api/v1/chat/sessions` + streaming). Configure API URL/key under **Settings**.

## Requirements

- `.env` configured (`GROQ_API_KEY`, database connection)
- API healthy: `curl http://localhost:8000/api/v1/health`
