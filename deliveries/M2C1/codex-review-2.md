# M2-C1 第二次独立复核：request_changes

精确候选6991f0b487955744d0f93a2b1cabcc5c80a69438；本机审核b9e90574c5406cd42d726bd9ddbd36d282fda93d。独立Linux检出运行：301原测试+83新增+23冻结保护测试=407 passed，0 failed/skip；Ruff check/format、specs、sdist/wheel通过。范围4文件1409新增行合规。UTC ASCII修复接受，真实执行入口仍拒绝。Mac结果328 passed/55 failed/1 skipped另计，不宣称Mac全套通过。

## 尚未关闭的既有发现

**M2C1-R1-evidence，major，部分修复。** control_readonly改unknown及exit=None约束说明接受。但network/fresh_review仍observed=yes，并以端口/分支存在为理由；上一轮明确要求对应边界未检查时observed=unknown。它们证明盘点事实，不证明网络隔离或fresh上下文。filesystem同样不应把名称盘点升级为边界观测。保留真实执行字段和盘点说明，把未验证边界的observed设unknown；不要求新增测试宿主权限。

**M2C1-R1-trace，major，未闭合。** source仍主要是命令/临时目录描述，缺少可定位的实际输出日志及捕获方法。新的时间字符串和哈希本身不能证明真实捕获，云端也不据此认定伪造。filesystem reason声称ls列出两个名称且同inode，上一轮已明确要求撤回无stat来源的同inode结论；本机Reviewer仅重算字符串哈希不能验证inode或运行真实性。若无既有证据，明确撤回该结论并记录不可核实缺口，不填代表性证据。上一轮要求不新增宿主写入，本轮报告却记载mkdir/touch及删除；如实保留这次副作用和授权无法追溯的缺口，不声称符合只读规则，不再次执行写入来补证据。

报告§10/14/16仍有TBD及旧账本，标明历史快照并增加最终精确范围和审核对应关系。它们不是新增预算硬门槛。不要继续为字符串时间/哈希重跑盘点；只用既有日志更正，不能恢复的证据承认未知。当前纯validator代码检查通过，但交付证据尚不满足验收；本机ACCEPT不覆盖上述事实缺口。不合main，不解锁live，不要求修改冻结合同或M1。
