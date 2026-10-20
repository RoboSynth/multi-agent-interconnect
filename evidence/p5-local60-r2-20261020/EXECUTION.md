# 第二批本地60格：执行与证据

本批执行[修复与重跑说明](../../docs/创新三修复与重跑_20261020.md)第三节。方法为MR、M0、M1、M2v2，5个原故障家族，各重复3次；模型、种子和预算与第一批一致。验证定义更新为`carried-intents-then-fresh-window-v2`，不能将新旧通过数当作同一定义下的直接对照。

业务代码经独立只读审查，未发现阻断本批执行的问题。排序的隐式正常预测不参与假设排除；遗留请求使用原编号收敛，之后独立计分。遗留阶段允许回执重试，不能写成全过程零异常。正常终态等待模型返回后结算用量；中断成本按`token_usage_complete`原值披露。

Windows验证记录在[windows-tests](windows-tests/)。初次全量中的缺少画图依赖记录保留，补齐后只复验受影响测试。

本机入口为`launch_windows.py`：启动独立后台控制进程，先检查本地端口与身份，配置新的本地账本路径，再启动原生业务、Qwen及本批stdio workers。控制器调用原样的`run.py`，结束后执行独立30秒/10流程健康验证，并关闭本批登记的进程。云端不部署、不启动新平台消费者。

生命周期辅助文件来自第一批已使用脚本，来源见[lifecycle/helper-provenance.json](lifecycle/helper-provenance.json)。文件先复制到本批外部产物目录再执行，旧批产物不改写。私密配置备份、账本和大日志保留在本机`incident-pilot/artifacts/p5-local60-r2-20261020/`。

结果整理顺序为`report.py`、`plot_report.py`、`verify_evidence.py`、`package_evidence.py`。原始matrix和两份源码冻结位于本目录；汇总先写本机产物的publication目录，再复制批准的文件到仓库。失败事故原样保留供算法负责人分析，执行中不调整算法。
