# Operator待批准的Mac操作（不是已授权）

执行机器当前operator的Mac mini、现有william账户；无sudo/安装/容器/账户/挂载/网络配置变化。不读真实凭证、不探测其他仓库/服务，不启动真实模型。

可信harness写根：/tmp/m2c2-sandbox（实际/private/tmp/m2c2-sandbox）。每attempt真实排他目录，work/ro/denied/secret/harness/{deps,profiles,capture,evidence,state}。Worker仅work写、ro只读，其余deny。合成拒绝目标都在该根内；不在根外试写真实AGENTS/凭证。
独立持久化根：本项目实际检出下deliveries/M2C2A/evidence；冻结handoff绑定operator实际项目绝对路径，不硬编码到production API。该输出根只有harness写，Worker全deny。写根必须operator明确批准，Git push授权不等于harness写权限。

允许harness：Python标准库mkdir/file I/O/shutil、git只读完整对象读取、profile生成；argv subprocess /usr/bin/sandbox-exec -f <profile> -- <固定python fixture argv>；ps -axo pid=,ppid=,pgid=,stat=,lstart=；sw_vers/uname/id/stat/ls仅相关元信息；精确attempt删除及确认；Git已授权普通提交推送。fixture只操作合成文件/受控子孙/最小环境。
网络仅harness自起自收127.0.0.1随机高端口TCP监听及连接，2s connect，8KiB单连接；不访问15721/18080/外网/DNS/UDP/IPv6。背景端口不能通过无监听伪拒绝。

每command120s/64KiB，attempt建议2h/总捕获1MiB；TERM->5s->KILL仅自建可确认PID，身份未知不kill他人。取消失败保留现场；先完整持久化再删除，真实清理结果写持久化包。无force/reset/clean/删除分支。

用户批准本清单及实际两个根后，operator在外部保存批准记录（任务/合同摘要、平台、根、回环范围、批准时间、授权来源），harness参数引用该文件；实现者不能自行代签。文件存在不是自动可信。未批准时无需询问重复Git权限，仍完成代码/离线测试并报告probe not_run。
