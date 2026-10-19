# 12例复验：结果与日志证据入口

本批按新计划实际执行12例，11通过、1失败。原22例的18通过/4失败继续保留为独立批次。

- [逐例结果与判据](summary.json)、[两阶段终态及最终停止](closure-and-recovery.json)、[原件摘要绑定](source-inputs.json)。
- [full_history首例诊断与运行补证、第二例独立复核](diagnostics/README.md)。首例在重新发现阶段记录ConnectError，没有发送resume；实际主容器退出码仍未知。第二、三例正式通过，不能据此改写首例。
- [闭合访问和凭据检查](closed-access-credentials.json)：158个Start，预期316条access，实际304条，每例缺1条，共12条；多余0。T05=false。133文件、73项已知值的raw/decoded命中与解析错误均0，捕获覆盖完整。
- [六域36份日志快照清单](domain-snapshot-manifest.json)、[采集失败和后续成功的真实进程/命令收据](collection-attempts.json)、[挂载顺序只读诊断](collection-diagnosis.json)、[日志发表投影绑定](log-publication-inputs.json)。原日志保留本机原字节；仓库提供结果投影和摘要，不包含消息正文或凭证。
- [Kafka/Monitor官方资料查证](official-config-check/official-monitor-config-check-20261019.md)。实际平台接入参数仍未取得。

首次日志采集的14条Docker命令均成功，但末尾identity比较失败；原失败保留。新两次只读inspect观察到mount数组顺序变化；它们不能重建首次未保存的原inspect数组。v2仅按Destination排序比较完整mount字典，再次采集和身份核验成功。这里的采集重试没有执行任何故障案例。

`staging-manifest.json`绑定正式结果采集器最初产出的6份材料；诊断和日志材料各有独立投影索引。`tooling/`保留真实使用的采集与对账入口及旧版本，固定来源和原始失败不覆盖。最终自有项目剩余运行容器0，Compose stop和keeper均实际exit0，卷和全部原记录保留。

这批结果不解除旧T05缺端、未知订单阶段、Kafka/Monitor、新机器、长期稳定性及最终交付材料等剩余任务。12页技术报告修订二仍以412f791为证据截止，未纳入本批结果。

发表tooling中的Windows路径转换采用标准路径解析；原执行源码不变。原件SHA与发表副本SHA分别绑定，内部工具SHA更新为发表副本值，详见[工具可移植性投影记录](tooling-portable-publication.json)。
