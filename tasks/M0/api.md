# M0 公共 API：独立验收固定入口

本文件是合同输入，由协调者维护。以下名字、参数和行为是实现目标，不是已经存在的实现。实现方不得为适配实现修改本文件或受保护测试。

## workers.process

提供标准库 frozen dataclass `ProcessRequest`，可用 `dataclasses.replace` 更新：

```python
ProcessRequest(
    argv: tuple[str, ...],             # 第一个元素为绝对可执行路径
    cwd: Path,
    workspace_root: Path,             # 授权目录；不表示 OS sandbox
    env: Mapping[str, str],            # 完整显式子进程环境，不继承宿主变量
    timeout_seconds: float = 10.0,
    cancel_grace_seconds: float = 0.2,
    max_output_bytes: int = 1048576,
    attempt_id: str = "M0-attempt",
    require_tree_cleanup: bool = True,
)
ProcessRunner().run(request, *, cancel_event: threading.Event | None = None) -> ProcessResult
```

参数错误在启动前抛 `ValueError`。时间必须有限且正数，输出限额必须正整数（bool 不算），argv 非空且都是字符串，cwd 位于授权根内。存在性/执行权限错误返回 environment_failure。调用不能更改调用方 cwd。

`ProcessResult` 是 frozen dataclass，下列字段都可作为关键字构造，`dataclasses.replace` 可用：

```python
ProcessResult(
    status: str,                       # 六种结果见 docs/interfaces.md
    exit_code: int | None,
    stdout: bytes,
    stderr: bytes,
    duration_seconds: float,
    truncated: bool,
    tree_cleanup_confirmed: bool | None,
    error: str | None,
)
```

两路输出合计不超过 max_output_bytes。completed 的退出码为 0，failed 保留非零实际退出码。取消前已标记 Event 时不启动进程。超时/取消/输出上限时回收进程，并报告实际确认结果。

POSIX 为本轮必需平台（云 Linux 与目标 Mac）。require_tree_cleanup=True 且平台无法实施进程树回收时，启动前返回 environment_failure，error 明确包含 `unsupported`，不能声称成功。Windows 允许报告该能力暂不支持，但仍须支持 require_tree_cleanup=False 的普通短进程。这里的进程组回收测试不证明抵御主动逃逸的恶意进程，完整隔离留在 M2。

stdout/stderr 只在有上限的内存中返回，不自动写入磁盘。公开错误/事件不应回显完整环境或损坏的原始 JSON。

## agents.base

```python
parse_agent_result(process: ProcessResult, *, expected: dict[str, str]) -> AgentResult
AgentResult.to_dict() -> dict
```

expected 必含 task_id、run_id、attempt_id、role、provider。完整 stdout 是一个 UTF-8 JSON 对象，满足 agent-result schema v1；前后空白允许，多个 JSON、未知字段、类型错误和缺失字段拒绝。不得导入 jsonschema 作为生产依赖。

仅当 ProcessResult=completed、exit_code=0、无截断、协议完整且 expected 五字段匹配时可返回 completed。stdout 的声明不能覆盖进程失败。协议损坏返回 failed，error 非空但不得回显原始 stdout；输出身份不匹配时绑定 expected 身份并返回 failed。

其他进程状态原样映射为 AgentResult.status，保留实际 exit_code；失败结果 error 非空，usage 未知为 null，不制造新的成功 session。公开结果仍需满足 schema。artifact 路径只允许规范相对路径，拒绝穿越/绝对路径/符号链接式引用；真实 artifact 内容验证属于 M1。

## agents.mock

```python
MockAdapter(scenario: str = "success")
adapter.build_request(context: dict[str, str], workspace: Path) -> ProcessRequest
adapter.parse_result(process: ProcessResult, *, expected: dict[str, str]) -> AgentResult
```

context 使用 expected 的五字段，provider 固定为 mock。scenario 仅支持 success、nonzero、timeout、malformed、wrong_identity；不支持的名字抛 ValueError。build_request 使用当前 Python 绝对路径、指定 workspace 和显式最小环境，任务身份来自 context。

Mock 不调用模型、网络或认证服务。success 产生完整 schema 结果；nonzero 退出 7；timeout 运行超过请求限时；malformed 产生非法 JSON；wrong_identity 产生不同 attempt_id。超时验收会将请求 timeout 调为 0.15 秒。正常模拟执行不得超过 2 秒。

## core.events

```python
EventRecorder(task_id: str, run_id: str, worker_id: str,
              provider: str | None = None, model: str | None = None,
              session_id: str | None = None)
recorder.record(event_type: str, *, attempt_id: str | None = None,
                message: str = "", artifact_sha256: str | None = None) -> dict
```

返回满足 event schema v1 的 dict，sequence 从 1 连续递增，event_id 唯一，时间带时区。并发 record 保持唯一连续序列；未知事件类型拒绝。只接受上述元数据，不接受 raw_prompt/transcript/env；调用方负责 message 的脱敏，Recorder 不宣称能识别所有秘密。
