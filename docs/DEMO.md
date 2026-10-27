# System Template demo / 系统模板演示

[Watch the historical Template 01 demo](https://heathcliffak.com/assets/prototypes/research-nexus-system-demo.mp4)

This historical MIT video illustrates Template 01, not the automatic builder. Install the current [v0.7.2 source kit](https://github.com/shwhwhwh/research-nexus/releases/tag/v0.7.2); the old release download is withdrawn without changing earlier permissions.

This demo only presents System Template 01: download/import, initial configuration, daily checks, bookmark archiving, duplicate prevention, and the shared RN workspace for alphaXiv, Zotero, and OpenResearch. The published v0.3.0 video predates DIY Beta and does not demonstrate it; current source-build functionality is documented in DIY.md.

It records only an isolated RN webContents. External accounts, services, installed applications, and Drive login are simulated and clearly labeled. No real third-party app, user library, conversation, account, credential, desktop notification, or personal browser profile is opened. The actual RN archive engine writes two valid fixture PDFs and metadata/source notes to fake services; repeat execution is verified not to create new records. This demonstrates product behavior, not a new live-cloud acceptance test.

视频只展示第一套系统模板，全部使用独立虚构数据。账号、第三方应用和 Drive 登录为明确标注的模拟服务 / 示意界面；归档逻辑为真实 RN 引擎，重复运行不新增条目。不访问真实文献库或研究对话，也不展示 DIY 搭建。

| Scene | English | 中文 |
| --- | --- | --- |
| Overview | System Template 01. One workspace for your research. | alphaXiv / Zotero / OpenResearch + Google Drive。 |
| Install | Download the template, then import it into RN. | 模板不包含账号或文献。 |
| Setup | Set up your own API keys and local applications. | 提供自己的 Key，安装并连接本地软件。 |
| Drive | Sign in to Drive for desktop and select its PDF folder. | Drive 客户端负责登录与同步。 |
| Run | RN deduplicates and archives metadata, notes, and PDFs. | 使用 RN 引擎归档文献与附件链接。 |
| Repeat | The same two papers, no duplicate imports. | 重复运行不新增条目。 |
| Zotero | Read and annotate in Zotero inside RN. | 本地应用在 RN 内使用；视频采用示意界面。 |
| Research | Continue in OpenResearch in the same workspace. | 人工把论文链接 / PDF 交给研究对话。 |

## Reproduce

After RN setup, install FFmpeg separately and put it on PATH (or set `RN_DEMO_FFMPEG`). Run `npm run demo`. No agent/model login is required for this template demo. Networking is disabled in the fixture backend; only its local RN service is accessible. Artifacts and QA files stay under ignored `artifacts/system-demo-*`.

Run `npm run test:systems` for the same functional walkthrough without video encoding. The video is a release asset and is excluded from Git; review every public frame before publishing.
