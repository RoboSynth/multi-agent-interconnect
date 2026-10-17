# E3 平台调度评测入口

`eval/run.py` 复用同一套 M0、完整工具 M1 和 M2、故障期1rps业务流、审批、预算与30秒独立域验证。默认仍是本地 AIP stdio 与原生资源。新增正式平台入口仅支持明确的隔离容器目标；本次只完成离线实现与验证，未运行新版45格、模型请求或新平台群组。

本入口只接受`local-aip-stdio/native`与`wutong-amqps/docker`两种组合；其他组合在读取target、创建组或注入前拒绝。已有E1-c容器实验使用其独立runner，不受此限制影响。

## 调用与身份独占

证书、独立域worker及目标部署就绪后，由主代理另行安排真实运行。下列是待运行命令，输出目录必须全新：

```powershell
& .\.venv\Scripts\python.exe eval\run.py `
  --transport wutong-amqps --backend docker `
  --config runtime\private\new7-container-20261017\coordinator.json `
  --target-config runtime\private\new7-container-20261017\evaluator-target.json `
  --scenarios F01,F02,F06,F07,F10 --methods M0,M1,M2 --repeats 3 `
  --enable-llm --model-base-url http://127.0.0.1:8089/v1 --model Qwen3-1.7B-Q8_0 `
  --seed 42 --instance-seeds 101,202,303 --max-output-tokens 768 `
  --model-call-budget 40 --model-token-budget 65536 --task-budget 40 --deadline-seconds 600 `
  --approve-high --output eval\results\platform\E3-full-tools-45-new7
```

新版协调者AIC必须独占：8877工作台、`platform_smoke.py`、本评测器都会拥有Leader/Inbound，不能以同一AIC并行运行；参与者只有一个active group。真实顺序为 **smoke关闭 → E3唯一Leader矩阵并关闭 → 持久工作台/循环**。旧8767/T07使用旧AIC与180xx目标，和新版380xx分开。onboarding不加入本业务模型工具集或故障矩阵。

## 明确容器目标

`--target-config` 是只含路径和公开目标参数的JSON，不接受凭据字段。示例：

```json
{
  "schema_version": "incident-evaluator-target/1.0",
  "backend": "docker",
  "project": "incident-pilot-new7",
  "wsl_distro": "Ubuntu-22.04",
  "compose_files": ["deploy/compose.yml", "deploy/agents.yml", "deploy/new7.yml"],
  "env_file": "runtime/private/new7-container-20261017/compose.env",
  "route_file": "runtime/private/new7-container-20261017/nginx-runtime/route.conf",
  "ports": {"app_v1": 38081, "app_v2": 38082, "order": 38088}
}
```

路径可为项目相对路径或项目内部绝对路径；文件必须存在，解析后的路径不能越出项目。WSL路径转换为`/mnt/<drive>/...`并作为独立参数传递，支持目录空格。直接Docker执行时`wsl_distro`为null。

协调器只解析非秘密target描述。私有业务env解析、Docker inspect完整输出和Compose配置读取均在独立`eval/inject.py`进程中；inspect中的`Config.Env`不回传、不落普通证据。协调器只接收项目、端口、容器/image ID、路由匹配结果、卷名和Compose摘要。

平台群组创建之前，先验证schema与源码，再由独立注入器执行只读`H00 check`：核对四个业务服务与全部六个域服务、项目label、loopback端口、nginx与ops-agent的路由挂载，以及项目独立数据库卷。缺域、端口、卷或挂载不匹配就停止，不执行故障或创建平台组。目标observer URL自动取38088；显式传入不同URL会提前拒绝。该profile没有声明reply-drop端口，因此拒绝F12，避免落到其他目标的8090。

预检仅从固定`/domain/config.json`或`/domain/bridge.json`提取公开AIC、role和base_url，核对应用指向同网络`app-v2:8000`、验证指向`nginx:80`。协调配置的trusted/initial AIC必须与这些实际容器身份一致，数据库初选必须是主域；组建立后再核对实际selected身份与ops describe三字段`compose_project/compose_service/container_name`。因此旧参与者配置不能与新版380xx注入目标混用。域配置挂载必须只读，域服务必须处于该项目独立网络。

注入器之后每次都核对相同Compose摘要并重新核对目标，保持F01停止/启动、F02路由、F06应用角色锁、F07只读/连接池及F10复合动作的原逻辑。原生默认命令接口不变；独立`eval/inject.py`原有未传target的Docker调用仍保留，正式E3入口要求显式profile。

## 版本与证据

运行目录冻结业务、协调、Bridge、完整SDK Python源码、域policy/SQL及公开Compose/Dockerfile等关键输入。每格前检查摘要，变化后停止；私有config、证书、env和数据库不纳入源码快照。私有overlay的内容只由注入器读取并返回摘要，不复制给协调器。主备共享同一新数据库资源账本；新版资源使用独立term/ledger，不能清空旧资源账本来消除陈旧令牌。

平台worker由外部独立容器运行。首次预检会只读读取运行容器内`/srv`下12个固定关键源码SHA（Bridge、policy、partners、contract、platform worker、ops guard及SDK任务/账本/access路径），与宿主冻结摘要逐项比较，旧镜像直接拒绝。六域rootfs必须只读，禁止挂载覆盖`/srv`源码；后续相同container ID、image ID和`State.StartedAt`仅复用首次源码digest，变化则拒绝。每次重新读取公开AIC/role/base_url与初始proof比对；域容器重启也会拒绝，防止同ID重启后加载被host改过的私有env/policy。F01只停业务app-v2，允许其PID变化；E1接管使用独立runner。核验覆盖这些固定文件，不能称整个镜像/全部依赖都已验同；域私有配置和依赖构建仍保留各自部署来源证据。真实验收继续保留域AMP、AIP生命周期、实际MCP调用及receiver业务结果。未知操作仍交给既有账本核验，不盲目重试。

模型实际usage、HTTP失败、回退、审批等待与业务观测沿用原记录。`seconds`是协调及30秒验证总耗时，首次恢复是1rps采样估计；成功修改任务数与真实MCP调用数不同。新版完整工具M1与历史观察选择M1按`method_definition_id`分开统计，旧失败与旧PDF保持原证据截止。

相关离线检查使用`tests/test_eval_platform.py`与已有`tests/test_model_eval.py`，覆盖目标拒绝、命令与默认兼容、源码变化、组前失败、两种传输下三方法共用预算/流量/审批协议。fixture通过不算真实平台E3结果。
