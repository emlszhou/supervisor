# 验收判定

1. 两个允许文件符合冻结基线和 scope；项目原测试及仓库级 lint/format 通过。
2. 九个检查 ID 各出现一次，每项有 declared/observed/enforced、status、reason、命令数组、cwd、UTC 起止、真实退出码、输出摘要和 session 证据；未运行项保留 null，不造命令/PID/退出码。
3. 实际路由符合用户对 M2 的授权；未知/错误端点不得悄悄回退；权限不足不执行 Agent 工具。
4. fresh_sessions 中至少两个不同实际启动的 id/source 与真实过程日志匹配；取消回收、响应格式、usage 未知都如实记录。
5. 全新 Reviewer 依据真实版本与可重复行为审核，不能由报告生成者签发 accept。

报告 `adapter_readiness=ready` 需要 cli_help/noninteractive/model_route/fresh_session/output_protocol/endpoint_failure/timeout/cancellation 八项真实通过，且控制面具备下一阶段授权的执行环境。permissions 未强制时不能声明无人值守运行已就绪。其余结果必须 `blocked`，列出缺失前提；完成调查不等于 Adapter/Worker/M2 已验收完成。

本任务允许诚实记录不支持能力；这些证据可以作为调查成果，但不得因此通过下一阶段真实执行门禁。保护校验器只验证证据结构与一致性，不验证时间戳、身份或命令结果的真实性。Reviewer 要独立查实。

## Reviewer 必查真实性清单

- provider 的实际服务端/工具元数据必须指向本任务已批准的 MiniMax cloud；不能用自称模型名或未授权 local/其他云路由替代。
- fresh_sessions 的两个身份分别对应独立启动证据，不是同进程中两个角色名，Reviewer 自己也未参与调查写入。
- 工具禁用来自已核验软件/控制配置，不是模型承诺；不支持禁用就不运行该 Agent smoke。
- 输出 SHA256 能对照本机私有本轮日志、真实 argv/exit/UTC 和精确候选，不能填任意 64 位字符串即验收。
- 非零退出码与预期失败 smoke 的行为分别核对，不能把普通调用失败写为正常成功。
- ready 仅表示调查支持准备下一阶段 Adapter 规格；不批准生产 Agent 执行、不证明 Worker OS 隔离。后续执行环境前提必须单独验证。

保护 validator 的 success 仅为结构一致，不是 accept。合成单元 fixture 是假数据，不能写成 Hermes 真机已通过。
