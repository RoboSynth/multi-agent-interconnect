# 本地模型工作台启用与验收（2026-10-18）

工作台复用既有诊断引擎，显式选择本机 Qwen。首次生成配置默认关闭模型；普通重跑保留已选 endpoint、模型和预算，不从外部 API 自动补位。

## 启用

先按已有模型部署准备本机 `http://127.0.0.1:8089/v1` 服务，模型名为 `Qwen3-1.7B-Q8_0`。`local-up` 不下载权重或启动模型。已有业务底座时，只配置和启动工作台：

```powershell
.\.venv\Scripts\python.exe tools/configure_local_coordinator.py --enable-llm
pwsh -NoProfile -File tools/start_workbench.ps1
```

也可显式指定本机模型与预算：

```powershell
.\.venv\Scripts\python.exe tools/configure_local_coordinator.py --enable-llm --model-base-url http://127.0.0.1:8089/v1 --model Qwen3-1.7B-Q8_0 --max-output-tokens 768 --model-call-budget 40 --model-token-budget 65536 --model-timeout-seconds 60
```

`--config <路径>` 可选其他配置；`--check` 仅校验、不写入。默认配置文件为 `runtime/local-coordinator.json`。启用时要求持久化模型名、本机回环 HTTP 地址和合法预算；缺失配置、外部地址、地址凭据或非法预算在写文件/启动前报错。本地模型调用不附带 API key；正式 `wutong` 配置保留原语义。

从项目根使用完整准备入口：

```powershell
# 先准备 Python 3.12 项目 .venv；首次需要安装依赖时加 -Install。
pwsh -NoProfile -File deploy/local-up.ps1 -EnableLocalModel
```

## 重跑与旧实例

不传模型选项的 `configure_local_coordinator.py` 或普通 `local-up.ps1` 保留用户选择；配置语义未变时保留原始字节。显式关闭使用 `--disable-llm`，仍需让工作台重新加载配置。

工作台启动器核对 `/api/state` 的完整配置原始字节 SHA、模式、连接和实际进程身份。旧实例没有加载所选配置时会明确拒绝，不会把旧进程误认为新配置已生效。保存旧运行记录，确认无运行中事故或待审批任务后，按已有 PID、创建时间、父子关系及项目命令行受控关闭旧工作台，再重试启动；保留原 journal、事故历史与日志。

Windows `.venv` Python 可能重定向为直接子 Python 进程。启动器核实同 PID 或指定解释器及完整参数一致的直接子进程，并分别记录 launcher/runtime PID，避免把正常重定向误判为端口冒占。

## 本轮实际结果

本轮只在既有开发环境中受控重启工作台；原公共业务、数据库、运维和模型服务继续运行。加载后 local AIP stdio 模式、5 个参与者、资源凭据 0、完整配置 SHA 与实际进程身份均通过。

通过独立无头浏览器填写健康症状并点击一次开始，事故 `inc-9cae7c3861bf408b` 完成：

- 6 次真实模型请求均为 HTTP 200，6 次输出通过校验；实际来源 `llm`，7098 tokens，使用量记录完整。
- 零 `act` 修改任务；独立业务窗口 30.015 秒，30 次请求全部成功、10 个完整订单流程，失败、未知和待决意图均为 0。
- 14 项真实浏览器检查通过，桌面/手机页面均无横向溢出；另用独立页面合成数据通过 10 项展示检查，包括规则回退、部分 token 用量、旧统计缺失及模型名称按文本显示。

[结果与来源摘要](../evidence/local-model-workbench-20261018/results.json)、[真实页面检查](../evidence/local-model-workbench-20261018/real-ui-checks.json)、[合成展示检查](../evidence/local-model-workbench-20261018/synthetic-ui-checks.json)分别保存。四图：[真实桌面](../evidence/local-model-workbench-20261018/desktop-real-healthy.png)、[真实手机](../evidence/local-model-workbench-20261018/mobile-real-healthy.png)、[合成回退/部分用量](../evidence/local-model-workbench-20261018/synthetic-fallback-partial-usage.png)、[合成旧统计缺失](../evidence/local-model-workbench-20261018/synthetic-legacy-missing-metrics.png)。合成图不代表新增真实模型失败或故障实验。

“已启用模型”只说明配置；实际参与应查看每次事故的来源、调用数、token 完整性和回退记录。缺失用量显示未记录，旧调用数缺失显示待统计，不以 0 填充。

## 离线边界与待验收项

| 范围 | 已有适用检查 | 证据含义 |
| --- | --- | --- |
| 数据库初始化与 ZIP 缓存 | 9 项，8+1 分轮通过 | 既有集群缺身份文件先拒绝；保留选定运行路径；缓存/下载 ZIP 验证与失败证据保留。仅合成临时目录，无真实数据库、下载或私密配置访问。 |
| 启动入口与进程身份 | 12 项，9 项当前 launcher + 3 项既有入口复用 | 配置及连接门、Python 重定向直接子身份与错误拒绝；隔离 stub。 |
| 模型持久配置与工作台 | 12 项不同相关检查，含 9 项新增与 3 项既有 | fake transport/TestClient/临时配置；11、3、2 为有交叠的执行批次，不相加。 |

本轮没有重跑完整 `local-up`、初始化数据库或下载依赖，不是新机器 15 分钟/T96 冷部署证明；实际健康事故也不补作新的故障对照或改写此前 45 格中断记录。

2026-10-17 证书曾按用户安排暂缓；2026-10-18 新授权后七新版角色各实际签发一次，官方 CLI 全 exit 0，CN/AIC、有效期、clientAuth 和密钥匹配检查通过，分别在 2026-12-06 对应时刻到期。七个新版 AIC 的官方 ADP 只读元数据与端点核对已通过；新版 AMQPS describe/任务往返与完整恢复尚未运行，见[隔离部署计划](../deploy/NEW7.md)。本页健康验收使用本地 stdio。
