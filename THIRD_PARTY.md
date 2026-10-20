# 第三方来源与许可证

本项目原创应用代码采用根目录 [MulanPSL-2.0](LICENSE)。第三方代码、许可证和版权声明分别保留；根许可不替代第三方许可。

| 组件 | 固定版本 / 来源 | 许可证及用途 |
| --- | --- | --- |
| ACPs SDK、CLI、ACS schema | SDK 2.2.0；[官方 ACPs-community](https://github.com/AIP-PUB/ACPs-community)，官方基线 `3985c1330209f075c124669cc9d31f0e75448140` | [MulanPSL-2.0](vendor/ACPs-community/LICENSE)；AIC、AIP、AMP与平台接入。各子目录原LICENSE保留 |
| 项目对 SDK 的改动 | [公开集成提交 6b701c6](https://github.com/RoboSynth/ACPs-community/commit/6b701c635139387ca536164226523d851b0388be)及后续本地容错、任务日志修订 | 同 SDK 许可；本交付源自应用提交 `3c539acc574ee99e35fe23d64776eb5a64bccfaf`，不声称所有后续修改已被上游接收 |
| MCP Python SDK | [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)，主程序固定1.30.0 | [MIT原文](third-party/licenses/mcp-1.30.0.LICENSE)；MCP客户端与本项目路由工具 |
| Postgres MCP | [crystaldba/postgres-mcp](https://github.com/crystaldba/postgres-mcp)，0.3.0 | [MIT原文](third-party/licenses/postgres-mcp-0.3.0.LICENSE)；独立进程执行受守卫限制的数据库工具 |
| Docker MCP | [ckreiling/mcp-server-docker](https://github.com/ckreiling/mcp-server-docker)，0.3.0 | [GPLv3许可正文](third-party/licenses/mcp-server-docker-0.3.0.LICENSE)；独立进程访问限定项目的容器；不据通用正文推导 only/or-later |

第三方MCP工具由Docker构建时按 `domains/database/requirements.txt` 和 `domains/ops/requirements.txt` 分别安装，不把其代码改称自研。数据库工具的传递依赖包含 `pglast`（GPLv3+）、`psycopg`（LGPL-3.0-only），整个环境不能统称MIT。Docker工具独立环境中的MCP版本以该环境解析结果为准，保留的1.30.0许可副本仅对应主程序版本。

运行时还安装FastAPI、asyncpg等Python依赖，并拉取PostgreSQL、Nginx、Python和Docker CLI基础镜像；各自版本声明见requirements与Dockerfile，保留上游包内许可证。代码压缩包不包含虚拟环境、模型权重、第三方安装包或容器镜像；本页不是完整运行时SBOM。

历史的逐文件归属核对、上游PR记录与安装元数据放在独立“佐证”包中。测试使用的ACS资料是未注册的合成样例，不可作为正式平台身份。
