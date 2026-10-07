# M2-C2 最新提案独立审核：request_changes

候选5b6f5ab42d764853acca7bd0bfdb7a622bf3033d。独立读取四文档/差异；4文件+194/-44，diff --check通过。仅Git只读复现，无Mac探测、真实模型、实现或main合并。认可R3修订方向，但不能接受“全部闭环”的结论。

## R4-fixture — major：脚本不可读，目标也不正确

permission §2明确harness/profiles/fixtures为Worker不可读，P2–P6和plan示例却要求sandbox内Python打开该目录的脚本，必然启动/加载失败，不能作为有效拒绝。固定fixtures放ro/fixtures（Worker只读，harness填充），profile/deps/capture/evidence/state继续harness专属deny。示例脚本从harness/profiles/fixtures所在目录退两层再拼denied得到harness/denied，并非attempt/denied；改为可信harness传入明确attempt/denied/AGENTS.md参数，fixture只解析固定argv、不猜相对层级。同时正向对照显式列实际argv/工作目录并设定隔离和非隔离模式；控制动作前后重建/记录合成目标初态，不能把对照写入算成隔离写入。

## R4-dependency — major：列出的Git调用和步骤尚不可执行

§6使用shell '< commit:path'不是读取Git blob；rev-parse commit^{blob}不能把commit解析成blob。本次只读实测436e3b0e026580a6b39ece891e8ffe47ac1bb698^{blob}失败（expected blob type, dereferences to tree）。纸面演练hash-object使用input却缺--stdin，importlibutil变量拼错；更重要的是依赖准备仍在排他创建attempt/子目录之前。

请采用一个明确方案，不再保留错误备选：
1. 创建并验证父根、新attempt、harness/deps和ro/fixtures。
2. 参数数组git rev-parse '<完整commit>:src/supervisor/workers/boundary.py'取blob_oid。
3. 参数数组git cat-file blob blob_oid获取bytes（限大小并检查exit）。
4. Python写harness/deps/boundary.py，读取落盘bytes；hashlib.sha256(expected_bytes)==hashlib.sha256(actual_bytes)。若另核Git对象，git hash-object --no-filters --stdin，input=actual_bytes，与blob_oid比对。不使用shell管道/重定向，不使用可变ref。
5. importlib.util.spec_from_file_location/module_from_spec/exec_module指定同一文件，验证API。
这只要求规划步骤正确，不要求本轮实施。纸面演练严格按此顺序重排。

## R4-verdict — major：拒绝动作成功仍可能误判正向通过

矩阵通用判定“action_exit0且目标未改=positive pass”对拒绝读凭证/网络连接不成立：越界读取或连接成功未必改变文件。必须先按test_kind分支：positive动作成功+断言正确才pass；expected_refuse动作成功即blocking，不论目标有没有变化；动作已产生越界副作用，即便最后exit非零也blocking；只有真实权限错误+目标/监听存在+有效正向对照等联合证据才拒绝pass。超时清理是另一个预期测试类别，不用EPERM规则，不把所有timeout永久unknown也不把未知整树回收判pass。fixture内部控制失败/观测不足按unknown，不混作OS拒绝。

## 同次完成证据引用及清理顺序

持久化后capture路径仍使用harness/capture/<attempt>/...，包内实际capture/...，重新基于最终包根写相对引用并重读验证；更新summary_ref等引用。cleanup结果在#15清理完成后才能写，不能说#14已经复制尚未发生的结果。顺序：完整capture/evidence持久化并校验→确认可清理→执行清理→在持久化根写实际cleanup结果→更新最终manifest。不得提前填ENOENT或exit0。permission §6/§9仍禁止独立输出根，统一列明确例外，避免用Git push解释宿主写权限。以上属于既有证据/权限一致性发现延续，不扩展宿主测试范围。

## 下一步

原四文件一次集中修订；不加大段“已完成”历史说明掩盖旧正文。用精确fixture路径/目标/argv、依赖顺序、positive/refuse/timeout三分支及证据树完成纸面核对。无需重复Ruff替代Markdown逻辑检查，不跑宿主探测。正常提交推送新SHA后待审核；尚未授权宿主操作，不合main。
