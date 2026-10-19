# T01 最终 fork/vendor 绑定审阅包（2026-10-19）

结论：当前团队提交 `3760b21c8a1ed62e8119925da6f24ebd8b851d14` 的 SDK 147 个 Git blob 与已通过完整 605 项套件的 147 份原件逐字节一致。现有公开 PR #13/#14 的组合只有 142 份文件；最终集成还需加入已在团队私库发布的 7 文件增量。当前没有能代表最终版本的 fork commit。本包提供可直接审阅、应用且已核验的补丁，以及完整候选 Git tree OID；tree OID 不冒充 commit SHA。

## 来源截面与剩余差异

| 来源 | 完整提交 |
| --- | --- |
| 官方实现基线 v2.2.0 | `3985c1330209f075c124669cc9d31f0e75448140` |
| 两 PR 的官方基线 | `94077d10b336bfdb9a7d68e4859390bf44a67a27` |
| [PR #13](https://github.com/AIP-PUB/ACPs-community/pull/13) 保存的 head | `09fe13bd699f4a9df279507ed23861f6f817babe` |
| [PR #14](https://github.com/AIP-PUB/ACPs-community/pull/14) 保存的 head | `72a994bfb8cd5cc832beb0204a4715a2c090f983` |
| 本次只读核对的团队源码 | `3760b21c8a1ed62e8119925da6f24ebd8b851d14` |

两个官方提交的 SDK **130 份 Git blob 原字节完全相同**。本地完整 fork worktree 仍在：`upstream-public-submission-20261018/branch-resumable` 和 `branch-message-emitter`，分别保存上述两个 PR head。该路径相对于本项目 artifacts；这是已有本地对象证明，不是新远端 fetch。

当前147份按 CRLF→LF 对照分为：官方未改125份、原字节内容来自PR13的12份、来自PR14的2份、两PR相同的Metrics测试1份、后续项目增量7份。相对官方SDK共有17份新增、5份修改（其中包含测试），不是147份自研文件。逐文件 Git blob/SHA256、原字节及 LF 哈希见 [inventory.json](comparison-r2/inventory.json)；分组见 [source-groups.json](comparison-r2/source-groups.json)。

两 PR 的最小组合为 PR13 全部 SDK，加上 PR14 的 `message_emitter.py` 与 `test_message_emitter_concurrency.py`。两 head 的 Metrics portability 测试 blob 同为 `0a21c32b77d8261cd848eb6b0e5217b47e1c4479`，只需保留一次。若用 cherry-pick 组装，应只取 PR14 的产品/并发提交 `ddf2094ef2ea7b687a8966e43302ab07d23b9950`，避免再次叠加同一 portability 修改；本包的 PR13→最终补丁已经包含这些内容。

组合之后仍有下面7份语义增量，均最后变更于团队提交 `613ecbfc6e7500a30264bfec3c702d17152f0b6a`，并已包含在当前605套件源清单中：

| 路径（相对acps-sdk） | 相对组合版本 | 作用 |
| --- | --- | --- |
| `acps_sdk/amp/__init__.py` | 修改 | 导出可选持久化发射器与完整性异常 |
| `acps_sdk/amp/group_access.py` | 修改 | 配合可选begin/finish持久化接口 |
| `acps_sdk/amp/durable_access.py` | 新增 | SQLite outbox与本地access崩溃恢复 |
| `tests/amp/fixtures/durable_access_process.py` | 新增 | 持久化access子进程夹具 |
| `tests/amp/test_durable_access.py` | 新增 | 持久化access/进程故障验证 |
| `tests/resumable/fixtures/coordinator_process.py` | 新增 | 协调者进程夹具 |
| `tests/resumable/test_coordinator_process.py` | 新增 | 协调者进程恢复验证 |

详见 [7文件对照](comparison-r2/delta-after-two-prs.json)与[团队提交来源](comparison-r2/project-delta-lineage.json)。本次未改这些文件，也未重跑605。

## 最小正确的绑定路线

建议最终使用**原字节精确候选**，保留当前已测147份文件，避免在等待4例验收期间改变源码绑定。另附LF最小补丁供代码审阅；两者只有CRLF→LF差异，不混称原字节相同。

| 候选 | SDK tree OID | 整个fork候选tree OID |
| --- | --- | --- |
| 原字节精确（建议实际绑定） | `2796a70756eba2405c108414e14b36186c188601` | `a656374c5030ca59c37daa3e93f447d2fcada1cc` |
| LF最小差异（审阅用） | `3e127540cd9024e24e66961d24a59a8d901baa32` | `9c86f39c2b04b8848f3ec353fb1cb8c0d2b80fdb` |

整个fork候选树保留官方94077d1的全部SDK外Git条目，仅替换SDK子树；共有1997份文件。这里只计算元数据，没有导出或复制整个官方仓库。SDK本身有127份CRLF文件。官方→原字节补丁涉及145份文件，其中大部分为换行变化；官方→LF最小补丁仅22份语义变化。

建议集成时从已保存 PR13 head 建立**新的独立分支**，例如 `integration/incident-ext-20261019`，应用 [PR13→原字节最终版](comparison-r2/pr13-to-raw-exact.patch)。现有 `incident-ext` 是 PR13 的来源分支，不能直接用于组合版，否则会把 PR14 和7份新扩展一起追加到现有 PR13。现有 `fix/message-emitter-append` 同样保持其独立范围。

本机已有 fork checkout 的 `core.autocrlf=true`，直接暂存原字节版可能再次被转为LF。获准实际整合时应在独立checkout中显式控制该次Git操作的换行转换，并在提交前核对SDK tree与上表原字节OID相同。与目录名称或工作区显示相同相比，Git tree OID才是这一步的判据。

最终完成需要一个真实集成commit（目前尚未创建），然后把该commit的完整SHA、SDK tree OID、147份原件清单写入vendor绑定文件及ORIGIN说明。继续保留普通vendored文件即可，不必为T01引入子模块和新的安装方式；团队应用仍使用本地vendor，离线克隆可运行。建议绑定字段见 [vendor-binding.proposed.json](vendor-binding.proposed.json)，其`fork_commit`故意为null，不能以当前提案宣称T01完成。若改选LF版，应先将vendor也改为该精确树并另建证据，不能套用raw版的原字节通过记录。

## 补丁与验证

| 补丁 | 变更文件数 | 用途 |
| --- | ---: | --- |
| [official→LF](comparison-r2/official-to-lf-minimal.patch) | 22 | 对照官方审阅全部语义增量 |
| [official→原字节](comparison-r2/official-to-raw-exact.patch) | 145 | 从官方基线重建已测字节 |
| [PR13→LF](comparison-r2/pr13-to-lf-minimal.patch) | 9 | 最简集成代码审阅 |
| [PR13→原字节](comparison-r2/pr13-to-raw-exact.patch) | 134 | 从现有PR13构建精确集成树 |
| [两PR组合→LF](comparison-r2/pr13-plus-pr14-to-lf-minimal.patch) | 7 | 单独审阅尚未公开的新扩展 |
| [两PR组合→原字节](comparison-r2/pr13-plus-pr14-to-raw-exact.patch) | 133 | 原字节组合差异与换行记录 |

每份补丁均实际在本批新建artifact副本上执行 `git apply --check` 与 `git apply`，两步均退出0，应用后147份文件逐字节等于对应候选。结果见 [patch-verification/results.json](patch-verification/results.json)，完整补丁SHA256及候选树见 [candidate-bindings.json](comparison-r2/candidate-bindings.json)。没有执行SDK、collection、模型、平台或真实资源操作。

`compare_sdk_binding.py`只读已有Git对象和指定测试清单，输出逐文件对照及补丁；`verify_patches.py`只在新建输出目录中检查/应用补丁，不写Git index或Git对象。canonical在比较前后均为clean、HEAD相同。原始605结果没有改写或重复累计。

## 上游许可与归属

官方94077d1的[根LICENSE](https://github.com/AIP-PUB/ACPs-community/blob/94077d10b336bfdb9a7d68e4859390bf44a67a27/LICENSE)和[SDK LICENSE](https://github.com/AIP-PUB/ACPs-community/blob/94077d10b336bfdb9a7d68e4859390bf44a67a27/acps-sdk/LICENSE)是同一份 **MulanPSL-2.0**，Git blob均为 `fe692b5fa3d0a736e459bd3325cfceb9a016c616`，SHA256均为 `27747b6305e1df148d41414363311ee114a4548d1b0dac352ece3c79ff15fec6`。SDK `pyproject.toml`也声明`MulanPSL-2.0`及`license-files=["LICENSE"]`。当前vendor SDK许可仅有CRLF差异，LF哈希完全一致；原字节候选保留当前许可原件，fork根许可和SDK外原声明不变。

原文第4条要求分发时提供许可证副本，并保留软件中的版权、专利、商标和免责声明。最终集成应保留官方Git历史、以上许可、各源文件原声明，并在新增来源记录中区分官方内容与团队增量；不把上游作者改成RoboSynth，也不从GitHub仓库名或提交者名字推断全部版权主体。已有SDK的Mulan声明只说明此组件的许可范围，不能据此给业务应用、资料和其他依赖统一套用一个总许可证。团队现有`THIRD_PARTY.md`和vendor的`ORIGIN.md`应保留，本包没有为项目选择整体LICENSE。

公开新集成分支前还须确认团队对本批新增SDK贡献的发布授权及组件许可标识；这与应用项目总许可证是两件事。其他MCP依赖及其传递依赖的许可不属于本次SDK补丁，不能把本包当作完整运行时SBOM。

## 发布权限与当前状态边界

可以直接纳入已授权团队**私库**审阅：本README、比较/验证工具、逐文件清单、六份补丁、候选绑定提案及验证收据。这些是已有团队代码的来源和复现材料。建议只上传这份明确清单，不递归复制patch-verification下的SDK副本。

当前授权明确覆盖已创建的两个PR和四条Issue。**新的公开集成分支或把新增7文件推送公开fork、修改现有PR、建立AtomGit公开镜像，都没有由这项只读任务获得授权。**本轮不新建PR/Issue，不修改既有PR，也不stage/commit/push。AtomGit镜像和真正的上游CI仍待完成；本地605通过不等于上游CI通过。

本轮两次匿名公开API读取均在首请求即失败：沙箱内为URLError（2026-10-19 09:16:53 UTC），局部提升后为HTTPError（09:17:21 UTC），后者未记录HTTP状态码；两次均无成功响应、无凭据或GCM调用，没有继续其他端点。失败摘要保存在 `public-ref-observations/summary.json`与`public-ref-observations-r2/summary.json`。远端状态沿用已有2026-10-19 08:50 UTC快照：PR13/14仍open/draft且head如上；本轮不能宣称已经刷新远端默认分支或当前PR状态。源码补丁的精确性由本地已保存Git对象和实际应用结果证明。

比较工具首次发现旧3985对象不在浅fork副本中，首次执行退出1且未产生对照文件；随后改用既存官方baseline仓库读取该对象，第二次完成（exit0）。首次空输出目录保留，未通过改写来源假造成功。
