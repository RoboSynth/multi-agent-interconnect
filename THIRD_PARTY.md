# 官方与第三方来源

| 内容 | 版本/来源 | 保留的许可 |
| --- | --- | --- |
| ACPs SDK（本项目已改造）与 CLI | ACPs-community v2.2.0，基线提交 `3985c1330209f075c124669cc9d31f0e75448140`；[官方仓库](https://github.com/AIP-PUB/ACPs-community) | `vendor/ACPs-community/LICENSE` 与各组件 `LICENSE`，MulanPSL-2.0 |
| registry ACS schema | 同一官方基线 | `vendor/ACPs-community/registry-server/LICENSE` |
| MCP Python SDK | 1.30.0；[官方源](https://github.com/modelcontextprotocol/python-sdk) | `third-party/licenses/mcp-1.30.0.LICENSE`，MIT |
| Postgres MCP | 0.3.0；[上游源](https://github.com/crystaldba/postgres-mcp) | `third-party/licenses/postgres-mcp-0.3.0.LICENSE`，MIT |
| Docker MCP | 0.3.0；[上游源](https://github.com/ckreiling/mcp-server-docker) | `third-party/licenses/mcp-server-docker-0.3.0.LICENSE`，GPL v3，保留发行包原文 |

MCP 工具通过独立进程 stdio 接入；此快照保留接入源码、依赖声明和许可，没有打包这些 Python 环境、Docker 镜像或上游工具二进制。
FastAPI/asyncpg/PostgreSQL/Nginx/Fluent Bit 等按部署脚本从各自官方来源安装或下载，版本/来源见 requirements 与 deploy 文档。
SDK 改造是本项目增量，不把官方原生实现算作自研。研究资料中的公开来源快照及官方赛题材料保留其原有署名/来源，不另行改写其许可。
