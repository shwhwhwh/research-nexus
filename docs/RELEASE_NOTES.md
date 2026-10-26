# Research Nexus v0.2.0 — public source preview

Research Nexus is a local visual designer and top-level controller for a DIY research system, created and maintained by Rui Li (@shwhwhwh).

This first public source preview includes:

- A visual graph for research tools and data flows.
- Structured plans generated with the user's local Codex / Claude Code.
- Sample preview, explicit version activation, local output, schedules, and revision feedback.
- Literature deduplication and archive integration.
- Persistent embedded websites, themes, tray support, and experimental Windows native embedding.
- A Windows setup script, fixture-based checks, MIT license, and English / Chinese usage guides.
- A short bilingual demo recorded in an isolated workspace with fictional data.

**Requirements:** Windows x64, Node.js 22.12+, Python 3.10+, and optional independently installed tools / logged-in CLI. This release is a source preview, not a signed desktop installer. The interface is currently Simplified Chinese. Use your own credentials. Arbitrary desktop embedding and universal website automation are not supported; see the README for boundaries.

**验证 / Validation:** 56 unit tests; isolated designer UI checks; embedded reading-state restoration checks; native host compilation; syntax checks; real local-agent demo generation and repeat-output verification. Preview tests do not verify all external APIs. An optional GitHub Actions template is included; hosted CI is not enabled in this preview.

**中文：**本次公开预览提供可视化科研系统设计器、本地 Agent 生成方案、测试与版本启用、文献去重归档及统一工作空间。仓库提供中英文说明；演示只使用独立虚构数据，不包含个人科研信息。版权 © 2026 Rui Li（@shwhwhwh），MIT 许可。
