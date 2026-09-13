# 合并上游更新并保留本地扩展

## Goal

将 `upstream/main` 的最新更新合入当前本地分支，同时完整保留本地已经实现的 CDK 管理、邮箱池、Pay153 与支付/提链功能，并保证主要注册、账号管理和 WebUI 流程可运行。

## Background

- 当前分支：`main`，HEAD 为 `c6477df`。
- 上游：`upstream/main`，当前为 `42ace02`。
- 本地与上游已分叉：本地独有 26 个提交，上游独有 32 个提交。
- 工作区现有约 134 项未提交改动，包含已跟踪修改和未跟踪文件，不能清理、重置或丢弃。
- Git 三方合并预检确认至少 6 个已提交层面的内容冲突：
  - `core/generic_api_mail_client.py`
  - `core/session.py`
  - `webui/app.py`
  - `webui/config_editor.py`
  - `webui/templates/index.html`
  - `webui/templates/index_legacy.html`
- 上游更新覆盖 68 个文件，主要包含 SQLite 存储升级、2FA、邮箱换绑、通用 IMAP、Remail、账号/查询优化、注册与查活改进。

## Requirements

- R1：吸收 `upstream/main@42ace02` 的功能和修复，不遗漏上游新增模块、配置项、依赖和测试。
- R2：保留本地 CDK 管理功能，包括 CPA 文件批量上传、CDK 管理端配置、API 路由及现代/旧版 UI 入口。
- R3：保留本地邮箱池功能，包括 Outlook、通用 API、Cloudflare 域名邮箱等现有来源、分配状态和批量管理能力。
- R4：保留本地 Pay153 集成，包括配置、客户端、Web API、UI 和现有测试。
- R5：保留本地支付/提链服务及各支付线路，不因主项目合并删除或降级 `services/paylink` 及其兼容接口。
- R6：冲突处理应以语义合并为准：共享基础设施吸收上游改进，本地扩展作为附加能力保留，不能简单整文件选择 ours/theirs。
- R7：不得清理或覆盖当前未提交改动；执行合并前必须建立可验证、可恢复的本地快照。
- R8：不推送远程仓库；最终提交动作须遵守用户对 commit 的明确授权。
- R9：对配置、数据库、后端路由和前端调用进行跨层核对，避免只有 UI 或只有后端的半合并状态。

## Acceptance Criteria

- [ ] 当前工作区所有原有改动均可从快照恢复，快照标识和恢复方式明确。
- [ ] 工作树中不存在未解决的 Git 冲突标记或 unmerged paths。
- [ ] `upstream/main@42ace02` 的新增文件和关键功能已纳入合并结果。
- [ ] CDK 管理相关配置、API、前端入口及测试仍存在并通过验证。
- [ ] 邮箱池相关来源、分配/删除接口、前端入口及测试仍存在并通过验证。
- [ ] Pay153 配置、客户端、API、前端入口及测试仍存在并通过验证。
- [ ] `services/paylink` 的本地支付线路与兼容接口保持可用，相关测试通过。
- [ ] 上游 SQLite、2FA、邮箱换绑、IMAP/Remail、查活和注册优化的关键测试通过。
- [ ] 主项目可导入，WebUI 可启动，关键 API smoke test 无启动级错误。
- [ ] 不包含意外删除的本地功能，不推送任何远程分支。

## Out of Scope

- 不重构与冲突无关的现有本地功能。
- 不修改生产服务器或部署环境。
- 不推送到 `origin` 或 `upstream`。

## Decisions

- 用户已明确允许创建仅位于本机、不推送远程的 checkpoint 与 merge 提交。
- 敏感日志、代理数据及运行时文件不进入提交历史；未提交内容使用完整 stash 快照保护，并保留到合并验证完成。
