# `wit.acps.infrastructure`

## `AcpsRegistration`

```python
AcpsRegistration(*, kind: AcpsRegistrationKind = "integrated", ontology_workspace: Path | None = None) -> None
```

选择一体化、ontology 或 entity ATR 注册流程。

|字段|类型|默认值|说明|
|---|---|---|---|
|`kind`|`AcpsRegistrationKind`|`"integrated"`|注册种类。|
|`ontology_workspace`|`Path | None`|`None`|仅 entity 注册使用的 ontology 工作区。|

### `integrated` / `ontology`

```python
@classmethod
def integrated(cls) -> "AcpsRegistration"

@classmethod
def ontology(cls) -> "AcpsRegistration"
```

分别创建一体化实体注册和仅 ontology 注册选择。

|返回值|类型|说明|
|---|---|---|
|返回值|`AcpsRegistration`|相应种类的注册选择。|

### `entity`

```python
@classmethod
def entity(cls, *, ontology_workspace: str | Path) -> "AcpsRegistration"
```

创建以既有 ontology 身份派生运行实体的选择。

|参数|类型|默认值|说明|
|---|---|---|---|
|`ontology_workspace`|`str | Path`|—|已激活 ontology 工作区。|
|返回值|`AcpsRegistration`|—|entity 注册选择。|

### `to_dict`

```python
def to_dict(self) -> dict[str, str | None]
```

输出可持久化的注册选择。

|返回值|类型|说明|
|---|---|---|
|返回值|`dict[str, str | None]`|含 `kind` 和 `ontologyWorkspace`。|

## `AcpsConfig`

```python
AcpsConfig(*, registry_url: str, registry_mtls_url: str | None = None, ca_url: str, discovery_url: str, public_endpoint: str | None = None, mq_url: str | None = None, mq_group_api_url: str | None = None, provider: AgentProviderProfile | None = None, certificate: AgentCertificateRequest | None = None, certificate_key_algorithm: CertificateKeyAlgorithm = "ed25519", icon_url: str | None = None, documentation_url: str | None = None, web_app_url: str | None = None, entity_user_id: str | None = None, entity_meta: Mapping[str, Any] = field(default_factory=dict), acs_path: Path | None = None, strict_interop: bool = True, notification_callback_origins: tuple[str, ...] = (), request_timeout_seconds: float = 30.0, group_invitation_ttl_seconds: int = 300, group_status_interval_seconds: float = 15.0, group_offline_timeout_seconds: float = 45.0, group_queue_expires_seconds: int = 60 * 24 * 60 * 60, group_message_ttl_seconds: int = 7 * 24 * 60 * 60, group_acl_refresh_seconds: int = 24 * 60 * 60, group_consumer_prefetch: int = 32, group_rpc_invitation_fallback: bool = False, registration: AcpsRegistration = field(default_factory=AcpsRegistration.integrated)) -> None
```

集中保存基础设施地址、ACS 输入和 Group 运行参数。

|字段|类型|默认值|说明|
|---|---|---|---|
|`registry_url`、`ca_url`、`discovery_url`|`str`|—|三个服务的基础 URL。|
|`registry_mtls_url`、`public_endpoint`|`str | None`|`None`|mTLS Registry URL 与公开端点。|
|`mq_url`、`mq_group_api_url`|`str | None`|`None`|成对的 MQ 与 Group API 地址。|
|`provider`、`certificate`|相应绑定类型或 `None`|`None`|生成 ACS 的输入。|
|`certificate_key_algorithm`|`CertificateKeyAlgorithm`|`"ed25519"`|证书私钥算法。|
|`icon_url`、`documentation_url`、`web_app_url`|`str | None`|`None`|ACS 展示链接。|
|`entity_user_id`、`entity_meta`|`str | None`、`Mapping[str, Any]`|`None`、空映射|实体字段。|
|`acs_path`|`Path | None`|`None`|显式 ACS 文件。|
|`strict_interop`|`bool`|`True`|严格 HTTPS/AMQPS 验证。|
|`notification_callback_origins`|`tuple[str, ...]`|`()`|通知回调 HTTPS origins。|
|`request_timeout_seconds`|`float`|`30.0`|请求超时。|
|`group_*`|`int` / `float` / `bool`|见签名|邀请、状态、队列、ACL、预取与回退参数。|
|`registration`|`AcpsRegistration`|`AcpsRegistration.integrated()`|注册流程。|

### 派生 URL 属性

```python
@property
def registry_api_url(self) -> str

@property
def registry_atr_url(self) -> str

@property
def registry_mtls_atr_url(self) -> str

@property
def ca_atr_url(self) -> str
```

派生 Registry API、Registry ATR、Registry mTLS ATR 和 CA ATR URL；未配置 mTLS URL 时第三项抛出 `RuntimeError`。

|返回值|类型|说明|
|---|---|---|
|属性值|`str`|对应派生 URL。|

### `to_dict` / `acs_overrides` / `load_acs`

```python
def to_dict(self) -> dict[str, object]

def acs_overrides(self) -> dict[str, Any]

def load_acs(self) -> dict[str, Any] | None
```

导出完整配置、生成 ACS 覆盖字段，或读取验证显式 ACS。

|方法|返回值|说明|
|---|---|---|
|`to_dict`|`dict[str, object]`|配置的可序列化表示。|
|`acs_overrides`|`dict[str, Any]`|用户指定的 ACS 字段。|
|`load_acs`|`dict[str, Any] | None`|规范化显式 ACS；未配置路径时为 `None`。|

### `ioa_pub`

```python
@classmethod
def ioa_pub(cls, *, provider: AgentProviderProfile | None = None, certificate: AgentCertificateRequest | None = None, certificate_key_algorithm: CertificateKeyAlgorithm = "ed25519", icon_url: str | None = None, documentation_url: str | None = None, web_app_url: str | None = None, entity_user_id: str | None = None, entity_meta: Mapping[str, Any] | None = None, acs_path: str | Path | None = None, public_endpoint: str | None = None, mq_url: str | None = None, mq_group_api_url: str | None = None, notification_callback_origins: tuple[str, ...] = (), request_timeout_seconds: float = 30.0, group_invitation_ttl_seconds: int = 300, group_status_interval_seconds: float = 15.0, group_offline_timeout_seconds: float = 45.0, group_queue_expires_seconds: int = 60 * 24 * 60 * 60, group_message_ttl_seconds: int = 7 * 24 * 60 * 60, group_acl_refresh_seconds: int = 24 * 60 * 60, group_consumer_prefetch: int = 32, group_rpc_invitation_fallback: bool = False, registration: AcpsRegistration | None = None) -> "AcpsConfig"
```

以 ioa.pub 固定基础设施地址构造严格互操作配置。

|参数|类型|默认值|说明|
|---|---|---|---|
|`provider` 至 `registration`|见签名|见签名|同名 `AcpsConfig` 输入。|
|返回值|`AcpsConfig`|—|ioa.pub 配置。|

### `custom`

```python
@classmethod
def custom(cls, *, registry_url: str, registry_mtls_url: str | None = None, ca_url: str, discovery_url: str, provider: AgentProviderProfile | None = None, certificate: AgentCertificateRequest | None = None, certificate_key_algorithm: CertificateKeyAlgorithm = "ed25519", icon_url: str | None = None, documentation_url: str | None = None, web_app_url: str | None = None, entity_user_id: str | None = None, entity_meta: Mapping[str, Any] | None = None, acs_path: str | Path | None = None, public_endpoint: str | None = None, mq_url: str | None = None, mq_group_api_url: str | None = None, strict_interop: bool = True, notification_callback_origins: tuple[str, ...] = (), request_timeout_seconds: float = 30.0, group_invitation_ttl_seconds: int = 300, group_status_interval_seconds: float = 15.0, group_offline_timeout_seconds: float = 45.0, group_queue_expires_seconds: int = 60 * 24 * 60 * 60, group_message_ttl_seconds: int = 7 * 24 * 60 * 60, group_acl_refresh_seconds: int = 24 * 60 * 60, group_consumer_prefetch: int = 32, group_rpc_invitation_fallback: bool = False, registration: AcpsRegistration | None = None) -> "AcpsConfig"
```

以调用方提供的服务地址构造配置。

|参数|类型|默认值|说明|
|---|---|---|---|
|`registry_url`、`ca_url`、`discovery_url`|`str`|—|必须提供的服务 URL。|
|其余参数|见签名|见签名|同名 `AcpsConfig` 输入。|
|返回值|`AcpsConfig`|—|自定义配置。|

### `from_env`

```python
@classmethod
def from_env(cls, environ: Mapping[str, str] | None = None, *, provider: AgentProviderProfile | None = None, certificate: AgentCertificateRequest | None = None, icon_url: str | None = None, documentation_url: str | None = None, web_app_url: str | None = None, entity_user_id: str | None = None, entity_meta: Mapping[str, Any] | None = None, acs_path: str | Path | None = None, notification_callback_origins: tuple[str, ...] = (), registration: AcpsRegistration | None = None) -> "AcpsConfig"
```

根据 `ACPS_PROFILE` 和环境变量创建 ioa.pub 或 custom 配置。

|参数|类型|默认值|说明|
|---|---|---|---|
|`environ`|`Mapping[str, str] | None`|`None`|环境来源；空值使用 `os.environ`。|
|其余参数|见签名|见签名|ACS 和注册输入。|
|返回值|`AcpsConfig`|—|环境解析后的配置。|

## `AcpsEnrollmentConfig`

```python
AcpsEnrollmentConfig(acps: AcpsConfig, state_dir: Path, token_path: Path, client_certificate_dir: Path, server_certificate_dir: Path, final_acs_path: Path, aip_task_store_path: Path, aip_group_store_path: Path, request_timeout_seconds: float = 30.0) -> None
```

描述一个工作区的注册状态、证书、ACS 与 AIP 存储布局。

|字段|类型|默认值|说明|
|---|---|---|---|
|`acps`|`AcpsConfig`|—|基础设施配置。|
|`state_dir` 至 `aip_group_store_path`|`Path`|—|状态、令牌、证书、ACS 与 AIP 存储路径。|
|`request_timeout_seconds`|`float`|`30.0`|注册请求超时。|

### `for_workspace`

```python
@classmethod
def for_workspace(cls, *, workspace: Path, acps: AcpsConfig) -> "AcpsEnrollmentConfig"
```

根据工作区约定生成路径布局。

|参数|类型|默认值|说明|
|---|---|---|---|
|`workspace`|`Path`|—|wit 工作区。|
|`acps`|`AcpsConfig`|—|基础设施配置。|
|返回值|`AcpsEnrollmentConfig`|—|路径配置。|
