# 参考 gpt-upi 优化 iCloud 工具 UI

## Goal

参考 `D:\VsCode-Code\turb-gpt-free-register\kuozhan\gpt-upi` 的管理后台视觉和交互风格，优化 `icloud-hme-local-toolkit/extracted/mail-code-dashboard` 的本地 iCloud 隐藏邮箱收件台 UI，让批量生成、库存管理、取码 URL 导出、收件状态和后续部署管理更清晰、更像一个可运营后台。

## User Value

当前 iCloud 工具已经具备批量生成隐藏邮箱、收件、JSON/网页收件接入等功能，但页面仍偏工具脚本风格。用户后续计划部署到服务器，并把邮箱取码 URL 提供给买家，因此管理后台需要更清晰地呈现库存、状态、操作入口和导出结果，降低批量运营时的误操作成本。

## Confirmed Facts

- 参考项目路径：`D:\VsCode-Code\turb-gpt-free-register\kuozhan\gpt-upi`
- 当前目标项目路径：`D:\VsCode-Code\turb-gpt-free-register\kuozhan\icloud-hme-local-toolkit\extracted\mail-code-dashboard`
- `gpt-upi` 是 Next.js + shadcn/Tailwind 风格项目。
- 可参考的 UI 结构包括：
  - `src/components/app/app-frame.tsx`：后台框架、顶部栏、侧边导航、页面标题区。
  - `src/components/app/metric-card.tsx`：圆角指标卡。
  - `src/components/app/status-badge.tsx`：带状态圆点的徽章。
  - `src/components/app/admin-client.tsx`：管理卡片、操作区、搜索、表格、分页和设置卡片。
  - `src/app/globals.css`：柔和背景、品牌色、圆角、阴影、滚动条和动效。
- 当前 iCloud 工具是单文件 HTML/CSS/JS 页面，不应为了 UI 优化强制迁移到 Next.js。
- 用户补充：后续会部署到服务器，让买家通过 URL 直接取码；因此 UI 要兼顾“运营管理后台”和“公开取码入口”的展示质量。
- 用户提供过服务器连接信息和密码；这些属于敏感信息，不进入任务文档、代码注释或日志。

## Requirements

- 保留当前 `mail-code-dashboard` 的单文件运行方式和已有功能，不因为 UI 优化重构成 Next.js。
- 借鉴 `gpt-upi` 的后台视觉语言：
  - 柔和浅色背景。
  - 大圆角卡片。
  - 顶部品牌栏或管理框架。
  - 指标卡展示总数、未使用、已使用、未读、iCloud 登录态、自动补货状态等关键数据。
  - 状态徽章统一显示等待中、收件中、成功、警告、失败。
  - 操作按钮分层：主操作、次操作、危险操作视觉上清晰区分。
- 优化邮箱列表展示：
  - 未使用、已使用、垃圾箱仍然保留。
  - 每个邮箱卡片应更适合批量操作，突出邮箱、状态、验证码、最近邮件、标签、网页取码 URL、JSON URL。
  - 支持快速复制邮箱、复制网页 URL、复制 JSON URL。
- 优化导出区域：
  - 明确区分“完整账号导出”和“买家取码 URL 导出”。
  - 买家取码 URL 导出格式应易读，例如 `邮箱----网页URL----JSON URL`。
- 优化部署后的公开取码页 UI：
  - `open.php` 网页取码入口要有干净的邮件列表展示。
  - `feed.php` 保持 JSON 输出，不受后台样式影响。
- 不暴露敏感信息：
  - 不在页面展示主邮箱 IMAP 密码、iCloud cookie、服务器 SSH 密码。
  - 公开取码页只展示目标邮箱和邮件/验证码内容。

## Acceptance Criteria

- [ ] iCloud 工具仍可通过当前本地服务直接打开，不需要 Next.js 构建链。
- [ ] 页面整体视觉参考 `gpt-upi`：柔和背景、大圆角卡片、指标卡、状态徽章、清晰操作区。
- [ ] 批量邮箱列表比当前更适合运营使用，关键状态和操作入口一眼可见。
- [ ] 后台提供清晰的买家 URL 导出入口，导出格式包含邮箱、网页 URL、JSON URL。
- [ ] 公开网页取码入口具备可读的邮件列表样式，JSON 入口仍返回机器可读结构。
- [ ] 现有 iCloud 隐藏邮箱生成、读取转发邮箱、读取 JSON 收件、导入导出、分组和垃圾箱功能不被破坏。
- [ ] UI 中不展示或泄露 cookie、IMAP 授权码、服务器 SSH 密码等敏感信息。

## Out of Scope

- 不把当前单文件项目整体迁移成 Next.js/shadcn 工程。
- 不实现登录系统、支付系统或完整买家账号体系。
- 不在任务文档中保存服务器密码或连接凭据。

## Open Question

- 是否这次 UI 优化要同时做“管理后台暗色模式”？推荐暂不做，先把浅色运营后台做好；暗色模式会增加 CSS 和测试成本。
