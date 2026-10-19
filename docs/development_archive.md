> **2026-10-19 新版完整源码包：** 固定提交 `3760b21c8a1ed62e8119925da6f24ebd8b851d14`，2018个文件，ZIP 19,249,930字节；逐文件与Git blob及当前外部清单核对通过，96项必要入口齐全。含原journal恢复、正常停机、一键SDK完整检查、四例复验准备及15页报告修订3。[检查与下载说明](../evidence/deployment/development-archive-3760b21/README.md)分别列出包截止、报告截止和仍未运行的复验。下文7fb2b2c、69647cf均为历史包。

## 3760b21 固定包复现

```text
git archive --format=zip --prefix=incident-pilot-development-3760b21/ --output=../incident-pilot-development-3760b21.zip 3760b21c8a1ed62e8119925da6f24ebd8b851d14
```

实际 ZIP SHA256：`e80b8bc73c42200ce562c2f553f36377ac956f142dae1b4c054df76aa3ecb43a`。也可使用自己的团队账号从[GitHub固定提交](https://github.com/RoboSynth/multi-agent-interconnect/archive/3760b21c8a1ed62e8119925da6f24ebd8b851d14.zip)下载，自动包的前缀和容器哈希另计。当前2018文件清单见[export-manifest.json](../evidence/deployment/development-archive-3760b21/export-manifest.json)；包内根目录原有SNAPSHOT-MANIFEST仅保留历史含义。本次实际只读校验未启动业务，不替代新机器或F10验收。

---

> **历史 7fb2b2c 完整源码包：** 固定提交 `7fb2b2c3cb7f4ad41dc40dba5b7ab0f12feb116b`，1613个文件，ZIP 16,553,937字节；全部文件与Git blob及快照清单逐字一致，80项必要入口齐全。包含当时E2-c源码/测试/证据、18条缺端诊断和8页报告。

## 当前包复现

```text
git archive --format=zip --prefix=incident-pilot-development-7fb2b2c/ --output=../incident-pilot-development-7fb2b2c.zip 7fb2b2c3cb7f4ad41dc40dba5b7ab0f12feb116b
```

本次实际ZIP SHA256：`3330f1606c105be0fd92229bb108e28c3b22721d6bf3f41bb6c2196e10211474`。GitHub也可从该固定提交导出源码；ZIP容器元数据可能随工具变化，核验应绑定固定提交和逐文件内容。本地实际校验见[验证结果](../evidence/deployment/development-archive-7fb2b2c/verification.json)及[退出收据](../evidence/deployment/development-archive-7fb2b2c/verification-exit.json)。

这一次只读验证无解压、构建、启动或真实业务调用；不计新机器15分钟部署、网盘永久分享或另账号访问验收。源码包不携带实际env、私钥、数据库、模型和依赖环境；队友按[开发者接手指南](开发者接手指南_20261018.md)配置自己的环境。归档固定在代码/报告提交，随后入库的归档验证记录可从最新主分支取得。

---

# 完整开发复现包

本轮源码固定于团队仓库提交 `69647cf29de96b50091c0a3e51ae2308115ad2fb`。归档包含1069个已审定跟踪文件：项目源码、完整改造SDK/CLI、部署模板与许可证、筛选基线、资料和闭合派生证据。它不依赖旧的baseline源码overlay来补齐SDK。

本次交付ZIP为 `incident-pilot-development-69647cf.zip`，11923563字节，SHA256：

```text
d5a50e822002a6cc3ecc2bf8f0c291a378cdbc6b91364be4e9038a0649387ff8
```

解压后的文件内容合计22889483字节。1069个ZIP文件均已逐项核对Git blob与快照清单；重复、越界、缺失和非普通文件检查通过。清单不包含自身，清单原件由上述Git提交固定。实际记录见[归档验证](../evidence/deployment/development-archive-69647cf/verification.json)。

在已克隆的团队仓库内，可从同一提交重新导出：

```powershell
git archive --format=zip --prefix=incident-pilot-development-69647cf/ --output=../incident-pilot-development-69647cf.zip 69647cf29de96b50091c0a3e51ae2308115ad2fb
```

上述SHA记录本次实际交付的ZIP；重新打包应以固定提交及逐文件内容为准。解压后按[协作快速开始](../COLLABORATION.md)和[部署说明](../deploy/README.md)准备自己的依赖和私有配置，先确认端口与身份未被其他进程占用。

归档不包含实际env、资源凭据、证书私钥、数据库、模型、虚拟环境或运行时二进制。它是开发源码复现包，非离线运行环境或最终比赛提交包。

本次在新解压目录使用测试占位env执行了真实Compose `config --quiet`及`config --services`，均exit0；默认服务仅postgres、app-v1、app-v2、nginx。检查没有启动或重建服务，也没有运行新故障；它证明解压配置可解析，不替代新机器15分钟部署与F10验收。
