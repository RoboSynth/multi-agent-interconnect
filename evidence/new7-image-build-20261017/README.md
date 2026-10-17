# 新七角色镜像离线验收

本机仅构建 incident-pilot-agent:new7；build exit 0。使用该 image ID 运行 --rm -i --network none --read-only 临时 Python 容器，无证书、资源或环境文件挂载，未运行 agent 主入口。PlatformWorker、Bridge、OnboardingPartner 可导入；12 个固定源码 SHA 和实际 import 路径均匹配冻结源。官方 ACS schema 与 SDK 离线校验通过；schema、许可及 onboarding 依赖字节对齐。integration 目录只有顶层 Python 源码，未带运行数据库、日志、env 或证书。

保留两个真实早期失败：legacy CLI 不接受 --progress（exit125）；首个临时探针未附加 stdin，脚本未执行，采集器 JSONDecodeError。去除日志参数后构建成功；补 -i 后只重跑临时探针通过，没有重建镜像。原始 build/probe 日志留本地，不属于公开清单。该结果只证明新镜像依赖和源码可用，不是七个新身份已启动或真实平台互联验收。
