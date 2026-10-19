# 项目离线测试环境（2026-10-19）

项目测试使用 Python 3.12 和标准库 `unittest`。从当前检出的项目根目录安装，避免引用另一个 checkout 的 SDK：

```powershell
py -3.12 -m venv .venv-dev
.\.venv-dev\Scripts\python.exe -m pip install -r requirements-dev.txt
New-Item -ItemType Directory -Force artifacts | Out-Null
```

`requirements-dev.txt` 复用现有 `requirements-high-score.txt` 和 `requirements-report.txt`，并安装本 checkout 的 SDK `amp-sign` extra。签名依赖固定为本机已验证的 `cryptography==50.0.2`、`jcs==0.2.1`；图表使用现有清单的 `matplotlib==3.11.2`。这些是项目当前版本，并非最新版本声明。首次安装需要取得依赖；以下检查使用合成数据，不需要启动数据库、模型、容器或平台智能体。

```powershell
.\.venv-dev\Scripts\python.exe -X utf8 -m unittest discover -s tests -p test_acs_fixtures.py -v
.\.venv-dev\Scripts\python.exe -X utf8 -m unittest discover -s tests -p test_onboarding.py -v
.\.venv-dev\Scripts\python.exe -X utf8 -m unittest discover -s tests -p test_evaluation_reports.py -v
.\.venv-dev\Scripts\python.exe -X utf8 -m unittest discover -s tests -p test_evaluation_report_integrity.py -v
```

`artifacts` 是部分测试临时目录的父目录，需提前创建；Linux 对应 `mkdir -p artifacts`。图表检查需要报告依赖，缺少 Matplotlib 时不应把跳过图表检查视为已验证。上游 SDK 的 `pytest` 测试环境单独管理，不是本清单的项目测试入口。若选择全项目发现，文件模式应为 `*test*.py`，才能同时包含 `business_*_test.py`；本轮仅执行受影响测试，没有执行全仓测试。

`integration/incident/database.submission.acs.json` 和 `application.approved.acs.json` 是公开离线 fixture：身份未注册、`active=false`、端点为 `fixture.invalid`，没有证书、私钥或凭据。`approved` 仅保留旧测试文件名，不表示平台审批。AIC 格式和 ACS schema 校验不证明身份存在，也不测试运行端点。真实平台配置仍须由开发者使用自有身份另行生成。

真实数据库业务测试继续遵循 `BUSINESS_TEST_DATABASE` 的显式选择；本说明不启用它，也不改变执行策略、测试时限或故障授权。实际结果保存在本机 `artifacts/p0-continuation-20261019/test-env/`。

本轮受影响检查为 ACS/mapper/平台样例 9 项、报告与图表 14 项，共 23 项通过，0 跳过；保留补 fixture 前 5 项 `FileNotFoundError` 的原始记录。

随后按上述清单在本 checkout 的全新 `.venv-dev` 安装成功，`pip check` 通过，10 个依赖模块均从该新环境导入；ACS、正式 E1-b 辅助模块和报告模块可共同使用。此环境复验了 ACS fixture 1 项、E1-b fake/history 6 项、图表导出 1 项，8 项通过、0 跳过。这是同一批行为在新环境中的复验，不增加独立测试覆盖数；没有启动真实服务。安装与复验记录在上述证据目录的 `dev-environment/` 下。
