# M2-A 最新推送复核：blocked

最新审核/对账分支 `local/m2a-review-1`：`dbdaf01177f056ade6cf0e15511f7cd527788c9a`。实施分支仍为 `63c6c5f55506553c5c0b20f95d15e5f01255a0bb`，两个候选交付文件未修改。本次只复核新增文本；上轮精确候选 Linux 301 passed、validator/specs/Ruff 通过仍适用，没有重复执行未变代码或 Hermes 模型。

## 新增可采纳信息

现已有公开 fresh Reviewer 报告，包含自述模型/会话来源、精确候选、私有输出摘要复算和 session 字符串核对。这补足了上轮“远端未见审核记录”的发布缺口，但云端仍无法独立查实 Mac 私有日志。不能把报告的存在等同于全部门禁通过。

对账回应明确承认 smoke 未显式禁用工具、timeout 实际运行、cancel 缺 wait/tree 证据、enforced 过度声明，以及调查清单未完成。这些承认与上轮发现相符；不是已修复。回应还承认 coordinator + 6 smoke + Reviewer = 8 次启动，超过合同 7 次上限。

## 仍阻塞及新增矛盾

1. **预算矛盾**：回应承认 8/7，review-final 却仍称预算合规并 ACCEPT。后者还提到 probe4/4b/5/5b/6/7 是 prep/control runs；是否启动模型必须按真实日志逐个归类，不能因未被报告引用而从预算排除。8 是目前自述下界，不是已完整核对的总数。调用启动 UTC/身份、coordinator continuation、各预备调用与审核启动都需公开脱敏账本。cycle close 写 2026-10-06T07:00Z，原 wall 起点 2026-10-05T22:48:30Z；若这是同一周期实际结束，则跨度 8小时11分30秒，超过4小时。是否包含等待、审核或仅文档发布时间须据日志核对，不能沿用原约3分钟。
2. **ACCEPT 无效**：fresh 审核检查了结构与摘要，但接受了已执行 timeout 写 not_run、遗漏角色调用及必需 pytest 非零等问题。调查成果可以保留，不能凭“诚实 blocked”改写冻结验收或把失败检查变成通过。应发布更正/撤回，保留旧报告历史。
3. **没有实际返修**：hermes/m2a 的 capabilities.json/hermes-report.md 没变；所谓八项 documentation-only option 是方案，不是修复。M2A-R1-budget 不能仅因私有 terminal-summary 记载便声明 closed，超额事实不会消失。
4. **工具禁用方案未经验证**：--safe-mode/--ignore-rules 的存在不证明禁用 shell/文件/MCP/凭证访问；原报告自己解释 safe-mode 为禁用 customizations。不要按提案直接重跑。六次 smoke 即使由一个 coordinator 批量调度，仍是六次启动，回应 Option B 的“需要1次启动”错误。
5. **timeout/cancel 纠正必须保留已执行事实**：timeout 可据原日志恢复执行字段并标失败，不能因硬超时未触发说未运行。cancel 曾运行，不能把 unsupported + 全字段 null 当成抹去已运行记录的替代；exit 未捕获就明确 unknown，当前 validator 表达不了时保持 blocked，由协调者另立证据格式修订规格，不能编造返回码或改保护 validator。
6. **失败摘要不能由 collect-only 得出**：pytest --collect-only 只能列测试，不运行断言。需现有 pytest 失败日志的 nodeid、异常摘要、平台/解释器与 exit code，不能据 collection 或被引用提交断言责任根因。Reviewer 同机重跑55失败支持平台复现，不证明根因；Linux同候选301通过仍有效。
7. **其他未知前提仍在**：VM/容器/受限账户比较、资源/输出字节、resume 差异等尚未补齐；help 只能作为 declared。session 字符串与 SHA 匹配不证明禁用工具、真正上下文独立或强制路由。
8. **推送权限文本过时**：对账文档称 branch local-only/待批准，但远端已存在 dbdaf01。正常仓库 commit/fetch/push 早已授权；上轮审核没有撤销普通推送授权。需要协调决定的是超额后继续执行/新周期，不是重复申请常规 Git 权限。

## 处置

保持本周期 blocked/超额停止，不新增模型探测、返修会话或接管，不合并 main、不自动推进真实 Adapter 执行。本轮未增加任何额度。保留原候选及审核记录，后续先据现有日志完成可核验脱敏账本和审核撤回；工具控制、cancel未知退出码或证据表达缺口无法靠文案消除。可以提取已证实调查事实为后续规格准备材料，但必须另外冻结范围/预算/工具禁用与运行前提，不能续跑原周期绕过限制。
