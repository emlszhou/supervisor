# 状态机与恢复

正常路径：

```text
CREATED → PLANNING → PLAN_READY → IMPLEMENTING → REVIEWING_1
                                             ├─ accept → COMPLETED
                                             └─ return_once → REPAIRING_PRIMARY → REVIEWING_2
                                                                               ├─ accept → COMPLETED
                                                                               └─ takeover → FALLBACK_REPAIR
                                                                                              → FINAL_VERIFY
                                                                                              ├─ accept → COMPLETED
                                                                                              └─ reject → VERIFICATION_FAILED
```

计划阶段由 A 生成草案，经可信策略和验收规格核对后冻结。涉及新的权限或无法确定的业务要求时进入 `NEEDS_HUMAN`；不让 Agent 自己批准扩权。外部直接提供的已冻结任务可以从 PLAN_READY 开始。

## 转换守卫

- 所有结果必须属于当前 run/task/attempt，且解析有效。
- accept 必须有当前快照的独立验证完成证据、没有未解决 blocking finding、fresh session 和匹配任务包摘要。
- Review 1 只能 accept/return_once/blocked/reject；Review 2 只能 accept/takeover/blocked/reject；Final Verify 只能 accept/blocked/reject。
- 返修次数不超过 1，接管次数不超过 1；预算耗尽即停止。
- 更改任务要求创建新版本，旧 run 标为 `SUPERSEDED`，不继续使用旧验收。
- 安全违规优先停止，不因为测试通过继续返修。

## 非成功终态

| 状态 | 含义与动作 |
| --- | --- |
| `BLOCKED` | 外部前提不具备；明确所需条件 |
| `NEEDS_HUMAN` | 要求或副作用无法判定；保留证据 |
| `ENVIRONMENT_FAILURE` | 执行环境或依赖问题；与代码缺陷分开 |
| `AGENT_FAILURE` | 非零退出、协议损坏或服务故障 |
| `POLICY_VIOLATION` | 越界或受保护输入变化；立即停止 |
| `VERIFICATION_FAILED` | 可信检查或最终审核未通过 |
| `SCOPE_EXPLOSION` | 变更文件、行数或行为预算超限 |
| `CANCELLED` / `SUPERSEDED` | 用户取消或任务版本被替换 |

非法状态转换、陈旧结果和重复结果不推进状态；保留对应事件。失败不能被解释成可用的空输出。

## 恢复协议

每次启动恢复时核验数据库、冻结包、基线和候选快照。`IMPLEMENTING` 状态只说明有意图，不证明 Agent 尚未运行。

1. 查询 operation/attempt 和实际进程/Worker 证据。
2. 已完成且结果、摘要齐全：幂等导入并继续。
3. 仍在运行且身份匹配：重新连接或报告运行中，不启动第二份。
4. 工作区已变但完成证据缺失：进入 NEEDS_HUMAN。
5. 只有能证明未产生副作用的操作才允许重试；签发新的 attempt ID。

不能承诺任意命令恰好执行一次。模型调用、网络请求、文件写入和数据库提交之间存在崩溃窗口；设计以可解释的不确定状态处理。
