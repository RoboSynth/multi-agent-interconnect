# 原域访问日志恢复与下一轮验证

`incident/recover_access.py` 提供不连接平台和资源工具的日志恢复入口。它只读取既有 bridge 配置中的身份、AMP 名称和目录，不打开 env、证书私钥或 MCP 服务。恢复前以只读方式要求原 SQLite 已有恰好一条匹配 AIC/规范日志路径的 owner 和原 attempts 表结构；空文件、缺 owner、目录或身份不同均拒绝，不能把新建 journal 当作恢复证据。

恢复只重放已经固化的不可变记录；真实请求曾进入但没有持久结果的，形成 `OutcomeUnconfirmed`，不填响应/耗时，不重执行业务。仍存活的独占 owner 会阻止恢复。既有内容冲突或半行仍由 durable emitter 保留并拒绝重放。

## 资源复原阶段的显式门

`eval/platform_resume_experiment.py --prepare ... --recover-access` 可将这一步加入新冻结计划与 effects。执行授权文件必须同时绑定新的 plan SHA 和严格布尔值 `recover_access: true`；旧计划默认路径不增加这一效果。

控制器先核实数据库 worker 原身份、镜像、只读 domain 挂载及归属，正常停止两个自有 worker，再次确认同容器 ID 且确实停止。恢复用一次性 `docker run --network none --read-only`：挂载原资源域的配置和**原 worker 同名 state 卷**，使用冻结镜像，只执行 `incident.recover_access`。两个身份分别处理各自日志，不能替另一身份制造接收端记录。资源域配置挂载中仍有本域证书文件；恢复程序不读取它们。

每个域的配置摘要、日志/journal 前后摘要、行数和未知结果数写入 `access-recovery.json`。恢复失败仍尝试启动正常 worker、恢复业务并执行 H00，但该例保留 `access_recovery_error_class`、判为失败，不借健康恢复改判日志门。

当前 E1 实验 worker 与普通数据库 worker都从同一份 `bridge.json` 读取 `platform.name` 和 `/state/amp-<role>`，并使用共享 state 卷内同一个日志/journal。目录并非天然分离；新步骤将这份路径绑定与恢复收据明确呈现。更换目录或 AIC 后不会自动扫描或接管旧 journal。

## 已完成的验证

- 新恢复入口 6 个方法通过，含真实临时 handler exit71、结果未知、append 后未确认、重复恢复字节相同、原归属/目录检查、活 owner 和空/无 owner 数据库拒绝。
- 控制器 5 个方法通过，含严格 plan/auth、停序、无网络原卷、恢复失败保留及拒绝另一个同项目 state 卷。
- 整例结果2个方法通过：两域恢复且健康才可成功；恢复日志失败时，资源复原与H00仍执行并通过，但整例保持失败。
- 65 个已有 E1 方法保持通过：首轮17项已过；52项因新检出缺少测试临时目录父目录而未进入主体，补齐后52项全过，其中48项属原方法。随后只重跑新分支受影响方法；不把各轮相加计数。
- 两个旧镜像/源码版本门通过；受限 Temp 读写失败原记录保留，正常临时目录环境中重跑通过。
- 新智能体镜像 `sha256:f91a92463cc29b39c55425e42115c81976183604911ee148e1f3a4ec7ab9ab3c` 已构建。无网络临时容器匹配19份关键源码和实际导入的SDK，在镜像内完成真实临时退出→未知结果恢复→再次恢复无重执行业务检查，实际exit0，容器已移除。

[运行原件与投影绑定](../evidence/current-source-validation-20261019/README.md)保留初轮失败、最终日志、镜像依赖清单与独立源码审阅。完整 SDK 的605项另见[当前组合套件](sdk_test_integration_20261019.md)，不与前述方法重复累计。

目前只有镜像和文件准备，没有启动七个正式身份、部署业务或执行新故障。下一轮拟验证一次 F10 与三个中断点各一次，必须使用新计划、新项目和本轮绑定镜像。原22例18/4、原复验12例11/1及缺18/12条access的冻结结果不变；平台 Monitor 入库、长期运行与新机器验收仍单独处理。
