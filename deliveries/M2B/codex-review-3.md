# M2-B 最终独立复核：ACCEPT（仅离线阶段）

精确接受候选：`77920b99f279956cbe88bc2b3b2364b5ae078ce7`。
Hermes fresh审核：`624ff4dc7703d45a8780ff8ff36add7c5e45fdb4`，与本次候选一致。
基线：`85fde6074d45ea0137a2dc55aae3362befa91639`。
冻结manifest：`9a46b4a424ffeab7c0f63ec9b3cbb1038b7d9168488da7697576613e38574703`。

独立Linux克隆精确候选运行：原301+新单元/集成70+外部保护29=400 passed、0failed、0skip。旧7个Codex探测全部PASS；新增独立检查session末尾换行拒绝，以及task/run/attempt三种可信身份末尾换行抛ValueError，全部满足要求。Ruff check/format、specs均exit0，sdist/wheel构建成功。四文件/1827新增行符合scope；无保护文件或公共Worker/M1修改。

所有M2B-R1-process/json/order/errors与M2B-R2-identity关闭。R3生产改动只把三个re.match替换为re.fullmatch，并补13回归；已复核最新报告候选，未沿用旧版本ACCEPT。原失败记录保留。

本决定只接受离线HermesAdapter协议子集与模拟CLI阶段。build_request仍恒拒绝live_execution_disabled；无真实Hermes启动、模型推理或OS隔离能力声明。本次未访问Mac私有日志；本机fresh Reviewer报告315pass/55fail/1skip作为平台结果保留，不宣称macOS已通过。后续平台任务应在明确支持的大小写敏感文件系统复验并裁决平台支持。

Git强推历史披露保留；已确认报告所列before基线仍是after审核commit祖先，不再构成本候选的内容阻塞；后续仍禁止force/reset/clean。周期用量为建议，不作为硬性验收拒绝依据。

尚未合入main，接受不自动授权实现合并或部署。下一步可准备M2-C执行边界与平台验证合同；真实模型入口仍需单独前置验证与授权，不自动解锁。若候选后续改变，须针对新完整SHA重新审核。
