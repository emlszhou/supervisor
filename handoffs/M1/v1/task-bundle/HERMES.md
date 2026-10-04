# Hermes 开发入口

先遵守 [AGENTS.md](AGENTS.md)，再读 [交接指南](docs/hermes-handoff.md)。

默认角色是 Implementer，不修改受保护规格，不自行扩大任务范围。首个任务是 M0；仓库 tasks/M0/ 是源草案，执行输入从 main 的 `handoffs/M0/v2/` 校验并导出，详见 docs/git-handoff.md。

用户已授权正常 commit/pull/push。仅向 `hermes/m0` 推送实现和 `deliveries/M0/hermes-report.md`，不向 main 推送、不 force-push。完成报告需给出基线、真实检查结果及未验证平台。

真实 Hermes CLI 尚未在此云环境核验。不要从本文推断命令参数、resume、取消、JSON 输出或 sandbox 能力。M0 使用模拟 Agent，真实接入见路线图 M2。

完成后按 `templates/implementation-report.md` 交付。最多根据明确 findings 返修一次；仍失败时由协调者决定接管。

当前开工任务已改为 M0R-review2-remediation：读取 main 的 handoffs/M0R/v1，使用 hermes/m0r 和 deliveries/M0R/hermes-report.md。原 M0/v2 与 hermes/m0 保留，不再返修。新版导出器和开工命令见 handoffs/M0R/v1/README.md。

当前任务M1-integrity-intents：读取main的handoffs/M1/v1/README.md，使用--contract-prefix handoffs/M1/v1导出外部冻结包，在hermes/m1实现，交付deliveries/M1/hermes-report.md。旧M0R无需进一步修改；不要merge main或审核分支到实现分支。
