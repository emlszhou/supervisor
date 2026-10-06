# 接口与实现要求

新增 supervisor.agents.hermes.HermesAdapter。生产依赖标准库，遵守现有ProcessResult/AgentResult，不修改公共类型。

## 精确API

- HermesAdapter() 无必需参数。
- build_request(context: dict[str,str], workspace: Path) 永远在启动任何进程前 raise RuntimeError，固定安全错误包含 live_execution_disabled。不提供enable_live、env/CLI开关、真实Hermes调用或resume入口。本阶段只是离线协议能力，未来另立合同解除门禁。
- parse_result(process: ProcessResult, *, expected: dict[str,str]) -> AgentResult。expected包含task_id/run_id/attempt_id/role/provider/model，其中provider必须minimax-cn、model必须MiniMax-M3。验证非空、现有身份格式与合法角色，拒绝非法expected为ValueError。返回身份来自可信expected，CLI session只作声明。返回provider/model保持expected。

## NDJSON规范（受支持子集）

stdout严格UTF-8，每非空行一个JSON object；禁止重复key、NaN/Infinity、bool冒充int。本子集仅支持type=system/subtype=init、type=text、type=result，tool_use/tool_result及任何未知类型失败。首事件init一次，末事件result一次，不能有后续事件或重复terminal。允许空行，不允许CLI文本session_id尾行或Markdown围栏。合法shape：
init {type,subtype,model,session_id,timestamp?}；text {type,text,timestamp?}；result {type,session_id,exit_code,text,tokens?,duration_ms?,timestamp?}。除问号字段外全部必需，未知字段失败；timestamp/duration_ms是非负有限数字，不能bool。init model等于expected model；session_id非空安全字符串，长度1..128，字符[A-Za-z0-9._-]，terminal同一id。result exit_code是int且为0；text必须str，不执行内容。terminal text长度不得超过4096，超过则failed（不能静默截断）；terminal text作为summary，text事件仅验证str，不要求与terminal重复一致。所有协议失败返回failed且固定安全error，不回显原始输出/秘密。

usage未知->None；tokens若存在必须object且恰含input/output，可额外含total/cache_read/cache_write；值为非负int非bool。只映射input/output为input_tokens/output_tokens；不推断total/input/cache之间恒等式，缺失字段失败。artifacts=[]，不把响应中路径当可信产物。

## 实际进程优先

先检查ProcessResult的status、真实exit、truncated、tree_cleanup_confirmed，不让输出伪造成功。非completed状态保留其合法状态及真实exit（包括None），错误固定安全字符串；completed但exit非零/None/bool、truncated=True或tree_cleanup_confirmed不是True均failed。非成功无需解析损坏输出，usage/session未知。stdout+stderr总字节超过65536失败；stderr不为空一律failed（本保守子集不接受警告、静默回退或未经理解的诊断）。超时、取消、输出预算属于既有Worker，Adapter不另起进程、不重试、不自行清理或推断整树成功。

## 测试与fixture

tests/fixtures/hermes_cli.py仅标准库模拟进程，参数固定scenario白名单：success/nonzero/malformed/wrong_session/fallback/slow/oversized。不得调用Hermes、网络、模型、动态代码、shell或读取用户配置/凭证；固定合成输出和有限sleep，不写目录。测试经sys.executable绝对路径+fixture脚本调用既有ProcessRunner.run，测试必须覆盖正常返回、真实nonzero、stdout坏JSON/UTF8、未知/工具事件、错model/session、重复key/terminal、result非零/bool、usage缺失/非法、stderr回退、timeout/output_limit和cleanup未知。单fixture wall<=3秒、输出上限64KiB，timeout/output-limit失败是预期验证而非套件失败。mock计数不算模型调用；不得伪称Hermes真机验证。

不修改M1/macOS测试。Linux全套必须通过；Mac大小写不敏感平台既有失败分类单独记录，不关闭测试、不虚构通过。CLI调查版本/子集来源及与真实CLI的未知兼容性写报告，不声称工具禁用或OS隔离已实现。
