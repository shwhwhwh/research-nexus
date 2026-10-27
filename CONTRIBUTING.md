# Contributing / 参与贡献

Research Nexus is maintained by Rui Li (@shwhwhwh). Issues and pull requests are welcome. Describe the problem, expected data flow, supported API, and a small **fictional** fixture. Preserve historical MIT notices and all current license/author notices and document third-party dependencies.

Before submitting, run `npm run check`, `npm test`, and, for template UI changes, `npm run test:systems`. Describe what was verified and any external service that could not be tested. Keep the archive pipeline backward compatible. The DIY designer is Beta; maintain its version/activation, provenance, idempotency and model-consent boundaries. Future connectors should specify origins, credentials by variable name, sample inputs, duplicate handling, and failure recovery.

Never include `data/`, real papers, conversations, browser profiles, tokens, personal account IDs, local absolute paths, or screenshots of a personal workspace. Tests must use isolated storage and must not access the contributor's real tools or libraries. Propose changes via a pull request; do not enable new live writes or schedules in tests.

欢迎提交 Issue 和 PR。请说明问题、期望的数据流及接口，提供虚构样例；提交前运行相应检查。保留历史 MIT 及当前许可、作者声明。请勿上传个人文献、对话、账号、密钥、浏览器状态或本地工作空间截图；连接器与测试应使用独立数据目录，并明确去重和失败处理行为。

## New contribution permission

Read [CONTRIBUTOR_AGREEMENT.md](CONTRIBUTOR_AGREEMENT.md) before submitting code and expressly include `CLA-ACCEPTED: PP-CLA-1.0` in the PR description if you agree and have authority. Contributors keep authorship; the grant permits Rui Li to maintain, publish and commercially sublicense accepted original contributions. Opening an issue alone grants nothing. Commercial use of restricted upstream material needs separate authorization; voluntary contribution work is free under LICENSE.

Official distribution scope: LICENSE 1.1 covers all owner-controlled code, including earlier self-owned code, not only additions. Keep valid prior grants and third-party licenses; accepted contributions retain authorship and require the documented grant.
