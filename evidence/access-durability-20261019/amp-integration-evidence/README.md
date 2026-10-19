# AmpRuntime最小集成验证

当前20个不同方法通过：修订后复跑18项，加2项输入未变的已通过检查。`summary-v2.json` SHA256为`577948172516570f82713731aeb66711405b3ce8a113843fbc14a3f68bac0b94`，逐文件绑定本批实际产品与测试源码。

| 范围 | 方法数 | 当前证据 |
| --- | ---: | --- |
| `tests/test_platform_worker.py` | 10 | `run-2/platform-worker.log`，0失败/0错误 |
| `tests/test_bridge_platform_preparation.py` | 7 | `run-2/bridge-preparation.log`，0失败/0错误 |
| `test_coordinator.py`的AmpRuntime start/stop | 1 | 复用`run-1/amp-start-stop.log`；产品及对应测试字节未变 |
| `test_f12_target.py`源码版本绑定门 | 1 | `run-2/domain-source-members.log`；缺失fingerprint与逐文件旧image源码拒绝，包括durable_access/amp_setup |
| `test_eval_platform.py`旧源码拒绝与稳定image摘要复用 | 1 | 复用`run-1/domain-source-rejection.log`；产品及对应测试字节未变 |

首轮实际OS exit1（tool chunk `5cb80f`）：worker10项中有1个旧任务数断言失败（仍预期2，实际3），另有5条Temp cleanup错误，原因是fixture未关闭新SQLite outbox。该轮其他选择已过。修订后受影响18项实际exit0（chunk `73f6c7`）；没有将两轮相加成38个独特测试。

仅修改三份测试：worker增加`asyncTearDown`，在Temp清理前真正调用`amp.close()`，任务数断言更新为3；bridge fixture用`try/finally`真正close；F12版本门把新增durable access和AmpRuntime源码纳入必须与逐文件stale拒绝验证。未忽略cleanup错误或修改产品语义。

首轮遗留5个目录严格从原失败日志提取、核实为系统Temp的直接子目录，并记录库存后清理；实际删除5、剩余0，失败日志保留，见`initial-fixture-temp-cleanup.json`。`summary.json`是清理前的历史截面，最终读`summary-v2.json`。

所有检查均为临时自签证书、SQLite、broker/resource double；Windows asyncio使用允许本机自唤醒的执行环境。未启动真实业务、平台、Docker或模型，也未重复根代理的SDK durable或resumable验证。结果不代替T05真实平台流量对账。
