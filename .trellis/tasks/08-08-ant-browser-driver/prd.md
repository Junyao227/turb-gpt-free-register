# 接入 Ant Browser 注册驱动

## 目标

将本地 Ant Browser 的指定浏览器 Profile 接入注册流程，使用户可在 WebUI 选择 `ant_browser` 驱动。该驱动启动 Ant Browser Profile、通过其 CDP 地址连接 Selenium，并复用既有浏览器注册页面流程。

## 已确认事实

- 当前“本地指纹浏览器”页面配置的是项目内置 CloakBrowser；RoxyBrowser 另有独立配置页。
- 当前注册分发位于 `main.py`，只支持 protocol、Roxy、Cloak、Browser Use 和 Skyvern。
- Ant Browser 本地 Launch API 的 `POST /api/launch` 可以用 Profile ID 启动实例，并返回 `cdpUrl`、调试端口和启动状态。
- Ant Browser 必须有与 Selenium ChromeDriver 同主版本的 Chromium 内核；本次默认内核和 ChromeDriver 对齐到 `151.0.7922.77`。

## 需求

1. 新增独立 `config/ant_browser.py`，在 WebUI 中作为“Ant Browser”配置组显示。
2. 用户必须能配置本地 API 地址、可选 API Key、Profile ID、启动超时和保留浏览器开关；Profile ID 为空时启动应给出明确配置错误。
3. Ant 驱动须调用 `POST /api/launch` 启动指定 Profile，并验证 API 成功、浏览器调试已就绪和 CDP 地址有效。
4. Selenium 应附着到 Ant Browser 返回的 CDP 地址，复用既有 Roxy 浏览器注册流程的页面交互、OTP、会话提取和账号保存能力。
5. 注册账户的扩展信息须记录 Ant Profile ID 与非敏感启动元数据；不得记录 API Key。
6. 默认不关闭用户在任务前已启动的 Ant Profile；本次驱动启动的 Profile 仅在“保留浏览器”关闭时停止。无论如何均不得删除 Ant Profile。
7. 在 `REGISTRATION_DRIVER` 支持 `ant_browser`，并保持已有驱动行为不变。

## 验收标准

- [ ] WebUI 可保存并重新加载 Ant Browser 配置，API Key 仅保存到 `.env` 且不在读取接口中明文返回。
- [ ] `REGISTRATION_DRIVER=ant_browser` 能启动配置的 Profile、附着 Selenium 并进入既有浏览器注册流程。
- [ ] 启动 API 的无效响应、未就绪状态、无 CDP 地址和网络错误均产生可诊断错误，且不泄露 API Key。
- [ ] 任务结束时仅按策略停止本次启动的 Ant Profile；预先运行的 Profile 不会被停止。
- [ ] Ant API 客户端的启动、鉴权、响应解析和清理策略存在单元测试。
- [ ] 现有 Roxy、Cloak、Browser Use、Skyvern 和 protocol 分发分支的代码不发生功能改写。

## 范围外

- 将 Ant Browser 复用于 Codex OAuth 自动授权。
- 修改现有其他驱动的注册页面行为。

## 扩展：自动托管 Ant Profile

用户要求 Ant Browser 支持与 RoxyBrowser 相同的按任务实例生命周期。此扩展取代上方原先排除的 Profile 创建、删除与批量维护限制。

### 需求

1. 新增 Profile 模式：`managed` 自动创建实例，`existing` 使用 `ANT_BROWSER_PROFILE_ID` 指定的实例；默认使用 `managed`。
2. `managed` 模式为每个注册任务创建唯一 Profile，并将任务传入的代理写入 `profile.proxyConfig`；未提供代理时明确使用 `direct://`。
3. 创建请求使用 Ant LaunchServer `POST /api/profiles` 并直接使用返回的 Profile ID 调用启动接口；不得依赖实例名称二次查询。
4. 任务结束时，托管 Profile 按配置停止并删除；默认删除。保留浏览器或关闭自动删除时，Profile 必须保留。
5. `existing` 模式继续沿用既有行为：Profile ID 必填，预先运行的实例不会被停止或删除。
6. 自动创建的 Profile 使用 Ant Browser 的默认内核，使用唯一、非邮箱的名称和固定标签；不得把 API Key、完整代理凭据或完整 API 响应写入账号记录。
7. WebUI 需要清楚展示模式、Profile ID 在不同模式下的要求、删除策略和说明文字。
8. Ant 默认内核升级时，必须先在隔离临时目录下载并验证新版 Chromium，再登记为默认内核；已有且显式绑定旧内核的 Profile 不自动迁移。

### 验收标准

- [ ] `managed` 模式在 API 请求中传递任务代理和安全的 Profile 元数据，并返回由本轮创建的 Profile ID/CDP endpoint；Selenium 附着后仅由注册层跳转一次启动 URL。
- [ ] 托管 Profile 的清理顺序为 Selenium 断开、stop、delete；失败只记录脱敏警告，不覆盖注册结果。
- [ ] `existing` 模式的创建/删除 API 均不会被调用，且现有测试继续覆盖原清理归属。
- [ ] 创建、启动、停止、删除及 HTTP/JSON 失败的客户端单元测试覆盖请求体、认证头和错误脱敏。
- [ ] WebUI 的配置写入/读取覆盖新增字段，API Key 仍只保存于 `.env`。
- [ ] 临时托管 Profile 能使用默认 Chromium `151.0.7922.77` 附着 Selenium，ChromeDriver 版本也为 `151.0.7922.77`。
