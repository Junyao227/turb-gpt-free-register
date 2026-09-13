# 技术设计：Ant Browser 注册驱动

## 架构

新增三个职责明确的模块：

- `config/ant_browser.py`：默认配置与 `.env` 覆盖。
- `core/ant_browser_client.py`：Ant Browser HTTP API、启动结果解析与 Selenium CDP 附着。
- `core/ant_browser_registration.py`：生命周期编排，调用现有 Roxy 浏览器页面流程。

`main.run_registration` 只增加 `ant_browser` 路由。WebUI 配置白名单增加 Ant 字段，页面导航自动按配置组展示。

## 数据流与边界

```
WebUI/.env -> config.ant_browser -> AntBrowserClient
AntBrowserClient -> POST /api/launch -> launch result (profileId, cdpUrl, debugReady)
launch result -> Selenium debuggerAddress -> shared browser registration flow
shared flow -> account export (Ant metadata, no API key)
finally -> optional POST /api/profiles/{id}/stop
```

配置边界负责把字符串转换为明确的 Profile ID、超时和布尔策略。Ant 客户端负责验证第三方 JSON，不将未验证字段传播到注册层。注册层只使用已准备好的 Selenium driver 和最小 Profile 元数据。

## 兼容性与复用

`core/roxy_registration.py` 已包含已维护的 Selenium 页面交互函数，CloakBrowser 当前也按此方式复用。Ant 注册层将复用这些页面交互、OTP、会话提取与账号保存约定，不重写页面选择器或请求协议；Roxy 的公开函数签名和清理行为保持不变。

Ant 的 Selenium 附着使用 Chrome `Options().add_experimental_option("debuggerAddress", host:port)`。CDP URL 必须是本地 `http(s)` URL，连接时只取 hostname/port，避免把 URL 路径、凭据或不受支持协议传给 Selenium。

## 生命周期与清理

启动前调用 `GET /api/profiles/{id}/status` 判断该 Profile 是否已运行：

- 已运行：复用其 CDP endpoint，`started_by_run=False`，默认不停止。
- 未运行：调用启动 API，`started_by_run=True`。
- 任务结束：关闭 Selenium 客户端连接；仅当 `started_by_run=True` 且 `ANT_BROWSER_KEEP_BROWSER_OPEN=False` 时调用 Profile stop API。

不调用任何 Profile 删除接口。

## 配置契约

| 配置 | 默认值 | 用途 |
| --- | --- | --- |
| `ANT_BROWSER_API_BASE` | `http://127.0.0.1:19876` | Ant 本地 API 根地址 |
| `ANT_BROWSER_API_KEY` | 空 | 可选 API Key，存于 `.env` |
| `ANT_BROWSER_API_KEY_HEADER` | `X-Ant-Api-Key` | API Key 请求头名称 |
| `ANT_BROWSER_PROFILE_ID` | 空 | 必填的 Ant Profile ID |
| `ANT_BROWSER_START_TIMEOUT` | `90` | API 和 Selenium 等待上限（秒） |
| `ANT_BROWSER_KEEP_BROWSER_OPEN` | `False` | 本次启动实例是否在完成后保留 |
| `ANT_BROWSER_START_URL` | ChatGPT 登录页 | Ant 启动时打开的页面 |

若 API Key 的实际头名称与默认值不同，用户可以在 WebUI 修改 Header 名称。日志只输出 API 基址、Profile ID 和脱敏 endpoint，不输出 header 值。

## 测试与回滚

使用 `unittest.mock` 模拟 Ant HTTP 响应和 Selenium 构建，不需真实启动 Ant Browser。覆盖成功启动、运行中复用、缺失/未就绪 CDP、API Key header、清理归属和异常信息脱敏。

回滚只需移除新增 `ant_browser` 分发分支与配置/客户端文件；既有驱动不共享 Ant 配置，不会受到数据迁移影响。

## 扩展：自动托管 Profile 设计

### 模式与默认值

`ANT_BROWSER_PROFILE_MODE` 取值为 `managed` 或 `existing`，默认 `managed`。`existing` 保留此前固定 Profile 合约；`managed` 不读取 `ANT_BROWSER_PROFILE_ID`。`ANT_BROWSER_DELETE_MANAGED_PROFILE` 默认 `True`，但 `ANT_BROWSER_KEEP_BROWSER_OPEN=True` 优先保留实例以便调试。

### 数据流

```
registration job proxy
  -> AntBrowserClient.open_profile(proxy)
  -> managed: POST /api/profiles { profile }
  -> POST /api/launch { profileId }
  -> Ant Browser profile/CDP result
  -> Selenium attach -> one navigation to ANT_BROWSER_START_URL -> shared registration flow
  -> driver.quit -> POST /api/profiles/{id}/stop -> DELETE /api/profiles/{id}
```

托管 Profile 的创建请求包含唯一 `profileName`、`tags: ["gpt-registrar", "managed"]`、`proxyConfig` 与 `proxyId: "__direct__"`（仅无代理时）。创建成功后立刻按返回的 Profile ID 调用启动接口；Selenium 附着后由注册层跳转一次 `ANT_BROWSER_START_URL`，避免 Ant 启动页与 Selenium 跳转产生重复标签页。Profile 名称使用随机运行标识，不使用邮箱或任务 Token。

### 客户端边界

`AntBrowserOpenResult` 增加 `created_by_run`，而 `started_by_run` 表示当前调用是否启动了浏览器。客户端负责模式校验、创建请求、原有状态/启动路径、精确 Profile ID 回显校验和清理顺序。注册层只传递任务代理，不读取 Ant JSON。

对于托管 Profile，清理只在本轮创建的实例上执行：先停止（除非 keep-open），再在允许删除时删除。既有 Profile 不会进入删除路径。所有清理错误仅日志告警且脱敏。

### 内核与 ChromeDriver 兼容性

Selenium 通过 CDP 附着 Ant Profile 时，ChromeDriver 必须与该 Profile 的 Chromium 使用相同主版本，优先使用完全相同的 Chrome for Testing 发行号。本次默认内核为 `chrome-151`，版本 `151.0.7922.77`，与 Selenium Manager 缓存的 `chromedriver 151.0.7922.77` 对齐。

升级顺序为：下载到隔离临时目录，验证 ZIP 结构与 `chrome.exe` 文件版本，将已验证目录移入 `chrome/chrome-151`，更新 `config.yaml` 和 SQLite `browser_cores` 的默认项，然后重启 Ant LaunchServer 并用可删除的托管 Profile 进行 Selenium 附着测试。旧 `chrome-148` 目录和显式绑定 `core-chrome-148` 的已有 Profile 保留，用于回滚和兼容。

### 兼容与回滚

默认内核由 Ant Browser 管理；没有 LaunchServer core REST API 不是阻塞项。原固定 Profile 用户设置 `ANT_BROWSER_PROFILE_MODE=existing` 即可恢复此前行为。回滚仅需切换回 `existing`，不会修改已创建的 Ant Profile。
