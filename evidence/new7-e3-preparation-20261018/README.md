# NEW7 E3 45格协议审阅包（未执行）

本包供团队审阅、排障和提出修改。45格为F01/F02/F06/F07/F10 × M0/M1/M2 × 3，精确顺序见 [plan.json](plan.json)。目标隔离项目及380xx端口见 [target.json](target.json)，157份源码SHA见 [source-hashes.json](source-hashes.json)，离线入口与模型守门fixture结果见 [offline-checks.json](offline-checks.json)。包装器源码及节点前提见 [wrappers/README.md](wrappers/README.md)。

当前只有准备和离线检查；新45次故障尚未获得授权。旧本地45次授权已使用，历史失败及中断不被这份新计划替换。后续真实授权必须另存，绑定最终本地plan/source-ready SHA；[authorization-template.json](authorization-template.json)不是授权。不得凭此包注入故障或创建平台组。

M0固定观察、不调用模型。M1为free-tools-v1，不规则兜底；M2为evidence-ranked-v1，披露规则回退。M1/M2同用本机Qwen3-1.7B-Q8_0、32768单槽、seed42、temperature0、top_p1、max_output768、每格40次调用/65536 tokens/40任务/600秒。顺序按重复轮换M0/M1/M2、M1/M2/M0、M2/M0/M1，workload seed101/202/303，预处理连接池次数0/1/2。

旧上下文为8192，曾有10422-token请求被拒绝。本轮将M1/M2共同升至32768，是明确容量协议变化，不作为完全相同容量条件下的新旧直接比较。一次由旧封存record8重建的容量请求实际HTTP200、schema valid、10422+32=10454 tokens、5.172秒；旧原始HTTP字节未保存。首次GET失败/0POST也保留。这一单次容量检查不是E3方法表现、恢复或NEW7健康模型调用证据，未派发工具。

未来本地显式模型启动使用：

```powershell
& .\.venv\Scripts\python.exe tools/local_model.py start --context-size 32768
```

兼容默认仍是8192。准备入口默认仅检查文件、不访问网络；实际执行必须先验证新的精确授权，再用无代理且禁止重定向的GET核对 `/props`、`/slots`、`/v1/models` 的同alias、32768、单空闲槽、权重路径与绑定PID，随后才能建立输出和启动eval。此包的PID4272及freeze属于当前开发节点，其他机器需要重新准备自己的身份/配置/证据。

45次apply仅作用于incident-pilot-new7隔离资源：F01停止/恢复新app-v2，F02切新路由，F06订单事务锁，F07新应用角色只读及连接池，F10路由与只读组合。每格先后尝试restore，`--approve-high`仅为既有固定实验修复工具。自动接管统一关闭，不加入成员退出/接管故障。route是故障及恢复允许变化的运行文件，按前后SHA单列；其它静态配置必须不变。

恢复分子只使用独立continuous_recovery_confirmed；status completed不等于恢复。保持45键/顺序/seed/预算和原始失败。矩阵后独立HTTP H00至少30秒/10流程，不进入故障恢复分母。监督保留真实Popen.wait、正常群组close及SDK清理warning；不自动重跑、补格、重注入或冒充Broker/ACL库存验证。执行输出目录一旦存在即拒绝复用。

本包不含私密配置、env、证书密钥、真实授权、模型二进制、原始prompt/response或群组流量。团队可优先复核目标归属、方法公平性、恢复分母、fresh guard顺序和异常闭合，并提交具体源码修订建议。
