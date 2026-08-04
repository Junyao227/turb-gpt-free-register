# ChatGPT OAuth Refresh Token 生命周期 Research

## Current repository persistence

- `core/db.py:_account_line()` exports the main account material with the current ChatGPT access token.
- `core/db.py:insert_account()` persists the top-level access token and, for Outlook sources, copies the mailbox `refresh_token` from the email pool. This field must remain mailbox-scoped.
- `core/account_export.py:fetch_session()` obtains `accessToken` from `https://chatgpt.com/api/auth/session`; this is the present browser-registration completion input.
- `core/account_export.py:save_account_data()` is the shared registration persistence boundary and delegates to `core.db.insert_account()`.
- `core/db.py` uses process-local locking and atomic JSON replacement; lifecycle updates should reuse this boundary.

## Current OAuth boundary

- `core/codex_oauth.py:exchange_codex_token()` exchanges a Codex authorization code for token data.
- `core/codex_oauth.py:build_codex_storage()` stores access, refresh and id tokens in Codex credential storage. It demonstrates token-response persistence but remains a separate credential domain.
- Registration implementations call `save_account_data()` after they have obtained a ChatGPT access token: `core/browser_use_registration.py`, `core/roxy_registration.py`, and `core/cloakbrowser_registration.py`.

## WebUI surfaces

- `webui/app.py:_compact_account_for_list()` intentionally omits full secrets from account rows.
- `webui/app.py:_account_secret_value()` is the existing on-demand secret boundary.
- `webui/templates/index.html` and `webui/templates/index_legacy.html` render account actions and bulk action groups.

## Reference implementation

- `D:/cursor-code/any-auto-register/platforms/chatgpt/chatgpt_registration_mode_adapter.py` persists ChatGPT access, refresh and id tokens after refresh-token registration.
- `D:/cursor-code/any-auto-register/platforms/chatgpt/token_refresh.py` performs the refresh grant and reports token response data.
- `D:/cursor-code/any-auto-register/tests/test_chatgpt_login_session.py` includes refresh-token rotation persistence coverage.

## OAuth capture investigation

- Protocol registration follows `auth.openai.com/authorize/continue` or the ChatGPT callback, then reads `/api/auth/session`. It does not retain a raw OAuth authorization code plus its matching PKCE verifier after the callback.
- Browser Use, Roxy, and Cloak registration paths likewise only return `/api/auth/session.accessToken` at completion.
- `core/account_reauth.py` repeats the session callback flow and also has no independently usable authorization-code/PKCE pair.
- The repository's existing PKCE flow in `core/codex_oauth.py` belongs to the Codex client and remains isolated. Its refresh token must not be copied into the main ChatGPT account record.

## Implemented boundary

- `core/chatgpt_token_lifecycle.py` accepts only a real OAuth token response plus its captured `client_id`, `redirect_uri`, and token endpoint context. Session-only flows are persisted as `unavailable`.
- The lifecycle object is stored in `extra_json.chatgpt_oauth_tokens`; the top-level mailbox `refresh_token` remains unchanged.
- Refresh success atomically writes the current access token and nested lifecycle object. A returned refresh token replaces the previous one; an omitted refresh token is retained.
