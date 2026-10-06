# M2-B 独立复核：request_changes

候选 `2961690bb44ebfe13effad75aa88e0600a1767a2`，实施代码 `49e9152`；Hermes 审核 `e3710df2acb7ba272702c1b88b393285b7559221`。范围4文件/1272新增行合规。Linux独立检出：原301 + 新39 + 外部保护29 = 369 passed，0failed/skip；specs、Ruff check/format通过。真实调用入口保持拒绝，无真实Hermes/模型probe。本审核不受建议周期用量限制。

附属独立探测脚本 `codex-review-1-probes.py` 应用候选安装环境执行，当前7个probe均不满足预期，exit1。这些是原合同要求，不新增验收语义，不修改冻结输入。

## M2B-R1-process — blocking

parse_result 不检查 status 必须completed；输入 status=failed、exit=0、合法stdout/cleanup=True，返回completed。违反实际进程优先，输出不能覆盖进程失败。应先验证真实状态：非completed合法状态保留，未知状态不得成功。timed_out/cancelled/output_limit/environment_failure 分支把真实exit强行置None，示例timed_out/-15变成timed_out/None；需保留实际退出码，并给固定安全错误分类，不回显原始输出。

## M2B-R1-json — major

_is_finite_non_bool_float 只检查float类型，未检查math.isfinite；json.loads未拒绝parse_constant，Infinity/NaN时间戳被接受。timestamp:null、duration_ms:null、tokens:null被当字段缺失，违反存在时必须合法数字/object。tokens未知key也被接受。需要区分缺失与null、严格拒绝非有限常量/溢出float、未知tokens字段，并覆盖全部事件位置和可选字段。

## M2B-R1-order — major

text事件不检查seen_init，text/init/result被接受。合同要求首事件init；应显式状态机约束第一/重复/末事件及空白处理。

## M2B-R1-errors — major

事件type为[]或{}时，set membership抛TypeError；subtype类似。协议损坏应返回failed固定安全错误，不抛解析异常。额外需覆盖深度嵌套导致RecursionError等可控解析异常；不要吞KeyboardInterrupt/SystemExit或系统级异常。测试类型矩阵及保密error。

## 交接与记录

Reviewer ACCEPT 没有覆盖上述真实合同失败，不能作为合并依据。返修只改四个允许文件，增加有意义回归，并针对最新完整candidate另起fresh Reviewer；外部脚本为协调者审核工件，在checkout外运行，不加入实施allowlist。

用户自述用了--force-with-lease，这也是force-push，既有规则没有“修detached HEAD”的例外。当前fetch看见实施分支从基线正常快进，但远端现态无法证明是否历史被覆盖。需在报告中提供实际命令、目标ref与before/after SHA，核对对象可达性，必要时普通新分支保存旧tip；禁止进一步强推/reset/clean。detached HEAD可正常push HEAD:refs/heads/<新分支>处理。

Mac55失败与Linux通过分别保留，不在本任务修改M1。预算建议值不阻止返修，停滞时检视方法。尚未合并main、未解除真实运行门禁。
