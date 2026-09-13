# 实施计划：Ant Browser 注册驱动

1. 新建 Ant Browser 配置模块，并将其纳入 `config.reload_all()`。
2. 新建 Ant Browser API 客户端：验证 Profile ID、状态探测、启动、CDP endpoint 解析、Selenium 附着和有归属限制的 stop。
3. 在 Ant 注册层复用 Roxy 注册模块已维护的 Selenium 页面交互函数，保持已有 Roxy/Cloak 流程不变。
4. 新建 Ant 注册编排模块，调用客户端和页面交互流程，并记录非敏感 Ant 元数据。
5. 在注册分发、WebUI 配置白名单和配置帮助文案中增加 `ant_browser`。
6. 添加客户端和路由的单元测试，模拟 Ant API 和共享注册入口。
7. 运行格式/编译、目标测试与完整测试套件；检查所有改动不覆盖已有未提交内容。

## 验证命令

```powershell
python -m compileall config core main.py webui
python -m unittest tests.test_ant_browser_client tests.test_ant_browser_registration
python -m unittest discover -s tests -p "test_*.py"
```

## 风险点

- Ant Browser 的 API 启动成功并不必然代表 CDP 已可连接，客户端必须明确验证调试就绪与 endpoint 格式。
- Profile 若由用户手动启动，错误清理会终止其调试会话；必须以启动前状态识别所有权。
- Roxy 流程较长，抽取共享入口时应先用最小参数化，不重写页面操作或 OTP 逻辑。

## 扩展实施：自动托管 Profile

1. 在 `config/ant_browser.py`、`config/__init__.py`、环境变量白名单和 WebUI 编辑器中加入模式与托管删除配置；默认模式为 `managed`。
2. 扩展 `AntBrowserClient`：构建托管 Profile 请求、解析创建后自动启动结果、维护 `created_by_run`，并实现仅针对托管实例的 stop/delete 清理。
3. 修改 Ant 注册编排，将任务代理传给客户端；账号元数据仅记录安全的 Profile 生命周期信息。
4. 更新客户端和注册单元测试，明确覆盖 managed/existing、代理传递、清理顺序、keep-open 和 API Key 脱敏。
5. 运行 `python -m compileall config core main.py webui`、目标单元测试、WebUI 配置测试和完整测试套件；保留并报告无关既有失败。
6. 下载 Chrome for Testing `151.0.7922.77` 到临时目录，验证归档和 `chrome.exe` 文件版本；将其登记为 Ant 默认内核，保留 `chrome-148` 并备份 SQLite 内核表后重启 LaunchServer。
7. 创建临时托管 Profile 进行 Selenium CDP 附着验证，断言浏览器和 ChromeDriver 均为 `151.0.7922.77`，随后停止并删除测试 Profile。
