"""Bound F10/M0 wrapper retaining evaluation, close, restoration and H00 failures."""
from __future__ import annotations
import argparse
import asyncio
import logging
from pathlib import Path
import sys
import traceback
from types import SimpleNamespace

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "plan-preparation"))
import batch_scope as scope


def arguments(runner, plan):
    return runner.build_parser().parse_args([
        "--config", str(scope.local(plan["config"])), "--target-config", str(scope.local(plan["target_config"])),
        "--transport", "wutong-amqps", "--backend", "docker", "--scenarios", "F10", "--methods", "M0",
        "--repeats", "1", "--instance-seeds", "101", "--approve-high", "--output", str(scope.local(plan["output"]))])


def instrument_close(transport, e1, warnings, report):
    """Retain the original close handle; close_owned must never call this wrapper."""
    raw_close = transport.close
    called = False

    async def close():
        nonlocal called
        if called:
            raise RuntimeError("Never retry an already requested platform close")
        called = True
        # Resolve session/runtime when close is requested, after start populated them.
        facade = SimpleNamespace(session=transport.session, runtime=transport.runtime, close=raw_close)
        try:
            report["close_checks"] = await e1.close_owned(facade, warnings)
        except BaseException as error:
            report["close_error_class"] = type(error).__name__
            report["close_traceback"] = traceback.format_exc()
            raise
        finally:
            report["close_requested"] = True
    transport.close = close
    return transport


async def execute(plan, *, runner=None, observer_factory=None):
    e1, *_ = scope.product()
    if runner is None:
        from eval import run as runner
    if observer_factory is None:
        from business.load import OrderObserver
        observer_factory = OrderObserver
    output = scope.local(plan["output"])
    report = dict(case="F10", method="M0", model_calls=0, status="failed", close_requested=False)
    warnings = e1.CleanupWarnings()
    logger = logging.getLogger()
    logger.addHandler(warnings)
    original_factory = runner.create_transport
    created = []

    def create(*args, **kwargs):
        transport = instrument_close(original_factory(*args, **kwargs), e1, warnings, report)
        created.append(transport)
        return transport

    runner.create_transport = create
    try:
        try:
            report["evaluation_exit_code"] = await runner.run(arguments(runner, plan))
        except BaseException as error:
            report["evaluation_error_class"] = type(error).__name__
            report["evaluation_traceback"] = traceback.format_exc()
        finally:
            # eval.run normally closes in its finally. A failure before entering
            # that try still needs exactly one owned normal-close attempt.
            if created and not report["close_requested"]:
                try:
                    await created[0].close()
                except BaseException:
                    pass  # Full close error/traceback retained by the wrapper.
    finally:
        runner.create_transport = original_factory
        logger.removeHandler(warnings)
        report["cleanup_warning_events"] = list(warnings.events)
    if not created:
        report["close_error_class"] = "NoTransportCreatedOwnershipUnconfirmed"
    output.mkdir(parents=True, exist_ok=True)
    options = dict(backend="docker", target_config=scope.local(plan["target_config"]),
                   expected_sources={name: plan["file_sha256"][name] for name in runner.DOMAIN_SOURCE_FILES})
    record = output / "private/independent-restoration.jsonl"
    try:
        proof = await runner.inject("H00", "check", None, record, **options)
        options.update(expected_compose_hashes=proof["target_proof"]["compose_sha256"],
                       expected_domains=proof["target_proof"]["domains"])
        await runner.inject("F10", "restore", None, record, **options)
        report["resource_and_worker_restore"] = "completed"
    except BaseException as error:
        report["restore_error_class"] = type(error).__name__
        report["restore_traceback"] = traceback.format_exc()
    try:
        target = scope.deployment()[1]
        report["independent_final_H00"] = await observer_factory(target.order_url,
            run_id="access-validation-f10-final-H00", expected_api_version="v2").observe(duration=30, min_complete=10)
        if not e1.healthy(report["independent_final_H00"]):
            raise RuntimeError("Independent final H00 failed")
    except BaseException as error:
        report["H00_error_class"] = type(error).__name__
        report["H00_traceback"] = traceback.format_exc()
    rows = scope.load(output / "results.json") if (output / "results.json").exists() else []
    exact = (isinstance(rows, list) and len(rows) == 1 and rows[0].get("scenario") == "F10"
        and rows[0].get("method") == "M0" and rows[0].get("model_enabled") is False
        and type(rows[0].get("model_calls")) is int and rows[0]["model_calls"] == 0)
    if not exact:
        report["result_scope_error_class"] = "F10NoModelResultMismatch"
    if (report.get("evaluation_exit_code") == 0 and exact and len(report.get("close_checks", {})) == 6
            and all(report["close_checks"].values()) and not warnings.events
            and not any(key.endswith("error_class") for key in report)):
        report["status"] = "completed"
    scope.save(output / "wrapper-result.json", report)
    return 0 if report["status"] == "completed" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    # E1 outputs may be consumed only by earlier cases, never by this first case.
    summary, *_ = scope.validate_summary()
    if not args.execute:
        print('{"status":"VALIDATED_NOT_EXECUTED","case":"F10"}')
        return 0
    scope.validate_authorization(args.authorization_file, summary)
    plan = scope.validate_f10(scope.load(scope.local(summary["plans"][0]["plan"])))
    return asyncio.run(execute(plan))


if __name__ == "__main__":
    raise SystemExit(main())
