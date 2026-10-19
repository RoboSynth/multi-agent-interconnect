# SDK来源对照证据

截止团队afb46e1，完整140份跟踪SDK文件按官方原生127/改造3/新增10划分，官方3985与94077的130个SDK Git blob完全相同。物理行数包含注释和空行，运行时实际增量+916/-12；新增测试、示例、README分别计数。本轮只读，不运行SDK测试或平台。

[解释与T01边界](interpretation.json)、[逐文件JSON](file-comparison.json)、[CSV](file-comparison.csv)、[行数口径](line-counts.json)及[原生/改造/新增清单](source-ready.json)分别保存。原审计脚本依赖开发机的已冻结Git树，留在本机；当前SDK字节与三清单的绑定可在团队检出内直接校验：

```text
python evidence/sdk-attribution-20261019/verify.py
```

工具只读本地文件与Git索引，不取远端、不运行平台或测试；Git不在PATH时用`--git`传其可执行文件路径。全部140份源、清单绑定和跟踪范围匹配才通过；它不重新证明官方Git对象的真实性，也不把源码校验称为运行验收。原审计产物中的脚本hash保留，未承诺那些本机脚本已随公开数据复制。

当前vendor组合了两个独立PR的产品改造，测试树不等于任一PR头；T01的AtomGit、最终fork版本绑定及上游CI继续单列。后续SDK改动需新增审计截面，不覆盖本轮140份清单。
