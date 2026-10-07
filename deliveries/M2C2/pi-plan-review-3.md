# M2-C2 云端修订提案审核：request_changes

候选3b5e285fdba4a8ade8932b54e53f345e49cfc2d2。已核对四文档和R2处置，diff --check通过；未执行Mac探测、模型、实现或main合并。MCP范围、full_pass/partial、harness专属profile/capture及取消确认限制方向接受；剩余问题是具体可执行性，不追加平台测试范围。

## R3-dependency — major

plan §6/纸面演练#3把git rev-parse得到的blob对象标识与文件SHA256比较。在当前仓库该对象标识是Git SHA-1，不是裸文件SHA256；即使Git采用SHA256对象格式，也包含Git对象头，与文件摘要不同。应从固定完整commit读取同一blob字节，用同一种文件SHA256计算预期与落盘值，或用git hash-object得到同种Git对象标识核对。§6导出/tmp/m2c2-c1-boundary.py却从/tmp/m2c2-c1-boundary-dir/导入；演练又导出后一个目录，两者都在唯一授权根外。统一到已排他创建attempt的harness/deps/boundary.py，先创建attempt再准备依赖；使用importlib指定文件加载或唯一一致导入路径，Worker不得读取该目录，不修改生产模块。所有操作用参数数组和Python文件I/O，不写shell重定向操作当只读命令。冻结任务包由正常规格流程准备，不是新的用户权限请求，也不把未发布任务包当C1模块来源。

## R3-evidence — major

当前只复制harness/evidence而不复制harness/capture，记录仍引用随后删除的日志；“可重跑/hash”不能替代Reviewer实际读取捕获。保存完整脱敏合成captured bytes、逐子项记录、summary与manifest，采用持久化包内相对路径，复制后验证每个引用和hash可访问再清理。只合成无秘密输出可保存，不要求提交真实Agent transcript。持久化deliveries/M2C2/evidence路径同时被permission“不写主仓库/授权根外”禁止，需将该交付目录明确列为可信harness允许写的单独输出根（Worker仍全deny），更新全部权限表及禁止项；这是提案待批准范围，不是已有Git push授权自动包含宿主写权限。harness/state统一Worker全deny，不在permission写Worker只读。清理结果要在持久化记录中补记，不能把唯一清理证据写进已删目录。

## R3-verdict — major

多处字段和说明写“action_exit_code非零即拒绝”，仍把命令错误/崩溃当拒绝。示例重新引入/bin/sh -c echo，违反参数数组固定fixture约定。改为版本化Python fixture argv，并捕获真实OSError errno；非零只表示动作失败，只有明确权限错误、同动作非隔离正向对照成功、目标存在/监听有效、目标未变化等联合证据才判预期拒绝。字段exit_code必须真实int/null，不能填errno。普通控制面/凭证子项不能仅凭非零+零泄漏通过。timeout/崩溃/启动失败/output_limit各自分类，不能写pass；截断必须终止并标记，不只是静默截断。纸面演练#12用一条EPERM非零规则覆盖环境变量断言与超时清理也错误，每类子项按自己的成功/拒绝/取消判定。

## 完成方式

在原四文件中集中替换上述条款，更新完整attempt表：父根→排他创建→harness/deps固定依赖→profile/合成动作→每类真实判定→完整证据包持久化并复核引用→确认进程→清理及持久化清理记录。无需宿主探测、代码实现、main合并或新增模型probe。报告列出精确导出/校验/导入路径、证据包树、三类pass示例（正向/预期拒绝/超时清理），不要只写处置打勾。正常commit/push后待外部审核，再准备冻结规格。
