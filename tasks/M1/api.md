# M1 固定 Python API v1

仅标准库，Python3.12。以下全部公开入口必须按签名实现，不修改CLI/公共__init__或已有M0模块。
无效输入、内容/身份/摘要/策略冲突统一抛ValueError；外部Git/SQLite环境错误可抛OSError或sqlite3.Error，不伪造成功。所有返回对象可JSON序列化。

## workspace.baseline
`inspect_baseline(repo: Path) -> str`：只读检查并返回完整HEAD SHA。必须是实际Git根且有可解析提交，拒绝dirty tracked、暂存修改、未跟踪文件（含被.gitignore忽略但不属于固定产物排除的文件）、merge/rebase进行中、submodule、LFS pointer、不支持链接。拒绝目录符号链接/逃逸。不修改cwd、Git配置或工作区，不fetch/checkout/reset/push，不执行hooks或Agent命令。

固定产物排除：.git、.venv、.supervisor、.pytest_cache、.ruff_cache、__pycache__目录。除.git外，排除仅作用于未跟踪产物；已跟踪文件始终受控。项目.gitignore不能自行增加排除范围。控制根下大小写碰撞、软链接、普通文件硬链接(nlink>1)应拒绝；OS缺少安全检查能力时明确失败而非声称防护。

## workspace.snapshot
`capture_snapshot(repo: Path, *, baseline_commit: str) -> dict`
`assert_snapshot(repo: Path, expected: dict) -> None`
快照必须包括所有受控tracked/untracked普通文件、删除列表和可执行模式；dirty候选允许。baseline_commit须为实际可解析完整Git SHA（40/64小写hex），不要求等于当前HEAD；同仓库使用该基线判断删除。拒绝submodule/LFS/链接/大小写碰撞/非法相对路径。哈希不持久化原始文件内容。检查读取期间文件身份/大小/mtime和库存变化，观察到变化则失败；不得追随链接读取根外路径。此检查不是OS sandbox，不承诺面对并发恶意改目录的完全隔离，M2提供实际执行边界。
返回严格字段：
```
{"schema_version":1,"baseline_commit":"...","files":[{"path":"a.py","mode":"100644","sha256":"..."}],"deleted":["gone.py"],"snapshot_sha256":"..."}
```
files/deleted按规范POSIX路径排序，无重复/大小写碰撞，mode仅100644/100755；文件sha256为原始字节hash。
snapshot_sha256=SHA256(json.dumps(其余四个字段,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8'))。
assert_snapshot先严格校验expected结构与自身摘要，再重算当前候选，任何基线/内容/模式/删除/库存不同ValueError。M1全工作区快照算法不同于M0R仅tracked提交算法，报告需标明算法，不混用摘要。

## workspace.bundle
`freeze_bundle(source: Path, output: Path, *, task_id: str, baseline_commit: str) -> str`
`verify_bundle(root: Path, expected_sha256: str) -> dict`
source为任务draft目录，最少含task.json、requirements.md、allowed_files.json、forbidden_files.json、verification.json。task.json须严格满足任务schema v1、status=draft、baseline_commit=null、task_id与输入相同；角色/预算/文件指针合法。baseline_commit是调用者已确认的非null完整SHA，仅验证格式，此入口没有repo参数不能自行证明其可解析。revision保留。
输出必须不存在、不能在source内或与其重叠、不能通过父目录链接逃逸；只在新输出写入。复制输入原始文件字节，输出task.json改为frozen并绑定基线；不修改source。source不能自带manifest.json，不含链接/硬链接/大小写冲突/非法路径。最少JSON文件严格验证（未知字段/错误类型/空或穿越patterns拒绝，verification按v1 schema）。生产不能使用开发依赖jsonschema，可标准库实现这些v1检查。
manifest严格四字段schema_version=1/task_id/baseline_commit/files，files为相对path->原始字节SHA256映射，包含输出task.json，不含manifest自身；采用排序key紧凑UTF8 JSON，无尾部newline，返回manifest原始字节SHA256。输出普通文件设为只读mode444；这不是OS sandbox。
verify_bundle使用调用者提供trusted expected摘要；验证manifest严格结构、排序规范编码、冻结task和identity/baseline一致、全目录inventory/每项digest，拒绝额外文件、修改、遗漏、路径链接/大小写冲突。不从包内自行获取trusted摘要。成功返回manifest字典。失败不能覆盖既有输出；失败清理仅限本调用新建目录。

## policy.changes
`check_changes(before: dict, after: dict, *, allowed: list[str], forbidden: list[str], max_changed_files: int, max_diff_lines: int, diff_lines: int) -> dict`
输入是完整M1快照，先严格校验自身摘要/结构/基线相同。判定内容、mode、增加、删除；按path排序返回{"changed_files":[...],"changed_count":N,"diff_lines":D}。
所有变化必须匹配至少一个allowed且不匹配任何forbidden；forbidden优先；越界/预算超限ValueError。整数预算拒绝bool，max>0，diff_lines>=0。diff_lines来自可信协调者的Git新增+删除统计，不信Agent报数，本API不自动启动Git。
patterns为相对POSIX模式，*匹配单段，**作为整个段匹配0或多个目录段，?匹配单字符；无绝对/.././反斜杠/冒号/空段。匹配严格大小写；snapshot任意casefold重复拒绝。

## storage.intents
`IntentStore(path: Path)`，显式`.close()`。
`.reserve(operation_id: str, *, task_id: str, run_id: str, attempt_id: str, kind: str, bundle_sha256: str, snapshot_sha256: str) -> dict`
`.get(operation_id: str) -> dict | None`
`.complete(operation_id: str, *, attempt_id: str, bundle_sha256: str, snapshot_sha256: str, evidence_sha256: str) -> dict`
`.mark_unknown(operation_id: str) -> dict`
返回严格字段operation_id/task_id/run_id/attempt_id/kind/bundle_sha256/snapshot_sha256/status/evidence_sha256；kind仅agent_execute/verification，status仅pending/completed/unknown，初始evidence null。
IDs匹配[A-Za-z0-9][A-Za-z0-9._-]{0,63}；摘要64小写hex。reserve先事务写意图，重复相同绑定幂等返回原记录（completed/unknown不能变回pending）；同operation_id不同任何绑定ValueError。不同连接并发同ID仅1记录，SQLite锁冲突不得静默丢失。
complete绑定attempt/bundle/snapshot必须与意图相同；pending或unknown可由独立证据明确完成，重复相同完成幂等，不同证据冲突拒绝。mark_unknown仅pending->unknown或unknown幂等；completed不得降级。不存在操作complete/mark_unknown抛ValueError。事务提交前任何失败不能留下部分完成/部分记录；close/reopen保留记录；显式rollback失败窗口由Reviewer故障注入。
不启动进程、不连接模型、不自动重放pending/unknown、不把数据库状态视为外部副作用证明。SQLite库及sidecar拒绝现存软链接/普通文件硬链接；DB不能供Worker写入（真实权限M2），不保存prompt/token/env/原始transcript。
