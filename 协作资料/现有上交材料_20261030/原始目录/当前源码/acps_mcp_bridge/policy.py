"""Allowlisted aliases and exact schemas form the remote execution boundary."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import json
from pathlib import Path
import re
import time

from jsonschema import Draft202012Validator


class PolicyRejected(ValueError):
    pass


@dataclass(frozen=True)
class AuthorizedCall:
    alias: str
    server: str
    tool: str
    risk: str
    arguments: dict
    specification: dict


class Policy:
    def __init__(self, document: dict, *, approval_verifier=None, clock=time.monotonic):
        self.document = document
        self.domain = document["domain"]
        self.allowed_callers = frozenset(document.get("allowed_callers", []))
        self.tools = document["tools"]
        self.resources = document.get("resources", {})
        scope_keys = ("compose_project", "compose_service", "container_name")
        present = [key in self.resources for key in scope_keys]
        self.container_scope = {}
        if any(present):
            if not all(present) or any(
                    not isinstance(self.resources[key], str)
                    or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", self.resources[key])
                    for key in scope_keys if key in self.resources):
                raise ValueError("container scope requires compose_project, compose_service and container_name")
            self.container_scope = {key: self.resources[key] for key in scope_keys}
        self.approval_verifier = approval_verifier
        self.clock = clock
        self._calls = defaultdict(deque)
        for alias, spec in self.tools.items():
            if not alias.startswith(self.domain + ".") or spec.get("risk") not in {"read", "write", "high"}:
                raise ValueError(f"Invalid tool policy {alias}")
            Draft202012Validator.check_schema(spec.get("input_schema", {}))

    @classmethod
    def load(cls, path, *, allowed_callers=None, **kwargs):
        import yaml
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if allowed_callers is not None:
            document["allowed_callers"] = list(allowed_callers)
        return cls(document, **kwargs)

    def authorize_caller(self, caller_aic: str):
        if caller_aic not in self.allowed_callers:
            raise PolicyRejected("caller_aic is not authorized for this resource domain")

    def authorize(self, payload: dict, caller_aic: str) -> AuthorizedCall:
        self.authorize_caller(caller_aic)
        alias = payload.get("tool")
        if not isinstance(alias, str) or alias not in self.tools:
            raise PolicyRejected("tool is not in the allowlist")
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
        key, now = (caller_aic, alias), self.clock()
        calls = self._calls[key]
        period = self.document.get("rate_limit", {}).get("window_seconds", 60)
        maximum = self.document.get("rate_limit", {}).get("max_calls", 60)
        while calls and calls[0] <= now - period:
            calls.popleft()
        if len(calls) >= maximum:
            raise PolicyRejected("rate limit exceeded")
        calls.append(now)
        arguments = dict(spec.get("fixed_arguments", {}))
        arguments.update(args)
        if "sql_template" in spec:
            # Only server-owned templates are formatted; remote arguments never supply SQL.
            arguments = {"sql": spec["sql_template"].format(**args)}
        if "argument_map" in spec:
            arguments = {spec["argument_map"].get(k, k): v for k, v in arguments.items()}
        return AuthorizedCall(alias, spec["server"], spec["mcp_tool"], risk, arguments, spec)

    def describe(self, inventory: dict[str, list[dict]]) -> dict:
        descriptions = []
        for alias, spec in self.tools.items():
            upstream = next((t for t in inventory.get(spec["server"], []) if t["name"] == spec["mcp_tool"]), None)
            if upstream:
                descriptions.append({"name": alias, "risk": spec["risk"], "description": spec["description"],
                                     "inputSchema": spec["input_schema"], "mcp_tool": spec["mcp_tool"]})
        return {"schema_version": "ifc/1.0", "interface_version": "1.0", "domain": self.domain,
                "resource_scope": self.resources, "skills": [f"{self.domain}.observe", f"{self.domain}.act"],
                "resources": sorted({self.resources[key] for key in ("database", "application", "resource")
                                     if isinstance(self.resources.get(key), str)}),
                "tools": descriptions}
