"""Configure local routing and an optional key-free loopback model."""
import argparse
import ipaddress
from pathlib import Path
import json
import math
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
MODEL_DEFAULTS = {
    "llm_base_url": "http://127.0.0.1:8089/v1",
    "llm_model": "Qwen3-1.7B-Q8_0",
    "llm_max_output_tokens": 768,
    "llm_max_calls": 40,
    "llm_token_budget": 65536,
    "llm_timeout_seconds": 60,
}


def local_model_settings(document):
    """Validate persisted local settings without reading environment or networking."""
    enabled = document.get("llm_enabled", False)
    if type(enabled) is not bool:
        raise ValueError("llm_enabled must be a boolean")
    for key in ("llm_base_url", "llm_model"):
        value = document.get(key)
        if enabled and (not isinstance(value, str) or not value.strip()):
            raise ValueError("Enabled local model requires persisted " + key)
        if value is not None and not isinstance(value, str):
            raise ValueError(key + " must be a string")
    base_url = (document.get("llm_base_url") or MODEL_DEFAULTS["llm_base_url"]).strip() or MODEL_DEFAULTS["llm_base_url"]
    model = (document.get("llm_model") or MODEL_DEFAULTS["llm_model"]).strip() or MODEL_DEFAULTS["llm_model"]
    if enabled:
        parsed = urlsplit(base_url)
        try:
            loopback = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname or "").is_loopback
        except ValueError:
            loopback = False
        try:
            parsed.port
        except ValueError as error:
            raise ValueError("Local model endpoint has an invalid port") from error
        if (parsed.scheme not in {"http", "https"} or not loopback or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment):
            raise ValueError("Enabled local model endpoint must be a credential-free loopback HTTP URL")
    settings = {"enabled": enabled, "base_url": base_url, "model": model}
    for source, target in (("llm_max_output_tokens", "max_output_tokens"), ("llm_max_calls", "max_calls"),
                           ("llm_token_budget", "token_budget")):
        value = document.get(source, MODEL_DEFAULTS[source])
        if type(value) is not int or value < 1:
            raise ValueError(source + " must be a positive integer")
        settings[target] = value
    timeout = document.get("llm_timeout_seconds", MODEL_DEFAULTS["llm_timeout_seconds"])
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("llm_timeout_seconds must be a positive finite number")
    settings["timeout_seconds"] = timeout
    return settings


def default_document():
    workers = [
        {"name": "应用团队", "role": "application", "aic": "local-application",
         "env_file": "runtime/private/application.env", "base_url": "http://127.0.0.1:8082"},
        {"name": "数据库主", "role": "database", "aic": "local-database-primary",
         "env_file": "runtime/private/database-bridge.env", "bridge_config": "runtime/database-bridge.json"},
        {"name": "数据库备", "role": "database", "aic": "local-database-backup", "standby": True,
         "env_file": "runtime/private/database-bridge.env", "bridge_config": "runtime/database-backup-bridge.json"},
        {"name": "运维团队", "role": "ops", "aic": "local-ops",
         "env_file": "runtime/private/ops-bridge.env", "bridge_config": "runtime/ops-bridge.json"},
        {"name": "业务验证", "role": "verification", "aic": "local-verification",
         "base_url": "http://127.0.0.1:8088", "verification_duration": 30},
    ]
    return {"mode": "local-aip-stdio", "coordinator_aic": "local-coordinator", "python": sys.executable,
                "journal_path": "runtime/coordinator-journal.sqlite", "amp_directory": "artifacts/local-aip/amp",
                "term_journal_path": "runtime/coordinator-terms.sqlite",
                "approval_env_file": "runtime/private/approval.env", "llm_enabled": False, "workers": workers}


def configure(config_path=None, *, enable_llm=None, model_base_url=None, model=None,
              max_output_tokens=None, model_call_budget=None, model_token_budget=None,
              model_timeout_seconds=None, check=False):
    path = Path(config_path or ROOT / "runtime/local-coordinator.json")
    document = default_document()
    existing = None
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(existing, dict):
            raise ValueError("Coordinator configuration must be a JSON object")
        document.update(existing)
    changes = {"llm_base_url": model_base_url, "llm_model": model,
        "llm_max_output_tokens": max_output_tokens, "llm_max_calls": model_call_budget,
        "llm_token_budget": model_token_budget, "llm_timeout_seconds": model_timeout_seconds}
    local = document.get("mode", "local-aip-stdio") == "local-aip-stdio"
    if not local and (enable_llm is not None or any(value is not None for value in changes.values())):
        raise ValueError("These model options configure only local-aip-stdio")
    if enable_llm is not None:
        document["llm_enabled"] = enable_llm
        if enable_llm:
            for name, value in MODEL_DEFAULTS.items():
                document.setdefault(name, value)
    document.update({name: value for name, value in changes.items() if value is not None})
    if local:
        local_model_settings(document)
    if check or document == existing:
        return document
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return document


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "runtime/local-coordinator.json")
    parser.add_argument("--check", action="store_true", help="Validate only; never create directories or write configuration")
    enabled = parser.add_mutually_exclusive_group()
    enabled.add_argument("--enable-llm", dest="enable_llm", action="store_true", default=None,
        help="Explicit local model opt-in; missing settings use the local Qwen defaults")
    enabled.add_argument("--disable-llm", dest="enable_llm", action="store_false", default=None)
    parser.add_argument("--model-base-url")
    parser.add_argument("--model")
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--model-call-budget", type=int)
    parser.add_argument("--model-token-budget", type=int)
    parser.add_argument("--model-timeout-seconds", type=float)
    args = parser.parse_args()
    document = configure(args.config, enable_llm=args.enable_llm, model_base_url=args.model_base_url,
        model=args.model, max_output_tokens=args.max_output_tokens, model_call_budget=args.model_call_budget,
        model_token_budget=args.model_token_budget, model_timeout_seconds=args.model_timeout_seconds, check=args.check)
    print(json.dumps({"status": "CONFIGURATION_CHECKED" if args.check else "CONFIGURATION_READY",
        "config": str(args.config), "mode": document.get("mode", "local-aip-stdio"),
        "llm_enabled": document.get("llm_enabled", False)}, ensure_ascii=False))
