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
