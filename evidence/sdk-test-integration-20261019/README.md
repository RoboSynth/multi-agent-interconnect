# 当前组合 SDK 完整测试

从团队源码 `613ecbfc6e7500a30264bfec3c702d17152f0b6a` 精确补入三份 PR 测试后，当前 SDK 完整测试树实际收集 **605 项，全部通过**，pytest exit0，执行器原 session51878 终结观察也为 exit0。总运行约39.907秒；call/setup/teardown各605 passed，无collection error。

[整合说明](../../docs/sdk_test_integration_20261019.md)、[全部147份SDK输入清单与三份Git blob绑定](source-manifest.json)、[准备回执](preparation.json)、[完整nodeid/phase结果](full-first/results.json)、[JUnit](full-first/junit.xml)、[stdout](suite.stdout.log.txt)、[stderr](suite.stderr.log.txt)及[实际执行器终结观察](executor-observation.json)分别保留。唯一warning是pytest-asyncio插件已导入、不能assert-rewrite，不影响本次通过结果。

[Synthetic TLS摘要](public-tls.json)只记录离线CA/leaf证书、公钥及有效期。生成器和本次实际准备/运行器源文件保存在[helpers](helpers/)用于审查：原运行器使用本机工件布局，不能原样当作团队机器的通用启动入口。生成的私钥、临时数据库和测试副本未随本证据复制。

本次实际使用独立的冻结36包Python环境，完整保留`acps-sdk/tests`，显式启用pytest-asyncio和AnyIO，关闭无关插件自动加载。TLS listener仅为本机随机回环端口；MQ/Registry/OIDC使用fake、ASGI或MockTransport，进程恢复fixture只持有自己的临时子进程。源码和TLS夹具前后完全一致，SDK模块均来自隔离副本；SDK产品源码未随测试整合修改。

若要复现同一检查范围，先按[仓库随附的SDK入口说明](../../tools/sdk-suite/README.md)准备独立Python环境，在仓库根目录运行：

```text
python tools/sdk-suite/run_sdk_suite.py --repo-root . --output ../sdk-suite-run-01 --python .venv-sdk/Scripts/python.exe
```

入口自动复制当前完整SDK并生成八份synthetic TLS文件，无需使用本目录历史helper的本机工件布局。[可移植入口的两次验证](../sdk-suite-reproducer-20261019/README.md)另存；本目录原605及其源码/结果绑定保持不变。证书重新生成后哈希会变化，每次输出到新目录并保留新的回执。

本轮是当前SDK本地完整suite；不代表上游CI、真实平台故障、Monitor入库或七身份重连。最终fork绑定和AtomGit仍待后续处理。旧两PR的581/558以及此前单项17/2结果不与本轮605相加。

## 源码绑定复查

在本仓库检出中执行：

```text
python evidence/sdk-test-integration-20261019/verify.py
```

只校验147份本地SDK文件及已安装三份测试的原字节哈希，不运行测试或访问平台。源码再次变化后应创建新的验证截面，不改写本清单。旧afb46e1的来源审计继续保留。

`publication-manifest.json`逐项绑定本机原始字节和当前发布字节；发布时将精确匹配的本机绝对路径前缀映射为`[project]`、`[sdk-copy]`等标记，路径后缀使用POSIX斜杠。revision2保留首次投影manifest的哈希，修正JSON路径中的反斜杠表示；JUnit原字节不变。原始回执中的hash引用不重写，查验投影后文件时应使用manifest中的`published_sha256`，不是原始文件hash。README和verify属于新增说明文件，不在19份原始投影项内。
