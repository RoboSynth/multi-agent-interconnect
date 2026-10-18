> **2026-10-18 公开提交更新（UTC 08:29:35）**：已创建公开 [GitHub fork](https://github.com/RoboSynth/ACPs-community)，[接续PR #13](https://github.com/AIP-PUB/ACPs-community/pull/13)与[日志并发PR #14](https://github.com/AIP-PUB/ACPs-community/pull/14)均为 draft、尚未合并。四条 Issue 已发布：[乱序 #15](https://github.com/AIP-PUB/ACPs-community/issues/15)、[MQ文档 #16](https://github.com/AIP-PUB/ACPs-community/issues/16)、[access #17](https://github.com/AIP-PUB/ACPs-community/issues/17)、[发现语义 #18](https://github.com/AIP-PUB/ACPs-community/issues/18)。六项创建均 HTTP201、随后 GET200 且标题/正文一致；[提交事实与正文快照](../../../evidence/upstream-public-submission-20261018/submission.json)保留分支提交和验证边界。尚无合并或CI通过声明，AtomGit未做，正式NEW7 E1及24小时验收仍未完成。以下原文完整保留，作为此前审阅/提交前状态记录。

# 当前上游贡献审阅包（2026-10-18）

当前审阅目标是官方 `main` 的已核实提交 `94077d10b336bfdb9a7d68e4859390bf44a67a27`。
它与原固定基线 `3985c133` 的 129 个 SDK 源文件在换行归一后逐字相同：2 件原字节相同，
127 件仅 CRLF/LF 不同。原补丁直接应用当前 checkout 的两次失败已保留；下面两包仅转换
补丁换行后，在各自独立的官方源码副本中通过实际应用和相关检查。

| 审阅包 | 范围 | 当前官方提交上的实际验证 |
| --- | --- | --- |
| [接续、状态排序与可选 access](resumable/README.md) | 13 文件：原 12 项 SDK 改造与迁移的排序测试 | apply-check / apply / 逐文件比对通过，3 项排序检查通过；25 项未变组件检查复用历史证据 |
| [MessageEmitter 并发追加](message-emitter/README.md) | 2 文件：发射器与迁移的并发测试 | 当前未修复 SDK 上 2 个负例失败，应用后 5 项通过；不与 3 项项目集成检查相加 |

两包互相独立。旧 3985 补丁、首次超时、收据路径 KeyError、原始 CRLF 应用失败及 EOF
空行警告均在本机原件和各自校验摘要中保留；补丁适配没有修改生产 SDK、旧包或 E1 冻结输入。
正式 NEW7 E1 尚未执行，新增单次故障实验仍待授权。

从官方仓库根目录应用所选包后，先安装本 checkout 的 SDK，避免测试导入机器上别的版本：

```text
python -m pip install -e "./acps-sdk[amp-sign]"
python -m unittest discover -s acps-sdk/tests/aip -p test_task_ordering.py -v
python -m unittest discover -s acps-sdk/tests/amp -p test_message_emitter_concurrency.py -v
```

排序与并发命令分别对应各自补丁；运行哪个命令，应先应用对应的补丁。实际隔离验证显式限定
SDK 和依赖目录，未导入 incident-pilot 业务模块。这里给出的是复现入口，不是新机器安装验收。

[四条 Issue 草稿](../README.md)保留固定版本与观测日期；其中 access 建议已补正式健康窗口
12 任务 / 双端 24 条访问记录的独立对账，并把去重缓存范围收窄到每个 middleware 实例。
本次官方 issue 检索范围内未找到四主题的明确同题；匿名 API 曾 403 限流，后改用官方网页检索，
不能据此断言从无相关问题。见[官方检索记录](upstream-issues-search.json)与[兼容性、负例和历史失败摘要](upstream-compatibility.json)。

当前仅在团队内准备审阅包。外部 GitHub / AtomGit fork、两个 PR、四条 Issue 均尚未创建或提交；
私有团队上传不计作 T01、T34、T80 外部验收完成。
