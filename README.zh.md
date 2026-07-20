# AI Literature Management

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](./requirements.txt)
[![skills.sh](https://skills.sh/b/yctrrr/AI_literature_management)](https://skills.sh/yctrrr/AI_literature_management)

<!-- README-I18N:START -->

[English](./README.md) | **中文**

<!-- README-I18N:END -->

AI Literature Management 是一个本地优先的研究文献与个人知识工作流。它把文献发现、文件整理、本地检索、AI 辅助理解、文献管理工具和带引用的论文写作连接起来，同时不把用户的文献库和运行数据迁移到云端服务。

它适合需要稳定文献工作流的科研人员，也适合希望围绕个人论文库搭建私有、可复用知识工作流的 AI 工具用户。

## 工作流

```text
发现或提供一篇论文
          |
          v
解析并整理本地文件
          |
          +--> 按需定位论文与补充材料
          |
          v
审核、分类与总结
          |
          +--> 导出审核清单或 EndNote 导入包
          |
          v
确认后链接至 Zotero，并写作带引用的 DOCX 文档
```

所有阶段默认在本地完成。下载、修改 Zotero 和编辑 DOCX 都设有明确的确认边界。

## 支持能力

- **收集**：从已配置来源发现文献，下载可访问的 PDF 与补充材料，并避免重复文件。
- **整理**：在受控的本地归档中维护论文、元数据、待审核队列、总结和导出包。
- **查找**：不修改文献库即可定位已知论文及可能的附件。
- **理解**：把新论文加入独立的 LLM 分类与总结队列，并维护结构化和 Markdown 索引。
- **复用**：在任何文献库修改前，生成 EndNote 导入包或只读的 Zotero 导入审核清单。
- **写作**：通过带范围限制和备份的 Word 文档修改，安全协调 Zotero 管理的引用。

## 内置 Skills

| Skill | 作用 |
| --- | --- |
| [`weekly-literature-crawl`](./skills/weekly-literature-crawl/SKILL.md) | 验证、预览并执行经确认的定期收集、待总结队列处理和 EndNote 导出。 |
| [`literature-ingest`](./skills/literature-ingest/SKILL.md) | 对 DOI、arXiv、出版社页面等来源解析、查重、分类，并在确认后下载文献。 |
| [`literature-locator`](./skills/literature-locator/SKILL.md) | 不修改文献库，查找本地论文及可能的补充文件。 |
| [`zotero-link-import`](./skills/zotero-link-import/SKILL.md) | 在确认后将已有本地 PDF 链接到指定 Zotero collection。 |
| [`zotero-docx-paper-writing`](./skills/zotero-docx-paper-writing/SKILL.md) | 通过备份和引用安全检查，对 DOCX 做有证据支撑、范围受控的修改。 |

在支持的 Agent 环境中安装全部 skills：

```powershell
npx skills add yctrrr/AI_literature_management -g -y
```

已发布的 skill 目录见 [skills.sh](https://skills.sh/yctrrr/ai_literature_management)。

## 快速开始

```powershell
git clone https://github.com/yctrrr/AI_literature_management.git
cd AI_literature_management
pip install -r requirements.txt
playwright install chromium
python .\init_project.py
```

初始化器会创建已被 Git 忽略的本地 `config.yaml`，并询问文献库与归档路径、可选浏览器 profile、Zotero 链接文件根目录和 LLM 服务配置。请将 LLM API Key 存在环境变量中，不要写入配置文件。

```powershell
$env:LLM_API_KEY = "..."
```

全部配置项与环境变量覆盖方式见 [`config.example.yaml`](./config.example.yaml)。

## 可选的自动收集

仓库提供一个可选的自动收集器，用于已配置的 Nature 平台 feed 和搜索结果。它只处理可访问文件，不绕过付费墙，也不宣称覆盖所有出版社。

需要时可启用自动收集；如果只需处理单篇论文，可直接从 `literature-ingest` 开始。有关预览、确认下载、总结、导出与定时任务的详细说明，请查看 [`weekly-literature-crawl`](./skills/weekly-literature-crawl/SKILL.md)。

## 本地产物

根据实际使用的能力，项目可能创建：

- `_pending_summary`：等待审核或 LLM 处理的论文。
- `_summaries`：结构化和 Markdown 文献索引。
- `_endnote_import`：RIS/ENW 导入包及附件报告。
- `_zotero_import`：只读 JSON/CSV 导入审核清单。

这些目录、下载论文、浏览器 profile、运行状态、生成的 XPI 和本地配置默认不进入 Git。

## 安全与隐私

- 不要把 API Key 或 Zotero token 写入 YAML、Markdown 或 Git。
- 收集器只下载公开或用户已授权的文件，不绕过访问控制。
- 修改 Zotero 始终需要明确确认。
- 修改 DOCX 必须遵守明确的编辑范围，并经过已验证的备份流程。
- 本项目不提供云端文献数据库，也不提供无人值守的 Zotero 或 Word 修改服务。

## 开发

运行不访问网络的测试套件：

```powershell
python -m pytest -q
```

## 许可证

[MIT](./LICENSE)
