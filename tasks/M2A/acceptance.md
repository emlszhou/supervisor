# 验收判定

1. 两个允许文件符合冻结基线和 scope；项目原测试及仓库级 lint/format 通过。
2. 九个检查 ID 各出现一次，每项有 declared/observed/enforced、status、reason、命令数组、cwd、UTC 起止、真实退出码、输出摘要和 session 证据；未运行项保留 null，不造命令/PID/退出码。
3. 实际路由符合用户对 M2 的授权；未知/错误端点不得悄悄回退；权限不足不执行 Agent 工具。
4. fresh identity 与真实过程日志匹配；取消回收、响应格式、usage 未知都如实记录。
5. 全新 Reviewer 依据真实版本与可重复行为审核，不能由报告生成者签发 accept。

报告 `adapter_readiness=ready` 需要 cli_help/noninteractive/model_route/fresh_session/output_protocol/endpoint_failure/timeout/cancellation 八项真实通过，且控制面具备下一阶段授权的执行环境。permissions 未强制时不能声明无人值守运行已就绪。其余结果必须 `blocked`，列出缺失前提；完成调查不等于 Adapter/Worker/M2 已验收完成。

本任务允许诚实记录不支持能力；这些证据可以作为调查成果，但不得因此通过下一阶段真实执行门禁。保护校验器只验证证据结构与一致性，不验证时间戳、身份或命令结果的真实性。Reviewer 要独立查实。
