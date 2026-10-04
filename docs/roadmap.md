# 分阶段路线图

M0核心模块经M0R接管和fresh最终验收接受，已集成main；Linux和模拟Windows有证据，原生macOS/Windows仍未实测，未提供OS sandbox。M1现已发布规格，M1及之后里程碑尚未实现。

| 阶段 | 范围 | 必需验收 |
| --- | --- | --- |
| M0 | Worker ProcessRunner、统一 AgentResult、Mock Adapter、最小事件 | 正常/失败/取消/超时/输出上限/协议损坏；真实退出码；任务身份；支持平台的进程树回收 |
| M1 | 干净 Git 基线、TaskBundle 冻结、快照、策略校验、SQLite 操作意图 | 输入不可变、穿越/链接/大小写/陈旧快照拒绝、持久化与故障窗口 |
| M2 | 核验并接入本地Hermes/本地角色Adapter、LocalWorker隔离、可信验收执行 | 非交互调用、输出解析、fresh Review、实际权限与网络/MCP 边界；合成仓库端到端 |
| M3 | PLAN→IMPLEMENT→REVIEW，加一次返修/接管/最终验收 | 所有分支、预算、修改后审核失效、authorship；真实完整任务 |
| M4 | 崩溃恢复、故障注入、兼容性、受监督到无人值守的运行评估 | 重复/陈旧完成消息、未知副作用不重放、取消回收、各支持 OS、脱敏和保留 |
| M5（可选） | SSH/RemoteWorker、Claude 等扩展 Adapter、评测汇总 | 跨机路径/身份/断线/重连、最小凭证、同合同对比 |

M0 可并行讨论后续接口，但不能提前声称 M1/M2 的安全或恢复有效。M2 必须完成隔离验证后才能运行真实有写入能力的 Agent。远程 Worker 的协议边界从最初保留，运输实现后置。

当前实现任务源规格见 `tasks/M1/`，权威执行包在 `handoffs/M1/v1/`。后续任务应继续使用相同合同模板，每个合同给出有限范围和可失败的验收。

后续全部由本地模型执行，详细子任务和角色提示词见 [全本地模型执行规划](LOCAL-MODEL-EXECUTION-PLAN.md)。云端Agent兼容不再是当前M2的必需门槛；真实隔离、fresh审核和全部验收要求保留。
