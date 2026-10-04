# 接口协议 v0.1

下列是目标接口，不是已实现 API。JSON Schema 定义记录格式，运行时还必须检查跨字段约束、来源可信度和摘要真实性。

## Worker

```text
describe() -> WorkerCapabilities
execute(ProcessRequest) -> ProcessResult
cancel(attempt_id) -> CancellationResult
inspect(attempt_id) -> AttemptEvidence
```

`ProcessRequest` 包括参数数组 argv、worker 内工作目录、经白名单过滤的环境、wall timeout、取消宽限期、输出总字节上限、日志路径和 attempt ID。拒绝空命令、相对可执行路径歧义、非有限/非正数预算和未授权目录。生产配置禁止 `shell=True`。

`ProcessResult` 区分 completed、failed、timed_out、cancelled、output_limit、environment_failure，含退出码、输出引用、持续时间、是否完成子进程树回收、truncated 和证据摘要。未知是否回收成功必须报告，不能默认为成功。原始输出属于敏感数据，默认不持久化，选择持久化时受信任配置、访问限制与保留期控制。

## Agent Adapter

```text
probe(worker) -> ObservedCapabilities
build_request(task_bundle, role, attempt, grants) -> ProcessRequest
parse_result(process_result) -> AgentResult
resume_request(session_id, task_bundle, grants) -> ProcessRequest  # 可选
```

Adapter 转换厂商语法，Worker 启动进程。Workflow 只消费统一 AgentResult。返回身份与资源消耗属于声明数据，要与 Supervisor 签发的 attempt 身份核对；缺失 usage 是未知，不是零。

能力需要区分 declared、observed、enforced：structured_output、filesystem_write、shell、resume、sandbox、network、mcp、timeout、model_selection。CLI help 或 Adapter 自报 sandbox 不证明限制有效。以实际操作验证最低权限；不满足合同则阻断。

审核/最终验收必须新 session；resume 仅用于允许的实现阶段，并重新核验 task/snapshot。一次 Review 中修改了代码，该 session 不能再签发独立通过。

## 记录格式

| Schema | 核心绑定 |
| --- | --- |
| `task.schema.json` | draft/frozen、task ID、版本、基线、角色、预算、验收 |
| `agent-result.schema.json` | attempt/run/task、角色、状态、退出码、解析错误 |
| `review.schema.json` | reviewer session、任务包与代码摘要、决定、发现和独立性 |
| `event.schema.json` | event ID、run、attempt、sequence、时间、事件与脱敏属性 |
| `project.schema.json` | Worker、角色绑定、命令 argv、默认拒绝策略与预算 |

未知字段默认拒绝。时间用带时区的 RFC3339；事件存 UTC，展示可转换为用户时区。版本不兼容时明确失败，不能静默忽略。

## 快照与 TaskBundle

冻结包应含 task.json、requirements.md、allowed_files.json、forbidden_files.json、verification.json、基线 commit 和 manifest.json。冻结摘要计算不包含摘要字段本身：按规范化相对 POSIX 路径排序，对每个文件的原始字节记录 SHA256，manifest 采用 UTF-8、排序 key、紧凑 JSON；其 SHA256 为 bundle 摘要。

输入路径只允许包内普通文件，拒绝 `..`、绝对路径、符号链接、大小写冲突和归一化后重复路径。冻结包存控制面，执行者不可写。代码快照包括受控范围内的跟踪、未跟踪文件、删除与文件模式；排除的产物目录在可信配置中固定。文件链接、submodule 和 Git LFS 未支持时明确阻断。

`task.json` 自身不含 bundle 摘要，避免自引用。draft 的基线可以 null；frozen 必须有实际可解析提交。M0 源合同保持 draft，协调者在开工阶段生成外部 frozen 交付包。自动运行时冻结器的实现属于后续里程碑，协调者离线打包不代表该功能已实现。
