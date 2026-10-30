# 联枢当前源码快照

本目录用于队友接手当前实现与修复问题。它来自本轮实际工作树，保留未提交的有效源码；不含Git历史、旧报告、旧证据、运行状态、真实平台配置或密钥。

## 环境与依赖

建议使用Python 3.12。先在本目录创建独立虚拟环境，再安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

依赖清单包含本地vendor SDK。不要复用指向其他检出目录的editable SDK。数据库与Docker MCP运行环境分别按 domains/database/requirements.txt 和 domains/ops/requirements.txt 安装，避免两套MCP依赖相互覆盖。

## 本轮核心验证入口

与源码相邻的 `../测试记录/` 保存本轮新结果及可移植验证脚本。脚本默认定位本源码目录；新运行结果应指定一个尚不存在的输出目录。

```powershell
.\.venv\Scripts\python.exe -X utf8 -B ..\测试记录\run_current_validation.py --repo . --output ..\测试记录\队友核心复验 --check
.\.venv\Scripts\python.exe -X utf8 -B ..\测试记录\run_current_validation.py --repo . --output ..\测试记录\队友核心复验
.\.venv\Scripts\python.exe -X utf8 -B ..\测试记录\run_isolated_takeover.py --repo . --output ..\测试记录\队友进程复验
```

核心入口选择17个测试模块，共146项。本轮原运行记录为143通过、3错误；补充健康通道夹具诊断3项通过，原错误没有改判。进程入口覆盖观察后退出、修改前退出、修改后退出，资源是隔离JSON文件，不是正式平台或数据库。本源码快照不修复这些问题；修复后请在新目录保留独立结果。

完整 tests/ 还包含依赖历史归档或真实平台的检查，不能把全目录发现测试当成上述146项离线核心检查。旧归档不随此源码分发。

## 本地业务演示与正式平台

本地容器演示入口为 `python deploy/review.py up`，需可用的Docker，Windows也支持WSL中的Docker；该命令会构建并启动本地资源。正式平台部署另需各自AIC、证书、信任链、发现及群组认证配置。`.env.example` 与其他example文件仅供填写，快照不附真实凭据。

## 来源与脱敏

`SOURCE-SNAPSHOT.json`列出每份文件的相对路径、来源哈希、副本哈希及排除规则。核心算法按当前内容复制；仅一个平台测试的真实AIC替换为合成测试身份；带真实外部目标及旧运行依赖的单次调用辅助脚本已排除。第三方许可证原文保留。此目录没有上传，也不自动推送或发布。
