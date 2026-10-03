# 开发与交付

从 `docs/roadmap.md` 选择最小任务，使用 `templates/task-contract.md` 明确目标、边界、验收和失败条件。一个任务只解决一个可独立验收的问题。

实现任务只修改合同白名单，测试新增到 `tests/unit/` 或任务允许的路径。需要改变规格、受保护测试、依赖或治理规则时先提出理由，由协调者另立任务。

提交前执行 `AGENTS.md` 的检查，按 `templates/implementation-report.md` 记录真实结果。独立 Reviewer 使用 `templates/review.json`，绑定当前任务包和代码快照；修改代码后旧审核自动失效。

设计来源是用户提供的“Codex Claude 接力方案”对话。第三方项目的审计、许可和 CLI 能力描述尚未在本仓库独立验证，不应当作已证实的实现依据。当前没有添加软件发布许可证；正式公开发布前由仓库所有者确定许可。
