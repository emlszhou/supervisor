# M2C2A 独立审核 R3：request_changes

候选60ac8616e84b804037fb576156b95f3703cd5de2，origin/mcode/m2c2a-r1，继承97416f1。合同f01525c5b92dd516c7d2fbf9f7c2e8034514c1353d5d270460d7fcdca383b9ef；基线51d497cae7f20872e5a5f9c8825fd0f83323a92f。

独立检出/tmp/mcode-c2a-r3-review。从单独干净基线检出用prepare_git_handoff导出并校验/tmp/M2C2A-r3-contract，未绕过初始导出检查。Python3.12.14，frozen依赖。保护46+项目391，实际437 passed，50.28秒，exit0。Ruff check/format（69文件）、specs（6schema）、sdist/wheel通过。累计8允许文件5833新增行（6000上限剩167），未改保护/禁止文件。Macprobe未授权/未执行，不将离线结果解释成强制隔离通过；没有main合并或部署。

## 已改善

两遍判定和对照优先已实现；恢复、ro fixture副本与显式解释器、最小环境、原始stdout/stderr捕获、独立预清理校验、最终校验、profile/tree/目标证据持久化和C1调用均有实际代码。R2元文件符号链接豁免已经关闭。报告诚实保留Macnot_run及部分能力缺口，但以下关键实现与报告仍不一致。

## C2A-R3-process — blocking

preflight.py625–686：_group_alive返回True表示组仍存在，wait_gone直接返回这个值；_cancel_process_tree却仅gone is not True时升级KILL，并把该alive值写group_gone；_cleanup_state_from_cancel将group_gone=True解释为清理成功。等于残留组被判True且不升级KILL，已消失组反而False。独立mock真实语义的活性接口（不发信号）：

- _group_alive=True：cleanup_confirmed=True、kill_sent=False。
- _group_alive=False：cleanup_confirmed=False、kill_sent=True。

此外identity=None仍发信号，随后identity_confirmed=None可被当清理True；正常退出路径不验证组内子孙，_cleanup_blockers仅timeout_cleanup None才阻止删除。独立构造positive输出超限取消记录，cleanup=None、identity=None、group_gone=None，blockers实际[]。未知取消状态仍允许删现场。

修正alive/gone明确语义，升级依实际组存活，任何启动身份未知/变化均禁止不可信信号和删除；leader退出后子孙仍需处理，取消故障及正常退出残留/unknown都必须挡清理。测试注入的是alive实际语义，不只断言自行构造的group_gone。无需真Mac探测。

## C2A-R3-controls — blocking

_classify_records2461：任何无paired_control记录第一遍调用_case_for_classifier(record,'pass')，包括两个control=False的链接拒绝。独立构造T1-link-escape-read，无对照，exit1/EPERM/目标未变，实际verdict=pass。交付说明“control_passed恒False只能unknown”与执行代码相反，不能接受该有限候选的真实性。

没有对照的拒绝必须unknown（越界成功仍fail优先），不得默认pass。链接在work不妨碍allow_target指向其解析后的denied/secret单一真实目标：保持fixture/argv中的同一链接路径、只改目标许可；是否Seatbelt能支持须Mac另验证，不需要扩大冻结API或把别的对照冒充同目标。

T3-connect拒绝refused_port却配T3-connect-control的control_port，仍违反同端点对照。保留两个required端点，但每个拒绝目标要有同端点allow profile正向对照，恢复后仅换profile。T2-write-direct实际目标denied/direct-target.txt，不能代替合同ro直接写拒绝；若原profile API确实无法表达ro同目标allow，对该项如实unsupported/unknown或提出具体协调者规格变更，不能换目标冒充已实现。

## C2A-R3-summary — blocking

_build_boundary_record1803：每个group只取第一个代表case，且代表positive pass/exit0就enforced=yes。独立构造T1 work positive pass + denied escape fail，生成filesystem observed=yes/enforced=yes，实际阻止策略已失败。这正是R2要求的组完整验收，不是validate_evidence结构通过能证明真实性。

按每组全部required子项聚合；任何越界fail不能enforced=yes，unknown/not_run保持unknown，单个positive只能证明动作可执行。C1 summary exit应可信harness组断言退出码，不是代表动作的exit；原始动作exit完整保留在case记录。写入可定位聚合捕获/依据hash，不把positive捕获当整组强制证明；T4/T7继续诚实未执行。

## C2A-R3-observations — major

_jsonable_worker移除stderr_bytes后_case_for_classifier仍用worker.get('stderr_bytes')判断完整性，实际持久记录只有stderr_bytes_len/stderr_text，非空stderr不能被看到。独立构造stderr_bytes_len=10，observation_complete实际True。

网络判定只received_bytes判成功，served=True/received_bytes=0（连接已成功但无payload）被当无越界effect；独立构造bound/closed/served True，fixtureEPERM，结果effect_observed=False。这违反任何未授权连接成功即fail，包括fixture错误或输出损坏。

最小修复以真实持久长度/采集状态检查stderr，served/accept成功作为连接effect，未知也不能升级pass。stdout/stderr共享reader在释放lock之后用旧room写入，双流并发可各自消耗同一剩余预算；入锁后重新算空间，补并发边界回归。C1导出reader仍>=cap误判精确上限，也要保持严格超过才失败，限额不要通过加大值避开。

## 处置建议

本轮4项集中返修，优先阻止假pass与错误删除。既有行数近上限，重构/替换错误代码及测试，不机械追加以突破冻结scope；周期用量仍建议、不重置历史。给实际两写根/网络授权之前先完成离线修复，不创建Macprobe监听或执行sandbox-exec。

普通提交推送同一mcode分支，新精确SHA复核；报告逐项写真实状态，不能提前全部fixed或模拟fresh。main/部署/live仍关闭。如果实现者不能解决，交付安全候选与遗留问题供协调者安排兜底，而不是改ID或弱化验收。
