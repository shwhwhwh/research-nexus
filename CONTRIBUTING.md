# Contributing / 参与贡献

Research Nexus is maintained by Rui Li (@shwhwhwh). Issues and pull requests are welcome. Describe the problem, expected data flow, supported API, and a small **fictional** fixture. Preserve the MIT copyright notice and document third-party dependencies.

Before submitting, run `npm run check`, `npm test`, and, for template UI changes, `npm run test:systems`. Describe what was verified and any external service that could not be tested. Keep the archive pipeline backward compatible. DIY connector work is unfinished and remains experimental. Future connectors should specify origins, credentials by variable name, sample inputs, duplicate handling, and failure recovery.

Never include `data/`, real papers, conversations, browser profiles, tokens, personal account IDs, local absolute paths, or screenshots of a personal workspace. Tests must use isolated storage and must not access the contributor's real tools or libraries. Propose changes via a pull request; do not enable new live writes or schedules in tests.

欢迎提交 Issue 和 PR。请说明问题、期望的数据流及接口，提供虚构样例；提交前运行相应检查。保留 MIT 版权声明。请勿上传个人文献、对话、账号、密钥、浏览器状态或本地工作空间截图；连接器与测试应使用独立数据目录，并明确去重和失败处理行为。
