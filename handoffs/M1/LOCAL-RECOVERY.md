# M1 本地路由恢复与接管交接

协调日期：2026-10-05（Asia/Shanghai）。这是一份协调交接，不修改 M1/v1 冻结合同，不证明本机服务已恢复，也不授予额外返修、调用或时间预算。

## 当前生效的路由补充决定

2026-10-05 用户在收到“允许 Hermes + MiniMax 云模型执行 M1 接管及最终审核”的选项后要求继续下一步。本轮按这一范围执行：允许本机 Hermes 使用实际 MiniMax 云模型完成 M1 协调、一次接管和全新最终审核。此决定覆盖下文原先的全本地模型路由前置要求、§2 本地 smoke 和 §4/§5/§6 中本地供应者限制；§2 保留为未来恢复全本地实验的步骤，本轮无需启动 MLX、llama.cpp 或 Claude CLI。

这不是 smoke 通过，也不追溯改变原交付的云 fallback 事实。M1-13 记录为用户更新后续路由政策，历史违规保留；只使用明确选定的 MiniMax 供应者，记录实际模型、版本、会话和请求结果，失败不得隐式切换其他供应者。本轮不扩大 M2–M4 路由、合并或部署授权。

当前证据提交 `2e7e49ab05a109b0622a83ade6bddc0c678ca227` 仍不能解除 M1-14：Markdown wall=4890，JSON wall=5760，均包含未知阶段的估计；调用 ~5/7 也缺少完整调用账本。不能把“有估计”写成“额度明确”。下一步先修证据，再决定是否能进入接管；不增加额度，不重置时钟。

### 下一步证据任务

在 `local/m1-recovery-evidence` 正常 ff-only 更新后，修正以下内容并推送；不触碰实现分支：

1. Findings 计数改为 12 major、2 blocking、1 minor，总计 15。删除“Codex 是合同所有者、可以自行豁免”的说法，授权来自用户。
2. 核对每个实际 Agent 启动/续接/委派的 operation/session ID、角色、开始结束时间、结果和证据出处。`max_agent_calls` 按合同的 Agent 调用核对，不把每个模型 token 请求算一轮，也不把多个独立 Agent 启动压成一个会话。无法确定的调用单列 unknown；云审核根会话与 fresh Reviewer 分别说明来源和计数归属，不能从一份报告推定只有一次调用。
3. wall 使用真实操作起止记录重建；提交时间不是任务开始/结束证据。解释等待、暂停与并发如何按可信规则计数，不能擅自扣除未知时间或默认采用较小估计。两个文件保持一致；无法确定则值为 null，并保留估计字段和原因。
4. 根据实际证据确认 takeover=0、repair=1；核对本任务没有活跃/未知写入进程，历史 revert 本身不证明有孤儿进程。
5. 同步 Markdown/JSON，将额度结论改为 verified 或 unknown，并列出接管和独立 final_verify 需要的剩余 Agent 调用及时间。记录明确 MiniMax 路由；本地 smoke 仍为 not_run，本轮政策下不适用。

满足额度和单写入者前提后，按 §4 原范围进入唯一一次接管，不必再次请求正常 Git 权限。无法证明额度、已耗尽、或 fresh 最终审核调用无法容纳时，保持 blocked，提交缺失证据清单；不能以路由变更为理由扩大预算。本文件没有把原 review_2 blocked 改成 accept/takeover，也没有授权额外返修。

## 1. 精确输入与当前结论

- 仓库：`https://github.com/emlszhou/supervisor.git`。
- 原候选：`7f301ea72f759e4ec87128af68deb3e6dd8c9c45`，分支 `hermes/m1`。
- 审核提交：`9c4abdb46d3dfa75353bec9be71ba0a3175124ad`，分支 `codex/m1-review-2`。
- 审核文件：`deliveries/M1/codex-review-2.json`，同目录 checks/evidence/probes 文件是复现材料。
- 基线：`c6e224587b930a5b96c7723009584424f6bc52d5`。
- 冻结输入：`handoffs/M1/v1/task-bundle`，manifest SHA256 `47ea6c51c46570e92f97c89428c9783a90bcc10e301e3e8d6ce38d4fb25dd142`。
- 状态：review_2 blocked；Linux unit 151 pass / 13 fail，full 247 pass / 13 fail，外部验收 42 pass；不能据此 accept。

当前云端没有 Mac 远程执行入口。报告中 127.0.0.1:18434、15721 是 Mac 的 loopback，不是云环境的服务。不得在云端启动同端口后声称恢复了 Mac。以下操作由本机确定性工具或操作者完成；修复模型会话只在路由验证之后启动。

## 2. 先恢复路由，再启动模型角色

1. 保留当前会话/工作区；核对正在运行的写入任务，确认没有重复 Agent。不要用正在使用云 fallback 的会话继续生成修复代码。
2. 本机记录 `claude --version`，若仍使用 Hermes 再记录其版本和帮助。根据实际帮助与已安装配置确认调用链：Claude CLI → 本地兼容代理 → llama.cpp。不能假定 Hermes 配置决定 Claude CLI 路由。
3. 只检查必要配置，输出变量名称/是否存在与脱敏后的 endpoint 类型。不要提交 `~/.claude`、`~/.hermes`、凭证、完整环境变量或原始 transcript。
4. 从实际服务配置确认模型文件、模型名、服务启动方式与端口；用该版本帮助核验命令。旧 `server.json` 的 PID 不是运行证明。用本机进程身份、监听地址、健康请求和实际模型响应交叉核对；不猜启动参数，不杀未知 PID。
5. 备份将修改的本机配置到私有目录。使用工具支持的配置关闭所有云 fallback，将当前角色指向明确的本地后端。若工具不支持禁止 fallback，使用可验证的网络限制或明确停止；不能靠提示词保证。
6. 启动全新 Claude CLI 会话，执行一个短、无工具副作用的推理 smoke 请求。记录 UTC 起止时间、实际会话 ID、CLI 版本、实际模型标识和脱敏服务端请求关联证据。端口开放、`/models` 列表或 `doctor` 成功都不足以证明 Claude 的实际请求走了本地。
7. 在支持的方式下暂时使该会话的本地模型端点不可达，再执行同类 smoke：必须失败，不能收到云模型回答。只控制已确认属于此测试的服务，避免影响用户其他进程；恢复服务后再跑一次成功 smoke。保留三个真实结果，不能模拟故障证据。
8. 若本机无法实现上述验证，状态保持 ENVIRONMENT_FAILURE/blocked，报告具体缺能力。不要安装未经核验代理、关闭 TLS 验证或使用 `--dangerously-skip-permissions` 来绕过。

Claude CLI 在本机运行不等于本地模型推理。若实际使用 Anthropic 托管模型，同样不满足全本地约束。服务端证据只提交脱敏摘要/摘要 SHA；私有原始日志留本机。

## 3. 已用额度：保守审计，不能重置

| 项目 | 上限 | 当前证据 | 下一步 |
| --- | --- | --- | --- |
| 返修 | 1 | 历史 Review-1 请求返修；97a5bb9 并发初始化修复和后续报告修正已发生 | 按已用 1、剩余 0；删除审核文件不能恢复额度 |
| 接管 | 1 | 现有已检查 Git 历史未发现明确接管记录；本机操作账本未知 | 本机确认未发生接管后，最多剩余 1 |
| 模型调用 | 7 | 原实现、历史 Reviewer、续接与后续云审核的计费归属没有完整账本 | 逐项核对实际调用；未知不能按 0，云审核单列并说明归属 |
| 总 wall | 7200 秒 | 本机原 run 起止/暂停/操作记录不完整 | 重建合同规定的累计用时；不能给新会话重新分配 2 小时 |
| 文件/净 diff | 14 / 2800 行 | 原候选 11 文件 / 2509 行 | 相对同一基线重算最终净差异；重写/删除新增代码可减少差异 |

历史材料通过 `git show 3f61b9b5da472c50272db0f178297b51dc47c4f1:deliveries/M1/review-1.md` 与同提交的 `review-1-response.md` 读取。后续 `ddde3c4` 撤回文件不撤销已发生的调用或修复。历史报告里的 fresh 声明不能代替实际会话证据。

把调用、时间、接管审计保存为本机私有 sidecar，使用 `templates/local-run-status.json` 的实际值；未知字段保持 null，记录出处。若已耗尽或无法证明剩余额度，停止并提交额度核对报告，不换 task/run ID、不另起同问题合同规避终态。路由运维与模型 smoke 单列记录，由协调者解释归属，不能隐式豁免。

## 4. 条件满足后的唯一接管路线

只有本地路由 smoke+失败关闭探测通过、额度明确、无未知运行副作用后，协调者才能记录解除环境阻塞并进入一次 takeover。用户已要求安排修复；无需重复询问正常 Git 操作权限，但前提缺失不能写成已满足。

- 接管分支：`local/m1-takeover`，从精确原候选创建；远端已有该分支时先核对用途/HEAD，不能覆盖。
- 外部冻结合同从可信规格提交导出到实施目录之外，按照 M1/v1/README 校验完整 inventory；不从实施者目录重新冻结一份。
- 先 fetch 并核对远端原候选未变、工作区干净、单写入者；脏目录或分叉保留并停止，不 reset/clean/force。
- 仅修改五个允许生产模块、`tests/unit/test_m1_*.py` 和 `deliveries/M1/hermes-report.md`。审核文件、治理文件和冻结合同不能加入接管实现差异。

修复顺序（全部 findings 都要处置，不只修冻结测试）：

1. M1-02～05：Git 实际根、ignored 受控 inventory、基线删除、固定产物规则、链接祖先与读取/清单变化检测；LFS/submodule 和能力缺失如实拒绝。
2. M1-06～07：整段 globstar 的零目录匹配、禁止优先、严格 snapshot 类型/路径/模式/摘要/排序/碰撞验证。
3. M1-08～10：完整递归 bundle 输入、普通目录与硬链接区分、源读取一致性、输出祖先/重叠/并发不覆盖、精确 schema 与错误归一。
4. M1-11：SQLite 打开前检查 DB/sidecar 与全部祖先，拒绝悬空链接和侧文件硬链接；保留已通过的并发和 COMMIT rollback 行为。
5. M1-01、12～15：移除 Mac 绝对路径测试依赖、补充有意义回归，纠正报告退出码/计数/平台/供应者与历史声明。

macOS 大小写不敏感 APFS 的失败不能豁免，也不能改保护测试。可选择本机已有的大小写敏感工作/临时测试卷或本机 Linux 执行环境，在保持合同不变的前提下运行验收，并明确平台能力与未测试项。Linux 通过不宣称 macOS 通过；保护规格若确有矛盾，停止并提出具体规格问题。

从项目根运行 frozen sync、合同 verification 全部命令、完整测试、审核故障探测、最终 scope/diff 检查。外部 pytest 使用 `python -B`、禁用 cacheprovider，检查冻结输入前后未改变。每条命令记录 argv/cwd/候选/时间/真实退出码和本轮计数，不相加重叠测试。

先提交允许的代码，再更新报告并提交；正常推送接管分支。报告绑定精确代码 SHA、最终 tip、冻结摘要及本轮真实结果。不能自签 accept、合并 main 或再给自己一轮返修。

## 5. 交给真正全新本地 Final Verifier

另一会话、独立检出、只读精确候选；未参与接管，重新运行全部检查和故障探测。审核 stage=final_verify，decision 只 accept/blocked/reject；使用真实 session ID 与实际模型/供应者，不虚构独立性。审核写入独立 `local/m1-final-verify` 分支，模型调用仍计入已审计的剩余额度。最终失败即停止，不自动开启下一轮。

## 6. 可粘贴给本机协调者的提示词

```text
先 fetch origin，读取 codex/m1-local-recovery 的 handoffs/M1/LOCAL-RECOVERY.md
以及 main 的 AGENTS.md、docs/LOCAL-MODEL-RUNBOOK.md。
先遵守本文件“当前生效的路由补充决定”：本轮允许 Hermes + MiniMax 云模型，
无需启动 Claude CLI/MLX；不得宣称本地 smoke 通过，不得隐式切换其他供应者。
核对 M1 全部历史调用、累计 wall、返修与接管；返修已用 1，不得重置。
把脱敏路由与额度证据提交到独立 local/m1-recovery-evidence 分支，
路径 deliveries/M1/local-recovery-evidence.md；不要放进受限实现分支。
先修正 2e7e49a 的证据：15 findings=12 major+2 blocking+1 minor；
wall 4890/5760 冲突和 ~5/7 调用数必须按实际日志核对，不能当已验证余额。
只有 MiniMax 实际路由明确、额度有证且无未知副作用，才能进入一次 local/m1-takeover。
从候选 7f301ea72f759e4ec87128af68deb3e6dd8c9c45 接管，读取审核提交
9c4abdb46d3dfa75353bec9be71ba0a3175124ad 的全部 findings 与 probes。
冻结合同、API、保护测试、预算不变；修复只在 allowed_files，真实复跑全部检查。
完成后推送代码/报告，由另一真正全新 Hermes/MiniMax 会话 final_verify；不自行验收或合并。
不能证明剩余额度或缺少 fresh 能力时保持 blocked，只交付证据与最小缺失条件。
```
