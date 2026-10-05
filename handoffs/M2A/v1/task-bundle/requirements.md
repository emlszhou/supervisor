# 要求与非目标

本任务产出真实版本下的 Hermes 能力证据，使下一阶段可以按已验证语法调用 Agent。

- 在实际 Mac 上记录 Hermes 的可执行路径、版本、OS、架构；具体命令从实际 help/安装文档发现。不得猜测非交互、JSON、session、取消、模型参数。
- 逐项区分 declared/observed/enforced。帮助或模型宣称是 declared；真实行为是 observed；对抗性拒绝并有可信控制边界证据才是 enforced。
- 必需调查九项：cli_help、noninteractive、model_route、fresh_session、output_protocol、endpoint_failure、timeout、cancellation、permissions。
- 可实施的 smoke 仅在无秘密的合成临时目录中进行，模型请求不授予 shell/文件写入/MCP 等工具；当前会话不是 fresh/noninteractive 证据。若无法确保工具不被执行，记录 unsupported 并停止该 smoke。
- 用户已明确批准本任务使用 Hermes + MiniMax 云模型（实际模型标识来自运行证据，不能猜测）。记录实际 provider/model/backend 元数据，不把 CLI 在本机运行称为本地推理，不把模型回答中的自称当实际供应者证明。无法验证则 unknown，不隐式换供应者。
- fresh_session 要有两个实际独立启动身份及来源，不能只是聊天中更换角色。取消/超时按核验方式执行，只作用于本次测试可确认进程，不杀推理服务或其他用户进程；leader 退出不等于整树回收。
- 原始 transcript/认证配置/环境变量值/模型权重只留本机私有目录。提交 argv 必须脱敏，认证参数不得出现在 argv；记录输出摘要 SHA256 和格式描述，不提交请求正文、秘密或原始响应。未知 usage 不能记成零。
- permissions 在本任务只记录当前能力。未做真实攻击拒绝测试则 enforced=unknown；不把目录、Git 分支、提示词或工具名单当 OS sandbox，不开展宿主越界攻击测试。实际 Worker 文件/网络/MCP 执行边界留给 M2-C 单独合同。
- 对 unsupported/not_run 给明确原因和最小前提；不得伪造零失败结论。所有测试有外部时间/输出限额，单项最多 120 秒、输出最多 64KiB，累计不超过任务预算；输出只留本机受控位置。

非目标：生产 Adapter、CLI 改造、状态机、修改 M1、OS sandbox 实现、依赖/模型安装、端口重配置、main 合并、部署。不得为取得绿色报告扩大权限。

交付 capabilities.json 和 hermes-report.md，绑定冻结基线、task/run/attempt、实际会话与命令证据。独立 Reviewer 重验可重复的无副作用项目，核对私有证据出处/摘要；结构验证不能证明真实执行。

## 加长任务的完整交付要求

在 hermes-report.md 统一汇总以下内容，不能只回一句“端口没启动”：

1. 实际 help 与版本支持的调用参数、工作目录、最小环境变量名称、输出格式、exit code 语义；记录可重复的参数数组，不给 token 值。
2. 核验 session 创建/续接的差异、上下文是否独立、实际身份来源；三个安全 smoke 中至少包含两次独立启动（共三个 smoke，不额外叠加两次会话）（每次都有预算、真实结果，失败不盲重放）。
3. 记录实测 wall、可确认的峰值内存、输出字节和 usage 可见性，区分宿主整体、服务进程与 Agent 进程；无法隔离测量则 unknown，不估算成真实数据。
4. 按 observed 事实提出 HermesAdapter 请求/解析/错误/取消/身份绑定契约建议、必需的有限故障用例与未知前提；这不是生产 API 已批准或已实现。
5. 比较本机可用的隔离路径（已有 VM、容器、受限账户），列明 declared/observed/enforced、文件/网络/MCP/进程/凭证边界和实际缺失前提。只做只读环境盘点，不创建账户、不装容器、不修改网络防火墙、不探测宿主秘密；真正强制测试与实现留给后续明确授权合同。
6. 给出 M2-B Adapter、M2-C Worker 边界、M2-D 验收器的依赖顺序、候选文件/API、风险与验收建议，使下一阶段能一次冻结可执行合同。

共用四小时与七次 Agent 启动，至少保留一次真正全新 Reviewer 调用；不因长任务增加返修/接管次数。保护验收不能被报告提议替代。

## 启动额度安排

七次 Agent 启动是共享硬上限，不保证同时用完一返修与一接管。建议实现/调查角色一次、三个 smoke（其中至少两个真正 fresh）三次、fresh Reviewer 一次，合计五次；剩余两次最多用于一次返修与再次审核。此时接管+最终审核已无启动额度，必须停止，不能启动第八次。若减少或没有 smoke，可按实际证据给其他路径留额；不能把未运行 smoke 记通过。

开始任何角色/模型 probe 前先核对剩余时间与 Agent 启动数，优先保留必需 fresh Reviewer；无法容纳下一步就保持 blocked。纯 help/version/文件结构工具检查不启动模型 Agent，不计 Agent 启动，但其运行时间仍计 wall。调查报告记录两个独立 fresh 启动的 id/source 到 fresh_sessions；结构验证不证明身份真实性，由 Reviewer 对照私有启动日志核实。
