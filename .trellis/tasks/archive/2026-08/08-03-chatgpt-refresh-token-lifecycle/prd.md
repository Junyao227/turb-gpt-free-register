# ChatGPT OAuth Refresh Token 生命周期

## Goal

让注册成功的 ChatGPT 账号在实际获得 OAuth refresh token 时，将其与 access token、过期信息和来源一并保存；后续刷新 access token 时，持久化服务端轮换后的 refresh token，使账号可长期维护。

## User Value

- access token 过期后可通过已保存的 ChatGPT OAuth refresh token 获取新 token。
- 轮换后的 refresh token 立即持久化，后续刷新始终使用最新有效凭据。
- 账号页可区分“可刷新”“仅有 access token”“刷新失败”三种状态，并支持单个和批量刷新。

## Confirmed Facts

- 当前浏览器注册流程从 `https://chatgpt.com/api/auth/session` 读取 `accessToken`、用户、套餐和过期信息；该响应不是 OAuth token 交换响应。
- 当前 `core.account_export.save_account_data()` 和 `core.db.insert_account()` 只将 ChatGPT access token 作为账号凭据写入。
- 当前账号记录中的 `refresh_token` 来自 Outlook 邮箱 OAuth 素材，供收取邮件使用；它不是 ChatGPT OAuth refresh token。
- `core.codex_oauth.py` 会为 Codex 授权单独保存 refresh token 到 `codex_accounts/`，该凭据与主账号的 ChatGPT token 生命周期分离。
- 参考实现 `any-auto-register` 通过 OAuth/PKCE token 交换获取 ChatGPT access token、refresh token 与 id token，并在刷新后保存轮换 refresh token。

## Requirements

- R1：仅在注册或重新认证流程实际获得 ChatGPT OAuth refresh token 时保存；不得把邮箱 OAuth refresh token 或 Codex OAuth refresh token 当作 ChatGPT refresh token。
- R2：账号数据保存 ChatGPT access token、refresh token、可选 id token、过期时间、最近刷新时间、来源和刷新状态；字段命名必须与现有邮箱 `refresh_token` 明确隔离。
- R3：新增刷新服务，使用保存的 ChatGPT OAuth refresh token 申请新 access token；服务端返回新的 refresh token 时必须在同一次账号更新中替换旧值。
- R4：刷新成功后更新账号当前 access token、过期时间、刷新时间和状态；刷新失败后保存可诊断状态与脱敏错误信息。
- R5：账号页提供单个与批量刷新入口，并在列表或详情中显示可刷新状态；缺少 ChatGPT refresh token 的历史账号保持可用并显示“不可刷新”。
- R6：注册成功、重新认证成功、刷新成功的落盘路径使用同一份 token 生命周期数据结构，避免多处手工拼装字段。
- R7：主账号 JSON、批次归档和导出格式的兼容性须保留；历史账号不要求迁移，读取时须有默认值。
- R8：日志、toast、错误消息、列表摘要和批量结果不得输出完整 access token、refresh token 或 id token。

## Acceptance Criteria

- [ ] AC1：支持的注册/重新认证路径获得 ChatGPT OAuth token 响应后，账号记录保存独立的 ChatGPT refresh token 及关联元数据。
- [ ] AC2：刷新动作请求成功时，账号 access token、expires_at、last_refreshed_at 和服务端返回的 refresh token 被原子更新。
- [ ] AC3：服务端未返回替代 refresh token 时保留当前 ChatGPT refresh token，并记录成功刷新后的 access token 与时间。
- [ ] AC4：refresh token 缺失、失效或网络失败时，账号记录得到脱敏失败状态；原有账号 token 数据保持可读。
- [ ] AC5：新版和旧版账号页均提供单个及批量刷新入口，批量操作跳过不具备 ChatGPT refresh token 的账号并显示统计。
- [ ] AC6：历史账号、仅 access token 账号、Outlook 邮箱 OAuth 账号和 Codex 凭据不会被错误当作 ChatGPT refresh token 刷新。
- [ ] AC7：单元测试覆盖 token 数据归一化、刷新成功、refresh token 轮换、服务端未轮换、刷新失败、落盘兼容和批量跳过逻辑。
- [ ] AC8：全量测试通过，且新增代码和用户可见消息不泄露完整 token 值。

## Out of Scope

- 不为没有 OAuth refresh token 的历史账号伪造或推导 refresh token。
- 不改动 Outlook 邮箱 OAuth 刷新逻辑。
- 不把 Codex OAuth 凭据合并到主账号 ChatGPT token 字段。
- 不实现定时后台刷新；本任务仅提供注册后保存和用户触发的刷新动作。

## Open Questions

- 注册流程需要在哪个 OAuth/PKCE 回调点捕获授权码及 verifier，待实现前根据现有浏览器/Roxy/Cloak 路径做一次代码级确认。
