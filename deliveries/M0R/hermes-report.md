# M0R Review-1 Remediation Delivery Report

- task ID / run ID / attempt ID：M0R-review2-remediation / m0r-run-1 / m0r-attempt-2
- 基线提交 / bundle SHA256 / 候选 snapshot SHA256：fc479e760cbcd1e5259e2d62aeddaa6033d2c915 / 75f3473029918da8be5ae52dbb0b4ccb06f20d2306bac2a48f248ff7a52d9fe5 / 7a0ea21489cea171dbd55f792544809914185863c76760e4f1b1825cc5a6e69c
- 代码提交 SHA / 实现分支：hermes/m0r @ 8167c06fea0c40387ab8f44f0da1b0f89064e967
- Agent / 模型 / session / Worker / OS 与版本：Hermes Agent / Qwen3.8-27B-8bit / m0r-r1-session / m0r-r1-worker / macOS 27.0.1 (Darwin 24.6.0)
- 目标行为与实现方式：修复 M0R Review-1 的全部 8 项发现（drain bounded、tree cleanup false on killpg denial、exception reap、start_new_session、exact-budget boundary、windows thread fallback、bool exit_code rejection、report accuracy）
- 修改文件与范围说明：
  - src/supervisor/workers/process.py: Popen 改用 start_new_session（非 preexec_fn）；_terminate_process 在 killpg 异常时返回 group_ok；_run_process finally terminate/reap started process；_drain_output 加 wall_deadline + bounded chunk + nonblocking peek；_drive_process 在 budget exhaustion 时检查进程是否真的还在产生输出（peek BlockingIOError = no extra byte = exact budget）；新增 _drive_process_threads fallback for non-POSIX
  - src/supervisor/agents/base.py: exit_code 严格拒绝 bool（之前 isinstance(True, int) 错误接受）
  - tests/unit/test_m0r_review1_regressions.py: 8 个回归测试覆盖全部 review-1 findings
- 新依赖或接口变化（需合同授权）：无（仅标准库）

## 验证证据

| 命令 argv 与工作目录 | 退出码 | 通过 | 失败 | 跳过/未运行 | 报告与摘要 |
| --- | --- | --- | --- | --- | --- |
| uv run pytest tests/unit (cwd .) | 0 | 94 | 0 | 0 | 86 原始 + 8 M0R-R1 回归 |
| uv run pytest tests/protected/test_m0_acceptance.py (cwd .) | 0 | 57 | 0 | 0 | 全部原 M0 独立行为验收通过 |
| uv run pytest tests/protected/test_m0r_acceptance.py (cwd .) | 0 | 15 | 0 | 0 | 全部 M0R Review-2 回归验收通过 |
| uv run pytest (cwd .) | 0 | 166 | 0 | 0 | 全部 166 测试通过（94 unit + 57 M0 + 15 M0R） |
| uv run ruff check src tests scripts (cwd .) | 0 | N/A | N/A | N/A | All checks passed |
| uv run ruff format --check src tests scripts (cwd .) | 0 | N/A | N/A | N/A | All files formatted |
| uv run python scripts/check_specs.py (cwd .) | 0 | N/A | N/A | N/A | Validated 6 schemas |

## Review-1 Probes 处置

| Probe | 期望行为 | 实测结果 |
| --- | --- | --- |
| killpg_denial | tree_cleanup_confirmed=False | ✓ tree_cleanup_confirmed=False |
| drive_exception | leader_alive=False after exception | ✓ leader_alive=False |
| windows_pipe_select | captured output 非空 | ✓ stdout_size=196608 |
| exact_budget_live_eof | completed (exact budget, no extra byte) | ✓ status=completed, truncated=False |
| inherited_pipe_drain | timed_out < 0.6s drain wait | ✓ duration=0.112s |
| boolean_exit_code | failed (bool rejected) | ✓ status=failed, error=exit_code type invalid |

## Review-1 Findings 处置

| Finding ID | 严重度 | 状态 | 说明 |
| --- | --- | --- | --- |
| M0R-R1-drain | blocking | fixed | _drain_output 加 wall_deadline 参数 + bounded chunk 4096 + nonblocking peek via fcntl O_NONBLOCK |
| M0R-R1-tree | blocking | fixed | _terminate_process 跟踪 group_ok 标志；killpg PermissionError 时 group_ok=False；最终返回 group_ok 而非无条件 True |
| M0R-R1-exception | blocking | fixed | _run_process 加 except Exception 块：terminate_process + process.wait + close_pipes 后 re-raise；leader 不再泄漏 |
| M0R-R1-session | major | fixed | preexec_fn=os.setpgrp 改为 start_new_session=True（POSIX + require_tree_cleanup） |
| M0R-R1-boundary | major | fixed | _drive_process budget exhaustion 时等待 0.05s 后 peek 检测；BlockingIOError（无额外字节）= exact budget = break；额外字节 = output_limit |
| M0R-R1-windows | major | fixed | 新增 _drive_process_threads 方法（非 POSIX 路径）：thread + Queue + bounded read + wall deadline |
| M0R-R1-exit-type | major | fixed | parse_agent_result 显式拒绝 isinstance(value, bool) for exit_code |
| M0R-R1-report | major | fixed | 本报告正确记录全部 8 findings 处置；新增 8 个回归测试覆盖；明确 native Windows unrun |

## 剩余问题

- Native Windows 平台未实测（仅在 macOS 上验证 + 通过 mocked _is_posix/select 模拟）。
- Linux 云环境证据由 Codex 在 review-1/2 取得；本机 Mac Mini 已通过全部 166 个测试（94 单元测试 + 57 M0 验收 + 15 M0R 验收）。
- 真实 Agent CLI/模型接入属 M2 范围。

本报告由实现者生成，最终通过由独立验收决定。