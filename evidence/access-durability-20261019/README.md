# Access 持久化与进程恢复：离线实现证据

本轮基于 `d8ae1958aef411c61742f57ddb96e0de453ec885`，完成访问日志 durable outbox、协调者独立进程恢复夹具，以及原生停止入口的失败返回修正。当前结论是**已实现并完成下表本地验证，未部署到平台验收镜像**。产品接入与恢复方式见[使用说明](../../docs/access_durability_20261019.md)。

| 验证组 | 最终实际结果 | 主要记录 |
| --- | --- | --- |
| Durable access | 17项通过，进程 exit0 | [最终日志](durable-tests-final.log.txt)、[源码与执行绑定](source-ready.json) |
| 原 GroupLeader/Partner | 8项通过，exit0 | [原集成日志](legacy-group-tests.log.txt) |
| AMP 项目接入 | 20个不同方法通过；18项复跑、2项输入未变复用 | [最终摘要](amp-integration-evidence/summary-v2.json)、[解释](amp-integration-evidence/README.md) |
| 协调者任务恢复 | 新2项、原相关1项通过，exit0 | [摘要](t30-evidence/summary.json)、[过程与边界](t30-evidence/README.md) |
| 原生停止入口 | 修前6项中2失败；修后6项全过 | [摘要](native-stop-evidence/summary.json)、[日志说明](native-stop-evidence/README.md) |

新发射器在进入回调前持久化真实请求元数据与稳定 logId，结果形成后冻结完整记录，再追加 JSONL、fsync、确认。进程在结果形成前退出时，下一 owner 仅恢复 `OutcomeUnconfirmed`，不捏造响应、耗时或业务成功，不重执行业务。已形成记录原样重放，同 ID 不改正文；同一 journal 的跨进程独占和线程串行保护写入。最终17项日志有一次约0.11秒的 asyncio 慢回调提示；本轮没有性能提升结论。

临时 Python 退出覆盖 handler、ready、append、确认前及 fsync 窗口，并由全新进程恢复。T30 使用真实公开 SDK wrapper/journal，但传输为明确的离线 double；writer 自退出37或被其父进程终止（Windows实测exit1），新reader exit0，两例各恢复5次尝试、3项在途、13条事件，任期1→2且没有重发任务。它不证明真实平台群组重连、整机断电或 P1 完整事故续跑。原生停止验证使用命令夹具，完整 native 启动/H00/停止仍待运行。

## 历史失败保留

- Durable 首次受限 asyncio 检查中断，未形成完整判定；[观察记录](durable-tests-attempt1-observation.json)与空日志保留。第二次7个 teardown 错误源于测试辅助连接未关闭，改为真正关闭后16项通过，随后跨进程独占检查通过，最终当前17项一起通过；不将这些轮次相加为更多独特测试。
- AMP 首轮旧2-task断言和5条目录清理错误保留在 `run-1/`。测试收尾真正关闭 outbox、断言改为3任务后，受影响18项通过；原通过且字节未变的2项复用。5个遗留目录的精确库存与清理收据保留。
- T30 受限环境的中断、SQLite打开错误与seed超时保留；允许本机 asyncio 自唤醒后，两个新方法和原相关方法通过。没有把旧失败重写成通过。
- 原生停止入口先复现 Nginx/PG 命令失败仍成功返回的2个失败，再修正退出码检查；修前与修后日志并存。

原正式22例仍为18通过/4失败、缺18条access；已完成的修复复验12例仍为11通过/1失败、缺12条access。本轮没有回填旧日志、改判实验、启动七个身份或执行新故障。新源码后续正式验收必须重新绑定镜像，并显式恢复实验所属域的**原日志路径和原journal**；正常worker的另一目录不会替实验worker补日志。E1-b两批数据与图见[独立对照包](../e1b-comparison-20261019/README.md)。

## 原件、投影与复核

[publication-bindings.json](publication-bindings.json)逐文件列出本地原件和仓库投影的SHA-256、字节数与是否投影。局部本机路径改为 `[project]`、`[batch]`、`[canonical]`、`[python-runtime]`、`[test-venv]`、`[system-temp]`、`[local-venv]`、`[workspace]`；源码审阅链接转为已审基线的固定GitHub链接或仓库相对链接。它们是资料定位占位符，不是可以直接执行的路径。原件仍留本地，没有复制SQLite数据库。摘要内既有hash绑定的是**原件**，读取仓库文件时应经publication-bindings核对投影hash。

[source-ready.json](source-ready.json)绑定当时测试使用的15份产品/测试源码，以及各组检查日志和摘要。它在随后文档、图表入库前生成，不是整个最终Git树的清单。最后新增跨进程owner测试之后，最终17项所用测试字节以该文件为准；[源码复核](review/code-review.md)保持此前实际审阅的测试hash与时间。

[final-source-bindings.json](final-source-bindings.json)另列测试后到发布时的源码映射：14份字节一致；仅T30测试的源码hash键将手工分隔符替换改为标准`Path.as_posix()`，仍是相同的相对POSIX路径。该纯路径格式写法经过静态核对，没有重跑行为检查，也没有改写历史运行所绑定的hash。[publication-scan-r2.json](publication-scan-r2.json)保留发布过程中94文件扫描通过的截面（73个已知值、0命中、0解析错误）；它早于本段与最终映射文件，完整提交范围的最后扫描收据保存在本地batch。

独立审阅：[协议语义](review/semantic-review.md)、[初审](review/code-review-r1.md)、[修正后复核](review/code-review.md)、[部署边界](review/deployment-review.md)。[P0缺口审计](review/current-p0-gaps.md)的截止基线为本轮改动前的d8ae195；不要把它当作本轮之后的实时状态。

[fixture-process-closure.json](fixture-process-closure.json)记录按精确fixture路径的只读进程检查：378个枚举、205个可读，0个匹配；172个拒绝访问、1个已消失未分类。此检查早于最终17项，最终套件子进程另由其原handle收尾；不能据此声称全主机进程均已检查。没有为了整理证据再启动业务或平台服务。

投影脚本见[tooling/publish_evidence.py](tooling/publish_evidence.py)，需要显式传入保留的本地batch、checkout、canonical与路径映射。协作者复跑行为检查应使用源码中的tests与自己的临时输出目录，不应运行历史清理脚本或把占位路径当配置。Kafka/TLS和Monitor入库、新机器部署、长期运行与最终展示材料仍未完成。
