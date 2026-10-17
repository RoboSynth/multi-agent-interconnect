# `wit.acps.group.acl`

## `MqGroupAclError`

```python
MqGroupAclError(
    message: str,
    *,
    operation: str,
    retryable: bool,
    status_code: int | None = None,
    code: str | None = None,
) -> None
```

表示 MQ Group 授权 API 操作失败及其重试属性。

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `message` | `str` | 必填 | 错误消息。 |
| `operation` | `str` | 必填 | 失败操作；构造后可作为同名字段读取。 |
| `retryable` | `bool` | 必填 | 是否适合重试；构造后可作为同名字段读取。 |
| `status_code` | `int \| None` | `None` | HTTP 状态码；构造后可作为同名字段读取。 |
| `code` | `str \| None` | `None` | 服务端问题代码；构造后可作为同名字段读取。 |

## `MqGroupAclClient`

```python
MqGroupAclClient(
    *,
    base_url: str,
    local_aic: str,
    certificate_paths: CertificatePaths | MtlsClientPaths | None = None,
    request_timeout_seconds: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> None
```

通过 mTLS 调用 MQ 授权服务的 Leader-only Group API。

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `base_url` | `str` | 必填 | 无凭据、无路径参数的 HTTPS origin；规范化后保存在同名字段。 |
| `local_aic` | `str` | 必填 | 本地 Leader AIC；验证后保存在同名字段。 |
| `certificate_paths` | `CertificatePaths \| MtlsClientPaths \| None` | `None` | 创建内部客户端时必需的 mTLS 路径。 |
| `request_timeout_seconds` | `float` | `10.0` | 正数请求超时。 |
| `client` | `httpx.AsyncClient \| None` | `None` | 可注入的异步 HTTP 客户端。 |

### `add_member`

```python
async add_member(self, leader_aic: str, group_id: str, member_aic: str) -> None
```

授权成员访问 Leader Group。

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `leader_aic` | `str` | 必填 | 必须等于本地 AIC 的 Leader AIC。 |
| `group_id` | `str` | 必填 | Group 标识符。 |
| `member_aic` | `str` | 必填 | 待加入成员 AIC。 |

### `remove_member`

```python
async remove_member(self, leader_aic: str, group_id: str, member_aic: str) -> None
```

撤销成员的 Group 授权；服务端 404 按幂等成功处理。

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `leader_aic` | `str` | 必填 | 必须等于本地 AIC 的 Leader AIC。 |
| `group_id` | `str` | 必填 | Group 标识符。 |
| `member_aic` | `str` | 必填 | 待移除成员 AIC。 |

### `delete_group`

```python
async delete_group(self, leader_aic: str, group_id: str) -> None
```

删除 Group 授权资源；服务端 404 按幂等成功处理。

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `leader_aic` | `str` | 必填 | 必须等于本地 AIC 的 Leader AIC。 |
| `group_id` | `str` | 必填 | Group 标识符。 |

### `close_member_connection`

```python
async close_member_connection(
    self,
    leader_aic: str,
    group_id: str,
    member_aic: str,
) -> None
```

请求关闭指定成员的 Group MQ 连接。

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `leader_aic` | `str` | 必填 | 必须等于本地 AIC 的 Leader AIC。 |
| `group_id` | `str` | 必填 | Group 标识符。 |
| `member_aic` | `str` | 必填 | 成员 AIC。 |

### `aclose`

```python
async aclose(self) -> None
```

关闭由该对象自行创建的 HTTP 客户端。
