# v0.6.0 source build — Project events and layout templates

- OpenResearch project onboarding uses its official local SSE stream (`/api/events`, `project.updated`), replacing RN's minute project-list polling.
- Startup/reconnect reconciliation, busy-task queuing, and failure backoff preserve onboarding after interruptions; citation delivery remains daily.
- Two saved, theme-aware diagram templates: Ptolemaic orbital arrangement and structured directional data flow, with curved/orthogonal routes and readable labels.
- Layout changes retain active integration contracts, all tools, edges, consent and delivery receipts.
- Validation: 95 Python tests, 5 graph layout tests, 6 desktop lifecycle tests, syntax checks, and isolated five-tool UI checks in light/dark themes.

# v0.5.0 source build — Automatic project onboarding

- Opt-in discovery of all current and future OpenResearch projects, independent empty folders, and daily incremental citation delivery.
- Future-project semantic consent is source/provider-bound and distinct from fixed-project grants.
- Durable completion receipts per destination avoid reprocessing completed citations and continue capped backlogs in later daily batches.
- Paused destinations receive no onboarding writes. Renames keep folder identity; deleted projects keep their archives.
- Discovery status and a manual check are available in the DIY designer.

# v0.4.0 source build — DIY Beta

- Visual graph editing, local Codex/Claude declarative plan generation, preview, version-bound activation, repair, rollback and hourly/daily schedules.
- Scoped OpenResearch project references → alphaXiv project/category folders, plus Zotero citation-context notes, source IDs, citation tags and linked PDFs.
- PDF highlights require unique verbatim source matches. Unsupported alphaXiv note/highlight writes use the Zotero route.
- Optional semantic classification requires provider/project-bound consent and caches validated decisions. Keyword classification stays local.
- Real RN acceptance testing covers two selected-project papers and repeated-run identity checks. Public tests and screenshots use fictional data.

The release/demo below documents the previous stable template-only build.

# Research Nexus v0.3.0 — System Template 01

Created and maintained by Rui Li (@shwhwhwh). Copyright © 2026 Rui Li, MIT licensed.

This preview focuses on an installable, reviewed **Literature Research System**: alphaXiv bookmark reading → RN deduplication → Zotero metadata and linked PDFs, with PDF files synchronized by Google Drive for desktop. The installed Zotero and OpenResearch applications can be opened inside RN. Paper handoff to OpenResearch is manual.

- Download/import `literature-workspace.rn-system.json`, or install the same template from RN.
- Complete your own API keys, Zotero ID, installed applications, Drive folder/login, and local agent setup.
- Check connections and enable daily bookmark checks; no connector generation is required.
- Reimport preserves existing settings; setup changes pause archive until re-enabled.
- **DIY data-flow design and agent-driven evolution are unfinished.** The UI marks them as such, their execution APIs are gated, and their scheduler is disabled.
- New English/Chinese guides and a privacy-safe template-only demo replace the earlier DIY demo.

Validation: 63 unit tests, isolated system-template import/setup/archive/repeat checks, syntax checks, native host compilation, and reading-state checks. External services in the public video are simulated; the video does not access personal accounts. Optional hosted CI remains a template requiring workflow permissions.

Windows x64 source preview; Node.js 22.12+, Python 3.10+, and separately installed third-party tools. No signed installer is included.

中文：本次先发布第一套已搭建的文献科研系统模板。导入后完成自己的 Key、本地软件及 Drive 配置即可使用。DIY 数据流搭建与自动演化明确标为未完成；演示只展示此模板，不含个人科研信息。
