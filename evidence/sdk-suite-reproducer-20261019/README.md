# 可移植 SDK 完整套件入口验证

仓库已提供[一条命令入口](../../tools/sdk-suite/README.md)，只需指定检出目录、新输出目录及已准备好的Python环境。两份程序与最后一次通过验证的字节相同；本次落库没有重跑605项，也没有改动SDK源码。

| 运行 | 入口版本与环境 | 实际结果 |
| --- | --- | --- |
| [首版](run-first/results.json) | `f3ac4926`，仓库外独立36包环境 | 收集605，call/setup/teardown各605通过，0 warning；pytest/worker/driver/执行器均exit0 |
| [修复后](run-second/results.json) | `9ced5840`，独立复制仓库内的36包venv | 收集605，call/setup/teardown各605通过，0 warning；pytest/worker/driver/执行器均exit0 |

[首版独立审查](review-first-version.md)指出：按整个repo过滤sys.path会误删仓库内venv依赖，且继承TMPDIR可能使POSIX临时文件落在指定输出外。当前入口只排除原SDK子树和准确的仓库根路径，保留选定环境；启动worker前预建临时目录并设置TEMP/TMP/TMPDIR。首版程序和结果保留为历史，不推荐执行首版程序。修复后实际检查覆盖Windows仓库内venv；TMPDIR的POSIX分支仍为代码核对，其他操作系统尚未实测。

两次均使用相同147份SDK文件，collected nodeid全集与[原组合SDK605套件](../sdk-test-integration-20261019/README.md)相同，不将重复运行相加。原仓库、副本及synthetic TLS前后hash一致；已加载SDK模块全部来自各自副本。[第二次环境观察](environment-second.json)另核实11项主要依赖模块来自复制仓库内的venv。

每次运行保留`source-manifest.json`、`preparation.json`、`results.json`、`driver-start.json`、`driver-result.json`、`public-tls.json`及stdout/stderr。`driver-result.json`记录实际worker退出；[源码绑定检查](source-binding-check.json)另绑定执行器session终结观察和当前发布检出的147份SDK及两份程序字节。

[环境版本](environment-first.json)、[第二次环境准备](second-run-preparation.json)和[历史阶段汇总](historical-validation-summary.json)保留原记录。历史汇总中的“尚待落库”等字段属于当时工件阶段，当前使用入口以仓库内tools说明为准。首次环境的36份实际distribution版本已随`tools/sdk-suite/requirements-tested.txt`提供；没有在本次落库中重新安装环境或重跑套件。

## 发布绑定

`publication-manifest.json`采用22份显式白名单，只复制本页列出的JSON、日志、首版审查及首版程序。每份记录原件与投影字节的SHA256；原件hash引用保留，查验发布文件使用`published_sha256`。绝对路径仅按精确已知原前缀映射为标记，路径后缀转换为POSIX斜杠。两份现行程序保持验证字节；README作为当前使用说明另有最终发布hash。

临时SDK副本、synthetic TLS私钥、venv、数据库和真实身份资料不在白名单内。完整原始JUnit与其他本地工件保留在开发机，不在此包复制。该证据覆盖本地SDK完整套件，不代表正式平台、全栈部署、异机或长时验收、上游CI；最终fork绑定与AtomGit仍需继续完成。
