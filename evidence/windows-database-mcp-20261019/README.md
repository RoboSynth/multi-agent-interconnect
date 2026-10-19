# Windows数据库MCP安装验证

在固定9cc215f检出的新`.venv-mcp-postgres`中，按项目原requirements实际安装：CPython3.12.14 AMD64，pglast7.2、postgres-mcp0.3.0、mcp1.30.0。创建venv、安装及pip check全部exit0；安装约83.5秒，包含缓存，不作冷下载或新机器15分钟验收。

修正检查脚本自身的非依赖导入后，实际模块路径均在新venv，官方Windows wheel SHA匹配，7.2满足上游7.2.0要求，FastMCP导入、`SELECT 1`解析及`postgres-mcp.exe --help`均通过。新环境未启动业务、数据库或平台消费者，未使用身份材料；既有环境保持。

- [结果](result.json)、[实际导入与wheel来源](imports-and-parser.json)、[解析出的安装包版本和归档哈希](resolved-packages.json)、[来源及首个检查器失败](provenance.json)分别记录。
- 原安装和失败日志、完整pip report、本地venv和二进制仍保存在开发机；不将它们作为源码依赖包上传。
- 导入结果中的绝对venv路径已转为相对路径，原stdout哈希保留。其他判定和包/文件哈希未改。

这些证据仅补齐Windows安装与入口导入，不代替真实MCP数据库调用、原生local-up服务启动、新机器冷部署、F10或正式平台验收。
