# 示例说明

`synthetic/project.toml` 是可解析的模拟项目配置；只用于 schema 校验，配置执行器尚未实现，不会启动 Agent。

`artifacts/` 中的 task/result/review/event 是协议样本。task 为 draft，review 为 blocked，全零摘要仅作格式示例，不是真实运行证据。

正式运行应将合成测试项目复制到独立受限工作区，再初始化自己的 Git 基线。不要让实验接管用户当前业务仓库。
