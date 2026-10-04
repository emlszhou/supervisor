# 本地模型 Git 交接入口

后续规划、实现、审核、返修、接管和最终验收全部由本地模型执行。详细规划和可粘贴提示词见 [LOCAL-MODEL-EXECUTION-PLAN.md](LOCAL-MODEL-EXECUTION-PLAN.md)。

当前先完成M1：按 [冻结包README](../handoffs/M1/v1/README.md) 获取hermes/m1与外部只读合同，遵守固定API和允许文件。保留现有M1合同字节和42项验收，不因模型路由改变重建合同。

实现代码和报告分别commit并push；全新本地Reviewer独立克隆精确候选，核验包/基线/范围/预算后重跑检查和故障探测。审核报告放local/m1-review-*分支，Implementer只读取，不merge/cherry-pick报告进实施分支。

最多一次主要返修、一次接管，接管后另起Final Verifier。accept绑定精确候选与摘要，不能凭实现者口述通过。当前授权范围内正常Git交接不需重复确认；main合并和部署按任务授权或可信预授权执行。

云环境发布不影响本地Git交接。模型会话、凭证、权重和运行日志不提交Git；同模型新会话只算上下文分离，原生平台未测写明未测。
