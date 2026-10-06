# API与行为

新增supervisor.workers.boundary，标准库纯证据校验，不读取配置/日志/凭证、不启动进程/联网、不实施sandbox。API：validate_evidence(record:dict, *, expected:dict[str,str])->dict，成功返回深拷贝，非法输入ValueError固定安全错误、不回显原值；require_live_execution(*args, **kwargs)恒raise RuntimeError包含live_execution_disabled，无可配置解除开关。

expected恰含task_id/run_id/attempt_id/worker_id，均安全ID：完整匹配[A-Za-z0-9][A-Za-z0-9._-]{0,63}，非法ValueError。record恰含schema_version/task_id/run_id/attempt_id/worker_id/platform/checks；版本严格int1非bool，身份与expected完全相同。platform非空str长度<=128。checks为list，以下7个ID每个恰一次：filesystem/control_readonly/network/mcp/credentials/process_tree/fresh_review。

每check恰含id/declared/observed/enforced/executed/argv/cwd/started_utc/ended_utc/exit_code/output_sha256/source/reason。前三态yes/no/unknown；executed严格bool；reason非空str<=4096且不输出秘密。source为非空str<=1024，引用脱敏证据来源，校验器不访问来源、不证明真实行为。

executed=False：argv/cwd/started_utc/ended_utc/exit_code/output_sha256全null，observed/enforced都unknown；declared可任意三态。executed=True：argv非空str列表，每元素非空且不含NUL；cwd非空str；UTC为严格YYYY-MM-DDTHH:MM:SSZ有效日期，end>=start且跨度<=120秒；exit_code允许真正int（含负数）或None，bool/float拒绝；output_sha256为小写64hex。允许运行过但exit未知：保留全部证据且exit=None，enforced不能yes；不能因为exit未知就把executed=False。

enforced=yes须executed=True、observed=yes、exit_code==0且非bool，但这只表达提交者声明一致性，不能变成可信attestation或解锁执行。没有ready/allow_live返回值。拒绝未知字段、缺失、重复检查、错误类型、非法身份/摘要/UTC/跨度，且不能修改输入。

# 真机盘点与平台验证

只读盘点已有VM/容器/受限账户、可确认状态及版本，工具名单/CLI flags/PTY不是OS边界。允许读取非秘密help/status元信息、不创建实例、不访问用户凭证或全量环境。报告列出文件/网络/MCP/凭证/进程/fresh控制缺失及C2可实施路径；无能力则unknown，不再次模拟ACCEPT。

Mac平台：读取既有pytest失败日志与实际项目Python/uv/fs信息，区分APFS大小写不敏感拒绝和测试regex后果；有操作者已存在且已授权大小写敏感项目检出时，可运行原测试（保持现有文件），不创建卷/挂载/重置/装工具。否则写not_run并给最小环境前提。每项命令外部限时120秒/输出64KiB，仅合成数据或项目测试，无真实模型probe、宿主攻击或越界秘密读取。

boundary-evidence.json为实际盘点的七项记录；未做强制探测executed=False/enforced=unknown。可以引用报告来源，但不将纯help版本说成强制边界检查。合成测试fixture不作为真机证据。报告必须明确所有观测、未测、真实exit/null、哈希、平台差异，及C2实施/攻击拒绝验收方案；不能实现或宣称完整Worker隔离。真实Agent调用依旧关闭，M2-B未合main不阻塞本独立任务。
