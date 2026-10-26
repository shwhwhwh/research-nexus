<p align="center"><img src="desktop/nexus-aurora-soft-rainbow.png" width="112" alt="Research Nexus 莫比乌斯环图标"></p>

# Research Nexus

**画出你的科研流程，连接你的工具，搭建属于自己的科研系统。**

[English](README.md) · [架构说明](docs/architecture.md) · [路线图](docs/ROADMAP.md) · [项目归属](OWNERSHIP.md)

Research Nexus（RN）是运行在本地的科研工作台、可视化设计工具和顶层控制器。你可以添加科研网页、API、本地应用和输出目录，画出工具之间的数据流向并说明用途，再调用自己电脑上的 Codex 或 Claude Code，把一条连线生成可以检查、测试和运行的集成方案。

**项目由 [Rui Li（@shwhwhwh）](https://github.com/shwhwhwh) 创建和维护，版权所有 © 2026 Rui Li。** 原创代码、文档及项目图标采用 [MIT 许可证](LICENSE)，允许他人使用和修改，并要求保留版权与许可声明。第三方工具及商标归各自权利人所有。

## 简短演示

[![Research Nexus 独立样例工作空间](docs/assets/demo-poster.png)](https://github.com/shwhwhwh/research-nexus/releases/tag/v0.2.0)

[观看 / 下载演示视频](https://github.com/shwhwhwh/research-nexus/releases/download/v0.2.0/research-nexus-demo.mp4) · [录制方式与中英文字幕稿](docs/DEMO.md)

演示在独立 RN 窗口中录制，全部采用虚构样例，不打开个人账号，不展示真实文献库、研究对话或第三方应用窗口。

## 当前可以实现什么

- **可视化搭建：**添加工具、拖动排列、画连接线，填写数据用途及样例 JSON。
- **本地 Agent 协作：**复用你安装并登录的 Codex / Claude Code，生成版本化的数据流方案，会消耗对应服务的额度。
- **先测试再启用：**查看步骤和样例预览，手动启用指定版本；修改接口、用途等集成约定后，需要重新生成和验证。
- **数据处理与输出：**HTTP JSON 读写、字段选择与映射、筛选、去重、保存 JSON / Markdown。已成功的 POST 通过持久化记录减少重复写入；结果不确定时需要人工核对。
- **持续改进：**把失败记录和改进要求交给 Agent 生成新候选；可切回与当前连线兼容的已测试版本。
- **文献归档：**内置 alphaXiv 收藏 → 去重 → Zotero，支持元数据、PDF 及用户指定的同步目录链接文件。
- **统一工作空间：**网页保留会话和阅读位置；Windows 实验性嵌入已安装的 Zotero / OpenResearch；支持 F11、深浅色与跟随系统、托盘后台运行。

当前方案采用受约束的声明式操作。没有可用 API 的网页仍需开发连接器；画线本身不代表任意服务都已接通。

## Windows 安装

当前为 **Windows x64 早期源码预览版**，尚无签名安装包，不附带第三方科研工具。界面目前为简体中文，仓库提供中英文使用说明。

准备 Windows 10/11 x64、Node.js 22.12+（含 npm）、Python 3.10+（含 pip）及 Git。Python 应可通过 `python` 启动，也可以手动指定路径。需要使用 Agent 时，另外安装并登录本地 CLI；内置适配器目前支持 Windows 的 npm Codex / Claude Code 安装方式。

```powershell
git clone https://github.com/shwhwhwh/research-nexus.git
cd research-nexus
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
npm start
```

指定 Python 位置：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Python "C:\path\to\python.exe"
```

安装脚本会安装 Python 依赖和 Electron，生成不进入版本库的 `runtime.local.json`，并使用 Windows .NET Framework 编译本地窗口组件。请选择可写目录。完成后可运行 `desktop/install-nexus-shortcuts.ps1` 创建桌面和开始菜单快捷方式；也可双击 **Start Research Nexus.vbs** 或 **Start System Designer.vbs**。

## 从第一条 DIY 数据流开始

1. 打开 **系统设计器**，点击 **示例流程**，加入虚构论文与阅读清单节点。
2. 选择连线，写清用途、数据类型和手动 / 每小时 / 每天运行方式，然后保存画布。
3. 选择已安装的本地 Agent，点击 **生成集成方案**。
4. 阅读生成步骤，再点 **测试与预览**。样例测试模拟网络数据，不请求真实 API，不写入外部工具，也不能证明真实接口已经可用。
5. 检查预览，点击 **启用此版本**，再点 **运行连线**。本地输出位于 `data/designer/outputs/<目标节点编号>/`。
6. 用 **添加工具** 接入自己的网页、API 或应用。为节点登记接口基础地址和授权环境变量名，在启动 RN 前设置实际环境变量；不要把密钥写进网址、用途、描述或样例。

自定义网页在 RN 内打开；自定义桌面程序以自身窗口启动，目前未实现对任意应用的通用嵌入。整图执行支持无环、单路输入的数据流。当前“自进化”是经过检查的新候选方案与版本迭代，尚不包含自动修改或部署 RN 自身代码。

## 配置文献归档

在 **连接与设置** 中填写你自己的 alphaXiv Key、Zotero User ID 和允许访问目标库的 Zotero Key，配置已安装应用的程序路径。先检查连接、预览归档内容、手动测试一篇论文，再开启自动归档。

PDF 可使用 Zotero 存储，也可选择已有同步文件夹并在 Zotero 中使用链接文件。Google Drive / OneDrive 同步目录需要相应桌面客户端及登录；RN 本身不提供 Drive OAuth 接口。链接 PDF 主要在桌面使用，不会因此自动进入 Zotero 网页阅读器。Zotero 桌面的元数据同步由 Zotero 自身管理。

归档引擎会根据稳定论文编号及已有条目去重；标题疑似重复会进入人工核对。成功归档后重复运行通常会复用原条目，PDF 失败和远端写入结果不确定等情况需要单独重试或核对。

## 数据、隐私与后台运行

个人配置、文献、浏览器登录状态和生成结果保存在被忽略的 `data/`，**不要提交或分享此目录**。已保存服务密钥由当前 Windows 用户的 DPAPI 保护。Agent 授权继续由本地 CLI 管理；生成集成时，所选连线的描述和样例数据会发送到该 Agent 的模型服务。本地运行不等于完全离线，接口与模型调用仍需联网。

关闭 RN 窗口会隐藏到托盘，在托盘菜单选择 **退出 Research Nexus** 才会结束。定时任务需要 RN 运行且电脑处于唤醒状态；当前没有 Windows 服务或云端调度。其他软件的后台行为取决于各自设置。

## 开发和参与

```powershell
npm run check
npm test
npm run test:designer
```

单元测试使用临时数据；设计器测试使用独立服务与浏览器目录，不打开真实科研工具。`test:alpha` 使用隔离的本地样例检查内嵌阅读位置恢复。参见 [贡献指南](CONTRIBUTING.md)、[安全说明](SECURITY.md) 和 [演示复现](docs/DEMO.md)。

仓库提供可选的 [GitHub Actions 检查模板](docs/ci/check.yml)。启用时，使用具有工作流管理权限的账号或令牌，将其复制到 `.github/workflows/check.yml`。

字体与排版参考 Codex 桌面端；原创柔和渐变扭转环图标的配色方向参考 Antigravity。未包含其应用代码、字体文件、标识或用户提供的参考素材。第三方组件见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
