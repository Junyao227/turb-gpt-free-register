# Implementation Plan

## 1. Safety Baseline

- [x] 记录 `HEAD`、`upstream/main`、`origin/main`、工作区状态和 diff 统计。
- [x] 建立包含 tracked、staged、unstaged、untracked 文件的本地可恢复快照。
- [x] 验证快照可枚举，记录恢复步骤。

## 2. Merge Upstream History

- [x] 在安全基线上合并 `upstream/main@42ace02`。
- [x] 解决已提交历史的 6 个已知冲突，优先建立上游最新基础能力。
- [x] 检查上游新增文件、依赖和配置均进入结果。

## 3. Reapply Local Work

- [x] 重新应用合并前的未提交改动。
- [x] 分类解决配置、数据库、邮箱/注册、WebUI 和测试冲突。
- [x] 保留 CDK 管理完整调用链。
- [x] 保留邮箱池完整调用链。
- [x] 保留 Pay153 完整调用链。
- [x] 保留支付/提链服务及 providers。

## 4. Cross-layer Review

- [x] 核对配置声明、导出、编辑器字段和环境变量存储。
- [x] 核对后端 API 路由与现代/旧版 UI 调用。
- [x] 核对数据库迁移与本地字段/状态兼容。
- [x] 搜索并清除冲突标记、重复绑定和失效导入。

## 5. Validation

- [x] 运行 Python 编译/导入检查。
- [x] 运行上游新增功能相关测试。
- [x] 运行 CDK、邮箱池、Pay153 和 WebUI 定向测试。
- [x] 运行 `services/paylink` 测试。
- [x] 启动 WebUI 并完成关键接口 smoke test。
- [x] 运行完整测试集或记录不可执行的环境限制。

## Risk and Rollback Points

- 数据库由文件存储升级为 SQLite，是最高风险点；必须验证迁移和旧数据读取。
- 两套大 HTML 同时包含大量内联 JS，需用测试与静态搜索防止覆盖本地功能。
- 在快照验证完成前，不进入实际合并。
- 不推送远程；用户已授权创建本地 checkpoint/merge commit。
