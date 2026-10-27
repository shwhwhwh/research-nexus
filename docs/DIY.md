# DIY research systems (Beta)

[中文](DIY.zh-CN.md)

The designer is now available in the current source build. Template 01 remains available independently. Agent-generated plans are versioned declarations executed by RN's supported operations; they are not arbitrary generated programs.

1. Open **DIY 搭建**. Add websites, API services, installed applications, or managed output folders. Drag an output port to an input port and describe the flow.
2. Register each service's API origin and credential environment-variable names. The designer never accepts API keys inside a plan. Your existing alphaXiv/Zotero keys stay in RN's protected configuration.
3. Ask your installed, signed-in Codex CLI or Claude Code to generate a version. Review the steps and requirements, run the sample preview, then activate that exact version.
4. Run the edge or the enabled graph. Manual, hourly, and daily schedules are available. Changing the source, destination, purpose, sample, or project scope invalidates the prior activation. You can test and switch back to an earlier version whose contract still matches.
5. If a run fails, use the repair action to generate a candidate revision. A revision requires testing and activation; RN never promotes it automatically.

## OpenResearch project citations

Choose **连接项目文献**, select projects, choose a per-run paper limit, and edit category names/keywords. This creates two scoped drafts:

```mermaid
flowchart LR
    O[OpenResearch selected project conversations] --> R[RN: explicit identifiers, branch, provenance, deduplication]
    R --> A[alphaXiv project folder / category subfolders]
    R --> Z[Zotero project collection / category subcollections]
    Z --> N[Citation-context child notes and additive citation tags]
    Z --> P[Linked PDF in configured Drive folder]
    P --> H[Verbatim quote found uniquely: PDF highlight]
```

Preview the real source read-only, then generate, sample-test, activate, and run each draft. The current alphaXiv MCP exposes folder/bookmark writes and annotation/note reads, but no supported note/highlight writer. RN therefore keeps discovery/classification in alphaXiv and writes detailed project citation context into Zotero. It does not post public comments or use private browser endpoints as a substitute.

The source reads OpenResearch's local project/session/message APIs. Busy sessions are deferred; only the selected message branch is exported. Legacy idle messages without a completion timestamp retain their existing text with unknown completion metadata. Reasoning parts, shell/tool inputs, unfinished tool results, and abandoned branches are excluded. Optionally include completed tool outputs, explicitly labelled as discovery rather than a verified paper quotation.

Explicit arXiv and DOI references are supported. Title-only mentions are not guessed. Non-arXiv papers can go to Zotero when Crossref verifies their DOI metadata. Choose local keyword rules or Codex/Claude semantic classification. Semantic classification sends only the selected project citation excerpts to the signed-in model service, after explicit consent bound to that provider and project set. Changing the projects/provider requires new consent. Decisions are validated against permitted categories and citation IDs, then cached across both edges and restarts. Uncertain context goes to **待分类**. Plan generation uses the declared purpose and sample. Compiler/classifier calls disable shell, connectors, plugins, memories and agent spawning for that invocation.

Every citation note retains its exact source-context excerpt, project, conversation, message/part identifiers, timestamp, source link, and stable receipt. Conversation context is labelled as such, not presented as a paper's verbatim statement. A repeated source occurrence reuses its note key and preserves user additions; a distinct occurrence can add another note to the same paper. Existing metadata, other collections, tags, and notes are preserved. Classification changes append a version-checked metadata update to the same citation note without replacing source text or user additions. Unsynced local duplicates or ambiguous matches require review.

PDF highlighting requires an exact quoted string and a unique text match in the linked PDF. Positions come from PDFium in PDF coordinates. Missing/ambiguous positions remain pending; RN never fabricates highlight locations. Scanned PDFs without selectable text need an independent OCR workflow. Installed app metadata sync and Drive file sync are still handled by those applications.

## Operating limits

- A run processes the first N distinct identified papers in the selected scope, keeping their citation occurrences. The preview and execution log show papers outside that limit. Raise the limit (up to 200) or split the project scope to cover more; the current scheduler does not paginate beyond this cap.
- Keep RN running and the computer awake for scheduling. The two project edges are independently enabled and can be paused separately.
- The complete OpenResearch-to-Zotero citation route does not require alphaXiv note support. API keys must permit writes and note access; Zotero desktop must expose its local API for duplicate checks.
- Generated custom HTTP steps are restricted to the source/target origins and registered credentials. An unsupported source/API remains `needs_setup`; a sample-only staging result is not called a live integration.
- Runtime files, project names, conversations, agent build requests, and receipts remain in ignored `data/`. Never commit or export it as a template.

## Verification

`npm test`, `npm run test:desktop`, and `npm run test:systems` use fixtures. Citation tests cover branch selection, provenance, nested folders, idempotent writes, interrupted-write recovery, local duplicate protection, and verified PDF coordinates. The opt-in `--verify-diy-live` check uses a user-selected project from private `data/research-test-scope.json`; it opens the real RN designer, invokes the local compiler, and performs real writes. Do not use that flag without deliberately selecting the project/account and write scope.
