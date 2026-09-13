# iCloud批量收件与JSON接入

## Goal

在现有 `mail-code-dashboard` 基础上，同时保留网页收件能力，并新增一个固定模板的 JSON 收件源，使批量创建后的隐私邮箱/收件结果可以统一展示、检索和导出。

## Background

当前项目已经具备：
- 网页收件台和本地状态管理
- iCloud Hide My Email 的 cookie bridge + generator
- 主邮箱 IMAP 收件能力

用户希望最终达到的效果是：
- 仍然能在网页里看收件结果
- 也能接入类似 `https://assurivo.com/console/feed.php?mail=...&pwd=...&limit=...` 的 JSON 数据源
- 批量场景下统一管理结果

该 JSON 源的实际形态是：
- GET 请求
- 通过 query 参数传入 `mail / pwd / limit`
- 返回 JSON 包装
- `data[].body` 里是完整 HTML 邮件体，需要再解析正文/验证码
- 与 `open.php` 的网页查看入口共用同一套账号参数，只是输出格式不同

## Requirements

- 保留现有网页收件功能，不移除现有收件列表、预览和导出流程。
- 新增 JSON 收件源适配能力，支持固定 URL 模板 + 参数形式。
- 允许每条账号/邮箱记录绑定 JSON 源配置。
- JSON 接入后的数据应映射到现有统一消息结构，至少包含邮箱、验证码/正文、标题、时间、来源。
- JSON 源以 GET + query 参数方式接入，优先支持固定模板。
- JSON 返回的 HTML body 需要能被解析出验证码。
- 网页查看与 JSON 接入共用同一套账号参数，但输出入口不同：`open.php` 用于网页查看，`feed.php` 用于程序拉取。
- JSON 收件结果并入现有总列表统一展示，不单独拆分新视图。
- 支持网页查看和 JSON 导出结果。
- 不破坏现有 iCloud 隐私邮箱生成和主邮箱收件流程。

## Acceptance Criteria

- [x] 现有网页收件流程仍可正常使用。
- [x] 系统可从固定模板 JSON 接口拉取收件数据。
- [x] 拉取到的数据可在网页中按现有列表/预览方式展示。
- [x] JSON 收件结果会并入现有总列表，并可与其他来源统一排序和导出。
- [x] 批量场景下可统一查看和导出结果。
- [x] 现有 iCloud 隐私邮箱生成与主邮箱 IMAP 收件不受影响。

## Implementation Notes

- 后端新增 `/api/json-feed/check` 和 `/api/json-feed/messages`，统一适配 `open.php` / `feed.php` URL。
- 前端支持导入、导出并保存 `jsonOpenUrl` / `jsonFeedUrl` / `jsonFeedLimit`。
- JSON feed 更新复用现有 `applyIncomingCode`，所以验证码、状态、分组和未读提醒会并入原总列表。
- iCloud 隐私邮箱标签已由流水号改为随机词组短码；每条本工具生成/同步的 iCloud 记录会补一个随机收件密码，导出基础形态为 `邮箱----密码`。
- 已在本地 mock feed 上验证 HTML body 可解析出 6 位验证码。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
