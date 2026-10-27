# Install Research Nexus v0.7.2 / 安装与升级

This is a **Windows x64 source kit**, not a signed installer. It includes RN source,
the reviewed literature template and license documents. It does not bundle Node.js,
Python, Electron, Zotero, OpenResearch, Google Drive or personal data.

## Windows 安装

1. 安装 Windows 10/11 x64、Node.js **22.12+**（含 npm）、Python **3.10+**（含 pip）及 Git，并确认新 PowerShell 能运行 `node --version`、`npm --version`、`python --version`。
2. 从 [v0.7.2 Releases](https://github.com/shwhwhwh/research-nexus/releases/tag/v0.7.2) 下载 `research-nexus-v0.7.2-windows-source.zip` 和 `SHA256SUMS.txt`。核对下列哈希与校验文件中的 ZIP 行一致。

```powershell
Get-FileHash "$HOME\Downloads\research-nexus-v0.7.2-windows-source.zip" -Algorithm SHA256
Expand-Archive -LiteralPath "$HOME\Downloads\research-nexus-v0.7.2-windows-source.zip" -DestinationPath "$HOME\Apps\RN-0.7.2"
Set-Location "$HOME\Apps\RN-0.7.2\research-nexus"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
npm start
```

3. Setup 从 npm / PyPI 安装依赖，并使用 Windows 自带的 .NET Framework 编译本地窗口组件，因此首次安装需要网络。遇到 Python 路径问题，可追加 `-Python "C:\path\to\python.exe"`。依赖安装和组件编译成功后，双击 **Start Research Nexus.vbs** 启动。
4. RN 中打开 **系统模板**，选择内置 Template 01 或导入包内 `system-templates/literature-workspace.rn-system.json`。按 [中文模板指南](docs/SYSTEM_TEMPLATE.zh-CN.md) 配置自己的账号、本地软件与同步目录。
5. 自动构建器需要自己的本机 Agent 授权，模型调用沿用相应账号并可能消耗额度；参见 [自动构建指南](docs/AUTO_BUILD.zh-CN.md)。没有密钥或登录状态随包分发。

## Upgrade / 升级

退出 RN（包括托盘），并备份旧安装目录及 `data/`。新版解压到独立的新目录并先运行 Setup；保留旧目录作为恢复点。需要延续原配置时，在两份 RN 均退出后，将备份的 `data/` 复制到新目录；DPAPI 密钥仅可由原 Windows 用户在兼容环境解密。不要覆盖正在运行的安装目录。历史预览版未提供通用降级迁移，升级后先核对配置和连接，再启用定时归档。

## Rights / 许可

Copyright © 2026 Rui Li (@shwhwhwh). All rights reserved, with free personal study,
noncommercial experiments and voluntary improvements under [LICENSE](LICENSE).
All owner-controlled code in this distribution, including earlier self-owned code, is offered under license 1.1. Commercial rights not already held require [separate written authorization](COMMERCIAL_LICENSE.md).
Contributions follow [PP-CLA-1.0](CONTRIBUTOR_AGREEMENT.md), with contributor authorship retained.

**既有有效的 RN MIT 授权继续保留原有范围的权限，包括商业使用；当前官方发行对全部自有代码提供许可 1.1。**
新版本号、撤下旧 Releases、添加新许可都不撤回既有授权。具体边界见
[LICENSE_HISTORY.md](LICENSE_HISTORY.md)、[LICENSING.json](LICENSING.json) 和 `LICENSES/`。
当前官方安装入口只推荐此版本；历史视频仅是旧版 Template 01 的功能示意。
