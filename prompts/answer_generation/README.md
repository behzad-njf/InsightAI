# Answer generation prompts (Phase 6)

File-based templates loaded by `insightai.infrastructure.prompts.loader` — not embedded in Python.

| File | Role |
|------|------|
| `system.md` | Grounding rules: no invented numbers, cite row count, JSON output shape |
| `user.md` | Per-request template with question, SQL, metadata, and formatted rows |
| `stream_system.md` | Same grounding rules; **plain prose** output for SSE streaming |
| `stream_user.md` | Same placeholders as `user.md`; instructs plain-language response |

## Placeholders (`user.md`)

| Placeholder | Source |
|-------------|--------|
| `{question}` | Original natural language question |
| `{sql}` | Executed read-only SQL |
| `{row_count}` | `QueryResult.row_count` |
| `{truncated}` | `QueryResult.truncated` (`yes` / `no`) |
| `{column_names}` | Comma-separated column names from `QueryResult.columns` |
| `{result_table}` | Markdown table from `format_query_result_for_prompt()` (sampled when large) |

## Row sampling (Phase 6.3)

When in-memory rows exceed `INSIGHTAI_ANSWER_MAX_PROMPT_ROWS` (default 50), `sample_rows_for_prompt()` picks **head + tail + evenly spaced middle** rows so the model sees the full range—not only the first rows. A footnote in `{result_table}` states how many rows were sampled.

Override per request via `AnswerGenerationRequest.max_display_rows` or `GenerateAnswerRequest.max_display_rows`.

## Output contract

**Sync (`generate`):** The model must return JSON with: `answer`, `summary_bullets`, `row_count_cited`, `truncation_noted`, `caveats`.

**Stream (`generate_stream`):** Uses `stream_system.md` / `stream_user.md` — plain natural language only (no JSON). The API assembles the final `AnswerGenerationResult` from streamed tokens.

## Security note

Cell values are untrusted (second-order prompt injection). The system prompt instructs the model to treat them as data only. Limit rows passed into the prompt in production (see `format_query_result_for_prompt`).
