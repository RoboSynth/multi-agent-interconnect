# 当前源码验证与日志恢复准备

本轮以 `613ecbfc6e7500a30264bfec3c702d17152f0b6a` 为基线，补齐 SDK 测试树、原域 journal 恢复、可选 E1 恢复门和 Windows 一键停止入口，并构建独立验收镜像。**当前是本地实现、合成进程/镜像与文件验证；未执行新正式故障或启动七个身份。**

| 检查组 | 实际结果与主要来源 |
| --- | --- |
| 当前完整SDK | 605收集/605通过、pytest及执行器exit0；[独立源码与套件证据](../sdk-test-integration-20261019/README.md) |
| 新journal恢复 | 6个方法通过，含真实自有进程退出、未知结果、空/无owner库拒绝、重复字节相同；[日志](recovery-evidence/domain-recovery-final.log.txt) |
| 新控制器恢复门 | 5个方法通过，含plan/auth、同容器停止、原卷、无网络和失败保留；[日志](recovery-evidence/controller-recovery-final.log.txt) |
| 整例结果分类 | 2个方法通过：健康恢复不能覆盖日志恢复失败；[日志](recovery-evidence/outcome-recovery-final.log.txt) |
| 原E1路径 | 65个不同方法保持通过；17项首轮已过、48项在环境修正后复跑通过。受影响52项整轮0错误；[run-2摘要](recovery-evidence/run-2/summary.json) |
| 镜像/源码门 | 2项通过；[日志](recovery-evidence/source-gates-final.log.txt) |
| Windows一键停止 | 15个不同方法通过，含真实自有base/venv进程退出、认证HTTP和PowerShell；[摘要](native-down-evidence/summary.json) |
| 新智能体镜像 | 实际构建exit0，离线匹配19份关键源码及实际导入SDK，真实临时exit71后恢复未知结果、重复恢复不重执行业务，检查容器已移除；[镜像检查](image-attestation-final/summary.json)、[依赖与检查数据](image-attestation-final/stdout.json) |
| 新应用镜像/配置 | app-v2实际构建exit0；12项Compose服务配置、只读domain、共享DB卷与协调者路径文件验证通过；[构建](app-image-build/result.json)、[配置](deployment-validation/summary.json) |

以上分组不与旧 PR/单项检查累加成更多独特测试。[root-validation-summary.json](root-validation-summary.json)保存各组实际退出收据及当前源码hash；`root-validation-summary-r1.json`是新增整例分类两项前的历史截面。

## 行为与边界

[恢复入口说明](../../docs/access_recovery_validation_20261019.md)解释原AIC/目录/owner/schema只读先验，以及停止自有worker→无网络原卷恢复→正常worker/资源复原/H00的顺序。未知结果保持 `OutcomeUnconfirmed`，不虚构回复或重执行业务；日志恢复失败时仍尝试恢复业务，但整例失败。新计划须显式使用 `--recover-access` 并绑定新授权；旧计划无此新增效果。

[一键停止说明](../../docs/windows_local_shutdown_20261019.md)解释 nonce、认证 supervisor、精确进程族句柄与实际退出确认。已修复“收据已写但进程未退出”和“接受关闭后响应断开”两个审阅问题；没有强杀或按进程名关闭回退。它仅管理本检出已有登记，完整业务启停、新机器和全局启动/停止互斥仍未证明。已停PG的旧登记仍可能由原native入口返回失败，并保留记录。

## 保留的初轮失败

1. 首轮74项中22项通过、52项因新检出没有 `artifacts` 测试临时目录父目录而在setup失败；补齐后只重跑这52项并全过。当前新增恢复门的后续owner/原卷/整例分类修订由上述6/5/2方法覆盖，不拿旧run-2单独证明新源码。
2. 源码门在受限Temp读写/清理时失败；允许正常自有临时目录后两项通过。原失败日志保留。
3. 首次镜像检查脚本从 `/probe` 启动时缺少其自身的 `/srv` 模块搜索路径，import失败；修正探针后同一镜像通过，未改产品或重建镜像。两次临时容器都已确认移除；[原失败摘要](image-attestation/summary.json)、[诊断](image-attestation/failure-diagnostic.json)、[关闭检查](image-attestation/closure.json)保留。
4. 停机夹具最初误把venv启动器当基础解释器，后续新增测试曾缺少测试侧导入；修正夹具后分组通过，先前日志和摘要保留。

独立源码审阅：[原审阅](review/access-recovery-review.md)、[修正后复核](review/access-recovery-review-r2.md)。r2修正了r1并发读取时的一个hash绑定说明，原件不覆盖。

## 发布映射与未完成项

[publication-bindings.json](publication-bindings.json)逐文件绑定本地原件与仓库投影SHA和字节数。只将本机路径转成占位符、将审阅链接转为固定基线或仓库相对链接；摘要内旧hash仍指原件，需要通过此表核对投影。SQLite、临时TLS私钥、私密部署配置、混合编码原stderr不复制进本目录；混合stderr的原hash和有界UTF-8诊断提取另行绑定。源码、配置及过程原件保留本地。

[发布扫描截面](publication-scan-r2.json)及其[适配器绑定](publication-scan-r2-binding.json)记录109个候选文件、78项已知值、0命中、0解析错误；PDF正文、属性和XMP经相同文本规则扫描，最终15页检查与PDF字节绑定。此截面早于本段及收据本身的加入，完整提交的最后扫描另留本地batch。

新部署文件位于独立项目 `incident-pilot-access-validation-20261019`，端口60881/60882/60888/60890。它们尚未启动；准备不表示授权或正式验收。智能体镜像ID见上，应用镜像为 `sha256:aafad4dda0299dab69e06e5d30777044149a6db811b969578f6153823a331eb7`。

原22例18通过/4失败、原修复12例11通过/1失败及缺18/12条access继续冻结。下一轮拟一次F10和三个中断点各一次，须另行冻结并授权。Kafka/TLS与Monitor、新机器、长期窗口及最终视频/分享等缺口仍保留。技术报告[修订三](../../deliverables/development-report-20261019-revision3/README.md)固定截止613ecbf，只吸收此前正式12例与已发布图表，不把本轮未部署改动写成实测结果。
