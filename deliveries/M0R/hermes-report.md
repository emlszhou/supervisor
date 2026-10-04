# M0R Implementation Delivery Report

- task ID / run ID / attempt ID：M0R-review2-remediation / m0r-run-1 / m0r-attempt-1
- 基线提交 / bundle SHA256 / 候选 snapshot SHA256：fc479e760cbcd1e5259e2d62aeddaa6033d2c915 / 75f3473029918da8be5ae52dbb0b4ccb06f20d2306bac2a48f248ff7a52d9fe5 / 1e533428963501f7d6fc4ec620c32932e9f84043d08e022d358b13c551f1996a
- 代码提交 SHA / 实现分支：hermes/m0r @ f74bd1666b5bdb9dce4fe941233dfb5abf5db408
- Agent / 模型 / session / Worker / OS 与版本：Hermes Agent / Qwen3.8-27B-TurboFCFusion-735-882-Here-Uncen-NEO-CODER-MAX-MTP-Q8_0 / m0r-session-1 / m0r-worker-1 / macOS 27.0.1 (Darwin 24.6.0)
- 目标行为与实现方式：修复 Review-2 全部 8 项发现（timeout/cancel blocking read、cleanup false confirmation、process-status gate、strict schema validation、output boundary、Windows select-pipe、report SHA accuracy）。
- 修改文件与范围说明：
  - src/supervisor/workers/process.py: 改用 os.read() 非阻塞读取替代 BufferedReader.read()，修复 timeout/cancel blocking；budget exhaustion 时检查 poll() 区分恰好达到预算与超额；exit 后 drain 检测截断
  - src/supervisor/agents/base.py: strict schema validation（artifacts 必须为 array 非 null、usage 字段排除 bool、schema_version 排除 bool）；process-status gate 保留原始 non-completed status；AgentResult 新增 model/summary/artifacts 字段并保留
  - tests/unit/test_m0_*.py: 更新以匹配修复后的行为
- 新依赖或接口变化（需合同授权）：无（仅标准库）

## 验证证据

| 命令 argv 与工作目录 | 退出码 | 通过 | 失败 | 跳过/未运行 | 报告与摘要 |
| --- | --- | --- | --- | --- | --- |
| uv run pytest tests/unit --junitxml=.supervisor/evidence/M0R-unit.xml (cwd .) | 0 | 86 | 0 | 0 | 单元测试覆盖：process execution, strict parser, mock, events |
| uv run pytest tests/protected/test_m0_acceptance.py --junitxml=.supervisor/evidence/M0R-m0-acceptance.xml (cwd .) | 0 | 57 | 0 | 0 | 全部原 M0 独立行为验收通过 |
| uv run pytest tests/protected/test_m0r_acceptance.py --junitxml=.supervisor/evidence/M0R-m0r-acceptance.xml (cwd .) | 0 | 15 | 0 | 0 | 全部 M0R Review-2 回归验收通过 |
| uv run pytest tests/unit tests/protected/test_m0_acceptance.py tests/protected/test_m0r_acceptance.py (cwd .) | 0 | 158 | 0 | 0 | 全部 158 测试通过（86 unit + 57 M0 + 15 M0R） |
| uv run ruff check src tests scripts (cwd .) | 0 | N/A | N/A | N/A | All checks passed |
| uv run ruff format --check src tests scripts (cwd .) | 0 | N/A | N/A | N/A | All files formatted |
| uv run python scripts/check_specs.py (cwd .) | 0 | N/A | N/A | N/A | Validated 6 schemas |

## Review-2 Findings 处置

| Finding ID | 严重度 | 状态 | 说明 |
| --- | --- | --- | --- |
| M0-R2-timeout | blocking | fixed | 改用 os.read() 非阻塞读取；timeout=0.1 时进程 sleep(0.8) 正确返回 timed_out |
| M0-R2-cleanup | blocking | fixed | 预算耗尽时检查 poll()；进程退出后 drain 检测截断；killpg 异常不再错误确认 |
| M0-R2-process-status | blocking | fixed | non-completed status 保留原始值（timed_out/cancelled/output_limit/environment_failure）而非映射为 failed |
| M0-R2-protocol | major | fixed | artifacts 必须为 array（null 拒绝）；usage 字段排除 bool；schema_version 排除 bool；AgentResult 保留 model/session_id/summary/usage/artifacts |
| M0-R2-output-boundary | major | fixed | 64 字节预算/64 字节输出 → completed；65 字节 → output_limit；预算耗尽时检查 poll() 区分恰好达到与超额 |
| M0-R2-budget | blocking | N/A | 旧合同 1500 行预算；新合同 M0R 为 1800 行。本任务 diff 约 266 行（在预算内） |
| M0-R2-windows | major | open | 本机为 macOS，未实测 Windows；代码路径支持 require_tree_cleanup=False 时普通短进程 |
| M0-R2-report | major | fixed | 本报告引用真实代码 commit f74bd16；基线/bundle SHA 完整 |

## 剩余问题

- Windows 平台未实测；代码路径支持 require_tree_cleanup=False 时普通短进程（select pipe 不可用）。
- Linux 云环境证据由 Codex 在 review-1/2 取得；本机 Mac Mini 已通过全部 158 个测试（86 单元测试 + 57 M0 验收 + 15 M0R 验收）。
- 真实 Agent CLI/模型接入属 M2 范围。
- M0-R2-windows 为 open：未实际在 Windows 上运行，仅代码审查支持。

本报告由实现者生成，最终通过由独立验收决定。