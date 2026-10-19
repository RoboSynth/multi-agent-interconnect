# 正式验收准备证据（2026-10-19）

基线 `4f157a1d557eba3008eec338d0cde5d7d523ee8a`。独立项目 `incident-pilot-acceptance-20261019`，回环端口 48081/48082/48088/48090；本批 22 个正式故障尚未执行，未生成执行授权。

- [检查汇总](root-checks.json)、[15 项部署检查](deployment-full-tests.log)；前期 7 项是子集，计划准备器另有 5 项守门检查。
- [七身份核查](identity-readiness/summary-v2.json)、[原运行库存](runtime-inventory/safe-summary.json)与[真实 Compose 文件检查](deployment-validation/summary.json)。
- [原版依赖调查](dependency-investigation/summary.json)：Linux/Windows 原版官方文件哈希及 Linux 离线安装/解析，保留索引缺失和前期探针失败。
- [智能体构建](image-build-retry2/result.json)、[应用构建](app-image-build/result.json)和[实际镜像取证](image-attestation/public-candidate/image-attestation.json)：27 份源码、7 份已安装 SDK 文件一致；三环境 pip check 通过，init 下 PID7，探针自然退出 0。
- [启动镜像与参数](startup-readiness/STARTUP-REVIEW.md)、[只读审阅](final-review/review.json)及[逐例运行范围与 SHA](plan-preparation/run-scope.md)。
- `plans/` 保存 22 份原始计划字节；对应私密源配置及实验 bundle 留在本机当前 checkout。`plan-preparation/` 脚本是原批次归档，ROOT 按原本机目录推导；队友按[操作说明](../../docs/acceptance_preparation_20261019.md)和自有身份重建自己的计划。

原 34 个容器保留。新增依赖/镜像探针均无网络、已退出；原构建、探针和辅助脚本的失败分别保留。文件、镜像与启动参数已准备，实际平台互联、恢复后 H00、新机器和长期在线仍待验收。
