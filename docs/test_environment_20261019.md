# 项目测试环境

使用 Python 3.12，在当前仓库根目录创建自己的 `.venv` 并安装完整开发依赖。SDK 必须来自本次检出，避免复用其他目录的 editable 安装。

Windows：

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
New-Item -ItemType Directory -Force artifacts | Out-Null
.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py'
```

Linux：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
mkdir -p artifacts
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

部分夹具假设 `artifacts/` 已存在；Windows 启动配置检查还会查找本仓库的 `.venv/Scripts/python.exe`，因此不要只用另一个目录的解释器代替本地环境。Windows 专属检查在 Linux 中会跳过，应按实际测试输出报告。

日常修改把文件模式换成受影响测试，例如 `test_onboarding.py`，不必每次全量重跑。`business_*_test.py` 不匹配上述默认模式，应按修改范围显式运行；`business_native_acceptance.py`、实验执行器和显式选择 `BUSINESS_TEST_DATABASE` 的检查涉及真实服务，须另行准备资源与运行范围。

`requirements-dev.txt` 包含报告/图表依赖及本检出 SDK 的签名依赖。缺依赖导致的跳过不能当作检查通过。上游 SDK 套件有[独立入口](../tools/sdk-suite/README.md)，不与项目 unittest 混作同一套结果。

`integration/incident/*.acs.json` 中的离线 fixture 使用未注册身份、`active=false` 和 `fixture.invalid`。测试文件名中的 `approved` 不代表真实平台审批；真实接入使用自己的身份和证书。

当前对照结果见[强基线](BASELINE.md)，原始测试和运行报告见[实验记录](../evidence/README.md)。
