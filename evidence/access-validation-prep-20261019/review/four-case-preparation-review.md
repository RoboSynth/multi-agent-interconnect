# 新四例正式验收准备：独立只读审阅

审阅时间：2026-10-19T08:58:10.087963+00:00。结论：**最终修订3未见阻断发布的发现；四例尚未获本批执行授权，不得执行。**

## 范围与已修发现

审阅 `plan-preparation/batch_scope.py`、`prepare_bound_plans.py`、`run_authorized.py`、`run_f10.py`、新run-scope，以及所调用的冻结产品关闭/结果路径。源码截止为 `a4d71e83444228a71499a75c932a2b9e7ba678f1`。本次仅阅读代码、原收据及计算文件/Git对象哈希，没有运行测试、Docker/WSL、平台身份、业务、模型或真实故障，没有修改checkout。

初审发现同ID容器的StartedAt前移可被原`match_registered`接纳；这会让外部重启后的容器进入最终停机集合。最终修订3改成ID/project/service/image/Created/StartedAt逐字段精确相等；只有`restored_registration`根据该子例原ID与恢复ID收据接纳数据库新ID。原风险已修。读取的`guard-start-identity-r4.log`记录3个定向mock方法通过，其中含同ID外部重启拒绝及合法数据库替换对照；本审阅未重跑它们，旧摘要和日志仍保留。

## 执行与结束边界

- 默认三个入口仅文件校验或显式准备；`run_authorized.py`、`run_f10.py`未带`--execute`不会进入资源动作。执行必须提供独立的新batch授权文件，严格绑定当前prepared-summary SHA、4个plan SHA/aggregate、源码提交、project、明确布尔effects和本批用户问题/回答。旧12授权因schema/字段/新哈希不匹配而拒绝；准备不生成可执行授权，派生E1逐例授权只在新batch授权通过后生成，并拒绝复用。
- 范围准确为F10/M0无模型1例，加E1-a的after_observation、before_modification、after_applied各1例，固定顺序串行。源码、private profile/deployment/target、两镜像构建收据及60881/60882/60888/60890均被哈希绑定；运行前还需实查镜像ID、既存项目/端口和环境覆盖。
- F10关闭包装先捕获原bound close，再以facade交给`close_owned`，不会递归调用包装器；called标记禁止重试，原异常和traceback保存。产品transport只对本session调用官方SDK dissolve，未知group/inbound ownership拒绝；六项关闭检查、cleanup warnings、独立资源复原和30秒/10流程H00同时约束继续。此为SDK返回/本地状态证据，不声称已直接盘点远端broker ACL。
- 启动前既存项目拒绝接管；只记录新创建且project/service/image/Created/StartedAt相符的ID。最终两次inspect核对登记集合和精确身份后，仅按已登记运行ID执行stop，复查实际非running，保留卷；未知替换或活动恢复容器导致失败保留。数据库合法换ID须绑定该子例原/恢复收据。
- 评估失败继续保留，清理/复原/H00不安全即停止后续例；原22/12结果不改判。WSL keeper仅一份原进程句柄，写专属stop文件后wait取得实际退出码；超时标terminal=false/批次失败，不以stop请求当终态，不强杀或启动替代keeper。

## 最终文件绑定

25文件白名单全匹配，4个plan及aggregate全匹配；166个冻结源码当前SHA及提交A Git blob全匹配；各plan输入、deployment输入和helper/summary/validation绑定全部匹配。四例输出与execution目录均不存在，未生成E1逐例授权。

| 材料 | SHA256 |
|---|---|
| `run_authorized.py` | `c4897d3751f6eb6605bf06d46304c0c343cb35da0ce213a3567d9afafbdf04d1` |
| `run_f10.py` | `7a21b0fa5d90d660db7d78f447835857ef278a12b7d94c188a32cc8101080392` |
| `plan-preparation/prepared-summary.json` | `b7bc975756db0ae78a02d8b80d52d670c214a9078ea8522f5191a55fa67cae82` |
| `plan-preparation/run-scope.md` | `40fa34e6c762ac618496ed9490e06b8da04bda5cda25959bfbed4dbd4479d28c` |
| `plan-preparation/publication-files.json` | `f4c474556aa3e28a05a7c1a48ee4cce670eeb9c37143f178f558878ecfaf12ed` |
| `plan-preparation/validation-result.json` | `1eaff85970f0f8b83e99a276d5353f2205b8d4d3a7dbc59da8577b07e400e450` |

四plan aggregate：`d1b6e10de8820cafd5a34d705bbea49f806c80257349eb5283abe8d590408fba`。这些SHA绑定原始本地文件；公开路径投影后应由发布映射保留原SHA与公开SHA，不改写本审阅绑定语义。
