# M0 需求与合同

## 目标

建立可测试的 ProcessRunner、统一 AgentResult 和 Mock Adapter，让后续 Workflow 不依赖具体 Agent CLI。接口遵守 docs/interfaces.md 和 schema v1。

固定的公共 Python 入口、构造参数、异常和平台要求见 `api.md`，独立测试以这些入口执行，不要求实现方猜测接口。

## 允许的实现文件

- `src/supervisor/workers/process.py`：ProcessRequest/Result 与进程执行。
- `src/supervisor/agents/base.py`：Adapter 协议、统一结果与严格解析。
- `src/supervisor/agents/mock.py`：无需模型、认证或网络的模拟实现。
- `src/supervisor/core/events.py`：可序列化最小事件及身份。
- `tests/unit/test_m0_*.py`：实现方测试，仅新增这一前缀。
- `deliveries/M0/hermes-report.md`：版本化交付报告。

不改现有 CLI、公共导出、schema、合同、受保护检查、依赖或锁文件。新增模块通过各自路径导入，避免扩大任务。依赖只用标准库。

## ProcessRunner 要求

1. argv 数组＋显式 cwd，禁用 shell；明确可执行文件解析，拒绝空命令、未授权目录、非有限/非正预算。
2. 接收取消信号/句柄，wall timeout、cancel grace、stdout/stderr 合计字节上限；两路输出并发消费，避免 pipe 死锁，不能先全部读入内存再截断。
3. 环境以显式 allowlist 构造，仅保留执行所需变量，不复制完整宿主环境。不得持久化环境值或原始凭证。
4. 保留正常非零退出码、失败原因和输出截断信息。文件/程序不存在、权限不足是 environment_failure，不伪造成 Agent 正常结束。
5. 超时、取消或输出超限，停止并回收支持平台上的进程树；确认结果。平台缺少必要能力时清楚标记 unsupported，不能声称已回收。
6. 不改变调用方工作目录，不更改代码仓库，不自动 git 操作或连接网络。
7. 所有进程资源和管道在异常路径也释放。持续时间使用单调时钟。

## Adapter 与结果

- Adapter 构建请求并解析结果，Worker 负责执行，不在核心层分支判断 provider。
- Mock 根据明确 fixture 产出正常结果、非零退出、超时和损坏协议；fixture 不包含任意用户 shell 命令。
- AgentResult 必须满足 schema；身份由 Supervisor 输入绑定并核对。
- completed 只有实际退出 0、解析完整、无截断且必需字段齐全时成立。退出 0＋非法 JSON 仍是失败；非零退出＋输出 completed 仍是失败。
- usage 未获取写 null；不能虚构 token 消耗或模型能力。审核 session 不能因缺失而沿用旧 session。
- 最小事件含 task/run/attempt、worker、时间和连续 sequence；只记录脱敏元数据，不写原始 prompt/transcript。

## 非目标

真实 Agent CLI、SSH、Git 快照、任务冻结器、状态机、SQLite、OS sandbox、MCP、网络策略、断点恢复、完整 CLI 和 Web UI。

## 验收与交付

实现方单元测试覆盖全部失败行为；Reviewer 使用独立黑盒检查。各平台的支持范围实测记录；只测 Linux 时不能宣称 Mac/Windows 已通过。完整要求见 acceptance.md。

用户已授权 Git 交接。实现代码和报告提交、推送到 hermes/m0，禁止向 main 推送或 force-push。新增文件必须纳入提交，普通 git diff 不包含未跟踪文件。报告参照 templates/implementation-report.md，写入 deliveries/M0/hermes-report.md，包含真实命令与结果、环境/平台及未实现能力。预算见 task.json。任何需求不清、超范围或必要能力缺失，应报告并停止相应行为；不得修改受保护规格使实现通过。
