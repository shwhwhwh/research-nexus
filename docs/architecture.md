# Research Nexus: reviewed System Templates

The released product is a local Windows Electron workspace and Python archive controller. A template is a reviewed declarative manifest selecting an existing engine, not a script or a downloaded program. `bridge/systems.py` accepts only the exact bundled manifest; it cannot import credentials, paths, commands, or arbitrary API destinations.

Lifecycle: download → import → configure own accounts and app paths → check read access → explicitly enable daily checks → archive and review. Reimport preserves existing settings. Configuration saves pause auto-archive; changing account credentials invalidates connection checks. API keys remain in the user's DPAPI-protected store. The first write verifies write permissions.

RN's existing archive engine reads alphaXiv bookmarks, reconciles local/cloud Zotero identifiers, stores source notes, places PDFs in a selected folder, and writes linked-file attachments. Zotero and Google Drive maintain their own respective metadata and file synchronization. OpenResearch is an installed native window inside RN. User-selected paper handoff is manual.

The experimental DIY compiler/controller remains source code for development. Its build/test/run/activate/save HTTP endpoints return 409, and its scheduler is not started. The UI clearly labels DIY as unfinished. This version makes no automatic self-evolution claim.

Offline public demos use a separate browser profile and backend with fake alphaXiv/Zotero/metadata adapters, real archive logic, real temporary PDF writes, and networking disabled. Installed-app views are clearly labeled illustrations, never screenshots of a personal workspace.
