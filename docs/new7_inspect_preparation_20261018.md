# NEW7 持续健康巡检：启动边界与待验收项

状态：启动准备方案，未作为8877首周期、登录/重启或长期运行验收记录。以下命令是未来由运行所有者执行的入口；启动前以本批真实E3闭合证据复核。

[后续三项优先工作](post_e3_priorities_20261018.md) · [正式E1适配](new7_e1_adaptation_20261018.md) · [协作任务清单](协作任务清单_20261018.md)

## 启动前必须确认

1. 本批E3监督及子进程真实退出，自有group/session正常close、client closed且无捕获清理warning。方法失败可以保留为CLOSED_WITH_FAILURES，不要求改写45/45恢复；资源已恢复、无未决操作且协调AIC释放后，才能进入巡检。
2. 公共38088为v2，独立H00至少30秒/10完整流程，failed/unknown/unresolved/pending为0，路由回到初始SHA。核清账本received/executing/unknown及未处理failed，不删账本或换namespace掩盖未知结果。
3. 8877空闲；本机与其它机器没有第二个新版coordinator AIC owner，六域无遗留active group。健康runner/E3的AIC锁不等于工作台启动器的全局锁。
4. 已有NEW7容器、证书和WSL保持就绪；保留其它已知实例与系统代理。先记录运行所有权，见[NEW7部署](../deploy/NEW7.md)。

## 配置与入口

由既有实例所有者在本机把**已核实的Windows E3协调配置**复制到独立私密位置，例如`runtime/private/new7-inspect-20261018/coordinator.json`，只显式覆盖：

```json
{"llm_enabled": false, "automatic_takeover": false}
```

保留leader、证书、信任、approval路径、持久term_journal/term_namespace、trusted/initial身份及五roles skills，数据库仍初选主域。不要重建权威term库，也不要用容器模板platform/coordinator.json替代Windows实际运行配置。仓库不分发该实例私钥或配置；新开发者自行生成私密材料，并安排独占AIC窗口。

工作台输出和scheduler state分别选新的固定目录，后续重启继续使用，保留未知派发对账。参考现有[schedule示例](../ops/schedule.example.json)，不要照搬旧8767的runtime/schedule或未适配目标。

以下两种工作台启动方式择一。只在子进程shell设置NO_PROXY，不更改系统代理，不加载compose.env：

```powershell
$env:NO_PROXY='wt.ioa.pub,127.0.0.1,localhost'
pwsh -NoProfile -File tools/start_workbench.ps1 -Port 8877 `
  -ConfigPath runtime/private/new7-inspect-20261018/coordinator.json `
  -OutputDirectory artifacts/new7-inspect-20261018
```

核API的mode=wutong-amqps、connected、实际config_sha256、resource_credential_count=0、model_config.enabled=false与身份；子进程环境名及资源凭据0分别留证。

现有隐藏启动器没有stop API；正常close发生在FastAPI lifespan退出，强制Stop-Process不等于正常close。需要可控完整收尾时，由所有者持有前台`workbench_server.py --port 8877 --config ... --output ...`，正常Ctrl+C/Uvicorn shutdown；不同时启动两种入口。

配置scheduler后复用[连续入口](../ops/run_startup.ps1)，首个真实周期即可用于验收，避免再起重复单次任务：

```powershell
pwsh -NoProfile -File ops/run_startup.ps1 `
  -ConfigPath runtime/private/new7-inspect-20261018/schedule.json `
  -LogDirectory runtime/private/new7-inspect-20261018/scheduler-launches
```

ScheduleLock按state目录拒绝第二实例，exit2。首周期立即inspect，其后按配置间隔；本预备方案为1800秒。若只验一次，用`ops/schedule.py --config <同一配置> --once inspect`代替连续入口，不同时运行两者。首周期应真实完成正常观察、域verification及30秒/10完整流程，记录act/model/审批的实际数量。

## 现有能力的限制

- **inspect不是严格只读。** 协调器遇异常可能执行write级route_rollback或pool_rebuild；high审批会停在operator_required，scheduler不自动同意。现配置不能一概禁止act，健康期须实际核act=0；“不注入故障”不等于“永不修改资源”。
- 不启用fault drills或allow-local。scheduler的drill注入器没有NEW7显式target支持，不能将本方案用于NEW7定时故障。
- llm_enabled=false关闭模型，automatic_takeover=false关闭自动接管。域离线或资源异常按人工流程保留证据，不自动改冻结评测。
- [登录启动入口](windows_startup.md)默认仅准备XML/摘要；真实注册、登录、重启另验。注册任务也只启动scheduler，不会启动WSL/Docker/域/工作台。

## 收尾与长期证据

先停止scheduler派发，保留active/next_due及事件，等待或核清当前incident、审批和unknown，再正常关闭唯一工作台。分别验证scheduler实际退出/锁释放、client与自有group关闭、清理warning、资源状态和公共v2健康；进程退出、任务注销、远端group关闭是不同事实。

记录首周期与自然后续周期的UTC起止、任务/产物、业务窗口和中断。keep_awake只是进程的Windows唤醒请求，现有WSL保持辅助也不是登录服务；短时在线不证明24小时或7×24。七身份心跳、Monitor入库和重启恢复分别验收，旧8767/T07的历史周期不证明其当前仍存活。
