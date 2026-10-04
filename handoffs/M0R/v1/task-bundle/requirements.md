# M0R: Review-2 专项修复合同

新任务 M0R-review2-remediation，不重开或追认旧 M0。旧 M0 Review-2 的 reject 与预算超限事实永久保留。
基线为 fc479e760cbcd1e5259e2d62aeddaa6033d2c915，包含旧实现和86单元测试。API/schema v1 与原57验收不放宽。

## 范围与预算
只允许 allowed_files.json 中四个模块、tests/unit/test_m0_*.py 与 deliveries/M0R/hermes-report.md。
不得修改旧交付报告、原合同、保护测试、依赖、CLI 或审核记录。
本次最多10个修改文件、1800行新增+删除，按本任务基线到最终候选累计 git diff --numstat 计算，含报告；不是每提交重置。旧1866行作为既有基线，不计为本轮新改动，也不使旧任务通过。
最多一次实现、一次反馈返修、一次协调者接管；本任务不能再靠新增合同重复重置返修次数。超范围先停止并报告。

## 必须处置 Review-2
1. timeout/cancel：并发读取不得执行可无限阻塞的 buffered read；短输出、双路短输出、继承管道、无输出均受单调wall期限约束。进程退出后的drain同样受字节和时间限制。POSIX启动用安全session/group机制，不用preexec_fn。
2. cleanup：组终止被拒绝或异常时不得把leader退出当作tree确认；返回false/unknown而非true。执行后异常必须关闭两管道并终止/reap已启动进程；取消、超时、输出限额同样处理。
3. actual ProcessResult.status不是completed时，退出码0也不能升级成功；保持实际失败类别。completed须实际completed/exit0/无截断且协议合法。
4. strict schema：拒绝artifacts=null、布尔token整数、布尔schema_version及所有未知/错误类型；保留合法model/session/summary/usage/artifacts。错误信息分类且不回显原始协议。
5. output boundary：只在确认有超额字节时output_limit，恰好预算+EOF正常完成；两路合计内存有限，退出drain不能隐藏截断。
6. Windows：require_tree_cleanup=False普通短进程、两管道消费/超时不能依赖select管道；require_tree_cleanup=True不支持时启动前明确unsupported。未实际测Windows时必须标未运行，不能声称已验证。Reviewer做故障模拟和代码审查；原生Windows为未验证项，不可伪造证据。
7. report：引用真实代码commit（先代码再报告单独提交），报告commit由交接消息另给；基线/bundle用完整摘要。snapshot绑定代码commit的tracked Git树：按path排序数组，每项path/mode/sha256(raw blob)，json sort_keys=True,separators=(',',':'),ensure_ascii=False的UTF8字节SHA256。另列最终交付tip，Reviewer重算最终候选树（报告加入后不同），禁止沿用1696.../8af...旧snapshot。

必须运行原单元+完整项目+冻结57验收+新增M0R验收+Ruff/specs；独立Reviewer重跑Review-2故障注入，确认拒绝killpg、drive异常、Windows pipe-select不可用下的行为。保护验收通过也不能覆盖独立审查发现。
