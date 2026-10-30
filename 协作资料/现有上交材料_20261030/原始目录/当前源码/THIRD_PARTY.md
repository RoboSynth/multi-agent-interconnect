# 第三方依赖与许可说明

本文件为当前源码快照重新整理的入口，不包含旧报告或历史验收结论。

- 本项目应用代码根许可证：LICENSE，MulanPSL-2.0。
- AIP配套SDK：vendor/ACPs-community/acps-sdk，包版本2.2.0（见pyproject.toml）；源自 https://github.com/AIP-PUB/ACPs-community ，保留vendor根目录及SDK/registry的LICENSE。当前vendor含工程维护的扩展，以本快照逐文件哈希为准；不声称所有修改已合入上游。
- MCP Python SDK：主环境requirements-high-score.txt固定1.30.0；MIT许可原文见third-party/licenses/mcp-1.30.0.LICENSE。
- Postgres MCP：domains/database/requirements.txt固定0.3.0；MIT许可原文见third-party/licenses/postgres-mcp-0.3.0.LICENSE。
- Docker MCP：domains/ops/requirements.txt固定0.3.0；GPLv3许可原文见third-party/licenses/mcp-server-docker-0.3.0.LICENSE。以独立进程/环境安装，不改称本项目自研工具。
- 其他Python依赖与基础镜像版本见requirements、pyproject.toml、Dockerfile和Compose定义；保留安装包本身许可证。本目录不包含虚拟环境、第三方安装包、容器镜像或完整运行时SBOM。
