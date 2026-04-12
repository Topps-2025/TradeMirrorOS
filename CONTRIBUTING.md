# Contributing

感谢你愿意为 Finance Journal 提交改进。

## 开始之前

- 先阅读 `README.md`
- 涉及会话协议时，再查看：
  - `finance-journal-orchestrator/references/openclaw-skill-functional-spec.md`
  - `finance-journal-orchestrator/references/data-contracts.md`
- 涉及运行时同步边界时，再查看 `GIT_SYNC_WORKFLOW.md`

## 本地开发

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 提交前建议执行

```powershell
python -m compileall finance_journal_core finance-journal-orchestrator\scripts tests
python -m unittest discover -s tests -v
```

## 提交约定

- 变更尽量聚焦，不要把无关重构混在同一个 PR
- 涉及用户可见行为变化时，请同步更新：
  - `README.md`
  - `IMPLEMENTED_FEATURES.md`
  - `FINANCE_JOURNAL_STATUS_AND_CHANGELOG.md`
- 不要把 `_runtime*/`、SQLite 数据库或本地调试日志提交到仓库
- 涉及安全问题，请不要公开提 issue，改走 `SECURITY.md`

## PR 内容建议

一个清晰的 PR 通常至少包含：

- 变更背景
- 主要改动点
- 验证方式
- 是否影响会话契约 / 数据契约 / Docker 使用方式
