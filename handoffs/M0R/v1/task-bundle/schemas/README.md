# 协议格式 v1

采用 JSON Schema Draft 2020-12，未知字段拒绝。`scripts/check_specs.py` 检查 schema 本身、示例和 M0 草案；并核对角色引用、文件路径、预算和必需验收。

这些 schema 是受保护规格；实现者不能为了适配错误实现放宽格式。格式校验不证明消息来源、摘要真实性、独立性或权限实施。完整运行时校验仍需由后续实现完成。

`project.schema.json` 当前只支持 scaffold 的 LocalWorker/Mock 配置，`real_agents_enabled` 必须 false。真实配置协议在 M2 的独立规格任务中扩展，避免当前样本暗示可以运行真实 Agent。

Task status=draft 时允许空基线；frozen 时必须有 commit 格式，但还需实际 Git 解析与不可变包校验。Review accept 要求 fresh session、检查已通过且没有 blocking/major finding；Workflow 进一步核验身份、authorship 和快照。

`examples/artifacts/` 与 `templates/review.json` 均为示例，不能作为运行证据。
