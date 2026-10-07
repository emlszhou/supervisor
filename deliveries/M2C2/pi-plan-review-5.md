# M2-C2 R4候选独立审核：request_changes

候选22952883ccafc2b84adfdb89041a060afc4e0466，独立核对四文档和Git差异；diff --check通过，未运行Mac/模型/宿主探测。R4-fixture位置和目标参数、R4-dependency的主要算法/顺序、按test_kind拒绝成功即失败的规则已修复。剩余两组问题仍影响证据可验证性，不能冻结为实施合同。

## R5-control — major：正向对照换了目标，不能证明拒绝原因

plan §4.0 T1-R4 JSON的动作指向denied/AGENTS.md，positive_control却改成work/AGENTS_positive.txt并加--allow-write（改变O_CREAT）。这不再是同一目标同一动作；目标不存在、路径错误或普通权限不足也可能得到不同结果。固定同一fixture、同一argv（除隔离启动wrapper）、同一denied目标，在非隔离或明确允许同目标的对照profile中确认成功。对照前后由harness保存并恢复该合成目标，拒绝测试重新记录基线。目标初始化由harness独立完成，不靠对照新增O_CREAT补偿；删除--allow-write改变动作模式。读与网络对照同理固定同一文件/端点。预期拒绝动作成功或有越界副作用始终blocking，不允许通过换目标对照掩盖。

## R5-manifest — major：清理与完整性记录仍循环

plan演练#15要求manifest“自身sha全一致”，manifest不能直接包含最终自身文件摘要（自引用）；cleanup又保存post_persistence_manifest_sha256，而最终manifest包含cleanup，形成循环。另称#14必须复制#15才产生的cleanup，使前置校验永远依赖未来记录。

唯一顺序建议：
1. 复制capture/evidence到新持久化目录，统一summary实际位置为evidence/summary.json，重写所有包内相对引用。
2. 生成pre-cleanup manifest（不含自身、没有尚未产生的cleanup），验证所有引用/hash。
3. 进程确认可清理后执行真实清理。
4. 在持久化根写cleanup.json，仅记录真实清理结果和pre-cleanup manifest摘要，不含最终manifest摘要；清理失败如实写入。
5. 生成final manifest，包含capture/evidence/cleanup所有文件，不包含manifest自身或外置摘要文件；如需其摘要放外置CHECKSUMS.sha256，不纳入该manifest。
6. 验证最终引用/hash并提交推送证据。不得在已删attempt再复制cleanup，不提前填成功。

#14写manifest后又重写summary引用会使摘要失效：先完成所有内容变换，再计算manifest。更正所有段落与演练，不靠一个新增声明覆盖旧循环。复制前后capture原字节必须同hash；JSON被有意改引用则记录原/最终分别摘要，不要求它们字节相同。

## 下一步：收敛而非继续累积修订文字

建议只重写plan §4.0证据算法、T1-R4示例、§4.2及矩阵对照/证据段，删除历史修复说明中仍被当成有效规则的重复算法；历史处置保留pi-report。给出单个文件拒绝测试全过程和最终证据包树，人工按同目标对照、非自引用hash和清理时序核对。不新增宿主操作，不改生产代码、不合main。两项关闭后可准备正式规格，不需要再为非执行性错字追加规划轮次。
