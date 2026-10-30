# policy_70-88_写入与审批检查

源文件：`acps_mcp_bridge/policy.py`，第 70–88 行。

校验参数与风险类型，并要求写入控制字段和高风险审批。

```python
        spec = self.tools[alias]
        args = payload.get("args", {})
        if not isinstance(args, dict):
            raise PolicyRejected("args must be an object")
        errors = sorted(Draft202012Validator(spec["input_schema"]).iter_errors(args), key=lambda e: str(e.path))
        if errors:
            raise PolicyRejected("arguments do not match the registered tool schema")
        risk = spec["risk"]
        if payload.get("kind") != ("observe" if risk == "read" else "act"):
            raise PolicyRejected("task kind does not match tool risk")
        if risk != "read":
            if not isinstance(payload.get("operation_id"), str) or not payload["operation_id"].strip():
                raise PolicyRejected("write/high tools require operation_id")
            fence = payload.get("fence")
            if (not isinstance(fence, dict) or set(fence) != {"coordinator_term", "takeover_version"}
                    or any(type(v) is not int or v < 0 for v in fence.values())):
                raise PolicyRejected("write/high tools require a valid fence")
        if risk == "high" and (not self.approval_verifier or not self.approval_verifier(payload, caller_aic)):
            raise PolicyRejected("high risk tool requires a valid independent approval proof")
```
