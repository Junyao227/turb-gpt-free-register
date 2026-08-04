# Design: ChatGPT OAuth Refresh Token 生命周期

## Data Boundary

新增主账号专属 token 生命周期对象，建议放在账号记录的 `extra_json.chatgpt_oauth_tokens`。该对象与以下现有数据严格分离：

- `access_token`：主账号当前 ChatGPT access token，保留现有顶层字段以兼容套餐查询、Codex Agent 和导出。
- `refresh_token`：Outlook 邮箱素材的 OAuth refresh token，继续只用于邮件读取。
- `codex_accounts/*.json`：Codex OAuth 凭据，继续由 Codex 授权模块独立管理。

建议结构：

```json
{
  "version": 1,
  "source": "registration | reauth | manual_refresh",
  "access_token": "...",
  "refresh_token": "...",
  "id_token": "...",
  "expires_at": "ISO-8601 UTC",
  "last_refreshed_at": "ISO-8601 UTC",
  "status": "active | unavailable | failed",
  "last_error": ""
}
```

The `refresh_token` above is scoped inside `chatgpt_oauth_tokens`; no new top-level `refresh_token` key is introduced.

## Data Flow

```text
registration / reauthentication OAuth callback
  -> normalize ChatGPT OAuth token response
  -> persist account.access_token + extra_json.chatgpt_oauth_tokens
  -> account page refresh action
  -> OAuth refresh grant
  -> atomically persist new access token + rotated refresh token + timestamps
```

## Service Contract

Create a focused service responsible for:

1. Normalizing token responses from registration and reauthentication flows.
2. Validating that a refresh token belongs to the ChatGPT OAuth response boundary.
3. Executing the refresh grant with the matching client identifier, redirect URI and required PKCE/OAuth context.
4. Merging a successful response with the stored token object. A response refresh token replaces the prior value; an omitted value preserves the prior value.
5. Producing safe status/error payloads without token values.

Only this service should construct or mutate `chatgpt_oauth_tokens`. Registration, reauthentication, WebUI routes and batch code pass normalized inputs or consume service results.

## Persistence and Compatibility

- Extend `core.db.insert_account()` / account update helpers to accept an account-extra patch or explicit token lifecycle payload without changing the meaning of the existing mailbox fields.
- Write the top-level `access_token` and nested lifecycle payload under one account lock and one JSON write.
- Preserve `注册成功的token.txt` as access-token-only compatibility output.
- Include the nested lifecycle object in JSON account exports and batch archives when present; existing text exports remain unchanged.
- Old rows without `chatgpt_oauth_tokens` resolve to `unavailable` and are skipped by refresh operations.

## WebUI Contract

- Add one single-account refresh action and one bulk refresh action in both UI variants.
- Account-list payloads expose booleans/status summaries only, for example `has_chatgpt_refresh_token` and `chatgpt_token_refresh_status`.
- Full token fields remain behind existing on-demand secret APIs or explicit JSON export paths; list and toast text remain redacted.
- A refresh response reports counts for refreshed, skipped and failed accounts, plus safe reason summaries.

## Failure Handling

- A registration or reauthentication remains successful when refresh-token capture is unavailable; mark lifecycle status `unavailable` rather than failing the account.
- Failed manual refresh writes status/timestamp/redacted error but retains the previously stored token object for inspection and retry.
- Refresh-token rotation is persisted before reporting success to the caller.
- No automatic periodic refresh is introduced in this task.

## Risks and Decisions

- Browser session data alone may contain an access token but no OAuth refresh token. The implementation must add or reuse a real authorization-code/PKCE exchange only where the required code and verifier exist.
- OAuth client, redirect URI and token endpoint assumptions must be sourced from the active registration/reauthentication flow rather than copied from the mailbox or Codex configuration.
- Token responses may rotate refresh tokens; refresh persistence requires a single account-level transaction/lock.

## Capture Result

Current protocol, Browser Use, Roxy, Cloak, and reauthentication completions only expose the browser session access token. They do not preserve a usable authorization-code/PKCE pair, so this task records those accounts as `unavailable` rather than manufacturing a ChatGPT refresh credential. The lifecycle service is ready for any backend that supplies a real OAuth token response with its own client and redirect context.
