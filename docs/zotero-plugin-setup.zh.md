# Zotero 链接文件插件：下载与部署

[English](./zotero-plugin-setup.md)

这个可选插件把已有 PDF 作为链接文件加入指定的 Zotero collection。它不会安装 Zotero 或 Zotero 的 Word 插件。只有准备使用链接文件导入、并已授权修改 Zotero profile 时才安装。

## 1. 获取插件源码

先安装 [Python 3.10 或更新版本](https://www.python.org/downloads/) 和[官网提供的 Zotero](https://www.zotero.org/downloads)。克隆本仓库，或从 GitHub 下载 ZIP 并解压。插件源码位于 `skills/zotero-link-import/assets/zotero-plugin`，安装器在本机生成 XPI；无需另外下载预编译 XPI。这个链接文件插件属于本项目，不是 Zotero 官方扩展。

```powershell
git clone https://github.com/yctrrr/AI_literature_management.git
cd AI_literature_management
python .\skills\zotero-link-import\scripts\install_plugin.py --help
```

如果已通过 `npx skills add` 安装这个 skill，也可从已安装的 `zotero-link-import` 目录运行相同脚本。生成的客户端配置和 XPI 都含有本地访问令牌，必须保密。

## 2. 安装前确认目标

- 选定一个**已经存在**的 PDF 根目录。插件拒绝导入该目录以外的文件。
- 确认目标 Zotero collection 已存在，且名称准确、无歧义；导入命令不会新建 collection。
- 检查将要使用的 Zotero `profiles.ini`。安装器选择标记为 `Default=1` 的 profile；若没有标记，则选择第一个。它无法判断当前打开的是哪个 profile。多个 profile 使选择不明确时，先停止并确认。`--profiles-ini` 指定的是另一个配置文件，不是从同一文件中选择某个 profile。
- 保存手头工作并关闭 Zotero，再修改其 profile；不要关闭或修改无关的 Word 文档。

用实际 PDF 根目录运行安装器：

```powershell
python .\skills\zotero-link-import\scripts\install_plugin.py `
  --allowed-root "<已有PDF文献库的绝对路径>"
```

若 Zotero 安装位置不标准，可增加 `--profiles-ini "<profiles.ini路径>"`，必要时再加 `--zotero-exe "<zotero可执行文件路径>"`。安装器在选定 profile 的 `extensions` 目录中生成含令牌的 XPI，并在当前用户的应用配置目录中保存私有客户端配置。输出会列出选定 profile 与文件路径；重启 Zotero 前请核对。默认安装不会写入 Zotero distribution policy。

## 3. 重启并检查

使用选定的 profile 启动 Zotero，确认插件已启用，然后运行：

```powershell
python .\skills\zotero-link-import\scripts\zotero_link_import.py health
```

只有返回 `status: ok` 且允许根目录正确时才继续导入。若检查失败，先核对 profile、插件状态和是否已经重启，不要直接执行导入。客户端读取安装器生成的私有配置。如果安装时使用了 `--config`，则在 `health` 或 `import` 子命令**之前**传同一个 `--config` 路径，或设置 `ZOTERO_LINK_CONFIG`。

只有常规 profile 安装未能激活、并且已单独授权使用 distribution policy 回退时，才用 `--install-policy` 重新运行安装器，重启 Zotero，再运行 `health`。此选项可能需要较高的文件系统权限。重启和健康检查成功后，运行 `python .\skills\zotero-link-import\scripts\install_plugin.py --finalize` 移除一次性策略；已安装的 profile 插件和客户端配置会保留。

## 4. 导入一篇已确认的 PDF

PDF 必须已在允许根目录内；collection 名称必须准确且无歧义。有经过核实的 DOI 时一起提供：

```powershell
python .\skills\zotero-link-import\scripts\zotero_link_import.py import `
  --path "<允许根目录内PDF的绝对路径>" `
  --collection "<现有collection的准确名称>" `
  --doi "10.xxxx/example"
```

核对返回的父条目、链接附件路径、`linkMode` 和 collection。同一文件重复导入应返回 `reused`，且不新增附件。首次集成错误发生后立即停止。源 PDF 保持原位；插件不会直接写入 `zotero.sqlite`。

Word 引用是另一条工作流。Zotero [自带 Word 集成](https://www.zotero.org/support/word_processor_plugin_installation)；若 Word 中没有 Zotero 工具栏，请检查 Zotero 的 **Cite → Word Processors** 设置。若要在 DOCX 中插入或刷新 Zotero 管理的引用，请依照 [`zotero-docx-paper-writing`](../skills/zotero-docx-paper-writing/SKILL.md) 对目标文档做范围限定和已验证备份。

## 隐私

不要提交或分享生成的客户端 JSON、XPI、token、个人 `profiles.ini` 或私人 PDF 文献库路径。仓库只公开插件源码和通用使用说明；凭据在用户本机生成。
