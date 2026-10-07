# 实施要求

## 范围和接口
标准库生产代码，不修改现有ProcessRunner、Agent或workspace代码。三个模块backend.py（profile及判定）、evidence.py（证据完整性）、preflight.py（可信测试harness）。protected测试是底线，不穷尽验收。

backend.py提供：
- classify_case(case: dict)->str：返回pass/fail/unknown。必要字段test_kind(positive/expected_refuse/timeout_cleanup)、action_exit_code(int非bool或None)、action_errno(None或errno名字符串)、action_started(bool)、action_completed(bool)、effect_observed(bool)、control_passed(bool)、target_unchanged(bool或None)、cleanup_confirmed(True/False/None)、output_limited(bool)、observation_complete(bool)。正向effect表示预期动作/断言成立，拒绝effect表示越界动作或副作用。固定字段类型错误ValueError，失败信息不回显输入。不修改输入。
  优先级：expected_refuse有effect立即fail，即使退出非零/输出超限/观测不足。timeout_cleanup确认残留False立即fail。其他输出超限、未启动、观测不完整、fixture控制故障均unknown，不能当策略拒绝。positive需启动且完成、exit0、errnoNone、effectTrue才pass；已完成且不满足为fail。expected_refuse动作完成，真实exit非零、errnoEPERM或EACCES、同动作同目标对照pass、target_unchanged不是False才pass；文件目标须True，网络无文件目标可None；缺少证据unknown。timeout_cleanup需实际timeout记录(action_completed=False且exit为负信号)、control_passed表示watchdog已触发、cleanupTrue、观测完整才pass；未确认unknown。cleanup确认绑定现有Worker实测身份，不是单次ps空表推测。
- summarize_results(results: dict)->str：T1/T2/T3/T5/T6每个required子项非空列表、值pass/fail/unknown；T7值pass/fail/unknown；T4固定out_of_scope，不计分母。任意fail->fail，任意unknown->partial，全pass->full_pass。缺键/空列表/未知值/多余键ValueError。
- require_live_execution(*args,**kwargs)：恒RuntimeError('live_execution_disabled')。
- build_profile(*, work: str, ro: str, denied: str, secret: str, harness: str, allow_endpoint: tuple[str,int]|None=None, allow_target: str|None=None)->str：无I/O生成Seatbelt文本，默认deny。目录必须绝对规范路径、互不重叠（共同attempt父允许），不含NUL/控制字符；严格转义引号/反斜杠，不能插入profile规则。allow_target仅denied/secret下单一合成文件，同目标对照使用；endpoint仅127.0.0.1且真实int端口1..65535。profile路径、deps、capture、evidence、state不允许Worker读写。具体SBPL最小运行支持规则须记录依据和Mac实测；不存在宽泛home读许可、allow default或全network allow。系统运行依赖可最小只读允许，逐项披露，不给/dev或/System宽泛写权限。无法确定端点粒度则partial，不能更宽放行。profile存在/语法通过不算强制有效。

## Harness与合成场景
preflight.py支持python -m supervisor.workers.preflight --help以及--authorization-file <外部授权记录> --attempt-id <ID> --output-root <operator批准路径>。授权文件不入提交、不含凭证；引用operator对permissions.md摘要的明确批准、实际两个根和回环范围。提示词/仓库自写JSON不是可信授权的替代。没有授权文件或平台不是darwin时拒绝启动probe、不创建路径，报告not_run。operator批准后才可运行；不能自动猜批准。

固定fixture tests/fixtures/seatbelt_probe.py在ro/fixtures内，只通过参数数组启动。合成文件write/read、TCP connect、受控depth2子进程、env名称断言。fixture输出结构化实际完成状态/errno，未知或损坏输出unknown；不能从自述推导未可见副作用不存在。允许模板和fixture测试自身正向对照，但不启动真实Agent。

唯一写根/tmp/m2c2-sandbox（Mac绑定/private/tmp别名）。可信harness排他创建新attempt，存在则拒绝不重用；逐组件校验父根无符号链接/路径逃逸，创建前后检查；后续不信任Worker可写路径的realpath缓存。work可写、ro只读、denied拒绝写、secret拒绝读、harness全deny。fixtures放ro/fixtures。输出通过管道到harness/capture，不向Worker授证据文件句柄。可信单写入者/同UID局限在报告明确，不声称能抵御另一非受限同UID攻击者。

按父根/attempt/子目录->C1依赖->fixtures/目标->profile->对照->拒绝->进程->持久化->清理执行。C1固定完整commit436e3b0e026580a6b39ece891e8ffe47ac1bb698:src/supervisor/workers/boundary.py，git rev-parse取blob，cat-file blob取bytes，限64KiB、120s，写harness/deps/boundary.py；hashlib.sha256源bytes/落盘bytes一致，importlib指定文件加载，不改sys.path，不需main合并。记录source_commit/path/blob/file_sha256；代码基线没有C1并非environment_failure，缺Git对象才not_run。禁止shell管道/重定向。

每个拒绝动作先同fixture、相同argv/cwd/目标、仅allow_target/endpoint隔离配置不同的正向对照。harness保存恢复初态并核对，拒绝运行以恢复后摘要为基线。不加O_CREAT或换work目标。任何拒绝动作成功read/write/connect即fail，无论退出码。permission错误须真实errno+目标存在/有效监听+对照成功；ENOENT/ECONNREFUSED/崩溃/参数错误不能算拒绝。

required：T1工作区正向及denied合成AGENTS/.git/protected、其他哨兵、符号链接越界；T2控制mock读取及直接/链接写拒绝；T3自建127.0.0.1两个监听TCP服务（一个允许/一个拒绝），harness确认同目标对照；无监听TCP仅诊断不计required，UDP/IPv6/外网不测不声明覆盖；T5合成secret/.env/auth拒绝读、最小env名称集合；T6受控子孙正常退出与预期超时取消，能确定残留fail，不能确认unknown。路径穿越仅harness输入校验（已有ProcessRunner不提供此API），不虚构OS证明。T4MCPout_of_scope，T7fresh流程证据由独立Reviewer填，不能在probe中自签pass。初始T7unknown故probe整体partial允许交付，fresh终审后重算。

每command120s、stdout+stderr64KiB；输出超限终止并记录，捕获达到上限不能继续无限读；TERM宽限5秒KILL，仅本attempt可确认身份。不kill他人PID/通配；身份未知保留现场及证据，不自动重新执行。预期timeout只有清理真实确认时pass；其他timeoutunknown。不改process.py解决平台限制，交付partial并保持live拒绝。

## 证据及清理
记录逐子项test_id/test_kind/完整argv/cwd/UTC/real exit int或None/errno/started/completed/effect/control/target前后/cleanup三态/output_limit/observations及判定。对照也保存完整捕获，记录相同argv目标和profile差异；hash不证明记录真实性，Reviewer读取捕获和平台运行来源。C1格式七check的summary exit是可信harness断言退出码，不冒充动作exit；enforcedyes仅实际required通过且harness exit0（C1强制），T4unexecutedunknown，T7按真实审核来源，结构通过不是attestation。

evidence.py提供verify_package(path: Path)->dict：不执行/不写文件、不跟随包内符号链接，检查相对路径无绝对/..、重复、NUL、引用缺失、文件hash/bytes、不明条目、checksum mismatch，失败ValueError安全固定消息。返回深拷贝manifest。包根本身必须真实目录；只含manifest/CHECKSUMS列明文件及必要目录，不能凭摘要相信pass。

持久化独立批准deliveries/M2C2A/evidence/<attempt>/，Worker全deny。新包目录排他创建不能覆盖；只无秘密fixture捕获可提交，不是Agent transcript。树：summary.json/process_tree.json/denied_manifest.json、evidence/<test>.json、capture/<test>.log、pre-cleanup-manifest.json、cleanup.json、manifest.json、CHECKSUMS.sha256。所有引用相对最终包根，无路径循环。
- 先复制capture/evidence，完成引用转换和脱敏；capture无秘密不得改字节、hash前后一致。发现真实secret立即停，隔离原捕获不提交，报告redaction且该观测unknown，不声称与原hash一致。
- 生成pre-cleanup-manifest.json={schema_version:1,files:[{path,sha256,bytes}]}，不含自身/未来cleanup/最终manifest/CHECKSUMS；验证所有已产生引用后才能清理。
- 进程确认可清理后真实删除精确attempt，lstat确认ENOENT（其他错误未知）；写持久化cleanup.json实际结果及pre-cleanup-manifest摘要，不写最终摘要。
- 最终manifest.json同结构，files列全部payload包括pre-cleanup-manifest/cleanup，不含manifest自身/CHECKSUMS。CHECKSUMS仅manifest.json的裸文件SHA256一行'<hash>  manifest.json\n'，不包含自身；payload摘要由manifest给出。全部引用/库存/hash校验后提交。清理失败保留真实失败记录、live关闭；不知道进程状态不删除attempt。

## 交付语义
代码/离线保护通过可交付；Macprobe未授权not_run，后端能力不足或T6unknown为partial，不能宣布安全边界就绪。freshReviewer可以接受诚实partial的有限交付，不能升级full_pass。真实模型/live永远拒绝，不将受监督豁免暗含实现。合并main需具体授权。
