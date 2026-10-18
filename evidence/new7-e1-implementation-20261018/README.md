# NEW7 正式 E1-a 单次准备包（尚未执行）

已实现正式 AMQPS 的 E1-a `after_applied` 单次入口、历史截断及恢复载荷接口。28 项接口检查与 27 项 runner 检查均为离线验证；两组计数不作为跨套件去重后的总数。原 E3 的冻结源码和负面结果保持原样。

本机已生成独立私密计划与实验 worker bundle。计划只包含一次 F07、一次主库在 applied 后退出 83、备用库恢复与去重核对、连接池重建、正常关组及收尾健康验证。实际执行尚未获新授权。`execution-plan.json` 是安全投影，不能替代私密计划；`authorization-template.json` 的四项布尔值均为 false。

当前 8877 巡检实例正在使用相同 coordinator AIC。新授权后先确认该实例空闲，按所属 PID/nonce 正常 drain/close，再核对无同身份消费者与无活动/未知操作，才可填写新的绑定授权。不得仅把模板布尔值改为 true 来代替实际核对。

在本项目目录中，默认仅校验文件：

```powershell
.venv/Scripts/python.exe eval/platform_resume_experiment.py --plan artifacts/new7-e1-a-preparation-20261018-revision3/private-plan.json
```

只有完成新授权和上述交接条件后，才由本机负责人前台执行：

```powershell
.venv/Scripts/python.exe eval/platform_resume_experiment.py --plan artifacts/new7-e1-a-preparation-20261018-revision3/private-plan.json --execute --authorization-file <本机新授权文件> --approve-high
```

缺少或不匹配授权会在锁、实验输出、网络及 Docker 前拒绝。已有实验输出也会拒绝复用。执行时先核正常/实验 Compose 的未来镜像均为计划中的固定 ID，两处启动都禁止 build/pull；未确认 ownership 的 preflight 失败不会触发订单 H00。

协作者可审阅 canonical `eval/platform_resume_experiment.py`、`tests/test_platform_resume_experiment.py` 及 `source-hashes.json`，提出修改或复用 fake transport/controller 的离线测试。其他机器需自行建立私密身份、配置、明确 target、镜像和新的计划/证明，不能把本机哈希当作自己的部署验收。

本目录不含私密配置、凭据、证书、原始通信或模型内容。MCP 调用前意图不等于已发送；本例要求恰好一次主库调用与匹配返回、备用零调用，并另外核对 applied/退出标记。原任务 Processing 行保留，通过同操作的备用 resume 单独解释，不能声称原始日志已被改成 Completed。正常 close 的证据为 SDK 返回、本地状态和警告，不代表远端 broker ACL 全量盘点。

本机另外完成了一次真实只读 Compose/镜像预检：正常和实验配置的两库镜像与有限差分核对通过，未启动或停止容器。此前编码读取失败和 profiles 定义缺失两次失败均保留，分别以原始 bytes 捕获、仅 config 渲染启用全部 profiles 的窄修解决；实际实验运行仍为零。见 `future-compose-readonly.json`。
