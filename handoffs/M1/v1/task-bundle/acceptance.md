# M1 验收

必需：全套旧测试、M1单元及外部冻结黑盒、规格、Ruff；真实收集、无skip/xfail替代核心行为，fresh Reviewer、可信包/精确候选/代码快照绑定、范围预算通过、无blocking/major遗留。

覆盖：干净/dirty/untracked/ignored/无HEAD Git；确定性snapshot、编辑/删除/untracked/mode/陈旧自身摘要；任务冻结不改源、预存在输出拒绝、包修改/额外/遗漏/链接/硬链接/case冲突/坏JSON；allowed/forbidden优先/删除/mode/预算/规范模式；SQLite幂等、绑定冲突、完成证据、unknown不重放、close/reopen、并发意图、事务失败回滚。

Reviewer补充：父目录链接、读取期间变更、submodule/LFS、内存/时间限制、源冻结竞态、任意恶意manifest类型、权限错误、不支持平台的诚实失败、SQLite相关文件链接及提交故障窗口。不得将本模块描述为OS隔离，M2另验。
