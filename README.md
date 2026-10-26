<p align="center"><img src="desktop/nexus-aurora-soft-rainbow.png" width="112" alt="Research Nexus ribbon icon"></p>

# Research Nexus

**Draw your research workflow. Connect your tools. Build your own research system.**

[简体中文](README.zh-CN.md) · [Quick start](#quick-start-windows) · [Architecture](docs/architecture.md) · [Roadmap](docs/ROADMAP.md) · [Ownership](OWNERSHIP.md)

Research Nexus (RN) is a local desktop workspace, visual designer, and top-level controller for a DIY research system. Add research websites, APIs, desktop tools, and output folders; draw the direction of data flow and describe its purpose. Your locally installed Codex or Claude Code helps turn a selected connection into a versioned integration plan that RN can validate, preview, and run.

Created and maintained by **[Rui Li (@shwhwhwh)](https://github.com/shwhwhwh)**. Copyright © 2026 Rui Li. [MIT License](LICENSE).

## See it in action

[![Research Nexus isolated sample workspace](docs/assets/demo-poster.png)](https://github.com/shwhwhwh/research-nexus/releases/tag/v0.2.0)

[Watch / download the short demo](https://github.com/shwhwhwh/research-nexus/releases/download/v0.2.0/research-nexus-demo.mp4) · [Demo notes and bilingual transcript](docs/DEMO.md)

The demo records an isolated RN window with fictional sample data. It does not open personal accounts or show a real literature library, research conversation, or third-party application window.

## What you can do today

- **Design data flows:** drag tools onto a canvas, connect them, describe their purpose, and supply sample JSON.
- **Use local agents:** generate an integration plan with your own Codex / Claude Code installation and login. Your provider's usage charges or limits apply.
- **Review before running:** inspect steps, test with sample data, then explicitly enable an exact version. Editing the integration contract invalidates its activation.
- **Execute supported operations:** read/write JSON HTTP APIs, select/map/filter fields, deduplicate records, and save JSON or Markdown. Successful POST receipts help suppress repeated writes; uncertain writes require review.
- **Keep improving:** send failure details and feedback to an agent to generate a new candidate. Select a previously tested compatible version to roll back.
- **Archive literature:** the built-in alphaXiv → deduplication → Zotero pipeline supports metadata, PDFs, and a user-selected linked-file folder.
- **Work in one place:** persistent embedded websites; experimental Windows embedding for installed Zotero and OpenResearch; F11 fullscreen; light/dark/system themes; tray background operation.

RN executes a constrained declarative plan, not arbitrary generated scripts. A website without a usable API still needs a connector; drawing a line alone cannot make every service interoperable.

## Quick start (Windows)

Current release: **early Windows x64 source preview**. No signed installer or bundled third-party tools are provided. The interface currently uses Simplified Chinese; both language guides are included.

Prerequisites: Windows 10/11 x64, Node.js 22.12+ with npm, Python 3.10+ with pip, and Git. Python must be available as `python` (or pass `-Python` below). Optional: independently installed Zotero / OpenResearch and a logged-in local Codex or Claude Code CLI.

```powershell
git clone https://github.com/shwhwhwh/research-nexus.git
cd research-nexus
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
npm start
```

If Python has another location:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Python "C:\path\to\python.exe"
```

Setup installs Python dependencies and Electron, writes an ignored `runtime.local.json`, and compiles the native window host with the Windows .NET Framework compiler. Use a writable installation folder. To create desktop / Start menu shortcuts, run `desktop/install-nexus-shortcuts.ps1` after setup. You can also double-click **Start Research Nexus.vbs** or **Start System Designer.vbs**.

### Build your first DIY flow

1. Open **系统设计器** (System Designer), then **示例流程** (Example flow). This adds sample-paper and reading-list nodes with fictional input.
2. Select the connection. Describe the desired transformation, data type, and manual/hourly/daily schedule. Save the canvas.
3. Choose an installed local agent, then **生成集成方案** (Generate). Install and log in to its CLI separately first. The initial Windows adapter supports the npm Codex / Claude Code installations.
4. Inspect the plan. Choose **测试与预览** (Test and preview). This uses sample JSON and simulates HTTP; it does not verify the live API or write to external services.
5. Review the preview, then **启用此版本** (Enable this version) and **运行连线** (Run connection). Local outputs are under `data/designer/outputs/<target-node-id>/`.
6. Add your own tools with **添加工具** (Add tool). Register API origins and credential *environment-variable names* on their nodes. Set the actual variables before starting RN; do not paste secrets into purposes, URLs, examples, or node descriptions.

Custom websites open inside RN. Custom desktop tools launch their own native window; generic embedding of every desktop app is not implemented. Graph execution currently supports acyclic, single-input routes. "Self-evolution" means reviewed candidate revisions; RN does not autonomously rewrite or deploy its own code.

### Connect your literature tools

In **连接与设置** (Connections and settings), enter your **own** alphaXiv API key, Zotero user ID, and a Zotero key authorized for your library. Configure the paths to your installed applications. Use **检查连接** (Check connections), preview the proposed archive, and run it manually before enabling scheduled archiving.

For PDFs, choose Zotero storage or an existing synchronized folder with linked files. A Drive/OneDrive folder requires that provider's desktop client and login. Linked files are mainly for desktop use; RN does not provide a Drive OAuth connector or make linked PDFs available in Zotero's web reader. Zotero itself manages its desktop metadata sync.

The archive engine checks stable paper identifiers and existing items before importing. Possible title matches go to review. A successful repeat normally reuses the original item; PDFs and remote write failures may need separate retry or reconciliation.

## Local data and background operation

Runtime data, credentials, browser profiles, literature, and generated artifacts stay under ignored `data/`. Windows DPAPI protects saved service keys for the current Windows user. **Do not commit or share this directory.** Local agent authentication remains with the CLI; the selected integration specification and sample data are sent to its model provider when generating a plan. RN is local software, but connected services and model calls use the network.

Closing RN hides it to the system tray. Choose **退出 Research Nexus** (Quit) from its tray menu to stop it. Schedules run while RN is running and the computer is awake; they are not a Windows service or a cloud scheduler. Other applications' tray behavior depends on their own configuration.

## Development

```powershell
npm run check
npm test
npm run test:designer
```

Unit tests use temporary fixture data. `test:designer` starts a separate backend and browser profile; it does not open your third-party tools. `test:alpha` checks embedded reading-state restoration with isolated local fixtures. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). Reproduce the privacy-safe demo with [docs/DEMO.md](docs/DEMO.md).

An optional [GitHub Actions template](docs/ci/check.yml) is provided. To enable it, copy it to `.github/workflows/check.yml` using an account or token with permission to manage workflows.

RN uses Electron, Python, and Requests. See [third-party notices](THIRD_PARTY_NOTICES.md). Typography and spacing are inspired by the Codex desktop design; the project icon uses an original soft-gradient twisted ribbon, with color direction inspired by Antigravity. No third-party application code, font files, logos, or user-provided reference artwork are included.
