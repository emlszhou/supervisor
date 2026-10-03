# M0 v2 Git 冻结交接

版本化元数据见 handoff.json。main 发布本目录；Hermes 克隆 hermes/m0 并按 docs/git-handoff.md 导出到实施目录外。

本版本增加用户已授权的 Git 推拉和交付报告路径。原始 v1 包不修改，公共 API 和57项独立行为验收的文件字节保持一致。39项准备检查通过，57项验收因实现尚不存在而失败；不是功能通过证明。

不要修改本目录的 frozen 输入。更改需求或允许范围需要新的版本。Git 路径和只读权限不证明 OS sandbox。
