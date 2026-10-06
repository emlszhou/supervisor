# M2-A 证据修订复核与阶段交接

候选：`1ef540d5dee9d05127aec016b200e4e5f0bcd442`；本机审核摘要：`bdfed2e625cb0619f33725c334f3b6f330acc0b0`。用户已将周期时间/启动额度改为建议值，覆盖旧硬停止条款；预算不再是阻止推进或否定成果的依据，历史账本仍保留。

## 已验证

精确候选独立 Linux 检出：301 passed、0 failed、0 skipped；外部 frozen validator exit 0；specs、Ruff check/format exit 0。两个允许交付文件，共673新增行；源码/测试/配置未变。没有再次启动 Hermes probe，未访问 Mac 私有日志。审核摘要自述 fresh Reviewer 已核对私有输出与运行日志，这属于本机审核证词，云端没有直接核验这些字节。

timeout 已从 not_run 修正为 failed 并补齐原调用时间/退出码/摘要；非交互、路由、fresh 身份的 enforced 已降为 unknown；cancel 未捕获退出码不再宣称 passed。已有真实 pytest 失败分类、resume declared/unknown、资源 unknown、输出字节及隔离方案盘点。这些是可用进展，不要求为了取得绿色结论不断重复同一调查。

## 结论

保留并采纳本轮成果作为后续规格准备材料。M2-A 原执行验收门禁仍 blocked：工具禁用控制未经验证、端点回退/硬超时未满足、取消实际退出与整树回收未知、Mac 必需测试非零。不能将 fresh Reviewer 的 ACCEPT 解读为原验收全部通过或真实 Worker 可运行。建议结束重复文案返修，转到明确范围的规格工作，先支持模拟进程/fixture，真机执行入口默认关闭。

## 后续需要继承的事实与修正

- 取消 probe 已执行但 exit 未知，冻结 validator 无法结构化表达。原始数据应在下阶段证据规格中以 nullable exit + executed/exit_known 等明确字段保留，不能用 unsupported 抹去运行事实或补造返回码。
- 公开审核没有绑定其实际核验候选完整 SHA，且最新1ef540d表格修订发生在 verdict 后。今后审核必须绑定精确 commit、列出可复核命令和状态；未经复核的后续改动不能沿用旧 ACCEPT。
- 启动表省略 probe4c，却在 JSON 称12 probes；表含 coordinator而 JSON又说不计 coordinator。加上新 Reviewer 后总数需补齐，不构成停止条件。13不应作为已闭环精确总数。diff行仍TBD，真实为673；repair0与实际修订需说明角色/计数定义。
- §7和§11仍称 leader exits clean / SIGINT honored，与新的未知 exit/回收记录不一致；后续不能照抄为验证结论。
- 隔离盘点是 declared：docker binary/version不代表 daemon/容器边界可用，screen/PTY不是安全隔离，sshd不是天然权限边界；不得把这些条目当 enforced。
- Mac39 case-insensitive异常+16 regex失败与snapshot.py显式拒绝大小写不敏感文件系统相符。建议单立平台验证任务，在已有大小写敏感环境复验，再裁决是否需要平台支持/测试修改；不在M2-A越权改M1，不把此假设升级成已验证根因。
- 后续 Adapter 应由调用者负责硬超时/输出上限/取消，禁止未知或错误端点悄然回退；错误必须成为明确结果。未验证禁用工具与实际隔离前不运行真实 Agent。

## 推荐下一步规格范围

先准备 M2-B HermesAdapter 的请求/事件/错误/identity/usage 契约与模拟CLI验收，并另设工具禁用前置核验及Mac平台检查。把接口、证据格式缺口和真正执行边界写成有限明确任务；模型用量给建议额度及停滞检视点，单次进程限制仍强制。冻结规格后才安排实现。不自动合并候选/main、不部署；本报告未修改冻结输入或Hermes分支。
