# 验收

四个允许文件范围合规；独立保护测试+完整原项目测试+specs+Ruff check/format通过，真实计数/exit分开记。模拟CLI集成测试必须真实执行既有Worker；解析测试不能只镜像实现。真实Hermes执行入口恒拒绝，无任何隐式开关/模型启动/网络或凭证读取。未知进程结果、回退stderr、协议错误均不得成功。可信expected身份与声明session分离。预算仅建议，不因超额否定正确结果；停滞/明显超额记录原因与策略。

fresh Reviewer核验精确完整候选SHA、外部冻结摘要、文件范围、命令、日志与失败路径；若Reviewer修改代码，另起fresh审核。最终反馈报告SHA和审核SHA，报告写真实与模拟/未运行边界。实现者不能merge main。此验收仅离线Adapter子集，不解锁真实模型执行/Worker OS隔离。
