# 今晚计划的 Windows 验证与上线准备（2026-10-19）

本轮针对 `docs/接下来的行动_20261019.md` 新增的日志类型选择、批次租约与10分钟巡检做 Windows 验证。原 Linux 报告的51项在 Windows 首轮通过；发现并修复上线入口问题后，本轮共有72项不同测试通过：collector 33、租约/批次20、调度/启动/状态14、日志扫描5，计数不重复累加重跑。

## 修正与结果

- `run.ps1` 默认解释器在团队 checkout 中不存在：新增可显式指定的 `-PythonExecutable`，实际 PowerShell `-CheckOnly` 传参检查通过，保留首次失败。
- Linux collector 的分阶段计划改为记录所选日志类型、实际输出数和路由。扩类型保留已有 offset；新类型只有无旧 offset 且 `Read_From_Head False` 时才从新行开始。
- `secret_scan.py` 补上 JSON/JSONL 解析、读取错误和空扫描失败检查；扫描结果不回显日志内容，CLI 遇到坏行会非零退出。5项测试通过，真实新部署日志仍须单独扫描；规则命中为零不等于证明任意敏感文字均不存在。
- 批次取消测试确认失败与剩余未执行例保留、身份持久隔离、OS锁释放，巡检不会在未知清理状态下恢复。
- NEW7 受管启动默认10分钟的两处旧文案已修正，旧 scheduler 的30分钟兼容默认保留。

详细记录：[collector](collector/README.md)、[lease](lease/README.md)、[readiness](readiness/README.md)、[根检查](root-checks.json)。此前其他 P1–P6 验证记录继续见[技术方案本地落实](../technical-plan-local-20261019/progress.md)。

## 运行与提交边界

WSL Ubuntu-22.04、Docker Linux daemon 和 Compose 已只读确认可用；七身份本地证书有效期、clientAuth、私钥匹配与TLS材料加载检查均通过，远端认证尚未尝试。已为独立项目 `incident-pilot-new7-tech-20261019` 准备新manifest，端口38081/38082/38088/38090；Compose静态校验、两业务应用镜像和共享智能体镜像构建均成功，见[构建摘要](deployment-prepared/summary.json)。

三份10分钟受管巡检登录任务文件已生成但未注册，身份锁显式复用原 `incident-pilot` 的ownership目录；heartbeat+access与六类日志两阶段collector配置也已生成，均默认不补发历史。详见 `startup-prepared.json`、`collector-prepared.json`、`certificate-material-check.json`；Windows Fluent Bit v5.1.3可执行，官方固定摘要的Linux镜像已在本机缓存，尚未用它采集或发送日志。

建议分支为 `tech-plan-20261019`，待提交文件的本地快照见 `git-candidate-inventory.json`；它不是已冻结的提交。尚未提交/推送、部署消费者、发送 Kafka 日志、注册自启或启动24小时计时，后续4例/60次/15次实验也未运行。

计划末尾的授权段落仍是待确认模板。实际开始第一阶段时按顺序记录新分支推送、健康窗口、六类日志扫描、协调者 heartbeat+access、七来源、六类输出、巡检与三个登录任务；Discovery在线只证明心跳状态同步，access入库仍需平台管理员确认。不得用历史状态充当本次运行结果。

切换到Linux七来源前须先正常停止自有Windows协调者collector，避免同时读取相同日志；首次Kafka仅采新行还要确认offset状态全新，不能复用旧offset后声称未补发。GitHub `main`只读访问成功，HEAD仍为 `2a401c6`；实际写权限由后续获准推送结果验证。
