# Hermes 开发入口

先遵守 [AGENTS.md](AGENTS.md)，再读 [交接指南](docs/hermes-handoff.md)。

默认角色是 Implementer，不修改受保护规格，不自行扩大任务范围。首个任务是 `tasks/M0/`；其状态为 draft，不能在基线和冻结步骤完成前当成已授权的执行包。

真实 Hermes CLI 尚未在此云环境核验。不要从本文推断命令参数、resume、取消、JSON 输出或 sandbox 能力。M0 使用模拟 Agent，真实接入见路线图 M2。

完成后按 `templates/implementation-report.md` 交付。最多根据明确 findings 返修一次；仍失败时由协调者决定接管。
