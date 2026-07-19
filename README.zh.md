# AI Literature Management

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](./requirements.txt)
[![skills.sh](https://skills.sh/b/yctrrr/AI_literature_management)](https://skills.sh/yctrrr/AI_literature_management)

<!-- README-I18N:START -->

[English](./README.md) | **中文**

<!-- README-I18N:END -->

AI Literature Management 是一个本地优先的学术文献发现、下载、整理、定位、总结和引用工作流。当前自动抓取器面向 Nature 平台文章；仓库内置的 Agent Skills 还支持 DOI、arXiv、出版社页面、本地文献库、Zotero 和 DOCX 工作流。

## 项目作用

本项目把周期性文献收集与后续研究工作连接起来：

1. 从配置的 feed 和搜索结果发现相关 Nature 平台文章。
2. 将可访问的 PDF 和补充材料下载到受控的本地归档。
3. 把新论文加入独立的 LLM 分类与总结队列。
4. 重建分类摘要，并生成 EndNote 导入包。
5. 通过内置 Skills 获取其他来源论文、定位本地文件、链接 Zotero PDF，并安全编辑带引用的 Word 论文。

本项目不用于绕过付费墙，不提供云端文献数据库，也不会在无人授权时修改 Zotero 或 Word。文件与运行状态保留在本地，所有修改型集成都需要明确授权。

## 功能

- 从可配置 feed 发现 Nature 文章，并使用受控搜索作为补充。
- 在应用每次运行的文章数量限制前先过滤期刊名称。
- 下载可访问的 PDF 和第一个真实补充附件。
- 将抓取与 EndNote 导出和 LLM 分类总结分开运行。
- 新文章先进入 `_pending_summary`，等待总结任务处理。
- 维护结构化 `summary_index.json` 和按分类组织的 Markdown 总结。
- 生成最近或全量 RIS/ENW 导入包及附件报告。
- 通过 DOI、来源 URL、元数据和文件名避免重复下载。
- 内置五个可复用 Agent Skills，覆盖每周抓取、文献获取、本地检索、Zotero 链接导入和引用安全的 DOCX 写作。
- 使用初始化生成的本地配置，不内置任何机器特定路径。

## 架构

```text
AI_literature_management/
  config.example.yaml
  init_project.py
  run_weekly.py
  run_summary.py
  prepare_endnote_import.py
  prepare_zotero_import.py
  scheduler_crawl_endnote.ps1
  scheduler_summary.ps1
  src/
  skills/
    weekly-literature-crawl/
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

生成完整的只读 Zotero 导入审核清单：

```powershell
python .\prepare_zotero_import.py --config .\config.yaml --all
```

该命令只生成 JSON/CSV 清单，不连接或修改 Zotero。实际链接文件导入仍需单独确认后交给 `zotero-link-import`。

## Agent Skills

仓库包含：

- `weekly-literature-crawl`：验证并编排试运行、经确认的每周下载、待总结队列、摘要重建和 EndNote 导出。
- `literature-ingest`：解析、查重、分类并在确认后下载文献。
- `literature-locator`：查找本地论文及可能的附件，不修改文件。
- `zotero-link-import`：在确认后将现有 PDF 链接到准确的 Zotero collection。
- `zotero-docx-paper-writing`：通过备份、Zotero 安全约束和文档包审计协调限定范围的 Word 修改。

为支持的 Agent 全局安装仓库中的全部 Skills：

```powershell
npx skills add yctrrr/AI_literature_management -g -y
```

仅查看可用 Skills，不安装：

```powershell
npx skills add yctrrr/AI_literature_management -l
```

Zotero 集成为可选功能。运行安装器前先阅读 `skills/zotero-link-import/SKILL.md` 并取得安装授权。本地 endpoint token 和生成的 XPI 不进入 Git。

## 每周抓取 Skill 工作流

先在不访问网络的情况下验证初始化配置：

```powershell
python .\skills\weekly-literature-crawl\scripts\weekly_literature_crawl.py `
  --project-root . check
```

下载前预览候选文献：

```powershell
python .\skills\weekly-literature-crawl\scripts\weekly_literature_crawl.py `
  --project-root . dry-run --limit 10
```

检查试运行结果并确认允许下载后，执行每周抓取：

```powershell
python .\skills\weekly-literature-crawl\scripts\weekly_literature_crawl.py `
  --project-root . crawl --confirm-download
```

设置配置指定的 LLM API Key 环境变量后，单独处理待总结队列：

```powershell
python .\skills\weekly-literature-crawl\scripts\weekly_literature_crawl.py `
  --project-root . summary
```

包装器还支持 `rebuild`、`endnote --since-days 7`、`endnote --all` 和 `zotero-plan --all`。从仓库外调用已安装的 skill 时，可设置 `AI_LITERATURE_PROJECT_ROOT`。

## 定时任务

只有在获得单独、明确的授权后，才能注册、替换或删除定时任务。

注册每周一 09:00 的抓取和 EndNote 任务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scheduler_crawl_endnote.ps1
```

注册每周一 11:00 的总结任务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scheduler_summary.ps1
```

两个脚本都从自身位置推导项目根目录。需要时可覆盖 `-ProjectRoot`、`-PythonExe`、`-WeeklyDay` 或 `-At`。

根目录 scheduler 文件是兼容包装器，实际注册逻辑位于 `skills/weekly-literature-crawl/scripts/`。

## 输出

- `_pending_summary\*.pdf` 和 `*.metadata.json`
- `<分类>\*.pdf` 及匹配附件
- `_state\*.jsonl`
- `_summaries\summary_index.json`
- `_summaries\summary.md`
- `_summaries\summary.backup.md`
- `_endnote_import\AI_literature_management_latest.ris`
- `_endnote_import\AI_literature_management_latest.enw`
- `_zotero_import\AI_literature_management_zotero_latest.json`
- `_zotero_import\AI_literature_management_zotero_latest.csv`
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

## 许可证

MIT。
