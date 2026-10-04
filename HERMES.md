# 本地 Hermes 开发入口

先遵守 [AGENTS.md](AGENTS.md)，再读 [全本地模型执行规划](docs/LOCAL-MODEL-EXECUTION-PLAN.md)。

用户已决定后续所有模型角色本地运行。默认Implementer；承担Planner/Reviewer/Repairer/Final Verifier时必须由协调流程明确角色，审核使用全新会话，不审核自己的实现。同供应者fresh不等于provider独立。不要自动切换云模型。

当前任务M1-integrity-intents，权威输入main的handoffs/M1/v1，开工命令见其README。实现分支hermes/m1，报告deliveries/M1/hermes-report.md；API/范围/预算/验收继续服从外部冻结包，不修改旧M0/M0R。

用户已授权本仓库正常commit/fetch/pull/push，不force-push/reset/clean。实现角色不向main推送，不merge main或审核记录。合并需当前任务用户授权或可信配置预授权，由本地Coordinator执行。

实际Hermes CLI参数、fresh会话方式、输出、取消与权限能力以本机探测记录为准，不从本文件猜测命令。M2实现真实Adapter和隔离，M3实现状态机；当前先完成M1。
