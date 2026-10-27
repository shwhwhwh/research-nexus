# System Template 01：配置与使用

[English](SYSTEM_TEMPLATE.md) · [下载模板](https://github.com/shwhwhwh/research-nexus/releases/download/v0.7.1/literature-workspace.rn-system.json) · [安装 RN v0.7.1](../INSTALL.md)

要求已安装 Windows 版 Research Nexus 0.3.0+。在 RN 的 **系统模板 → 导入下载的模板** 中选择 `.rn-system.json`。模板使用 RN 已有归档引擎，不执行额外代码，不需要画图、编程或生成连接器。

## 只配置自己的账号与软件

1. **alphaXiv：**在 Settings → API Keys 创建专用 Key，把实际密钥保存进 RN。参见 [官方 MCP 说明](https://www.alphaxiv.org/docs/mcp)。
2. **Zotero API：**在 [API Keys](https://www.zotero.org/settings/keys) 页面创建个人库专用 Key，允许读取、笔记及写入，并复制页面中的数字 User ID。连接检查验证读取，第一次归档验证写入。
3. **Zotero 桌面：**安装软件，选择其程序路径，登录与 API Key 对应的同一个 Zotero 账号，开启自动同步。参见 [官方同步说明](https://www.zotero.org/support/sync)。
4. **OpenResearch：**安装 [Windows 桌面版](https://github.com/alphaXiv/OpenResearch#readme) 和 Git for Windows，在 RN 中选择程序路径，在 OpenResearch 内完成自己的 Agent / 模型登录。
5. **Google Drive：**安装并登录 [Drive 桌面端](https://support.google.com/drive/answer/10838124)，在同步空间内创建 PDF 文件夹并在 RN 中选择，保持文件夹在本机可用。勾选登录与同步确认；RN 不获取 Google 密码，也不验证 Google 账号。
6. **启动：**保存配置、检查 API 连接，然后启用每日检查。保存配置会暂停自动归档；密钥框留空会保留已保存的 Key。

模板文件不包含账号、密钥、文献、会话、浏览器状态或本机路径。重复导入不会重置现有设置；修改或未知版本的模板会被拒绝。

## 在 RN 中使用整套系统

- 在 RN 内打开 alphaXiv，收藏一篇公开 arXiv 论文。
- 点击 **立即归档**，或在 RN 运行且电脑唤醒时等待每日检查。
- 查看归档记录：完成后会有 Zotero 条目、来源笔记和 PDF 链接；PDF 位于选定的 Drive 文件夹。
- 让 Zotero 完成元数据同步。在 RN 内打开本机 Zotero 窗口，阅读、批注、管理引用。
- 在 RN 内打开本机 OpenResearch 窗口，自己选择文献，把论文链接或 PDF 提供给研究对话。这一步是人工交接，尚无 Zotero 到 OpenResearch 的自动导入。
- 再次运行归档会核对稳定标识和已有条目。疑似重复或远端结果不确定时，先核对再处理。

Drive 的文件同步由其客户端完成，RN 不会把“本地保存成功”标成“云端上传已验证”。[Zotero 链接文件](https://www.zotero.org/support/attaching_files#linked_files) 主要在桌面使用，多电脑可能需要设置链接附件基目录。不要把 Zotero 数据库放进 Drive。

## 配置未完成时

检查列表会显示缺少的 Key、本地程序、同步文件夹、登录确认或 API 检查。更换 Key / User ID 会使旧检查失效。文件夹不可用时不会继续关联 PDF；失败与疑似重复保留为可检查记录。本地窗口嵌入目前为 Windows 实验功能，v0.4 DIY 设计器为独立 Beta 功能，见 [DIY 指南](DIY.zh-CN.md)。
