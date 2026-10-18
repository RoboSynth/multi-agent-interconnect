# T06 七源本地追加采集验证（revision4）

本机既有 Windows Fluent Bit 5.1.3 对七个独立合成目录完成实际采集：252 个唯一 ID，逐字段一致，重复/遗漏均为 0；42 个持久 offset DB，三个采集器及三个独立 console host 均正常退出 0。实际运行 2026-10-18 11:04:29.750–11:04:48.081 UTC，退出 0。

这次验证的是 SDK 固定文件追加、运行中发现新稳定正文文件、正常停止后追加续读，以及停机时在既有稳定文件追加并新建正文文件。六批各 42 条，三个阶段为 126/42/84 条。原文件始终保留；没有执行 rename。七个目录均为 fixture，尚未读真实七域容器卷，也尚未验证官方 Kafka 或 Monitor 入库。

`observed.jsonl` 按 phase1、phase2、phase3 拼接原 stdout 字节和原行，没有重新序列化或过滤；`expected.json` 是 revision4 原始映射的逐字节副本，source 全为相对路径。按 log_id 查询映射中的 record 可复核全部字段；phase 切分和正常退出记录见 `phases.json`。22 项离线检查及真实运行收据见 `summary.json`；六份已测源码、运行输入与二进制 SHA256 见 `source-inputs.json`。原输入、42 个 DB、原 stdout/stderr/host 记录完整保存在本机。

历史失败保留在 `prior-failures.json`：revision2 在 console 附着就绪前检查失败并强制清理；revision3 第二阶段 raw 输出 126 条，其中 84 条为跨阶段重放。后者来自将数字归档加入 Path 的方案；revision4 撤销该枚举，按真实追加语义验证，不宣称修复外部 rename、copytruncate 或停机归档。

SDK 六类 Emitter 的固定路径与 append 写入位置列于 `source-inputs.json`。[官方 Tail 文档](https://docs.fluentbit.io/manual/data-pipeline/inputs/tail#file-rotation) 提醒 Path 不应匹配轮转归档，以免重复读取。

团队复现可先阅读 `deploy/fluent-bit/README.md`，用 `verify_collection.py --prepare --output artifacts/<新的独立目录>` 准备，再审阅 plan 后使用同一目录 `--run`。准备会生成新的合成记录；本包保存本轮原始 observed/expected 便于独立复核。完整 T06 仍待官方 Kafka/Monitor 实际接入验收。
