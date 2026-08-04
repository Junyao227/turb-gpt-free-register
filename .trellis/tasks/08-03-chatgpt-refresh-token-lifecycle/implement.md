# Implementation Plan: ChatGPT OAuth Refresh Token 生命周期

## Context Loading Order

1. `.trellis/tasks/08-03-chatgpt-refresh-token-lifecycle/implement.jsonl`
2. `.trellis/tasks/08-03-chatgpt-refresh-token-lifecycle/prd.md`
3. `.trellis/tasks/08-03-chatgpt-refresh-token-lifecycle/design.md`
4. `.trellis/tasks/08-03-chatgpt-refresh-token-lifecycle/research/code-map.md`

## Ordered Checklist

### 1. Confirm OAuth capture capability

- Trace Browser Use, Roxy and Cloak registration completion paths.
- Identify the actual authorization-code/PKCE callback path and verify which client ID, redirect URI and verifier apply.
- Identify the reauthentication path that can renew ChatGPT OAuth credentials.
- Record unsupported paths explicitly; session `accessToken` alone does not create a refresh capability.

### 2. Add shared token lifecycle service

- Define `chatgpt_oauth_tokens` constants, status strings and JSON-safe normalization.
- Implement merge semantics for token responses, including refresh token rotation and omitted refresh token preservation.
- Implement a refresh-grant client using the confirmed OAuth context.
- Return redacted errors and result summaries only.

### 3. Extend account persistence

- Add account-extra read/merge/update helpers under the existing account lock.
- Extend successful registration and reauthentication persistence to attach lifecycle data when supplied.
- Persist top-level access token and nested lifecycle payload together.
- Extend JSON/batch archive output without changing existing plain-text token output.

### 4. Expose refresh actions

- Add single-account and bulk WebUI endpoints.
- Enforce account eligibility using the nested ChatGPT refresh token only.
- Add compact list status fields and on-demand secret handling where required.
- Add matching controls and result feedback to modern and legacy account pages.

### 5. Add tests

- Test token normalization and source separation from mailbox/Codex refresh tokens.
- Test refresh success with rotation and without rotation.
- Test refresh failure persistence, eligibility skipping and historical-row compatibility.
- Test registration/reauth persistence when refresh-token capture is available and unavailable.
- Test single/bulk WebUI actions, redaction, and both UI controls.

### 6. Verify and review

- Run Python compilation for touched modules.
- Run focused account, registration, reauthentication and WebUI tests, followed by the full suite.
- Review diffs for full token values in logging, list payloads and user-facing error text.
- Perform an authenticated browser check for both UI variants.

## Rollback Points

- Keep the existing access-token-only registration success path operational until OAuth capture has been verified.
- Gate each browser backend independently if its OAuth callback context differs.
- Revert the new refresh action while preserving the stored nested data if endpoint integration causes regressions.

## Start Gate

Before `task.py start`, review the PRD, design and implementation plan and confirm the OAuth capture strategy for the active registration backend.
