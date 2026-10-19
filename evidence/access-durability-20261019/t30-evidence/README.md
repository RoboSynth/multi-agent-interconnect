# T30：独立协调 fixture 进程重启验证

两个新增行为用例实际通过（`targeted-run-5.log/json`，2项、6.120秒、OS exit0）；原有同进程重开TaskJournal用例仍保持原字节，并独立实际通过（`original-restart-run-1.log/json`，1项、0.269秒、exit0）。未重跑无关完整suite。

新增源码位于本批checkout的：

- `vendor/ACPs-community/acps-sdk/tests/resumable/test_coordinator_process.py`
- `vendor/ACPs-community/acps-sdk/tests/resumable/fixtures/coordinator_process.py`

fixture使用真实公开`ResumableGroupLeader`、`TaskJournal`、`CoordinatorTerm`和TaskResult监听回调；传输端是明确的离线double，没有AMQPS、资源工具或模型调用。每例先通过wrapper写入开始/继续、多参与者、完成和发送结果未知的记录，再写持久ready握手。

| 实际方式 | writer exit | 全新reader exit | 恢复结果 |
| --- | --- | --- | --- |
| fixture主动`os._exit(37)` | 37 | 0 | 5条尝试、3条当前在途、13条事件原样；任期1→2 |
| 父进程收到durable-ready后终止自己持有handle的live writer | 1（Windows实际值） | 0 | 同上 |

每例核对全部尝试与事件的精确前后快照，已完成任务不进入在途集，同逻辑任务的旧尝试保留历史但不重复列为当前在途，delivery_unknown不冒充失败或完成。新进程重新构造wrapper/journal后没有发送或重放任务，旧尝试仍保留原任期1。Python finally标记两例均未出现。子解释器直接使用当前Python的base executable，并显式携带当前依赖搜索路径，避免Windows venv launcher与真实子解释器分离。

`summary.json`绑定5份实际使用源码及两例原始JSON收据；SHA256为`6d5d30b224658a0734c9347f98b38d181bea51c3f8c95087633bc30f81bfb2ef`。`fixture-process-inspection-final.json`使用既有Windows原生进程查询，按本批精确fixture脚本路径检查：剩余匹配0，检查本身未终止任何进程。canonical仍为clean `d8ae1958aef411c61742f57ddb96e0de453ec885`，尚未集成本批新增测试。

受限执行器中的首轮suite中断和run2–4失败均保留；第一条fixture曾报SQLite打开失败，后续seed超时；direct recover成功。随后仅提高本机asyncio执行所需权限，新两项和原一项通过。旧失败不改判，也不据这些现象推定产品故障根因。成功运行的stdout阶段点及实际child退出码在`run-5/`收据中。

验证覆盖临时离线协调进程的持久任务恢复，不代表真实平台GroupLeader被杀后的群组重连验收，也不代表P1 T33完整事故续跑。没有启动业务、平台、模型、Docker或网络服务；T05由根代理独立处理。

开发者可在自己的环境直接运行新两项：

```text
python -B -m unittest discover -s vendor/ACPs-community/acps-sdk/tests/resumable -p test_coordinator_process.py -v
```

如需保留合成任务、SQLite与过程收据，将`INCIDENT_T30_EVIDENCE_DIR`设为新的输出目录；已有目录不会覆盖。Windows环境需要允许asyncio创建本机自唤醒通道。
