# Technical Design

## Merge Boundaries

合并按四层处理：

1. 基础配置与持久化：`config/*`、`core/db.py`、`core/session.py`。
2. 邮箱与注册流程：邮箱 provider、注册、查活、2FA、换绑等模块。
3. WebUI：`webui/app.py`、配置编辑器、现代和旧版模板。
4. 本地扩展：CDK、Pay153、`services/paylink` 及其测试。

## Preservation Strategy

- 合并前记录 HEAD、远程 SHA、完整状态与差异，并创建包含已跟踪和未跟踪内容的可恢复快照。
- 先合并已提交历史中的上游变更，再将未提交工作区变更重新应用到新的合并基线。
- 对共享文件逐段进行语义整合：以上游的新数据模型/流程为基础，把本地 API、配置项和 UI 事件重新接入。
- 对上游未涉及的本地独立模块原样保留，并验证其导入与调用链。

## Conflict Policy

- `core/db.py` 与邮箱池：优先采用上游 SQLite 架构和迁移逻辑，同时迁移/保留本地邮箱池字段、查询和状态语义。
- `core/session.py`：吸收上游请求头、gzip/导航等会话行为，保留本地调用兼容性。
- `core/generic_api_mail_client.py`：合并上游公共收件箱能力与本地邮箱池/取码兼容逻辑。
- `webui/app.py`：保留本地 CDK、邮箱池、Pay153、支付代理路由，同时接入上游 2FA、换绑、筛选和查询接口。
- `webui/config_editor.py`：合并上游配置项，并保留本地 CDK/Pay153 配置分组与敏感值存储规则。
- 两套 HTML：保留本地导航和业务面板，吸收上游控件、批量动作与交互逻辑，检查 DOM ID 和 JS 函数无重复。
- `services/paylink`：上游当前不直接维护该目录，保持本地版本，仅处理共享依赖或入口兼容问题。

## Rollback

- 快照必须独立于工作树合并状态，并记录恢复命令。
- 冲突解决失败时回到合并前 HEAD，再从快照恢复未提交内容。
- 不使用 `git reset --hard`、`git checkout --` 或清理未跟踪文件作为常规步骤。

## Validation

- Git：检查 unmerged paths、冲突标记、diff summary。
- Python：编译/导入检查，运行与冲突模块和保留功能相关的定向测试。
- WebUI：启动 smoke test，验证页面模板和关键 API 注册。
- 最后运行可承受范围内的完整测试集，并单独报告环境性失败。
