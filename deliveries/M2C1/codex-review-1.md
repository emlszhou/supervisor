# M2-C1 独立复核：request_changes

候选 `88932913f3306756514f7488c66713a4bb698007`；本机审核 `dc742be2ba2ea91897ab9be24ba421632f47538f`。范围4文件/1260新增行合规。Linux精确独立检出：301原测试+76新增+23保护=400 passed，0failed/skip；specs、Ruff check/format及sdist/wheel构建通过。已提交evidence结构校验通过，live入口恒拒绝。未访问Mac私有输出，未运行真实Hermes模型。Mac结果为321passed/55failed/1skipped，exit1，不是“321/321全套通过”。

## M2C1-R1-utc — major

_TIMESTAMP_PATTERN使用Python默认Unicode \d；将提交记录中所有executed时间数字用translate换成全角０１２３４５６７８９，validate_evidence仍返回成功。合同要求严格YYYY-MM-DDTHH:MM:SSZ，应仅ASCII数字。改[0-9]或re.ASCII，保持真实日期/跨度检查；补全角及其他Unicode数字拒绝、普通合法时间和120秒边界回归。不改冻结保护测试。

复现：json加载candidate的boundary-evidence.json，expected取四身份字段；每executed check的started_utc/ended_utc调用translate(str.maketrans('0123456789','０１２３４５６７８９'))；validate_evidence目前未报错。

## M2C1-R1-evidence — major

control_readonly对应ls -la sandbox-exec/screen/sshd；此命令证明工具文件元信息，不证明控制面只读。fresh_review对应git ls-remote，仅能证明分支存在，不证明fresh会话/上下文独立，其命令只列review1/2却reason声称三个审核分支。network仅本机端口盘点，不证明网络隔离。应区分这些盘点事实与对应边界检查：若没真正检查边界，observed/enforced未知且executed=False，完整命令/已执行盘点事实在报告单独保留，不能抹去历史；或保留执行字段但明确observed=unknown、reason只描述实际工具盘点、不得说边界已observed=yes。fresh真正身份需要实际会话日志来源，分支名不是证据。C1不要求开展强制/攻击探测，不能为了补证据扩大权限。

现evidence network仍称18080没有本地model监听，报告补正却说Python LISTEN；同步两处真实观测，不把端口与模型语义等同。process_tree reason声称M2-A已确认本机Worker的tree_cleanup_confirmed=None，但M2-A取消检查没有整树证据；缺乏具体实际运行来源时改为unknown/待验证假设。报告§9.3称enforced=yes与exit=None约束“校验器不强制”，与模块代码相反，应更正。

## M2C1-R1-trace — major

已执行证据source大多只有real-host-probe通用文字，无本轮私有输出文件定位；四项时刻整分钟且恰1秒，报告又称代表性输出。需要用既有日志给实际argv/cwd/UTC/exit/hash与可定位source，并说明捕获方式。时间无法找回就明确未知/格式缺口，不填代表性时间代替真实时间；不要求字节重跑一致。云端不因哈希字符串/Reviewer自述而断言伪造，也不能据此断言已查实。filesystem argv的ls不能证明reason所称同inode，若有另行stat证据注明来源，否则撤回同inode实测说法，仅保留能够证明的结果。

候选只写报告却使用shell -c touch宿主临时路径，与本轮只读盘点默认及参数数组开发规则有出入；据实际情况披露命令、临时目录创建/授权来源和副作用，不再执行新增宿主写入。预算建议值不阻止返修；不创建挂载/容器/账户、不改网络、不读凭证。报告账本和tip/行数TBD用现有精确值补齐，并绑定真正最终审核SHA。

## 下一步

一次小返修：UTC数字严格匹配+真实证据语义/来源更正；仍遵守四文件1800行。不反复模型probe，不改M1或公共Worker、不修改冻结合同。新精确候选推送后fresh Reviewer复核全部发现；本机日志无法查实项保留unknown，不能把“诚实unknown”包装成已强制安全边界。没有新增硬周期额度，不合main、不解锁真实执行。
