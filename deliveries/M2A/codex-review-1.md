# M2-A 外部审计：blocked

候选 `63c6c5f55506553c5c0b20f95d15e5f01255a0bb`。仅两个允许文件、449新增行，scope 合规。Linux 独立检出 301 tests passed；外部结构 validator、specs、Ruff check/format 均 exit 0。此审计没有运行 Hermes 模型或访问 Mac 私有日志，不能证明真实 CLI 行为。本机调查报告本身也明确 adapter_readiness=blocked，不能据此进入真实 Adapter 执行或合并 main。

## M2A-R1-tools — blocking: 缺少 smoke 前禁用工具及无秘密合成目录的控制证据

所有模型 argv 只有 --in /tmp，实际 cwd 为项目目录；没有已核验工具禁用配置、隔离目录清单或外部 120 秒/64KiB 限额证据。普通提示词、--oneshot、--max-turns 不是工具禁用证明。不能反推过去调用安全；保留既有事实，无法核实则标 unknown/blocked，不追加 smoke。

## M2A-R1-budget — blocking: 共享启动账本未完成核对

报告列 6 个 probe，却省略继续参与本轮的 coordinator。合同将角色、probe、恢复启动共同计数；至少需核对调查角色和六个 probe，不能据此声称还剩一次 Reviewer。未见审核分支；本次外部审计也须在账本中据实际启动范围明确分类，不能自动豁免或重置。无确证前不得新增模型调用。

## M2A-R1-timeout — major: 实际执行的 timeout 被写为 not_run

JSON reason 与报告 §8 明确说运行 --run-budget 1 并等待约15秒响应，预算账本也列对应 probe；却全部运行字段为 null。需从现有私有日志恢复 argv/UTC/exit/hash/identity，并按真实观察记录 failed 或有理由的结果，不能将执行过的探测写成未执行。

## M2A-R1-cancel — major: 取消退出码与回收结论证据不足

ps 进程消失和空文件不能证明 wait 返回码为0或整树回收；需要本轮实际 wait/signal/进程身份和存活核对日志。未知时撤回 passed/enforced=yes 的过度结论，不编造退出码。

## M2A-R1-enforced — major: observed 与 enforced 混用

noninteractive/model_route/fresh_session/cancellation 标 enforced=yes，但现有证据主要是一次正常结果。合同要求可信控制边界或强制拒绝证据；应区分观察、配置声明与强制保证，路由必须绑定具体 probe 的实际后端，不能仅引用 coordinator 的 agent.log。

## M2A-R1-evidence — major: 私有摘要未获 fresh Reviewer 核验

没有 local/m2a-review-* 远端分支；报告只提供私有文件路径与 SHA 字符串。云端无法核对本机文件，结构 validator 通过不证明运行真实性。需要真实 fresh 审核核对精确 candidate 与私有原始日志，但先解决额度，不允许在同会话模拟。

## M2A-R1-completeness — major: 加长调查必需交付缺失

未提供最小环境变量名称、创建/续接差异、可确认峰值内存/输出字节或明确 unknown、已有 VM/容器/受限账户只读能力比较，以及后续候选文件/API 与完整有限故障用例。只能用既有证据补充；无法测得写 unknown，不安装或扩大权限。

## M2A-R1-report — major: 项目失败归因及最终预算未闭环

Linux 独立检出精确候选 301 passed，源码/tests/配置与基线相同。macOS 55 failed/245 passed/1 skipped 的原因未附失败摘要，不能断言通用基线继承缺陷。需保留平台、Python/依赖/文件系统与各失败类别及命令真实退出码，预算写实际结束时间、启动身份清单、449 diff行和精确候选；TBD/约3分钟不是最终账本。

## 后续处理顺序

1. 保留原始候选与日志，不修改冻结合同、main 或 M1。当前不批准追加预算或新增模型 probe。
2. 先由操作者使用既有日志核对本轮实际角色/probe/恢复启动、起止时间及私有 evidence；对账前不能启动新的 Hermes 会话或 Reviewer。不要把“六个 probe”误读为“七次共享额度尚剩一次”。
3. 在证据允许的范围纠正 timeout/cancel/enforced、补齐 unknown 与调查清单、平台失败摘要；只能在有确证剩余返修/时间/启动额度后安排返修。证据无法找回则如实保持 blocked，不重跑代替历史证据。
4. 若七次共享启动已耗尽，停止该周期并交回协调者；另立明确范围的证据 reconciliation/必要后续规格，不偷偷追加接管或模型调用。本次不要求购买额外预算，也不自动批准下一周期。
5. 即使完成文档补正，未知端点回退、硬超时、安全 smoke 和 fresh 审核门禁仍须据实处理。可以保留部分调查成果作为未来规格参考，不能签 ACCEPT 或宣称 Worker 就绪。

本报告独立于 Hermes 的候选文件，未改其实现分支。M1 Linux 检查通过不代表 macOS 故障已解决；55失败需真实日志诊断，不删除测试、不在 M2-A 越权修 M1。
