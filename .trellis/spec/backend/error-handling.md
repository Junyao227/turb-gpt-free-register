# Error Handling

> How errors are handled in this project.

---

## Overview

<!--
Document your project's error handling conventions here.

Questions to answer:
- What error types do you define?
- How are errors propagated?
- How are errors logged?
- How are errors returned to clients?
-->

(To be filled by the team)

---

## Scenario: Codex Agent failure reasons stay visible end-to-end

### 1. Scope / Trigger
- Trigger: Codex Agent Token generation fails after queueing or while the worker is running.
- This spans storage (`core/db.py`), list projection (`webui/app.py`), and account table rendering (`webui/templates/index.html` / `index_legacy.html`).
- The failure row must show the real diagnostic reason, not only the generic status label.

### 2. Signatures
- `update_account_codex_agent(acc_id: int, result: dict | None = None) -> bool`
- `_compact_account_for_list(row: dict) -> dict`
- `_codexAgentCell(r) -> str`
- `GET /api/accounts`

### 3. Contracts
- Failed Codex Agent rows MUST preserve `codex_agent_error` in storage.
- The account list projection MUST expose `codex_agent_error` when present.
- The table cell SHOULD render `codex_agent_error` before `codex_agent_message`.
- `codex_agent_message` remains the human status line (`已入队` / `正在生成...` / `Codex Agent Token 已生成`), while `codex_agent_error` carries the real failure detail.

### 4. Validation & Error Matrix
- `status=failed` and `codex_agent_error` present -> render the failure badge plus the error summary.
- `status=failed` and `codex_agent_error` absent -> fall back to `codex_agent_message` or `agent_runtime_id`.
- `status=running` -> clear any prior error from the live badge display, but do not delete the persisted failure history unless the row is re-queued.
- Worker exception with HTTP 403 / transport error / JSON failure -> store the raw redacted error text in `codex_agent_error`.

### 5. Good/Base/Bad Cases
- Good: `agent_registry_not_enabled` appears in the failed Agent Token row and can be read without opening logs.
- Base: a successful Agent Token row keeps `codex_agent_runtime_id` and action buttons.
- Bad: the table only shows `失败` while the real failure text stays hidden in backend state.

### 6. Tests Required
- Unit test the account projection to ensure `codex_agent_error` survives list serialization.
- Template regression test must assert that Agent failure rendering checks `codex_agent_error` before `codex_agent_message`.
- Smoke-test the browser UI after a failed generation to confirm the row shows a readable error summary.

### 7. Wrong vs Correct
#### Wrong
```python
out["codex_agent_message"] = row.get("codex_agent_message")
```

```javascript
const title = esc(r.codex_agent_message || r.codex_agent_runtime_id || "");
```

#### Correct
```python
out["codex_agent_error"] = row.get("codex_agent_error")
```

```javascript
const detail = r.codex_agent_error || r.codex_agent_message || r.codex_agent_runtime_id || "";
const title = esc(detail);
```

The generic status line is not a substitute for the actual error reason.

---

## Error Types

<!-- Custom error classes/types -->

(To be filled by the team)

---

## Error Handling Patterns

<!-- Try-catch patterns, error propagation -->

(To be filled by the team)

---

## API Error Responses

<!-- Standard error response format -->

(To be filled by the team)

---

## Common Mistakes

<!-- Error handling mistakes your team has made -->

(To be filled by the team)
