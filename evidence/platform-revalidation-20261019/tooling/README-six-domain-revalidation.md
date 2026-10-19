# 批末六域AMP采集与12例闭合对账准备

这些文件仅为后续执行入口，准备时未调用Docker/平台、未读取live日志判定终态、未执行采集或分析。正式结果采集器 `collect_closed_revalidation.py` 保持独立。

复用旧 `collect_six_domains.py` / `check_closed_access_credentials.py`，原件不变。派生工具只调整本12例项目、输出根、终态及安全采集检查；凭据内容扫描仍使用既有scanner/pattern，访问统计仍调用既有reconcile_access，具体来源及固定SHA见 `revalidation-analysis-tools.json`。没有另造扫描规则。

先由根代理实际等待两段父进程终止，核对逐例terminal与结果，并完成最终 `execution-rest/stop/result.json`、Compose-stop实际exit0、`execution-rest/keeper.exit.json`实际terminal exit0。将最终stop/keeper原件SHA与两段phase实际exit写入 `batch-terminal.json`。首阶段review-gate exit1与full_history-r1原失败保留。不得在session仍存活、stop未完成或keeper未返回时运行以下入口。

1. 采集：用开发Python运行本目录 `collect_six_revalidation_domains.py --collect --terminal <真实batch-terminal.json绝对路径> --terminal-sha <原件SHA>`。默认新目录为本publication的 `runtime-amp-capture`，必须不存在；失败目录及其元数据保留，下次明确指定新的 `--output`。无 `--collect` 时不读日志、不调用Docker。
2. 采集入口只允许Docker `inspect` / `cp`。先确认六个精确project/service/container-name/image/domain，全部 `State.Running=false` 且status=exited；核对 `/domain` bind确为本域路径且readonly，`/state`卷属于本项目与对应Compose卷标签。主备数据库共用 `database-agent-state` 是既有部署设计，不能虚报为六个独立卷。
3. 按容器完整ID复制 `/state/amp-<role>/.` 到本机新目录。只接受普通 `amp_*.jsonl` 文件，记录每个文件字节数与原字节SHA；不启动容器、不mount新容器、不执行容器内命令、不改源文件。采集后再次inspect验证容器ID、image、标签、状态、起止时间及mounts不变。Windows Python下cp目的路径转换到WSL的 `/mnt/<盘符>/...`。
4. 取得 `runtime-amp-capture/private-domain-snapshot-manifest.json` 的真实SHA后，用开发Python运行 `check_closed_revalidation_access_credentials.py --scan --terminal <真实终态绝对路径> --terminal-sha <终态SHA> --domain-snapshot-manifest <采集manifest绝对路径> --domain-snapshot-sha <manifest SHA> --output <本publication下不存在的新分析目录>`。此阶段只读已冻结的本机快照及12例捕获，不需要Docker，不使用 `--collect-docker`。

对账按每例捕获到的真实sessionId+taskId精确过滤共享域日志，每例必须一个会话，跨例会话必须不同。每个Start预期发送端和接收端各1条access；坏行、半行、缺端、多余端、生命周期不完整分别保存。normalized副本仅供旧reconciler读取，原消息与原AMP文件不改。任务实验通过数不能代替T05；即便11/12实验通过，任一坏行/缺端仍会保留并导致本批相应闭合项失败，原22例T05=false也不改判。

凭据清单复用旧63值，再读取保留的旧验收env与本批env，不输出实际值；附env原字节SHA以便绑定。最终不同值数量以真实分析输出为准。捕获覆盖不全、解析错误、原文或解码命中均保留；analysis exit1可以代表真实findings，而不是需要删除或重跑失败数据。报告在新目录写入 `closed-access-credentials.json`、`analysis-exit.json`；失败异常另存analysis-failure，不覆盖已有输出。

原domain快照manifest、命令元数据和raw captures继续作为本地原件，可能含身份或本机路径；不得直接当公开投影。根代理需对analysis结果再做字段白名单/路径投影、绑定原件SHA、最终隐私扫描后发布。该分析不证明官方Kafka入库、Monitor验签/查询、后台访问量或长期在线。
