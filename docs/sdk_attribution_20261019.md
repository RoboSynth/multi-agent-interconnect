# SDK来源与原生、改造、新增对照（2026-10-19）

本次核对以团队源码`afb46e1b898faad4e5724db0cb6cf52d7d94ef81`为截止，比较官方Git对象、v0.2.0冻结副本、当前vendor和已公开的两个PR头。只读检查，没有更改SDK、运行测试或重跑平台实验。

官方基线为`3985c1330209f075c124669cc9d31f0e75448140`，公开贡献面向`94077d10b336bfdb9a7d68e4859390bf44a67a27`。两提交的完整130份SDK Git blob字节一致。以前129份的源码选择器排除了`uv.lock`；本次库存包含锁文件，但运行时代码统计不含它。

## 代码对照

| 范围 | 文件数 | 当前物理行数 | 相对官方基线的实际增删 |
| --- | ---: | ---: | --- |
| 官方原生运行时Python | 57 | 12073 | +0 / -0 |
| 修改官方运行时Python | 3 | 4220 | +71 / -12 |
| 新增运行时Python | 7 | 845 | +845 / -0 |
| 新增SDK测试 | 1 | 405 | 单列，不计入运行时增量 |
| 新增示例 | 1 | 80 | 单列 |
| 新增接续README | 1 | 152 | 单列 |

运行时合计增量为**新增916行、删除12行**。物理行数包含注释、文档字符串和空行；改造文件现有的4220行中大部分仍来自官方，不能全部算作项目新增。这里也不累计历史patch、重复基线、证据快照或项目外层测试来放大改动量。

三个改造文件是`aip_group_leader.py`、`aip_group_partner.py`、`message_emitter.py`，分别接入可选任务/访问记录、保护乱序状态，以及同路径进程内写入互斥。新增模块提供任务日志、协调者任期、资源账本、fence、替代接管、Partner封装和access中间件。业务网关、协调器、工作台和订单服务在SDK外，未混入这张表。

完整SDK树为140份跟踪文件：127份保留官方内容、3份改造、10份新增，无遗漏官方文件。127份原生文件中125份只有CRLF/LF差异，2份原字节相同；换行差异不计项目改造。新增SDK测试由AST识别25个方法，本轮没有执行，不把方法计数写成新通过记录。

逐文件原字节/LF哈希、三类清单与行数定义见[来源证据](../evidence/sdk-attribution-20261019/README.md)。

## vendor与公开贡献的关系

当前依赖仍安装团队仓库里的普通vendored文件。其产品源码经CRLF→LF归一后，对应[PR #13头](https://github.com/RoboSynth/ACPs-community/tree/09fe13bd699f4a9df279507ed23861f6f817babe/acps-sdk)的接续/access改造，加上[PR #14头](https://github.com/RoboSynth/ACPs-community/tree/72a994bfb8cd5cc832beb0204a4715a2c090f983/acps-sdk)的MessageEmitter修复；它不是任一单独PR头的完整checkout。

本地SDK测试树也不等于两PR：上游审阅包新增的排序/并发测试位于各自PR，本地vendor尚无这两个文件；MetricsEmitter测试的可移植性修正也只在公开PR头。项目外层已有对应行为测试，不能用它们宣称vendor测试树已经对齐。

T01的GitHub fork/贡献提交已有独立证据；**AtomGit镜像、vendor到最终fork版本的绑定和上游CI仍未完成**。本次来源记录不改变依赖选择、提交新的公开分支或重写现有PR。当前PR状态以[2026-10-19状态快照](contributions/upstream_status_20261019.md)为准。
