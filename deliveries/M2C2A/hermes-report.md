# M2-C2A 实施报告（M2C2A-seatbelt-synthetic，C2A-R2 返修）

> 文件名沿用 `hermes-report.md`（冻结合同指定的版本化路径，历史接口名）。编码执行工具为
> **MiniMax Code CLI（mcode）**；合同、基线、验收、权限与既有消耗未因此改变。

## 0. 实际运行信息（本轮）

| 项 | 值 | 证据 |
| --- | --- | --- |
| 工具 | MiniMax Code CLI（`mcode`） | `mcode --version` → `0.6.8` |
| 角色 | Implementer | 本轮 |
| provider | **未知** | CLI 未暴露 provider 查询；不据工具名推断 |
| model | 运行时声明 `MiniMax-M3.1-Flash-Preview` | 运行时声明值，**未做独立路由核验** |
| 实施检出 | `/Users/william/Public/AI project/supervisor-M2A`（git worktree） | `git worktree list` |
| 实施分支 | `mcode/m2c2a-r1` | 本轮继续，未新建分支 |
| 起点候选 | `97416f1a677cbdc8bc1d4860f56f52565e885338` | `git ls-remote origin mcode/m2c2a-r1` 核验一致 |
| 输入审核 | `540a7f4fcb361664e36a3869729222a15b4b33d0`：`deliveries/M2C2A/codex-review-2.md` | `git ls-remote origin codex/m2c2a-review-2` |
| baseline（继承） | `51d497cae7f20872e5a5f9c8825fd0f83323a92f` | 未改动 |
| 冻结合同 | `f01525c5b92dd516c7d2fbf9f7c2e8034514c1353d5d270460d7fcdca383b9ef` | 导出包 `CHECKSUMS.sha256` 15/15 OK |

周期/调用数为建议值；本轮未重置历史消耗。

## 1. C2A-R2 六项 finding 逐项处置

| finding | 严重度 | 状态 | 关键改动 |
| --- | --- | --- | --- |
| C2A-R2-matrix | blocking | 代码层已改 | `_PROBES` 重排为**对照先行**：每个拒绝动作先跑同 fixture/同 argv/同 cwd/同目标的 positive 对照，harness 随后把目标恢复到原始字节并复核摘要，再跑拒绝动作。`_classify_records` 改为**两遍**：先判全部对照与独立 positive，再用对照结论判拒绝（原单遍在对照仍为 unknown 时判定，合法拒绝永远无法 pass）。矩阵由 16 probe 展开为 25 case，补齐 T1 其他哨兵与链接越界、T2 ro 直写/链接写拒绝、T3 两个独立监听端点。`fixture` 改为执行 `ro/fixtures/` 下的只读副本（原执行检出原文件），并以 `sys.executable` 显式入 argv 且记录。删除了给对照额外注入的 `M2C2A_ALLOW_TARGET`（fixture 根本不读它）。 |
| C2A-R2-process | blocking | 代码层已改 | `_kill_process_tree` → `_cancel_process_tree`：TERM 后**轮询整组**（leader 退出不再跳过组内回收），未清空则升级 SIGKILL 并再轮询；`killpg` 失败不再被吞（`term_error`/`kill_error` 记录）。新增启动身份快照 `_pid_identity(pid, wait=…)`（含 `lstart`+pgid，带重试以消除 `ps` 竞态），取消前复核身份，身份不符则**拒绝发信号**。`process_tree(pid, expected_identity)` 返回 `identity_match`。`_cleanup_state` 旧的语义反转 bug 已删除，改用 `_cleanup_state_from_cancel`：整组确认消失才 True、确认残留 False、答不出为 None。`cleanup_confirmed` 现从取消结果派生并随记录返回。 |
| C2A-R2-lifecycle | blocking | 代码层已改 | 清理改为**门禁式**：`persistence_verified` 且 `cleanup_blockers()` 为空才 `_clean_attempt` + `finalize_package`；C1 导出失败、执行故障、复制/引用/预清理校验失败、进程状态未知一律**保留现场**并如实报告。finalize 后调用 `evidence.verify_package` 记录最终验证。补齐合同要求的交付树：`process_tree.json`、`denied_manifest.json`、`profiles/<case>.profile`、`capture/<case>.stderr.log`、`boundary-record.json`。C1 模块不再只"加载"：实际调用其 `validate_evidence` 对自产记录做七 check 校验（本轮离线实测 `validated: True, checks: 7`）。 |
| C2A-R2-environment | blocking | 代码层已改 | `env=dict(os.environ)` 改为 `_minimal_env()`：只复制 `_MINIMAL_ENV_NAMES` 白名单（PATH/HOME/TMPDIR/LANG/LC_ALL/LC_CTYPE/TZ/TERM）加合成值，宿主其余变量（含凭证）不再进入合成 Worker。fixture 的 `action_env` 改为输出**全部**环境变量名并单列 `undeclared_names`，只报名称不报值。离线注入 credential sentinel（`M2C2A_TEST_CREDENTIAL_SENTINEL`、`AWS_SECRET_ACCESS_KEY` 等）验证未传递。 |
| C2A-R2-evidence | major | 已关闭 | 删除 `_META` 无条件豁免：`verify_package` 现在只豁免 `manifest.json`/`CHECKSUMS.sha256`，`pre-cleanup-manifest.json` 是**普通最终 payload**，未列即拒、被列为符号链接即拒、篡改即拒。阶段差异改由显式接口 `verify_pre_cleanup_package()` 承担（仅豁免自身、不要求 CHECKSUMS）。`_check_inventory` 对被忽略名仍先 `lstat`，忽略名放符号链接直接拒绝。 |
| C2A-R2-capture-budget-network | major | 已改 | reader 每次按 `room + 1` 读取：恰好写满预算再 EOF **不算超限**，第 N+1 字节才算（离线实测 max_output=16 写 16 → `output_limited=False`；写 17 → `True` 且存储仍为 16）。删除"内核不会多给一字节"的错误注释。捕获改为**原始 bytes** 落盘（不再 decode→encode），stderr 同步落盘为 `<case>.stderr.log` 并各自计 hash。实现 attempt 级 `TOTAL_CAPTURE_BUDGET`（1 MiB），超限时后续 case 记 `capture_budget_exhausted` 而非继续抓取。`run_loopback_control` 增加 ready 握手（bind+listen 都成功才置位）与 cancel，每条路径都显式关闭并回报 `closed_confirmed`；拒绝侧与对照侧各用**两个不同端口**，分类时 `_listener_evidence_ok` 要求 listener 确实 bind 且关闭确认，否则 `observation_complete=False` → unknown，ECONNREFUSED 不再被当作隔离。 |

### 本轮自行发现并修复的缺陷

1. `_restore_target` 收到 `baseline=None` 时直接返回摘要而**没有真正恢复**，所谓"恢复初态"是空操作；现已始终恢复。
2. 恢复逻辑会把 `PRISTINE_TARGET_BYTES` 写进 `ro/fixtures/seatbelt_probe.py`，**摧毁只读 fixture 副本**，导致 T6 超时用例以 exit 1 秒退。现对 `ro` 区只取摘要不写回。
3. 启动身份快照存在竞态：`Popen` 后立即 `ps` 可能查不到进程，被误判为"身份无法确认"。现带 1 秒有界重试。
4. 环境隔离检查暴露出 macOS 会向每个子进程注入 `__CF_USER_TEXT_ENCODING`。如实**声明**为 OS 注入项（harness 与 fixture 两侧同步声明并注明原因），而非放宽检查或隐藏。

## 2. 离线验证（本轮实际 exit / 计数）

| 检查 | 命令 | exit | 计数 |
| --- | --- | --- | --- |
| protected（冻结用例） | `uv run --frozen python -m pytest "$CONTRACT/task-bundle/tests/protected/test_contract.py" -q` | **0** | **46 passed** |
| M2C2A 单元 + 集成 | `uv run --frozen python -m pytest tests/unit/test_seatbelt_backend.py tests/unit/test_boundary_package.py tests/integration/test_seatbelt_preflight.py -q` | **0** | **90 passed** |
| 项目全套（macOS/APFS） | `uv run --frozen python -m pytest -q` | **1** | 335 passed, 1 skipped, **55 failed** |
| ruff check | `uv run --frozen ruff check .` | **0** | All checks passed |
| ruff format | `uv run --frozen ruff format --check .` | **0** | 69 files already formatted |
| specs | `uv run --frozen python scripts/check_specs.py` | **0** | 通过 |
| build | `uv build --no-sources` | **0** | sdist + wheel |

`${CONTRACT}` 使用实际已校验的外部导出绝对路径，未把开发机目录硬编码进生产代码或测试。

### 55 项失败基线对照

全部位于 M1 测试文件，与本任务改动文件零交集：`test_m1_fallback_regressions` 21、`test_m1_changes` 10、
`test_m1_bundle` 10、`test_m1_snapshot` 9、`test_m1_baseline` 5。根因一致为
`ValueError: case-insensitive filesystem is not supported`（`src/supervisor/workspace/snapshot.py:158`），
即交接单已单列的 macOS 大小写不敏感既有失败，数量与分布与上一候选完全一致。
**M2C2A 相关测试 0 失败。**

### 本轮新增的回归（证明合同行为，不镜像实现）

精确预算边界（16 不超限 / 17 超限且不超存）、非 UTF-8 捕获逐字节往返 + stderr 落盘、
整树清理三态（含身份不符 → unknown）、合法拒绝（EPERM + 目标未变 + 对照 pass）判为 pass、
对照失败时拒绝降为 unknown、观察到 effect 时立即 fail、
无真实 listener 的回环拒绝判 unknown / listener 收到连接判 fail、
listener ready 握手后可立即连接、最小环境丢弃宿主凭证 sentinel、端到端凭证 sentinel 不进入 Worker、
两个回环端点必须不同、`pre-cleanup-manifest.json` 未列/链接/篡改三种拒绝、
最小普通包仍被接受、持久化失败保留现场、进程状态未知阻止清理。

## 3. 宿主门禁与 not_run 事实

- Mac probe **未授权**。本轮**未**创建 `/tmp/m2c2-sandbox`、**未**执行 `sandbox-exec`、
  **未**启动真实 Hermes/mcode Agent、**未**读取真实凭证、**未**访问外网或非授权端口。
  离线测试中的 127.0.0.1 监听仅使用 pytest 临时端口，属合同允许的合成回环，未做实际网络探测。
- 全部 required 子项（T1/T2/T3/T5/T6）记 **not_run**；T7 记 **unknown**；平台能力 **partial**。
- 离线集成测试把 `run_worker` 替换为直跑 fixture，**不构成**任何 macOS 强制隔离证据。
  该用例中"拒绝动作"真的成功，因此相关子项得到 `fail`——这是策略被真实评估的证据，不是通过信号。
- `live` 恒拒绝：`backend.require_live_execution` 未改动。
- 生产实际 SBPL 有效性仍须 Mac 另测，离线测试不对此作任何声明。

## 4. 范围

- 本轮改动 5 个文件，全部在 `allowed_files` 内；累计相对 baseline 仍为 8 个允许文件（5851 新增行）。
- 未改 forbidden：`tasks/**`、`handoffs/**`、`schemas/**`、`tests/protected/**`、
  `src/supervisor/workers/process.py`、`boundary.py`、agents/workspace、`docs/**`、`AGENTS.md`、
  `pyproject.toml`、`uv.lock` 等。未新增依赖（生产代码标准库）。
- `MIGRATION_PLAN.md` **保留在磁盘但不提交**：过程快照，不在 allowed_files 内。

## 5. 尚缺权限与遗留问题（如实列出）

1. **Mac 两个写根与合成回环范围的明确批准**未获得，真机矩阵无法执行。
2. profile 的最小运行只读允许清单须在真机逐项披露并实测；当前仅为注释声明 + 默认 deny。
3. **无法表达的同目标对照**：`build_profile` 的冻结规则限定 `allow_target` 只能是 denied/secret 下的单文件，
   因此 `T1-link-escape-read`（work 内指向 secret 的符号链接）与 `T2-write-link`（work 内指向 denied 的符号链接）
   无法构造同目标 allow 对照。这两项**已执行并记录**，但因 `control_passed` 恒为 False 而只能是 `unknown`——
   这是如实上报的能力缺口，未通过弱化判定掩盖。
4. 离线替换 `run_worker` 后无法验证真实 Seatbelt 生效；`_cleanup_state_from_cancel` 的整树语义只在
   合成故障注入下验证，未在真机验证。
5. Linux 干净独立检出全套复跑：需 fresh Reviewer 环境，本轮未执行。
6. 实施合入 main 与部署：均未授权。

## 6. Git 事件

- 分支 `mcode/m2c2a-r1`，自 `97416f1` 继续；未 merge main、未 merge 审核分支。
- 普通提交 + 普通推送；无 force / reset / clean / 删除分支 / main 合并 / 部署。
- 候选 SHA：见交付消息（commit 后以 `git rev-parse HEAD` 与 `git ls-remote` 双向核验）。

## 7. fresh Reviewer 说明

本轮**不模拟** fresh 审核。请独立 Reviewer 绑定本候选精确 SHA 与合同 `f01525c5…`，
复跑 §2 全部检查（Linux 全套 + Mac 55 项单列 + protected 46），核对真实捕获、授权记录来源，
并填 T7 真实流程证据。同供应者执行则 `independent_provider=false`。
本报告**不自称 ACCEPT**，也未提前宣称全部 finding 关闭；第 5 节列出的遗留项需 Reviewer 独立判断是否可接受。
