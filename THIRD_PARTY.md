# 官方与第三方来源

本说明以团队源码 `afb46e1b898faad4e5724db0cb6cf52d7d94ef81` 的归属核对为依据；完整库存、许可原文哈希和安装包元数据见[来源证据](evidence/source-attribution-20261019/README.md)。本项目根目录尚无覆盖全仓的 `LICENSE`/`COPYING`，本次未选择整体许可；下列组件许可各按原有范围保留。

## 随源码保留的内容

| 内容 | 版本/来源 | 保留的许可 |
| --- | --- | --- |
| ACPs SDK（含本项目增量）、CLI、协议/参考文档与 Registry ACS schema | ACPs-community v2.2.0，基线 `3985c1330209f075c124669cc9d31f0e75448140`；[官方仓库](https://github.com/AIP-PUB/ACPs-community)，[本地来源说明](vendor/ACPs-community/ORIGIN.md) | [根许可](vendor/ACPs-community/LICENSE)、[SDK](vendor/ACPs-community/acps-sdk/LICENSE)、[CLI](vendor/ACPs-community/acps-cli/LICENSE)、[Registry](vendor/ACPs-community/registry-server/LICENSE)，MulanPSL-2.0 |
| v0.2.0 冻结 SDK 副本 | 同一官方基线，保留历史内容 | [冻结副本许可](baselines/incident-v0.2.0-20261017T045307Z/vendor/ACPs-community/acps-sdk/LICENSE)，MulanPSL-2.0 |
| MCP Python SDK 许可副本 | 1.30.0；[官方源](https://github.com/modelcontextprotocol/python-sdk) | [MIT 原文](third-party/licenses/mcp-1.30.0.LICENSE)，与本次 Windows 安装包许可字节相同 |
| Postgres MCP 许可副本 | 0.3.0；[上游源](https://github.com/crystaldba/postgres-mcp) | [MIT 原文](third-party/licenses/postgres-mcp-0.3.0.LICENSE)，与本次 Windows 安装包许可字节相同 |
| Docker MCP 许可副本 | 0.3.0；[上游源](https://github.com/ckreiling/mcp-server-docker) | [GPL version 3 正文](third-party/licenses/mcp-server-docker-0.3.0.LICENSE)，与既存发行包来源记录哈希相同；不据通用正文推导 only/or-later |

上述截止下的 vendor 共305份文件：281份官方原生内容（272份仅换行差异、9份原字节相同）、3份SDK改造、10份SDK新增，以及11份官方文档/规范的发布链接改写。[11份逐条复查](evidence/source-attribution-20261019/reference-docs-revision2.json)确认仅将Markdown链接目标改为固定3985官方blob/raw URL，技术正文仍属官方，自研行数计0。后来增加的本地来源说明不在305份截止库存中。

既有SDK运行时增量 +916/-12 行属于[SDK来源对照](docs/sdk_attribution_20261019.md)的历史截止；该页的140文件统计不代表后续147文件版本。当前普通vendored SDK已精确绑定公开集成提交`6b701c635139387ca536164226523d851b0388be`，147文件、Git模式及原字节哈希见[绑定清单](vendor/ACPs-community/sdk-binding.json)。T01的最终fork/vendor绑定已完成；AtomGit镜像及上游CI仍待完成。

## 按部署安装的依赖

MCP工具经独立进程stdio接入。requirements和部署配置声明的MCP、Postgres MCP、Docker MCP、FastAPI、asyncpg、PostgreSQL、Nginx、Fluent Bit等按各自来源安装或拉取；保留许可副本不表示其完整源码、Python环境、镜像或二进制已打包进本源码仓库。

[Windows新环境安装证据](evidence/windows-database-mcp-20261019/README.md)记录69个解析包；其[逐包许可元数据](evidence/source-attribution-20261019/installed-dependency-license-metadata.json)保留原归档、METADATA和包内许可文件哈希。Postgres MCP 0.3.0本体使用MIT，但安装依赖 `pglast 7.2` 的METADATA声明 **GPLv3+**，`psycopg`及`psycopg-binary 3.3.6`声明LGPL-3.0-only，不能将整个数据库工具环境统称为MIT。pglast所查wheel的dist-info未提供独立LICENSE；其原归档SHA256为 `06a5b2d3dd63c44ca71e29fcc0fe162f959708bd348754e420ac1b9332d1d340`，METADATA哈希见上述元数据清单。

MCP版本按实际环境区分：[既有镜像证据](evidence/p0-revalidation-prep-20261019/image-attestation/probe.stdout.json)中主程序及PostgreSQL工具使用1.30.0，Docker工具的独立环境使用2.3.0。本次核实的 `mcp-1.30.0.LICENSE` 只对应1.30.0；尚未另取2.3.0的精确发行包许可/元数据，不将两者混同。

本次核对覆盖跟踪vendor/冻结SDK、保留的许可、直接依赖声明和上述Windows安装元数据。研究来源快照、模型权重来源/许可及所有容器操作系统包未纳入本次范围；这份库存不是完整运行时SBOM。研究资料及官方赛题材料继续保留原有署名和来源。
