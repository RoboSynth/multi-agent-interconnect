# 本批四计划正式复验：结果归档

本批准备4项，实际尝试3项：**F10/M0通过1项，E1-a失败2项，最后after_applied未尝试1项**。模型调用0。计数以四份绑定计划及三份individual receipt为准，外层执行实际退出码1。原aggregate仅收前两例；第三例的清理守卫抛异常后未append，不能据aggregate误写为只尝试两例。原件保持不变，投影与原件SHA映射见`original-sha-map.json`。

| 例项 | 结果 | 实际达到阶段 | 最后独立H00 |
| --- | --- | --- | --- |
| F10/M0 | completed，exit0 | 复合故障与修复，平台通信 | 30.016秒，30请求成功，10完整流程 |
| E1-a after_observation | failed，exit1 | group-create ConnectTimeout；未到中断点 | 30秒，30请求成功，10完整流程 |
| E1-a before_modification | failed，exit1 | 发现后invite ConnectError；close也ConnectError，未到中断点 | 30秒，30请求成功，10完整流程 |
| E1-a after_applied | not_attempted | 上一例清理守卫停止后续；无receipt/结果目录 | unknown |

两个E1 coordinator journal均以`mode=ro&immutable=1`读取，所有表计数0，products为空，没有执行到声明的主智能体中断点，不能据此宣称接续恢复通过。该查询前后数据库与既有sidecar的SHA和大小相同。数据库access恢复记录中的6行属于F10后共享卷已有记录，两个E1恢复前后log/journal SHA均相同；这是保留既有记录的证据，不是本E1新生成6行。备库access为0；不追补旧批次缺失日志。

本批自有10容器经两次身份核实后实际停止，after快照running=0；卷保留。keeper实际exit0。before_modification留下的`group-incident-cef7f4c704374de1a376eab9ed086e60`正常SDK关闭由另一任务单独处理，本归档暂标pending；最终清理收据需另附，不能回改原失败及原close错误。

`source-bindings.json`保留冻结提交、166份源码SHA、两镜像ID、4份计划及授权绑定；三例各166份冻结副本逐一相符。授权原JSON以原始字节直接解析，原文与会话实际回复逐字符一致，`authorization-recorded.json`保留原值，`authorization-verification.json`记录核验。

发布内容仅为显式白名单：结果、H00全部30步的阶段/耗时/HTTP状态、case内生命周期事件和AMP的有用信封/状态/计时字段、恢复记录、原件SHA及自有停机快照。原始私密config、SQLite、stdout/stderr.bin、命令输出、业务正文、任意系统description和签名均未复制；AMP投影不用于密码学验签。全部取自本批文件，没有拼接长窗口或旧22/12数据。`publication-files.json`提供精确源与仓库目标映射，父任务上传前仍需完整库存扫描。

本目录由只读归档脚本产生，没有启动资源、平台、模型或故障；未尝试最后一例。新的补充清理证据应独立追加并保留本次pending快照。
