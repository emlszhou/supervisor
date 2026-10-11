# M2C2A MiniMax Code 候选独立审核：request_changes

候选：97416f1a677cbdc8bc1d4860f56f52565e885338（origin/mcode/m2c2a-r1）。继承7e5920b，基线51d497cae7f20872e5a5f9c8825fd0f83323a92f。冻结合同f01525c5b92dd516c7d2fbf9f7c2e8034514c1353d5d270460d7fcdca383b9ef。

独立检出/tmp/mcode-m2c2a-review，Python3.12.14/frozen依赖。冻结保护与项目联合pytest实际420 passed，exit0；Ruff check、format（69文件）、specs（6schema）、sdist/wheel均通过。累计8允许文件4395新增行，范围合规。真实Mac未执行、未授予探测权限、live仍拒绝。旧Linux两失败已关闭；导出TypeError和主入口纯占位问题已修。下述完整闭环问题使本候选尚不能接受，保护通过不穷尽合同。

## C2A-R2-matrix — blocking

preflight.py1096–1232拒绝在对照之前；1761–1777按记录顺序单遍判定，对照尚为unknown。独立构造真实语义的拒绝记录（completed/exit1/EPERM/目标摘要相同）和随后成功positive对照，实际结果{'r':'unknown','c':'pass'}，合法拒绝不能通过。合同要求先对照、恢复初态并核对摘要、再拒绝；当前没有恢复步骤，还给对照额外M2C2A_ALLOW_TARGET环境变量，违反仅隔离配置不同。修执行与判定顺序并检查完整必需case集合：缺T1其他哨兵/链接越界、T2 ro直接及链接写拒绝、T3两个监听端点。T5-env和T6-child fixture不输出effect，因此positive实际会fail；child depth2仅启动一个睡眠子进程却自述depth2。补真实合成深度与env集合验证，不能改判定掩盖缺证据。

fixture已复制ro却实际run_worker执行原检出fixture（1640后fixture=str(fixture)），未按合同使用ro副本；其执行模式/解释器启动需可靠argv路径并记录。生产实际SBPL有效性仍须Mac另测，不据离线测试宣布。

## C2A-R2-process — blocking

_kill_process_tree（721）TERM后只等待leader；leader及时退出时不再KILL仍存活组内子孙，killpg失败被吞。process_tree在结束后才采集，无启动身份快照，PID-only signal0不能确认整树。_cleanup_state直接返回_pid_alive：leader不存在实际False（独立patch复现），语义与cleanup确认反向；即便反向改成True也不能证明子孙消失。run_worker结果cleanup_confirmed始终None且未从树观测更新，T6无法有效判定。修独立整树身份/残留/拒绝三态，leader退出仍完成组内回收；无法确认保留unknown。复用已有ProcessRunner允许但不改保护process.py。离线故障注入覆盖leader退出、子孙忽略TERM/持管道、killpg拒绝和PID身份变化。

## C2A-R2-lifecycle — blocking

run finally（1470附近）无条件_clean_attempt，包含C1导出失败、执行故障、复制/引用/预清理校验失败、进程状态未知。这与报告“校验失败保留现场”相反且销毁唯一捕获。只有持久化完整验证成功且整树确认可清理才删除；失败/unknown留下现场并如实报告。finalization目前仅依据pre-cleanup文件存在，不能代替预清理校验成功。finalize后没有调用verify_package，包也缺合同process_tree.json/denied_manifest.json及profile持久化可读证明；C1模块加载但未真正调用validate_evidence七check。补生命周期完整性、C1结构转换、必需树及最终验证，不从存在文件推断成功。

## C2A-R2-environment — blocking

run env=dict(os.environ)继承宿主全部环境变量再加合成变量，没有最小环境白名单。真实凭证会进入合成Worker，action_env只报告M2C2A前缀名称不能证明其他变量不在；报告未接触真实凭证不能替代进程环境隔离。建立最小已声明环境（解释器必需及合成值），不记录真实值；注入虚拟credential sentinel证明不会传递且报告仅名称。

## C2A-R2-evidence — major

evidence._check_inventory将pre-cleanup-manifest.json无条件_META跳过（甚至链接），最终清单可不列它且仍通过。独立用冻结package helper生成有效最小包，再添加pre-cleanup-manifest.json悬空链接，verify_package实际ACCEPTED。最终generic包只能豁免manifest/CHECKSUMS；pre-cleanup是最终普通payload，阶段差异由明确预清理接口处理。拒绝此文件链接、未列普通文件、目录/非普通节点，不能跳过元文件检查；维持保护最小普通包接受。

## C2A-R2-capture-budget-network — major

_run_bounded_command达到预算>=max_output就宣布超限。独立命令os.write(1,b'x'*16)、max_output16得到output_limited=True/completed=False/exit-15；应只第17字节越界。注释“kernel never hands extra byte”不成立，正确区分精确预算EOF与额外字节。run_worker存储解码再编码stdout，仅stderr在内存不持久化，替换解码会改变原始bytes，违背capture字节完整要求；保留stdout/stderr原始bytes与可读派生记录，并落实总1MiB预算。

监听线程无ready握手便运行Worker，拒绝线程等待122秒而join只5秒，可能与紧接对照使用同端口冲突；accept失败返回路径不显式close且无取消/join确认。run_loopback_control的真实监听/连接结果没有进入_classify_records有效性判定。两个独立合成端点必须ready、边界内关闭、同目标对照、连接成功即fail且有效监听证据完整；无法确认则unknown，不能把ECONNREFUSED当隔离。用离线注入验证，无需也不得执行未授权Mac/network probe。

## 下一步交接

由mcode从97416f1继续同任务，集中完成上述6项，普通推送mcode/m2c2a-r1或新分支。原允许文件/标准库/冻结保护不变。新增回归需证明合同行为而非镜像实现；运行全套及冻结保护并报告实际结果。周期额度建议，不重置历史；Mac授权缺失不妨碍离线修复，不运行sandbox-exec/实际网络探测、不合main、不部署。报告不要提前写“全部关闭”；新精确候选再独立审核。实现者若不能解决明确遗留，由Codex按用户既有兜底授权接管，不能通过无限改任务ID绕过。
