# 第二批本地60格：执行与证据

本批执行[修复与重跑说明](../../docs/创新三修复与重跑_20261020.md)第三节。方法为MR、M0、M1、M2v2，5个原故障家族，各重复3次；模型、种子和预算与第一批一致。验证定义更新为`carried-intents-then-fresh-window-v2`，不能将新旧通过数当作同一定义下的直接对照。

业务代码经独立只读审查，未发现阻断本批执行的问题。排序的隐式正常预测不参与假设排除；遗留请求使用原编号收敛，之后独立计分。遗留阶段允许回执重试，不能写成全过程零异常。正常终态等待模型返回后结算用量；中断成本按`token_usage_complete`原值披露。

Windows验证记录在[windows-tests](windows-tests/)。初次全量中的缺少画图依赖记录保留，补齐后只复验受影响测试。

本机入口为`launch_windows.py`：启动独立后台控制进程，先检查本地端口与身份，配置新的本地账本路径，再启动原生业务、Qwen及本批stdio workers。控制器调用原样的`run.py`，结束后执行独立30秒/10流程健康验证，并关闭本批登记的进程。云端不部署、不启动新平台消费者。

生命周期辅助文件来自第一批已使用脚本，来源见[lifecycle/helper-provenance.json](lifecycle/helper-provenance.json)。文件先复制到本批外部产物目录再执行，旧批产物不改写。私密配置备份、账本和大日志保留在本机`incident-pilot/artifacts/p5-local60-r2-20261020/`。

结果整理顺序为`report.py`、`plot_report.py`、`verify_evidence.py`、`package_evidence.py`。原始matrix和两份源码冻结位于本目录；汇总先写本机产物的publication目录，再复制批准的文件到仓库。失败事故原样保留供算法负责人分析，执行中不调整算法。

本次实际执行代码为`43156ed`，175个运行源码文件与两份冻结快照一致。第一次启动漏掉数据库准备步骤，未进入任何故障格；原始失败与清理记录保存在[startup-attempt-1](startup-attempt-1/)。恢复文档原有准备步骤后，从第1格完整执行60格，没有中断或补跑。该启动失败不计入方法尝试。

包装控制器的命令退出记录与预检丰富记录曾同名，执行时`preflight.json`被命令元数据覆盖；预检退出0、14项工具及真实往返成功的原始输出仍见[execution-receipts/preflight.txt](execution-receipts/preflight.txt)，本批matrix与事故记录未受影响。执行后已把未来命令收据改为独立的`*-command.json`命名，本批原始记录保持原样。

60格已结束，但从首个M0起共享验证通道失效，结果不能用于方法比较，详见[运行诊断](runtime-diagnostic/README.md)。最终独立健康窗口与停机成功。59份失败事故及1份通过事故均按原始字节保存；仓库只上传有用结果、脚本和诊断，本机私密配置与重复源码快照保留在产物目录。
