# AI Literature Management

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](./requirements.txt)
[![skills.sh](https://skills.sh/b/yctrrr/AI_literature_management)](https://skills.sh/yctrrr/AI_literature_management)

<!-- README-I18N:START -->

[English](./README.md) | **中文**

<!-- README-I18N:END -->

AI Literature Management 是一个本地优先的研究文献与个人知识工作流。它把文献发现、文件整理、本地检索、AI 辅助理解、文献管理工具和带引用的论文写作连接起来。

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
确认后可链接至 Zotero，并引用文献到 DOCX 文档
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

| Skill                                                                      | 作用                                      |
| -------------------------------------------------------------------------- | --------------------------------------- |
| [`weekly-literature-crawl`](./skills/weekly-literature-crawl/SKILL.md)     | 验证、预览并执行经确认的定期收集、待总结队列处理和 EndNote 导出。   |
| [`literature-ingest`](./skills/literature-ingest/SKILL.md)                 | 对 DOI、arXiv、出版社页面等来源解析、查重、分类，并在确认后下载文献。 |
| [`literature-locator`](./skills/literature-locator/SKILL.md)               | 不修改文献库，查找本地论文及可能的补充文件。                  |
| [`zotero-link-import`](./skills/zotero-link-import/SKILL.md)               | 在确认后将已有本地 PDF 链接到指定 Zotero collection。  |
| [`zotero-docx-paper-writing`](./skills/zotero-docx-paper-writing/SKILL.md) | 通过备份和引用安全检查，对 DOCX 做有证据支撑、范围受控的修改。      |

在支持的 Agent 环境中安装全部 skills：

```powershell
npx skills add yctrrr/AI_literature_management -g -y
```

已发布的 skill 目录见 [skills.sh](https://skills.sh/yctrrr/ai_literature_management)。

安装 skill 不会自动创建文献库或完成项目配置。请按实际要使用的功能完成下面的设置。

## 快速开始

```powershell
git clone https://github.com/yctrrr/AI_literature_management.git
cd AI_literature_management
pip install -r requirements.txt
playwright install chromium
python .\init_project.py
```

运行初始化器前，先选定已经存在的文献库目录和分类来源目录（可以从 `example_taxonomy` 开始），并选定独立的归档目录；初始化器可以创建归档目录。初始化器随后创建被 Git 忽略的本地 `config.yaml`，请依次确认这些路径、可选浏览器 profile、可选 Zotero 链接文件根目录及 LLM 服务设置。首次运行收集前，检查生成文件中的 `paths`、`browser`、`zotero` 和 `llm` 段。

如果已安装的 skill 在克隆仓库之外运行，请在当前 PowerShell 会话中指定配置文件：

```powershell
$env:AI_LITERATURE_CONFIG = (Resolve-Path .\config.yaml).Path
```

单篇文献的收集与检索脚本也可直接传 `--root`，`weekly-literature-crawl` 可传 `--project-root`。确认这些路径指向你自己的文献库，不要把示例路径当成本机默认值。

先只检查项目配置，不下载文献，也不修改 Zotero：

```powershell
python .\skills\weekly-literature-crawl\scripts\weekly_literature_crawl.py --project-root . check
```

只有使用 LLM 总结功能时才需要 API Key。将其放在 `config.yaml` 的 `llm.api_key_env` 指定的环境变量中（默认是 `LLM_API_KEY`），不要把密钥值写进配置文件。

```powershell
$env:LLM_API_KEY = "..."
```

全部配置项与环境变量覆盖方式见 [`config.example.yaml`](./config.example.yaml)。

使用完整项目时，通常只需创建 `config.yaml`。如果单独安装收集或检索 skill、没有项目配置，可以在**每个**已安装的 skill 目录中放 `config.local.json`，内容为 `{"paths":{"library_root":"<文献库绝对路径>"}}`；JSON 中的 Windows 路径请用正斜杠或转义的反斜杠。直接传 `--root` 或设置 `AI_LITERATURE_LIBRARY_ROOT` 则不需要这些文件。Zotero 客户端配置由安装器生成，内含令牌，请勿手工编辑或分享。Word 项目规则模板按具体稿件填写，用于长期保持编辑范围。

### 按需配置功能

| 功能 | 使用前需确认 | 首次安全检查 |
| --- | --- | --- |
| 定期收集 | `config.yaml` 的路径、Nature 来源、下载设置及可选 LLM 设置 | 先运行 `check` 和 `dry-run`；正式 `crawl` 另行确认。 |
| 单篇收集与本地检索 | 通过 `--root`、`AI_LITERATURE_LIBRARY_ROOT` 或 `AI_LITERATURE_CONFIG` 指定已存在的文献库根目录 | 下载前先运行收集脚本的 `inspect`，或执行一次只读检索。 |
| Zotero 链接文件导入 | 已安装 Zotero，并选定插件允许访问的现有 PDF 根目录。检查 `profiles.ini`：安装器选择 `Default=1` 的 profile；若没有，则选择第一个。多个 profile 使目标不明确时先停止。需要此功能时再遵照[技能安装步骤](./skills/zotero-link-import/SKILL.md#installation)。 | 安装前运行 `install_plugin.py --help`；安装并重启后运行客户端 `health`。每次导入单独确认。 |
| 带 Zotero 引用的 DOCX 写作 | 如需 Word 自动化，使用 Windows、Microsoft Word 和 Zotero Word 插件；确定目标文档及允许编辑的范围，可参考[项目规则模板](./skills/zotero-docx-paper-writing/assets/AGENTS.md)。 | 先运行下面的离线合成测试；编辑真实文档前再创建已验证的备份，并遵照[Word 技能](./skills/zotero-docx-paper-writing/SKILL.md)。 |

公开版 Zotero 安装器默认**不会**写入 distribution policy；只有显式传入 `--install-policy` 才会执行，该操作可能需要更高权限和单独确认。Zotero 插件安装会修改用户的 Zotero 设置；Word 编辑会修改选定文档。这两步都不属于项目初始化。

插件下载、profile 部署、重启、健康检查、可选策略回退及首次导入的完整步骤见 [Zotero 插件部署指南](./docs/zotero-plugin-setup.zh.md)。插件源码已经包含在本仓库，安装器会在本机生成 XPI，无需另找预编译安装包。

可先用新建的临时目录测试 Word 技能的备份和范围审计脚本，无需打开 Word 或 Zotero：

```powershell
$out = Join-Path $env:TEMP ("zotero-word-skill-check-{0}" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
powershell -NoProfile -ExecutionPolicy Bypass -File .\skills\zotero-docx-paper-writing\scripts\test_skill.ps1 -OutputDirectory $out
```

这个合成测试不能证明真实引用刷新或稿件渲染已经可用。实际 Word 工作仍需文档编辑与渲染工具；Word 协调技能提到的其他专门技能在可用时使用。

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
