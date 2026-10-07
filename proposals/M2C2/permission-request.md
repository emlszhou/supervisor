# M2-C2 宿主授权请求（待用户审阅，本轮不执行任何请求项）

本文件是具体、可审阅的授权请求清单。M2-C2 实施合同冻结前，下列操作**一项都不执行**。授权按项粒度给出，用户可以只批准部分。"未授权即绝不执行"项在 §9 单独列出。

## 1. 执行机器

- 机器：当前 Mac mini（`Darwin Mac-mini.lan 27.0.0`，macOS 27.0.0，arm64）。
- 执行账户：`william`（当前开发账户；不创建新账户，不切换账户）。
- Linux 后端（plan.md §2 方案 B）不在本轮授权范围；如需 Linux 机器/CI，另行提出。

## 2. 统一授权根与精确写入目录

**唯一授权根**：`/tmp/m2c2-sandbox/`（所有合成路径都在此根内；无其他临时目录，无 `/tmp/m2c2-outside-*`，无根外 sidecar）。

允许的写入子树（每 attempt 一个目录，attempt_id 为安全 ID `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`）：

| 路径 | 用途 | 写入内容 |
| --- | --- | --- |
| `/tmp/m2c2-sandbox/<attempt_id>/work/` | 合成 Git 仓库（Worker 可写子树） | 合成项目文件、合成 tests/protected、合成任务包副本、合成 MCP 配置（哨兵内容） |
| `/tmp/m2c2-sandbox/<attempt_id>/out/` | Worker 可写区 | 正向测试产物、哨兵文件、符号链接逃逸测试用 |
| `/tmp/m2c2-sandbox/<attempt_id>/ro/` | 只读材料（Worker 内只读） | 冻结包副本、控制面 mock、合成凭证哨兵、合成 MCP 哨兵、自建回环服务脚本、**冻结 fixture 脚本（fixtures 在 `ro/fixtures/`；sandbox 内 Worker 可读，可执行 `python3 /path/to/ro/fixtures/<t_id>.py <argv…>`） |
| `/tmp/m2c2-sandbox/<attempt_id>/denied/` | Worker 不可写的拒绝目标区（Worker 全 deny） | 合成 AGENTS.md、合成 .git、合成 tests/protected（初始由 harness 填充，前后 sha256 校验） |
| `/tmp/m2c2-sandbox/<attempt_id>/secret/` | Worker 不可读的区（Worker 全 deny） | 合成凭证哨兵（固定内容如 `SENTINEL_CREDENTIAL_M2C2_NOT_REAL`） |
| `/tmp/m2c2-sandbox/<attempt_id>/harness/deps/` | C1 依赖导出（harness 专属，Worker 不可读/不可写） | `boundary.py` 单文件（从绑定不可变 ref `436e3b0e026580a6b39ece891e8ffe47ac1bb698` 导出，Python 文件 I/O，不写到 `/tmp/m2c2-c1-boundary*` 任何路径） |
| `/tmp/m2c2-sandbox/<attempt_id>/harness/profiles/` | Seatbelt profile 文件（harness 专属，Worker 不可读/不可写） | 合成 profile 文件 |
| `/tmp/m2c2-sandbox/<attempt_id>/harness/capture/` | Worker 输出捕获（harness 专属，Worker 不可读/不可写） | 测试 stdout/stderr 捕获文件（单项 ≤ 64KiB），通过 harness 管道捕获，不置于 Worker 可写区 |
| `/tmp/m2c2-sandbox/<attempt_id>/harness/evidence/` | 证据记录（harness 专属，Worker 不可读/不可写） | 逐子项结构记录 + summary + capture 文件 sha256 |
| `/tmp/m2c2-sandbox/<attempt_id>/harness/state/` | 状态 sidecar（harness 可写，**Worker 全 deny 不可读/不可写**） | 状态 JSON（按 LOCAL-MODEL-RUNBOOK §6 原子更新）；不暴露给 Worker 以免泄露 harness 内部状态 |

**可信 harness 独立输出根（这是提案待批准范围，不与 git push 不写入主仓库冲突）：**

| 路径 | 用途 | 写入内容 |
| --- | --- | --- |
| `/Users/william/Public/AI project/supervisor-M2A/deliveries/M2C2/evidence/<attempt_id>/` | **可信 harness 持久化输出根**（独立于授权根 `/tmp/m2c2-sandbox/`；Worker 全 deny 不接触） | 完整 evidence 包：`evidence/<test_id>.json`、`capture/*.log`、`manifest.json`（全部文件条目，不含自身）、`CHECKSUMS.sha256`（外置摘要表，含 manifest 自身）、`summary.json`、`process_tree.json`、`denied_manifest.json`、`cleanup.json`；脱敏合成字节，不含原始 Agent transcript、不含完整环境变量 |

只读/不可写参考（不写入）：`/tmp/m2c2-sandbox/<attempt_id>/ro/` 内所有内容对 Worker 只读；`denied/`（不可写）、`secret/`（不可读）、`harness/`（全 deny）对 Worker 全 deny。

清理策略（**顺序固定，不可提前填结果**）：每 attempt 结束 ①预清理校验（持久化根全部引用文件存在且 sha256 与记录一致），②生成 pre-cleanup `manifest.json`（全部文件条目，不含自身、不含尚未产生的 `cleanup.json`），③真实清理（`rm -rf /tmp/m2c2-sandbox/<attempt_id>` + `ls` ENOENT 验证，记录 argv/exit），④清理完成后写 `cleanup.json` 到持久化根（**不得提前填 ENOENT 或 exit_code=0**；含 `pre_cleanup_manifest_sha256`，不含最终 manifest 摘要），⑤更新最终 `manifest.json` 追加 `cleanup.json` 条目（仍不含自身）+ 写外置 `CHECKSUMS.sha256`，⑥最终校验（全部条目重读重算 sha256 比对）。完整算法见 plan.md §4.0 证据包生成与清理算法。cleanup_argv/exit_code/post_cleanup_ls_output/cleanup_enoent_confirmed/cleanup_timestamp_utc 字段完整记录。清理仅限上述精确路径，不做通配删除，不碰 `/tmp` 其他内容。**清理不删持久化副本**（`evidence/` 与 `capture/` 两目录在 #14 整体复制到持久化根，授权根外、Worker 不可达、版本控制内）；预清理校验不通过时不清理 attempt（保留现场）→ NEEDS_HUMAN；不能清理 attempt 时连唯一证据一起删除。

**不写入**（除上述 §2 列表与可信 harness 独立输出根外）：用户 home、主仓库目录、`~/.hermes`、`~/.config`、`/Users/william/Public/AI project` 下任何其他目录（包括兄弟目录 supervisor、supervisor-M1、supervisor-M0*、M2*-contract、test）、`/tmp` 下 `/tmp/m2c2-sandbox/` 之外任何路径。`/Users/william/Public/AI project/supervisor-M2A/deliveries/M2C2/evidence/<attempt_id>/` 是提案 §2 列表之外的**唯一可信 harness 独立写入根**（不在 §2 第一张表），它与"不写入主仓库"不冲突（git push 只把版本控制目录内容提交；harness 写入 evidence **不等于** git push 隐式获得宿主写权限——本提案必须经用户明确批准 §2 第二张表后，evidence 写入才生效）。

## 3. 安装 / 账户 / 挂载 / 容器 / 网络配置

- 软件安装：**不需要**（`sandbox-exec`、`git`、Python/uv 均已有）。如实施中发现必需新工具，另行单独请求，不捆绑批准。
- 账户：**不创建**新账户；不使用第二账户 `emlszhou`。
- 挂载：**不创建**任何卷/挂载点。
- 容器：**不启动** Docker daemon、不拉镜像、不建容器。
- 网络配置：**不修改**防火墙、路由、hosts、端口转发。
- 本地推理服务：**不启动/停止/重启**任何现有模型服务（cc-switch、18080 端点服务等）；C2A 范围内不访问 15721/18080（P2），网络测试只用 harness 自建回环服务。

## 4. 计划执行的探测命令或参数数组（授权对象）

以下 argv 数组是请求授权的**完整白名单类别**；实施时具体 argv 必须逐项可对应到本清单，超出即视为未授权。所有命令：单项外部 wall ≤ 120 秒、输出捕获 ≤ 64KiB、参数数组调用（无 `shell=True`、无字符串拼接 shell）、cwd 限定在 §2 目录内（除明确标注者外）。

| # | 用途 | argv 类别（`…` 为运行时填充的授权内值） |
| --- | --- | --- |
| P1 | 合成仓库生成 | `git init` / `git -C /tmp/m2c2-sandbox/… commit` / `git -C … add`（仅 work/ 内） |
| P2 | sandbox 启动合成动作 | `/usr/bin/sandbox-exec -f <profile路径> -- <argv…>`，profile 路径在 `harness/profiles/` 内（harness 专属，Worker 不可读/不可写），`<argv…>` **限于 P3–P7 类别（排除 P8 清理与 harness 盘点/记录），仅运行冻结 fixture 动作**（每个 fixture 是版本化 Python 脚本 `/tmp/m2c2-sandbox/<attempt_id>/ro/fixtures/<t_id>.py`，sandbox 内 Worker 可读；禁止 `/bin/sh -c "<string>"` 之类的 shell 重定向固化；禁止 echo > 等命令当 fixture 动作；**含拒绝项的同目标对照 profile 运行**——同 fixture、同 argv、只换隔离配置） |
| P3 | 文件拒绝测试 | `python3 /tmp/m2c2-sandbox/<attempt_id>/ro/fixtures/<t_id>.py --target <absolute_path>`（**版本化 Python fixture**，含 `try/except OSError as e: print(f"errno={e.errno}"); sys.exit(1)` 路径；**fixture 只解析固定 argv 参数，不猜相对层级**，harness 传入明确的 `<attempt>/denied/AGENTS.md` 等绝对路径作为 `--target`；不写 `/bin/sh -c echo`） |
| P4 | 网络测试 | `python3 /tmp/m2c2-sandbox/<attempt_id>/ro/fixtures/<t_id>.py --endpoint 127.0.0.1:<port>`（版本化 Python fixture；socket 连接 harness 自建回环服务；2 秒 connect 超时；固定字节回读；harness 传入明确 endpoint） |
| P5 | 凭证测试 | `python3 /tmp/m2c2-sandbox/<attempt_id>/ro/fixtures/<t_id>.py --secret-dir <attempt>/secret`（版本化 Python fixture；open() 尝试 `secret/.env` 与 `secret/auth.json`；只断言打开失败，捕获任何字节即测试失败；`os.environ` 变量名集合断言；harness 传入明确 secret-dir 路径） |
| P6 | 进程树测试 | `python3 /tmp/m2c2-sandbox/<attempt_id>/ro/fixtures/<t_id>.py --child-script <attempt>/work/child.sh`（版本化 Python fixture；fork 受控 `sleep`/包装脚本，固定深度 ≤ 2，固定时长 ≤ 5 秒；harness 传入 child-script 路径）+ 取消后 `ps -axo pid,ppid,pgid,command`（只读） |
| P7 | 只读盘点 | `ps`、`ls`、`stat`、`sha256sum`/`shasum -a 256`、`id`、`sw_vers`、`uname -a`、`/usr/bin/sandbox-exec` 自身行为探针（如 `sandbox-exec -f <deny-all> -- /usr/bin/true` 的退出码） |
| P8 | 清理（仅 harness 可执行，不通过 sandbox-exec 运行） | `rm -rf /tmp/m2c2-sandbox/<attempt_id>`（仅 §2 精确路径）+ 清理后 `ls` 验证 ENOENT |
| P9 | 证据记录（harness 专属，不通过 sandbox-exec 运行） | harness 用 Python `subprocess.Popen(..., stdout=PIPE, stderr=STDOUT)`（**禁止 shell redirect**）+ 内存写入 `harness/capture/<attempt_id>/<test_id>.log` + 完成后 `shasum -a 256` 计算摘要；Worker 输出**通过 harness 进程管道捕获**，不置于 Worker 可写区让其篡改；capture 文件**含完整脱敏合成字节**（Reviewer 实际可读取验证拒绝行为） |

约束：

- P5 中对 `secret/` 内合成哨兵的交互**只有"尝试打开并预期失败"一种**；任何成功读取、内容捕获、`cat`/`head`/`grep` 该文件都超出授权。
- 真实 Hermes CLI（`hermes …`）**不在本清单**（见 §9）。
- 任何 `sudo`、`chflags`、`chmod`（对授权目录之外）、`launchctl`、`systemsetup`、防火墙命令（`pfctl`/`networksetup`）均不在授权内。
- P8 清理只授权给可信 harness（运行在 sandbox 外），不授权给受测 Worker（运行在 sandbox 内）。

## 5. 网络目标与允许范围（P2：全部为 harness 自建回环服务）

| 目标 | 方向 | 用途 | 限制 |
| --- | --- | --- | --- |
| harness 自建回环服务 #1（127.0.0.1 随机高端口，harness 自起自收） | outbound TCP connect | 正向测试/同目标对照（确认 harness 监听有效，排除 ECONNREFUSED 歧义） | 单连接 ≤ 2 秒，总字节 ≤ 8KiB |
| harness 自建回环服务 #2（127.0.0.1 随机高端口，harness 自起自收） | outbound TCP connect | 网络拒绝测试（预期被 sandbox deny，harness 确认监听有效） | 单连接 ≤ 2 秒，总字节 ≤ 8KiB |
| 127.0.0.1 无监听端口（对照） | outbound TCP connect | 区分 sandbox deny 与 ECONNREFUSED | 单连接 ≤ 2 秒 |
| 其他一切目标（含 15721/18080/93.184.216.34） | — | 禁止 | — |

说明：C2A 范围内不访问现有 15721/18080 未知协议服务（P2）；不连接 93.184.216.34（P2）；纯回环证据只证明实际覆盖的端点/协议拒绝，不能直接声明所有外网/UDP/IPv6 均被验证（plan.md §4.1 T3）。

## 6. 禁止触碰的目录、凭证与其他项目（硬边界）

- 目录：`/Users/william/Public/AI project/` 下除当前 worktree（`supervisor-M2A`，且仅限 `proposals/M2C2/` 新文件）外的一切；`/Users/william/.hermes/`（C2A 范围内不访问）；`/Users/william/.ssh/`、`/Users/william/.aws/`、`/Users/william/Library/Keychains/`、`~/.config/`、`~/.local/share/`；`/etc`、`/usr`、`/var`（系统只读，不写）；用户其他任何仓库/项目。唯一可信 harness 独立输出根 `deliveries/M2C2/evidence/<attempt_id>/` 已在 §2 第二张表明确列入（不是从 Git push 隐式获得宿主写权限——本提案必须经用户明确批准后 evidence 写入才生效，详见 §2）。
- 凭证：任何真实 API key、token、密码、私钥、git 凭证（`~/.git-credentials`、credential helper 存储）——不读、不拷、不出现在 argv/日志/提交中。密钥测试只用 §2 的合成哨兵值。
- 进程：不 kill 任何非本 attempt 启动的进程；不停推理服务；不用 `pkill`/`killall` 通配。
- Git：本仓库内只做已授权操作（见 §8 之外另列）；其他仓库零操作。**git push 不授予宿主写权限**——git push 只把版本控制目录内已存在的对象提交；evidence 写入是 harness 用 Python `open(path, "wb")` 落盘到磁盘，独立于 git push 机制；harness 写入 evidence **不等于** git push 隐式获得宿主写权限——必须本提案 §2 第二张表被用户明确批准后 evidence 写入才生效。
- 数据：原始 Agent 对话/模型请求正文/完整环境变量不写入任何提交或共享目录。

## 7. 进程超时、输出上限与清理策略

- 单项测试外部 watchdog：wall ≤ 120 秒；到点 TERM → 宽限 5 秒 → KILL（只作用于本 attempt PID 集合）。
- 单命令输出捕获：≤ 64KiB（stdout+stderr 合计）；超限记 `output_limit` 并终止该命令。
- 单 attempt 总 wall：建议 ≤ 2 小时（advisory）；总输出捕获 ≤ 1MiB。
- 清理（顺序固定，不可提前填结果；完整算法见 plan.md §4.0 证据包生成与清理算法）：
  1. 预清理校验（持久化根全部引用文件存在且 sha256 一致）。
  2. 生成 pre-cleanup `manifest.json`（全部文件条目，不含自身、不含 `cleanup.json`）。
  3. **真实清理**（`#16`）：`rm -rf /tmp/m2c2-sandbox/<attempt_id>` + `ls` 验证 ENOENT，记录 argv/exit。
  4. **写 cleanup.json 到持久化根**（清理完成后才能写，**不得提前填 ENOENT 或 exit_code=0**）：`cleanup_argv` / `cleanup_exit_code` / `post_cleanup_ls_output` / `cleanup_enoent_confirmed`（bool）/ `cleanup_timestamp_utc` / `pre_cleanup_manifest_sha256`。
  5. 更新最终 `manifest.json` 追加 `cleanup.json` 条目（仍不含自身）+ 写外置 `CHECKSUMS.sha256` + 最终校验。
  6. 清理失败即整体记"清理未确认"，后续 attempt 不启动，先人工核对。
- 崩溃恢复：按 `docs/LOCAL-MODEL-RUNBOOK.md` §5–6：断线/超时先核对实际进程与副作用，不重放可能已有副作用的操作；状态 sidecar 在 §2 的 `state/` 子目录内（统一授权根）。

## 8. 已授权操作（无需本轮再批准）

- `emlszhou/supervisor` 仓库内普通 `git fetch / commit / push`（分支 `local/m2c2-plan-pi` 及后续实施/审核分支）。
- 当前 worktree 内 `proposals/M2C2/` 新增文件。
- 只读 Git 操作：`git log/show/ls-tree/diff/rev-parse`、`git ls-remote`。
- 只读系统元信息：`sw_vers`、`uname`、`id`、`git --version`、`hermes --version`（不发起模型调用）。

## 9. 未授权、本轮绝不执行的操作

| # | 操作 | 原因 |
| --- | --- | --- |
| N1 | 本提案 §4 中的任何宿主探测命令（P1–P9） | 本轮是规划，实施需 C2A 合同冻结 + 用户批准后按合同执行 |
| N2 | 启动真实 Hermes（任何 `hermes chat/agent` 调用，含 smoke） | 真实模型调用属 C2B 独立授权（plan.md §6 Step 3） |
| N3 | 合并任何分支到 main（包括 M2-B/M2-C1 候选） | 合并是用户授权门禁（plan.md §6 后续独立操作） |
| N4 | 安装/升级任何软件、启动 Docker daemon、创建账户/挂载/卷 | 宿主配置变更需单独审批 |
| N5 | 修改/读取任何真实凭证内容 | 永久禁止；只允许"打开失败"断言 |
| N6 | 修改 AGENTS.md、tasks/、handoffs/、schemas/、tests/protected/、生产代码、pyproject/uv.lock | 超规划范围；改动走规格流程 |
| N7 | force-push、reset、clean、覆盖未提交文件 | 永久禁止 |
| N8 | 对 `/tmp/m2c2-sandbox/` 之外的任何宿主写入 | 未授权 |
| N9 | 越界探测（针对宿主本身的攻击面探测、对其他进程/服务的探测） | 安全违规；本计划只测试 Worker 边界的合成拒绝 |
| N10 | 在同一会话中模拟 fresh Reviewer 审核本提案 | 当前软件无法自主新建真正 fresh 会话；交付后状态为"等待外部审核"，由用户决定如何发起（另起独立 Hermes/本地模型会话，或人工审阅） |
| N11 | **用 git push 操作作为证据写入宿主写权限的隐式来源** | git push 不授予宿主写权限——push 只把版本控制目录内已存在的对象提交；evidence 写入是 harness 用 Python `open(path, "wb")` 落盘到磁盘，独立于 git push 机制；harness 写入 evidence **不等于** git push 隐式获得宿主写权限——必须本提案 §2 第二张表（可信 harness 独立输出根）被用户明确批准后 evidence 写入才生效 |
| N12 | **提前填 cleanup.json 的 ENOENT / exit_code=0** | cleanup 实际执行（`rm -rf` + `ls`）必须在 cleanup.json 写入之前；不能把尚未发生的事实落记录 |
| N13 | **fixtures 放在 `harness/profiles/fixtures/`** | fixtures 必须在 `ro/fixtures/`（Worker 可读）；放 `harness/profiles/fixtures/` 是 Worker 全 deny，sandbox 内 Worker 启动 fixture 会失败 |

## 10. 请求用户决定的事项（按优先级）

1. 是否批准 §2 的 `/tmp/m2c2-sandbox/` 统一授权根 + §4 命令白名单类别（C2A 实施前提）。
2. 网络目标集合：全部为 harness 自建回环服务（§5），不访问 15721/18080/93.184.216.34（P2）。
3. M2-B（`77920b99f279956cbe88bc2b3b2364b5ae078ce7`）与 M2-C1（`436e3b0e026580a6b39ece891e8ffe47ac1bb698`）是否合并 main（plan.md §6 后续独立操作，不是 C2A 前置）。
4. 平台优先级确认：是否接受"macOS sandbox-exec 唯一推荐 + Linux 容器后续"（plan.md §2.2）。
5. 若 macOS `tree_cleanup_confirmed` 最终只能 None：是否接受受监督模式路径（需独立提出规格，不在本提案暗含例外），还是要求必须先在 Linux 取得 True 证据（plan.md §5 行 2 后续动作分支）。
