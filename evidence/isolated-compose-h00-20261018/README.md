# 隔离 Compose H00 实测（2026-10-18）

固定团队提交 `5b774525bea037bd8f4bf87959c29f4f3b8b8765` 的新检出，原 `deploy/up.ps1` 未修改；Windows 入口实际走现有 Ubuntu-22.04/WSL Docker。独立项目 `incident-pilot-h00-20261018`、127.0.0.1:48081/48082/48088、新 PostgreSQL 卷和独立 v2 路由实际启动成功。

同一轮验证前后公共 `/ready` 均为 v2；30.016 秒、30 次成功请求、10 个创建→查询→取消流程，失败、未知和未决均为 0。随后仅正常停止本轮四个容器，网络和数据库卷保留，新端口已关闭；原 25 个容器的 ID/StartedAt/重启数/状态与原 8766、8877、8089 监听 PID 保持。

首次入口执行在读取旧容器元数据时失败，`up_invoked=false`；修正仅作用于本地证据 helper，对没有 Health 的容器安全读取，并先通过只读校验。首失败及修正验证的来源、实际外层退出码与校验 hash 保留在 summary/source-inputs；原始本地记录完整保留。

这是已有镜像与构建缓存的同机独立项目验收。阶段耗时不能当作全新机器 15 分钟冷部署结果。本轮无故障注入、正式身份/MCP/模型调用或 E1 接管实验。

## 团队复现

选择自己的新项目名和三个未占用回环端口；从 `environment.example` 生成本机私密 env，填写三项互不相同的随机凭据。不要复用本机保留的数据库卷、现有项目名或其他人的凭据。使用项目原入口，保持 Agents/onboarding/faults 关闭，并先确认环境未覆盖 Compose/Docker 目标：

```powershell
pwsh -NoProfile -File deploy/up.ps1 -EnvFile runtime/private/h00.env -ProjectName incident-pilot-h00-yourname -WslDistro Ubuntu-22.04
```

业务验证应传 `expected_api_version='v2'`；当前 `business/load.py` CLI 默认没有开启这个可选契约检查。以下逻辑在新脚本中运行并把结果保存到新文件，不覆盖旧结果：

```python
import asyncio, json
from pathlib import Path
from business.load import OrderObserver
r = asyncio.run(OrderObserver('http://127.0.0.1:48088', seed=17,
    expected_api_version='v2').observe(duration=30, requests_per_second=1, min_complete=10))
Path('h00-new.json').write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
assert r['passed'] and r['requests'] == r['success'] == 30 and r['completed_workflows'] == 10
assert r['failed'] == r['unknown'] == r['unresolved_intents'] == 0 and not r['state']['pending']
```

另记录观察前后的公共 `/ready` 为 v2。结束时按本轮实际新容器 ID 和项目标签正常停止；保留卷/网络，不对其他项目执行停止或清场。这里的 `h00.json`、`ready.json` 为原始业务记录字节，三个阶段结果附真实外层退出码；selected-build-output 只提取构建相关行并替换两个精确 checkout 路径前缀，计数见 summary。
