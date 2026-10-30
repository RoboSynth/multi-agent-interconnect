# 本轮测试原始记录

本目录是2026年10月29日本轮测试记录的可分享脱敏副本。原件保留在内部采集目录。副本保留原有时间、任务标识、错误、结果和失败次数；机器绝对路径替换为占位符，测试审批密钥与HMAC证明值移除。

## 记录入口

- `原始记录/validation.log`：146项原始测试的完整文本日志，143通过、3错误、0跳过。
- `原始记录/validation-results.json`：逐测试名称、耗时、结果和异常栈，含3项错误。
- `原始记录/source-manifest.json`：当次代码提交、未提交修改、155个源码与配置文件的哈希。
- `原始记录/fixture-diagnostic.json`、`fixture-diagnostic.log`：补齐模拟会话健康通道字段后的独立3项通过记录。
- `原始记录/fixture-diagnostic-harness-error.log`：补充诊断脚本首次因嵌套事件循环产生的脚本错误，单独保留。
- `原始记录/local-process-results.json`：首次3个进程案例的原始汇总，2通过、1启动失败。
- `原始记录/local-process-cases/`：三种中断点及一次独立重试的原始过程副本，包括AIP消息、AMP日志、资源终态、错误和操作记录导出。
- `原始记录/submission-validation-summary.json`：完整匿名摘要，明确4次进程执行中3次成功、1次启动失败。
- `脱敏副本清单.json`：逐文件来源相对路径、原件哈希、副本哈希、转换方式和遗漏原因。

JSON和JSONL是逐字段或逐条脱敏后的原始记录，日志是文字替换后的原始记录。`.sqlite.export.json` 是只读数据库逻辑导出，包含表结构和已保存记录；3个SQLite回滚日志只在内部保留。`.py.reference.txt` 是原采集脚本的脱敏归档，原路径已替换，复现使用下节的可移植脚本。

本目录用于查看业务行为与定位异常，实际审批证明值在私有原件中保管。

## 可移植复现

下面两个脚本默认寻找同级的 `../当前源码`。也支持 `--repo <源码目录>`。使用已按源码依赖要求配置的Python运行；脚本运行离线测试和本地进程案例，每次创建新的时间戳结果目录。

在 `原始目录` 中运行：

```powershell
python -X utf8 -B .\测试记录\run_current_validation.py --check
python -X utf8 -B .\测试记录\run_current_validation.py
python -X utf8 -B .\测试记录\run_isolated_takeover.py --diagnostic-only
python -X utf8 -B .\测试记录\run_isolated_takeover.py
```

只复现修改前中断场景：

```powershell
python -X utf8 -B .\测试记录\run_isolated_takeover.py --retry-before-modification
```

指定其他源码检出和独立输出目录：

```powershell
python -X utf8 -B .\测试记录\run_current_validation.py --repo <源码目录> --output <尚不存在的结果目录>
```

启动异常在首次运行中出现、独立重试通过，原因待定位；复现脚本逐次保存成功与失败。

修复任务及验收细节见 `../测试问题复现与修复验收.md`。
