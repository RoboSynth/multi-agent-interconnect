# 可移植的完整 SDK 本地检查

仓库随附的`run_sdk_suite.py`只依赖同目录的`synthetic_tls.py`和所选Python环境。指定仓库、新输出目录及已安装测试依赖的Python，即会复制SDK当前完整源码、生成八份临时synthetic TLS文件并执行全部`acps-sdk/tests`，保存实际退出结果。

实际验证：Windows、Python3.12.14，147份SDK输入，605项收集/通过，0 warning；pytest、worker及外层入口均退出0。独立审查发现首版会过滤掉仓库内venv依赖路径，且未设置POSIX的TMPDIR；修复后在独立复制的仓库及其内部完整36包venv上再次实际运行，仍605/605通过。源仓库与测试副本前后哈希一致，全部已加载SDK模块来自副本。两个运行保留各自源码绑定与结果，不累计成1210项独特检查。605不在入口里写死；后续源码或Python环境变化时以新的实际collection和结果为准。其他操作系统尚未实际验证。

## 环境与一条命令

运行器不自动安装包。`requirements-tested.txt`记录首次运行所用环境的36份实际distribution版本，包含SDK运行时、pytest、pytest-asyncio、AnyIO、cryptography、jcs和PyJWT。初次建独立环境可在仓库根目录运行：

```powershell
python -m venv .venv-sdk
.\.venv-sdk\Scripts\python.exe -m pip install -r tools/sdk-suite/requirements-tested.txt
```

这些安装步骤需要已有wheel缓存或正常的包源访问；入口自身不安装依赖。完成环境准备后，在仓库根目录运行以下一条命令，输出目录须为未存在的新目录：

```powershell
python tools/sdk-suite/run_sdk_suite.py --repo-root . --output ../sdk-suite-run-01 --python .venv-sdk/Scripts/python.exe
```

也可直接用目标环境执行，省去`--python`：

```powershell
.\.venv-sdk\Scripts\python.exe tools/sdk-suite/run_sdk_suite.py --repo-root . --output ../sdk-suite-run-01
```

Linux上的目标环境路径为`.venv-sdk/bin/python`；入口保留venv可执行文件原路径，不将其符号链接解析到基础解释器。`--repo-root`与`--output`都可使用绝对路径，输出不得位于SDK源码目录内；已存在的输出目录会拒绝覆盖。

## 结果与边界

外层命令的退出码包含真实worker结果与原仓库完整性检查；pytest失败保留日志和结果，不删除失败输出。重点查看：

- `driver-result.json`：实际worker PID、退出码、入口退出码及日志hash。
- `results.json`：完整nodeid、call/setup/teardown结果、warnings、collection errors、源码与TLS前后校验及SDK模块来源。
- `source-manifest.json`：当前SDK逐文件hash；若发布的147文件参考清单可用，记录是否匹配。源码有变化时仍运行当前完整树，并明确记录差异。
- `preparation.json`：实际解释器、依赖版本、完整pytest参数、helper hash和TLS夹具hash。
- `stdout.log.txt`、`stderr.log.txt`、`junit.xml`：完整原始运行输出；`worker-failure.json`仅在准备/执行器异常时生成。

测试在输出内的隔离SDK副本运行。只跳过bytecode、pytest cache、`.venv`和`.git`等非源码目录，不按测试名称或标记过滤；关闭无关pytest插件自动加载，显式启用pytest-asyncio与AnyIO。`synthetic_tls.py`复用已审的`make_tls()`函数，函数体原样提取，来源绑定在`tls-source-binding.json`。

临时CA和leaf用于本机随机回环TLS listener；MQ/Registry/OIDC测试沿用SDK原有fake、ASGI或MockTransport，进程恢复测试只操作自己创建的临时子进程。无需GitHub账号、注册身份、业务凭据或模型。所选环境须允许本机回环监听；工具不更改系统代理或全局环境。

输出中的synthetic私钥留本机，不能把整个`suite-copy`当公开证据上传。分享时只整理代码、manifest、public TLS摘要、测试日志与结果，并检查本机绝对路径。该入口证明本地SDK suite，不能替代正式平台、异机部署、长时运行或上游CI。

## 验证证据

[两次运行与源码绑定](../../evidence/sdk-suite-reproducer-20261019/README.md)保留首版、独立审查发现及修复后的605项验证；已验证的两份程序原字节随仓库提供。原始记录到发布投影的hash单列，临时测试副本、venv和synthetic私钥留在本机。
