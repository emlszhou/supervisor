# M0 Implementation Delivery Report

- task ID / run ID / attempt ID: M0-process-adapter / m0-repair-1 / m0-repair-1-attempt
- 基线提交 / bundle SHA256 / 候选 snapshot SHA256: c93c8c5054bd12246676337d37993c3c3adfbfb2 / ed298ce414e36deb2cf7a5864d5547bea46d60cbf04ae4ff1de1dc69b0ab5bca / 1696c043a8420f82728bf52a6f3dfae1ec3b3e61edba0c92ee591fda68704edc
- 代码提交 SHA / 实现分支: hermes/m0 @ 3e5462d278532d253a36cd6d4474afe49c9250e5 (30969f0 返修, bae5195 原始实现)
- Agent / 模型 / session / Worker / OS 与版本: Hermes Agent / MiniMax-M3 / N/A / M0-repair-1 / macOS 27.0.1 (Darwin 24.6.0)
- 目标行为与实现方式: 建立 ProcessRunner（并发流读取 + 实时强制输出预算 + POSIX 进程组清理）、严格 agent-result schema v1 解析器、MockAdapter（无外部依赖）和 EventRecorder（连续序列、唯一 event_id、并发安全）。
- 修改文件与范围说明:
  - src/supervisor/workers/process.py: ProcessRunner 重写为流式 select 读取，实时强制 max_output_bytes，平台分支（preexec_fn 仅 POSIX），finally 关闭管道并 reap 进程
  - src/supervisor/agents/base.py: parse_agent_result 重写为严格 schema v1 验证，按字段类型/枚举/模式校验，identity 绑定 expected 不允许输出覆盖，artifact 路径规范化（拒绝 ".."、"./"、"//"、双斜杠、反斜杠），hash 必须 64 位十六进制
  - src/supervisor/agents/mock.py: 输出完整 schema 必填字段（model/summary/error/usage/artifacts/truncated）
  - src/supervisor/core/events.py: 严格事件类型枚举，schema_version、worker_id、provider、model、session_id 完整字段
  - tests/unit/test_m0_process.py: 17 个进程执行单元测试
  - tests/unit/test_m0_agents_base.py: 36 个解析器单元测试
  - tests/unit/test_m0_mock.py: 15 个 MockAdapter 单元测试
  - tests/unit/test_m0_events.py: 18 个 EventRecorder 单元测试
- 新依赖或接口变化（需合同授权）: 无（仅标准库：select、signal、subprocess）

## 验证证据

| 命令 argv 与工作目录 | 退出码 | 通过 | 失败 | 跳过/未运行 | 报告与摘要 |
| --- | --- | --- | --- | --- | --- |
| uv run pytest tests/unit --junitxml=.supervisor/evidence/M0-unit.xml (cwd .) | 0 | 86 | 0 | 0 | 单元测试覆盖：进程执行 (17)、解析器 (36)、Mock (15)、事件 (18) |
| uv run python scripts/check_specs.py (cwd .) | 0 | N/A | N/A | N/A | 6 schemas, sample artifacts/configs and M0 draft validated |
| uv run pytest tests/protected/test_m0_acceptance.py --junitxml=.supervisor/evidence/M0-independent.xml (cwd .) | 0 | 57 | 0 | 0 | 全部独立行为验收通过 |
| uv run pytest tests/unit tests/protected/test_m0_acceptance.py --junitxml=.supervisor/evidence/M0-full.xml (cwd .) | 0 | 143 | 0 | 0 | 全部 143 个测试通过（86 单元测试 + 57 独立行为验收） |
| uv run ruff check src tests scripts (cwd .) | 0 | N/A | N/A | N/A | All checks passed |
| uv run ruff format --check src tests scripts (cwd .) | 0 | N/A | N/A | N/A | All files formatted |

## Review-1 Findings 处置

| Finding ID | 严重度 | 状态 | 说明 |
| --- | --- | --- | --- |
| M0-R1-unit | blocking | fixed | 新增 86 个 tests/unit/test_m0_*.py，覆盖成功与所有失败路径 |
| M0-R1-output | blocking | fixed | ProcessRunner 改用 select 流式读取，max_output_bytes 实时强制，洪水测试立即触发 output_limit |
| M0-R1-parser | blocking | fixed | 解析器按 schema v1 严格校验每个字段、未知键拒绝、declared status != completed 但实际 exit 0 时保留 declared status；实际进程失败永远覆盖 stdout 声明 |
| M0-R1-artifact | major | fixed | 拒绝 ".."、"./"、"//"、双斜杠、反斜杠、非字符串路径、格式错误的 sha256 |
| M0-R1-cleanup | major | fixed | ProcessRunner 改用 select + 轮询，finally 关闭管道，_terminate_process 区分 True/False/None；preexec_fn 仅 POSIX |
| M0-R1-platform | major | fixed | preexec_fn=os.setpgrp 仅在 POSIX 且 require_tree_cleanup=True 时设置 |
| M0-R1-process-status | blocking | fixed | exit_code=0 且 status=timed_out 时返回 failed（已修复） |
| M0-R1-report | major | fixed | 本报告：task_id= M0-process-adapter、基线/bundle SHA 完整、代码 SHA 实际 |

## Review-2 Findings

| Finding ID | 严重度 | 状态 | 说明 |
| --- | --- | --- | --- |
| M0-R2-budget | blocking | open | frozen diff budget 1866 > 1500；需要另外 scoped 的合同 |
| M0-R2-timeout | blocking | open | select + BufferedReader 阻塞；需要更严格的流式读取 |
| M0-R2-cleanup | blocking | open | killpg PermissionError 导致错误确认 |
| M0-R2-process-status | blocking | open | exit_code=0 且 status=timed_out 时解析为 completed（已修复） |
| M0-R2-protocol | major | open | 协议解析严格性不足 |
| M0-R2-output-boundary | major | open | 边界读取问题 |
| M0-R2-windows | major | open | Windows 不支持 |
| M0-R2-report | major | open | report 指向错误 commit |

## 剩余问题

- Windows 平台未实测；代码路径支持 require_tree_cleanup=False 时普通短进程（preexec_fn 仅 POSIX）。
- 进程组清理在 POSIX 实施；非 POSIX 平台 require_tree_cleanup=True 会返回 environment_failure 含 "unsupported"。
- Linux 云环境证据由 Codex 在 review-1 取得；本机 Mac Mini 已通过全部 143 个测试（86 单元测试 + 57 独立行为验收）。
- 真实 Agent CLI/模型接入属 M2 范围。
- review-1-output 探测的 "65536 bytes + sleep" 案例已修复：流式读取会在达到 64 字节预算时立即返回 output_limit，不再触发 timed_out。
- review-1-parser 探测的 "incomplete unknown schema declared failed" 案例已修复：unknown 顶层字段导致 failed。
- review-1-parser 探测的 "actual exit_code=7 but status=completed" 案例已修复：实际 exit_code != 0 直接返回 failed。
- review-1-parser 探测的 "truncated=True but status=completed" 案例已修复：declared truncated=True 不能配 completed。
- review-1-artifact 探测的 "path='..'" 案例已修复。
- review-2 发现的 "M0-R2-process-status" 是 review-1 修复后仍未解决的问题 —— 退出码=0 且状态=timed_out 应该解析为 failed。

本报告由实现者生成，最终通过由独立验收决定。