# Security and privacy

Do not publish credentials or private research in an issue. To report a vulnerability, use the repository's private vulnerability reporting feature when enabled, or contact the maintainer through their GitHub profile without including secrets in a public thread.

The backend binds to loopback and validates Host, Origin, and CSRF tokens. The desktop renderer is isolated from Node.js. Saved service keys use Windows DPAPI; agent authentication stays with the installed CLI. Plans are restricted to registered HTTP origins and supported operations. These controls do not replace careful API permission scoping, plan review, and backups.

`data/` contains private material and is excluded from Git. Screenshots, logs, model requests, and sample payloads may still contain research data: review them before sharing. Generating a plan sends that connection's descriptions, sample data, and supplied feedback to the chosen model provider. Use minimal, non-sensitive fixtures. Keep Electron and Python dependencies updated and do not expose the local backend to a network.

Use your own accounts, API keys, and provider permissions. Preview tests simulate HTTP and cannot establish live connectivity. POST receipt tracking reduces repeated writes but cannot provide universal exactly-once delivery to arbitrary services.

请勿在公开 Issue 中发布账号、密钥或研究隐私。`data/` 不进入 Git；分享日志、截图和样例前仍需自行检查。模型生成会把相应连线描述、样例及反馈发送给所选模型服务。不要把本机服务暴露到网络。
