# 合成项目

`calculator.py` 提供一个极小、正确的示例接口，便于后续任务复制到临时独立仓库并故意引入可验收缺陷。这里不是嵌套 Git 仓库，没有真实数据。

`project.toml` 中 project.root 为相对配置文件的当前目录。验证命令从该项目工作区根运行。mock 可执行文件由运行时明确的 Python interpreter 路径解析；当前仅校验配置格式。
