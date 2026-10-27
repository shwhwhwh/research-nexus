# System Template 01 — setup and use

[中文](SYSTEM_TEMPLATE.zh-CN.md) · [Download template](https://github.com/shwhwhwh/research-nexus/releases/download/v0.7.2/literature-workspace.rn-system.json) · [Install RN v0.7.2](../INSTALL.md)

Requires Research Nexus 0.3.0+ on Windows. Import the `.rn-system.json` file through **System Templates → Import downloaded template**. This installs a reviewed preset over RN's built-in archive engine; it is not an executable plugin. No coding, DIY canvas, or model-generated connector is required.

## Complete your own setup

1. **alphaXiv:** create a dedicated API key under Settings → API Keys and save the actual key in RN. See [official MCP documentation](https://www.alphaxiv.org/docs/mcp).
2. **Zotero API:** create a dedicated key for your personal library at [API Keys](https://www.zotero.org/settings/keys). Permit reads, notes, and writes; copy the numeric user ID from that page. RN checks read access; the first archive verifies writes.
3. **Zotero desktop:** install it, select its executable in RN, log in to the same Zotero account, and enable automatic sync. The cloud API library and desktop account must match. See [Zotero sync](https://www.zotero.org/support/sync).
4. **OpenResearch:** install its [Windows desktop app](https://github.com/alphaXiv/OpenResearch#readme) and Git for Windows. Choose its installed executable in RN and complete its own agent/model login.
5. **Google Drive:** install [Drive for desktop](https://support.google.com/drive/answer/10838124), sign in, create a PDF folder within its synchronized drive, and select that existing folder in RN. Keep it available on this computer. Confirm the login and sync checkboxes; RN does not verify your Google account or upload through a Drive API.
6. **Start:** save, check API connections, then enable daily checks. Saving setup pauses auto-archive; existing service keys are retained when the password fields are blank.

The template file contains no keys, library IDs, cookies, local paths, papers, or conversations. Reimport is idempotent and does not reset existing configuration. Unknown or modified manifests are rejected.

## Use the system in RN

- Open alphaXiv in RN and bookmark a public arXiv paper.
- Select **Archive now** or wait for the daily check while RN is running and the computer is awake.
- Review the archive status. A completed linked-file archive has a Zotero metadata item, source note, and PDF link. The file is saved in the selected Drive folder.
- Allow Zotero to sync its metadata. Open the installed Zotero window inside RN to read, annotate, and cite.
- Open the installed OpenResearch window inside RN. Choose the paper yourself and supply its link or PDF in a research conversation. This handoff is manual; there is no automatic Zotero-to-OpenResearch import.
- Repeat archiving safely: RN checks existing identifiers/items and retains their identities. Investigate ambiguous matches or uncertain writes before forcing a retry.

Google Drive's own client synchronizes PDF bytes; RN does not report its cloud upload as verified. [Zotero linked files](https://www.zotero.org/support/attaching_files#linked_files) are primarily for desktop use, and paths may need a linked-attachment base directory on additional computers. Do not place the Zotero database in Drive.

## If setup is incomplete

The checklist identifies missing keys, app files, folder/login acknowledgments, and API read checks. Blank password fields keep saved keys. A changed key or user ID invalidates old connection checks. An unavailable Drive folder blocks PDF placement; a failed upload/link remains visible for retry. Native tool embedding is experimental and Windows-only. The separate v0.4 DIY designer is Beta; see [DIY guide](DIY.md).
