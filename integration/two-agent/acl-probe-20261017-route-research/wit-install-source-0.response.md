# 安装梧桐（wit）

wit `v2.1.0` 要求 CPython 3.12、3.13 或 3.14（`>=3.12,<3.15`），并通过发行目录中的 wheel 安装。完整的发行目录应包含以下三个相邻文件：

```text
<release_dir>/
├── acps_sdk-2.2.0-py3-none-any.whl
├── wit_framework-2.1.0-cp312.cp313.cp314-none-any.whl
└── release-manifest.json
```

这两个包独立发行，版本关系严格锁定：必须先安装 `acps-sdk 2.2.0`，再安装 `wit-framework 2.1.0`。SDK 缺失或版本不匹配时，wit 会直接停止导入。

## 环境准备

选择 conda 或 Python 自带的 `venv`。后续所有命令都要在同一个已激活环境中执行。

### Conda 环境

```bash
conda activate <env_name>
python --version
```

### Venv 环境

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python --version
```

`python --version` 应显示 Python 3.12、3.13 或 3.14。此 wheel 使用 CPython 字节码，不适用于 PyPy 或其他 Python 次版本。

## 安装 Wheel 包

```bash
cd <release_dir>
python -m pip install ./acps_sdk-2.2.0-py3-none-any.whl
python -m pip install ./wit_framework-2.1.0-cp312.cp313.cp314-none-any.whl
```

wit wheel 包会一并安装运行时依赖，包括 AMP Audit 签名所需的 `jcs` 与 `cryptography`。请保持上述安装顺序；`import wit` 会先检查 SDK 的发行版本和必需模块。

### 更新已安装的 2.1.0

如果环境里已经安装了旧版 2.1.0 wheel，需要强制重装才能替换同版本的文件。先确认 SDK 和运行依赖已安装，再执行：

```bash
python -m pip install --force-reinstall --no-deps ./wit_framework-2.1.0-cp312.cp313.cp314-none-any.whl
```

### IDE 中查看接口

此发行包提供 `.pyi` 接口声明，支持编辑器补全、参数提示和类型检查。跳转到接口时可查看签名和说明；Wit 实现以字节码交付，无法直接查看或单步进入原始源码。业务代码仍可正常调试。

### AIP Group 可选依赖

只有使用基于 RabbitMQ 的 AIP Group 时才需要 `acps-group` 可选依赖。将第二条安装命令替换为：

```bash
python -m pip install './wit_framework-2.1.0-cp312.cp313.cp314-none-any.whl[acps-group]'
```

该可选依赖会安装 `aio-pika`。单 Agent 与 AIP Direct 场景使用基础依赖包即可。

## 发行预检

```bash
wit-release-preflight --manifest release-manifest.json
```

> [!WARNING]
> `wit-release-preflight` 为安装流程中的必需校验步骤。完整验证 wheel、当前解释器与实际导入来源是否属于统一发行版。

发行预检会完成三类校验：

1. 校验 `release-manifest.json` 的结构、版本合同，以及相邻两个 wheel 的文件名、元数据和 SHA-256。
2. 校验当前 Python 环境中的精确发行版本、必需模块，以及 `acps_sdk` 和 `wit` 是否确实从该环境的 `site-packages/` 导入。
3. 创建一份临时 AIP SQLite 存储，关闭后重新打开，验证记录可读回且所有权约束仍然生效。

成功时命令会输出一行 JSON，其中包含 `acpsSdkVersion`、`witVersion` 和值为 `passed` 的 `aipPersistence`。

## 导入来源核对

```bash
python -c "from importlib.metadata import version; import acps_sdk, wit; print(version('acps-sdk'), acps_sdk.__file__); print(version('wit-framework'), wit.__file__)"
```

预期版本分别是 `2.2.0` 和 `2.1.0`，两个 `__file__` 都应位于当前环境的 `site-packages/` 中。这条命令便于定位环境问题，但不能替代发行预检对发行物哈希和持久化行为的校验。

## 常见故障

### `import wit` 提示先安装 SDK wheel

典型信息是：

```text
wit requires the bundled acps_sdk-2.2.0-py3-none-any.whl to be installed before importing wit; install that wheel first, then run wit-release-preflight.
```

它可能表示：

- 当前环境没有安装 `acps-sdk`；
- 安装的 SDK 版本不是精确的 `2.2.0`；
- SDK 缺少 `acps_sdk` 或 `acps_sdk.amp.models`；
- 你把 wheel 安装到了另一个 Python 环境。

重新确认环境已激活，然后先安装发行目录中的 SDK wheel，再安装 wit wheel，最后重跑 preflight。不要用 `acps-sdk>=2.2.0` 代替随包提供的精确版本。

### preflight 报 `site-packages: invalid`

当前 Python 导入了源码检出目录或另一个环境中的包。运行上面的手工核对命令，确认 `python`、`pip` 和两个包的 `__file__` 指向同一环境，然后在正确环境中重新安装。

### AIP Group 启动时缺少 RabbitMQ 客户端依赖

确认安装的是带 `[acps-group]` 的同一个 `wit_framework-2.1.0` wheel。该可选依赖只补充客户端组件；外部服务的完整职责边界见 [ACPs 总览](../acps/overview.md)。

