# 版本化交付与审核记录

通过 Git 交接，不提交原始会话、密钥、环境值、venv 或缓存。

M0 实现者只允许写 `M0/hermes-report.md`，按 templates/implementation-report.md 记录代码提交、基线、冻结包摘要和实际验证。

Codex 审核记录在独立审核分支中写 `M0/codex-review-*.json`，不得由实现者修改；审核和实现结果均需绑定具体候选代码提交。流程见 docs/git-handoff.md。
