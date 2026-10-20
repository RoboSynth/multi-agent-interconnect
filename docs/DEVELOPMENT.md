# 开发、测试与目录

当前 `main` 已合入以 `3c539acc574ee99e35fe23d64776eb5a64bccfaf` 为参照的评审版增量。默认部署入口使用本地评审模式，显式 manifest 参数保留正式部署路径。交付代码包从当前源码筛选并匿名化，清单分别记录来源与交付哈希。

## 目录

- `incident/`：协调器、协议数据、参与者、本地与梧桐传输。
- `acps_mcp_bridge/`、`domains/`：MCP桥接、资源权限、幂等操作与领域配置。
- `business/`、`demo-ui/`、`workbench_server.py`：真实订单业务和工作台。
- `deploy/`：评审一键入口、正式平台配置生成、云端服务脚本。
- `eval/`、`tests/`：实验源码与离线检查。运行产物不随代码包提供。
- `integration/`、`vendor/`、`third-party/`：平台集成、SDK、许可原文。

## 本地Python开发环境

正式开发/平台配置使用Python 3.12。先建立本目录自己的虚拟环境：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Windows对应命令：

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py'
```

`tests/business_native_acceptance.py`、平台实验执行器和`eval/run.py`涉及真实服务，不属于上述默认离线测试命令。平台实验用自己的身份、独立项目与明确范围；不应复用别人的正在运行身份。

## 评审部署

`deploy/review.py`只依赖宿主机Python标准库，支持`up/demo/status/logs/down/prepare`。Linux和Windows入口共用它；Windows优先Docker CLI，没有时使用WSL发行版`Ubuntu-22.04`，可通过`INCIDENT_WSL_DISTRO`修改。

首次启动生成`runtime/review/compose.env`及审批密钥；之后保留原密钥和路由状态，避免密码重置使既有数据卷失效。`.env.example`只提供空占位；要改端口或项目名，应在首次启动前复制为`.env`。默认项目`incident-review`只绑定回环地址。

默认本地配置在工作台容器中为每个参与者启动独立stdio进程；数据库与运维使用各自配置和MCP进程。这是本机演示的进程边界，不是正式多容器资源域凭据隔离。Docker socket只挂到本地演示工作台容器，部署在你控制的Docker环境中。正式领域隔离见[梧桐接入](WUTONG.md)。

工作台没有外部模型依赖，使用证据规则调度。启用本地模型、接管故障和平台实验均是独立运行模式，不能以本地演示结果替代相应实测。

常见问题：Docker未运行时先启动daemon；镜像下载失败时查看原错误并恢复网络；端口占用时在首次启动前改`.env`；工作台参与者未连接时运行`logs`检查对应worker日志。启动失败不会删除数据或自动重置环境。用`down`停止本评审项目，保留卷和记录。
