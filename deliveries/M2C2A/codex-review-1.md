# M2C2A 独立审核：request_changes

精确候选7e5920b1d90ac8582e558c8c09573ea1c6f49704（88232d470c261c2daeb38055d3db73c45b412217代码+报告更新）。基线51d497cae7f20872e5a5f9c8825fd0f83323a92f；合同f01525c5b92dd516c7d2fbf9f7c2e8034514c1353d5d270460d7fcdca383b9ef。独立clone/tmp/m2c2a-delivery-review，Python3.12/frozen依赖。范围8文件2115新增行合规，live仍拒绝。冻结46protected全部通过；protected+project总385passed/2failed，exit1；Ruff check/format/specs/build通过。无Mac/真实模型probe，不授予宿主操作。

## C2A-R1-matrix — blocking

preflight.run成功读取授权后只返回status=authorized、paths_created/listeners为空、sandbox_exec_invocations=0，没有调用attempt/依赖/profile/对照/网络/fixture/classify/summary/persist/cleanup任何步骤。helper存在不等于矩阵已实现。报告“真实执行路径已实现，授权后运行”不成立。合同允许Mac未授权not_run，但不允许把授权后应执行的功能留占位。实现完整编排，离线用依赖注入/受控mock验证实际调用顺序、同目标对照恢复、fail/partial和故障保留现场；不能mock结果作为Mac强制证据。真实Mac仍不执行，直到operator批准。

## C2A-R1-process — blocking

run_worker先阻塞proc.stdout.read(4096)再检查时间，无输出长进程/继承stdout子孙使外部120秒限制不起效；只有leader terminate/kill，无独立watchdog/start_new_session或既有ProcessRunner的整树取消/三态绑定，kill后部分路径未wait。process_tree读取整机ps表，没有关联attempt PID及启动身份。复用现有ProcessRunner而不改process.py或正确实现独立watchdog，输出超限/超时也绑定可确认整树清理；身份无法确认unknown，不能把ps成功/空表写True。增加静默挂起、leader退出子孙持管道、输出超限回归，限于离线合成单元测试不运行Mac探测。

## C2A-R1-dependency — major

export_c1_dependency比较proc.stdout[:max_bytes+1] > max_bytes，bytes与int比较必然TypeError。本次patch subprocess.run返回CompletedProcess(stdout=b'known module bytes',returncode=0)，实际复现TypeError。还先无界capture再限长/截断，不是读取上限。改len及有界读取/超时，禁止写截断模块；核对完整bytes/hash，固定C1commit/path、blob记录及importlib加载真正接入run；补正常/超大/对象缺失/超时回归。不需要C1合main。

## C2A-R1-boundary — blocking

load_authorization允许expected digest缺失时接受任意64字符，未检查platform/批准scope类型和回环范围；run丢弃加载结果，不验证output_root实际批准根或attempt ID。ensure_attempt没有父根逐组件无符号链接校验/排他mkdir，resolve会跟随父链接，params值也未与真实子目录绑定。公开CLI --platform可以假装darwin，应移入内部离线测试注入，真实CLI实际平台必核。权限记录结构与operator批准来源分开，缺合同绑定必须fail closed；匹配实际两个批准根和合成TCP范围、严格ID，拒绝已有attempt/输出包、符号链接/越界，不靠文档保证。纯离线输入拒绝测试即可，不为补证据申请Mac授权。

## C2A-R1-evidence — major

verify_package _check_inventory仅对path.is_file判断未列条目，忽略悬空符号链接/链接目录。本次用冻结test_contract.package生成有效包，加unlisted-link→/tmp/nonexistent-c2a-audit-target后verify_package实际ACCEPTED。应先拒所有链接/非普通节点，不跟随目录链接，路径含..不能先normpath消掉再接受；检查全部记录capture引用不只summary引用记录，异常固定ValueError。

persist_package源码按test_id无.json/.log查源；实际约定源是<test_id>.json/.log，可能静默不复制。fresh=True又允许非空existing包复用覆盖，隐藏文件被忽略，违反排他输出根。pre-cleanup manifest当前生成时库存未含新pre-cleanup文件/空CHECKSUMS，不接入真实预清理校验；finalize仅接收调用者结果未编排真实删除。统一实际文件名、相对引用、无循环manifest，复制/hash核验失败保留现场，真实清理后记录结果，拒绝任何已有非空输出和符号链接。补完整从真实合成记录到持久化/校验/清理的离线生命周期用例。

## C2A-R1-tests-report — major

新增integration test_refuses_mismatched_contract_sha在Linux先platform_not_darwin却强断authorization_invalid；test_non_darwin_platform_refuses读取../M2C2A-v1-contract/handoff.json，干净Linux独立检出无该特定外部路径而FileNotFoundError。用测试临时契约数据与内部平台注入，项目测试不得依赖开发机外部交接目录；真实保护测试仍外部运行，不能修改冻结保护。报告区分函数占位、真实实现、未运行平台，不再声称代码已就绪/阻塞仅授权。Mac既有55失败单列，Linux新增失败需修。

## 返修

一次集中实现闭环并修上述问题，仍遵守原合同/允许文件/标准库，不改既有Worker、Agent或保护测试。周期建议额度不硬停。Mac授权缺失不妨碍完成代码与离线故障注入，不能代签授权或实际跑sandbox-exec/监听。普通提交推送hermes/m2c2a，新精确候选再fresh审核；非快进保留分叉推新分支。当前不接受、不合main、不部署。
