# 官方片段与安装依赖归属

范围是团队afb46e1的跟踪vendor/冻结基线、保留的许可证、直接requirements与Windows新环境69个已解析安装包的元数据。完整文件级对照见[source-inventory](source-inventory.json)，元数据和许可字节核对见[source-ready](source-ready-revision2.json)。未扩写为所有研究资料、模型权重或容器操作系统包的完整许可清单。

当前vendor305文件：281份官方原生内容（272仅CRLF/LF、9原字节相同），3份SDK运行时改造、10份SDK新增，以及11份官方文档/规范的发布链接改写。[11份资料复查](reference-docs-revision2.json)逐条确认只把Markdown链接目标改为固定3985官方blob/raw URL，未新增技术正文，项目自研行数计0。

四份MulanPSL-2.0组件LICENSE及三份已留存的第三方LICENSE保留原字节。mcp1.30/Postgres MCP0.3的MIT声明与安装包许可副本匹配；Docker MCP0.3保留的文件为GPLv3正文，本次未据它推断only/or-later。Postgres MCP的pglast7.2依赖在本次真实安装元数据中标为GPLv3+，必须单列，不能把依赖链统称MIT。

MCP v1主/数据库工具环境与Docker工具的MCP2.3环境分开；MCP1.30的许可副本不作为MCP2.3的逐版本元数据证据。未重新取Docker工具环境原始元数据或起新容器。

这些安装依赖、运行时、模型和容器镜像不在本仓库源码包中。本项目根目录尚无整体LICENSE，原组件许可不自动成为新增应用代码的统一授权；本轮没有另行授权项目或公开新代码。
