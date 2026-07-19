# AI Literature Management

<!-- README-I18N:START -->

[English](./README.md) | **中文**

<!-- README-I18N:END -->

AI Literature Management 是一个本地优先的学术文献发现、下载、整理、定位、总结和引用工作流。当前自动抓取器面向 Nature 平台文章；仓库内置的 Agent Skills 还支持 DOI、arXiv、出版社页面、本地文献库、Zotero 和 DOCX 工作流。

## 功能

- 从可配置 feed 发现 Nature 文章，并使用受控搜索作为补充。
- 在应用每次运行的文章数量限制前先过滤期刊名称。
- 下载可访问的 PDF 和第一个真实补充附件。
- 将抓取与 EndNote 导出和 LLM 分类总结分开运行。
- 新文章先进入 `_pending_summary`，等待总结任务处理。
- 维护结构化 `summary_index.json` 和按分类组织的 Markdown 总结。
- 生成最近或全量 RIS/ENW 导入包及附件报告。
- 通过 DOI、来源 URL、元数据和文件名避免重复下载。
- 内置四个可复用 Agent Skills，覆盖文献获取、本地检索、Zotero 链接导入和引用安全的 DOCX 写作。
- 使用初始化生成的本地配置，不内置任何机器特定路径。

## 架构

```text
AI_literature_management/
  config.example.yaml
  init_project.py
  run_weekly.py
  run_summary.py
  prepare_endnote_import.py
  scheduler_crawl_endnote.ps1
  scheduler_summary.ps1
  src/
  skills/
    literature-ingest/
    literature-locator/
    zotero-link-import/
    zotero-docx-paper-writing/
  tests/
```

## 安装

```powershell
git clone https://github.com/yctrrr/AI_literature_management.git
cd AI_literature_management
pip install -r requirements.txt
playwright install chromium
python .\init_project.py
```

初始化器会询问：

- 主文献库根目录。
- 已存在的分类来源目录。
- 自动抓取归档目录。
- 可选的持久浏览器 profile。
- LLM provider、model、base URL 和 API Key 环境变量名称。
- 可选的 Zotero 链接文件允许根目录。

初始化器生成本地 `config.yaml`，该文件已被 Git 忽略。API Key 和 Zotero token 不会写入公共模板。

在运行总结任务前，设置初始化时选择的环境变量：

```powershell
$env:LLM_API_KEY = "..."
```

## 配置

`config.example.yaml` 记录了全部配置项。以下环境变量可显式覆盖配置：

- `AI_LITERATURE_CONFIG`
- `AI_LITERATURE_LIBRARY_ROOT`
- `AI_LITERATURE_CATEGORY_SOURCE`
- `AI_LITERATURE_ARCHIVE_ROOT`
- `AI_LITERATURE_BROWSER_PROFILE`
- `ZOTERO_LINK_ALLOWED_ROOT`

命令行路径参数优先于环境变量和项目配置。

## 命令

只发现候选文章，不下载：

```powershell
python .\run_weekly.py --config .\config.yaml --dry-run
```

下载新文章、保留在待总结队列并刷新最近 EndNote 包：

```powershell
python .\run_weekly.py --config .\config.yaml --headless false
```

分类并总结待处理文章：

```powershell
python .\run_summary.py --config .\config.yaml
```

调试时合并运行抓取、分类和总结：

```powershell
python .\run_weekly.py --config .\config.yaml --headless false --summarize
```

不抓取、不调用 LLM，只重建总结索引：

```powershell
python .\run_weekly.py --config .\config.yaml --rebuild-summary
```

导出最近 EndNote 记录：

```powershell
python .\prepare_endnote_import.py --config .\config.yaml --since-days 7
```

导出完整归档：

```powershell
python .\prepare_endnote_import.py --config .\config.yaml --all
```

## Agent Skills

仓库包含：

- `literature-ingest`：解析、查重、分类并在确认后下载文献。
- `literature-locator`：查找本地论文及可能的附件，不修改文件。
- `zotero-link-import`：在确认后将现有 PDF 链接到准确的 Zotero collection。
- `zotero-docx-paper-writing`：通过备份、Zotero 安全约束和文档包审计协调限定范围的 Word 修改。

GitHub 仓库完成重命名后，可安装全部 Skills：

```powershell
npx skills add yctrrr/AI_literature_management -g -y
```

Zotero 集成为可选功能。运行安装器前先阅读 `skills/zotero-link-import/SKILL.md` 并取得安装授权。本地 endpoint token 和生成的 XPI 不进入 Git。

## 定时任务

注册每周一 09:00 的抓取和 EndNote 任务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scheduler_crawl_endnote.ps1
```

注册每周一 11:00 的总结任务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scheduler_summary.ps1
```

两个脚本都从自身位置推导项目根目录。需要时可覆盖 `-ProjectRoot`、`-PythonExe`、`-WeeklyDay` 或 `-At`。

## 输出

- `_pending_summary\*.pdf` 和 `*.metadata.json`
- `<分类>\*.pdf` 及匹配附件
- `_state\*.jsonl`
- `_summaries\summary_index.json`
- `_summaries\summary.md`
- `_summaries\summary.backup.md`
- `_endnote_import\AI_literature_management_latest.ris`
- `_endnote_import\AI_literature_management_latest.enw`
- 带时间戳的清单和附件报告

## 边界

- 不要把 API Key 写入 YAML。
- 浏览器 profile、下载文献、生成总结、运行状态、Zotero 客户端配置和生成的 XPI 均只保存在本地。
- 抓取器只下载公开或用户有权访问的文件，不绕过访问控制。
- Zotero 修改始终需要明确确认。
- DOCX 修改必须遵守明确的编辑范围和已验证备份流程。

## 测试

```powershell
python -m pytest -q
```

测试套件不访问网络，也不会启动 Zotero、Word、浏览器或 LLM。
