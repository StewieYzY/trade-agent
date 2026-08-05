from __future__ import annotations

import json
import hashlib
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.provider_qualification import (  # noqa: E402
    ProbeCase,
    ProviderAdapter,
    QualificationRunner,
    _redact_error,
    build_parser,
)
import scripts.provider_qualification as qualification_module  # noqa: E402


def _case(method: str = "quote") -> ProbeCase:
    return ProbeCase(
        ticker="600519.SH",
        market="SH",
        security_type="consumer",
        method=method,
        fields=("last_price",),
    )


def _isolated_runner(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    timeout: float = 0.2,
    stop_policy: str = "continue",
    cases: list[ProbeCase] | None = None,
) -> dict:
    monkeypatch.setenv("PROVIDER_HEALTH_MODE", mode)
    monkeypatch.setenv("PROVIDER_HEALTH_SLEEP_SECONDS", "1")
    runner = QualificationRunner(
        adapter_module="tests.provider_health_adapters",
        cases=cases or [_case()],
        execution_mode="isolated",
        case_timeout_seconds=timeout,
        stop_policy=stop_policy,
    )
    return runner.run(output_root=tmp_path, run_id=f"health-{mode}")


def test_execution_options_reject_invalid_values(tmp_path):
    with pytest.raises(ValueError, match="execution_mode"):
        QualificationRunner(
            adapters=[],
            cases=[_case()],
            execution_mode="threads",
        )
    with pytest.raises(ValueError, match="timeout"):
        QualificationRunner(
            adapters=[],
            cases=[_case()],
            case_timeout_seconds=0,
        )
    with pytest.raises(ValueError, match="stop_policy"):
        QualificationRunner(
            adapters=[],
            cases=[_case()],
            stop_policy="retry",
        )


def test_isolated_case_completes_and_writes_terminal_event(
    tmp_path,
    monkeypatch,
):
    result = _isolated_runner(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        mode="fast",
        timeout=2,
    )

    manifest = result["manifest"]
    assert manifest["completion_status"] == "completed"
    assert manifest["execution_mode"] == "isolated"
    assert manifest["completed_cases"] == 1
    assert manifest["not_started_cases"] == 0
    event = json.loads(
        (tmp_path / "health-fast" / "events.ndjson").read_text().splitlines()[0]
    )
    assert event["status"] == "available"
    assert event["execution_mode"] == "isolated"
    assert event["elapsed_seconds"] >= 0
    assert (tmp_path / "health-fast" / "evidence.json").exists()


def test_timeout_continues_and_never_claims_completed(tmp_path, monkeypatch):
    result = _isolated_runner(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        mode="slow",
        timeout=0.05,
        cases=[_case("quote"), _case("calc_indexes")],
    )

    manifest = result["manifest"]
    assert manifest["completion_status"] == "incomplete"
    assert manifest["timed_out_cases"] == 2
    assert manifest["not_started_cases"] == 0
    assert manifest["stop_reason"] == "completed_with_timeout"
    assert manifest["stop_reasons"] == []
    events = [
        json.loads(line)
        for line in (tmp_path / "health-slow" / "events.ndjson")
        .read_text()
        .splitlines()
    ]
    assert len(events) == 2
    assert all(event["failure_class"] == "timeout" for event in events)
    assert all(event["terminated"] is True for event in events)
    assert not (tmp_path / "health-slow" / "evidence.json").exists()


def test_timeout_stop_policy_leaves_not_started_cases_explicit(
    tmp_path,
    monkeypatch,
):
    result = _isolated_runner(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        mode="slow",
        timeout=0.05,
        stop_policy="stop_on_timeout",
        cases=[_case("quote"), _case("calc_indexes")],
    )

    manifest = result["manifest"]
    assert manifest["completion_status"] == "incomplete"
    assert manifest["timed_out_cases"] == 1
    assert manifest["not_started_cases"] == 1
    assert manifest["stop_reason"] == "timeout"
    assert manifest["stop_reasons"] == ["timeout"]
    assert len(
        (tmp_path / "health-slow" / "events.ndjson").read_text().splitlines()
    ) == 1


def test_interruptible_adapter_is_terminated_by_timeout(tmp_path, monkeypatch):
    result = _isolated_runner(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        mode="interruptible",
        timeout=0.05,
    )

    manifest = result["manifest"]
    assert manifest["completion_status"] == "incomplete"
    assert manifest["timed_out_cases"] == 1
    event = json.loads(
        (tmp_path / "health-interruptible" / "events.ndjson")
        .read_text()
        .splitlines()[0]
    )
    assert event["failure_class"] == "timeout"
    assert event["terminated"] is True


def test_abrupt_child_exit_is_not_misclassified_as_timeout(tmp_path, monkeypatch):
    result = _isolated_runner(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        mode="crashing",
        timeout=1,
    )

    manifest = result["manifest"]
    assert manifest["timed_out_cases"] == 0
    event = json.loads(
        (tmp_path / "health-crashing" / "events.ndjson")
        .read_text()
        .splitlines()[0]
    )
    assert event["status"] == "source_failed"
    assert event["failure_class"] == "child_exit"
    assert "17" in event["reason"]


def test_manifest_records_code_dirty_state_and_fingerprint(tmp_path):
    result = QualificationRunner(
        adapters=[
            ProviderAdapter(
                "fixture",
                "direct",
                invoke=lambda _case: {
                    "last_price": 1.0,
                    "_fields": {
                        "last_price": {
                            "unit": "CNY/share",
                            "as_of": "2026-08-05",
                        }
                    },
                },
            )
        ],
        cases=[_case()],
        execution_mode="direct",
    ).run(output_root=tmp_path, run_id="health-provenance")

    manifest = result["manifest"]
    assert isinstance(manifest["code_dirty"], bool)
    assert len(manifest["code_diff_hash"]) == 64


def test_code_fingerprint_excludes_non_runtime_untracked_files(monkeypatch):
    def fake_check_output(args, **kwargs):
        if args[:2] == ["git", "rev-parse"]:
            return "head\n"
        if args[:2] == ["git", "status"]:
            return (
                " M value-screener/scripts/provider_qualification.py\n"
                "?? design/handoff.md\n"
                "?? value-screener/tests/test_provider_health.py\n"
            )
        if args[:3] == ["git", "diff", "HEAD"]:
            return b"RUNTIME_DIFF"
        raise AssertionError(args)

    monkeypatch.setattr(
        qualification_module.subprocess,
        "check_output",
        fake_check_output,
    )

    provenance = qualification_module._code_provenance()

    assert provenance["code_dirty"] is True
    assert provenance["code_diff_hash"] == hashlib.sha256(
        b"RUNTIME_DIFF"
    ).hexdigest()


def test_manifest_distinguishes_case_and_field_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_HEALTH_MODE", "fast")
    case = ProbeCase(
        ticker="600519.SH",
        market="SH",
        security_type="consumer",
        method="quote",
        fields=("last_price", "pe_ttm"),
    )
    result = QualificationRunner(
        adapter_module="tests.provider_health_adapters",
        cases=[case],
        execution_mode="isolated",
        case_timeout_seconds=2,
    ).run(output_root=tmp_path, run_id="health-counts")

    manifest = result["manifest"]
    assert manifest["case_status_counts"] == {"available": 1}
    assert manifest["field_status_counts"] == {"available": 2}


def test_incomplete_manifest_marks_aggregate_artifacts_not_written(
    tmp_path,
    monkeypatch,
):
    result = _isolated_runner(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        mode="slow",
        timeout=0.05,
    )

    artifact_status = result["manifest"]["artifact_status"]
    assert artifact_status["plan"] == "written"
    assert artifact_status["events"] == "written"
    assert artifact_status["manifest"] == "written"
    assert artifact_status["evidence"] == "not_written"
    assert artifact_status["raw"] == "not_written"
    assert artifact_status["comparison"] == "not_written"
    assert artifact_status["method_results"] == "not_written"


@pytest.mark.parametrize(
    "message",
    [
        "Authorization=Bearer secret-token",
        "access_token=secret-token",
        "client_secret=secret-token",
        "password=secret-token",
        "passwd=secret-token",
        "refresh_token=secret-token",
    ],
)
def test_redaction_covers_assignment_style_credentials(message):
    redacted = _redact_error(message)

    assert "secret-token" not in redacted


def test_production_output_roots_are_rejected(tmp_path):
    production_root = Path(__file__).resolve().parents[2] / "watchlist"
    runner = QualificationRunner(
        adapters=[
            ProviderAdapter(
                "fixture",
                "direct",
                invoke=lambda _case: {},
            )
        ],
        cases=[_case()],
        execution_mode="direct",
    )

    with pytest.raises(ValueError, match="production output root"):
        runner.run(output_root=production_root, run_id="health-protected")


def test_run_id_cannot_resolve_to_production_output_root(monkeypatch):
    repo_root = Path(__file__).resolve().parents[2]
    protected_run_dir = repo_root / "watchlist"
    original_mkdir = Path.mkdir

    def guarded_mkdir(path, *args, **kwargs):
        if path.resolve() == protected_run_dir.resolve():
            raise AssertionError("attempted to create a production run directory")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", guarded_mkdir)
    runner = QualificationRunner(
        adapters=[
            ProviderAdapter(
                "fixture",
                "direct",
                invoke=lambda _case: {},
            )
        ],
        cases=[_case()],
        execution_mode="direct",
    )

    with pytest.raises(ValueError, match="production output root"):
        runner.run(output_root=repo_root, run_id="watchlist")


def test_empty_adapter_registry_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_HEALTH_MODE", "empty")

    result = QualificationRunner(
        adapter_module="tests.provider_health_adapters",
        cases=[_case()],
        execution_mode="isolated",
    ).run(output_root=tmp_path, run_id="health-empty")

    assert result["manifest"]["completion_status"] == "incomplete"
    assert result["manifest"]["stop_reason"] == "adapter_load_failed"
    assert not (Path(result["run_dir"]) / "evidence.json").exists()


def test_factory_failure_is_redacted_and_run_scoped(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("PROVIDER_HEALTH_MODE", "factory_failure")

    result = QualificationRunner(
        adapter_module="tests.provider_health_adapters",
        cases=[_case()],
        execution_mode="isolated",
    ).run(output_root=tmp_path, run_id="health-factory-failure")

    manifest = result["manifest"]
    assert manifest["completion_status"] == "incomplete"
    assert manifest["stop_reason"] == "adapter_load_failed"
    assert "secret-token" not in json.dumps(manifest)


def test_isolated_adapter_factory_hang_is_bounded_and_run_scoped(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("PROVIDER_HEALTH_MODE", "factory_hang")
    monkeypatch.setenv("PROVIDER_HEALTH_SLEEP_SECONDS", "1")
    started = time.monotonic()

    result = QualificationRunner(
        adapter_module="tests.provider_health_adapters",
        cases=[_case()],
        execution_mode="isolated",
        case_timeout_seconds=0.05,
        adapter_load_timeout_seconds=0.05,
    ).run(output_root=tmp_path, run_id="health-factory-hang")

    assert time.monotonic() - started < 0.5
    assert result["manifest"]["completion_status"] == "incomplete"
    assert result["manifest"]["stop_reason"] == "adapter_load_failed"
    assert "timeout" in result["manifest"]["adapter_load_error"]


def test_case_timeout_does_not_limit_isolated_adapter_discovery(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("PROVIDER_HEALTH_MODE", "fast")

    result = QualificationRunner(
        adapter_module="tests.provider_health_adapters",
        cases=[_case()],
        execution_mode="isolated",
        case_timeout_seconds=0.000001,
    ).run(output_root=tmp_path, run_id="health-short-case-timeout")

    assert result["manifest"]["provider_count"] == 1
    assert result["manifest"]["adapter_load_error"] is None
    assert result["manifest"]["timed_out_cases"] == 1


def test_sigterm_preserves_incomplete_manifest(tmp_path):
    code = f"""
import os
import signal
import threading
import time
from pathlib import Path

from scripts.provider_qualification import (
    ProbeCase,
    ProviderAdapter,
    QualificationRunner,
)

case = ProbeCase(
    ticker="600519.SH",
    market="SH",
    security_type="consumer",
    method="quote",
    fields=("last_price",),
)

def invoke(_case):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        time.sleep(0.01)
    return {{"last_price": 1.0, "_fields": {{"last_price": {{"unit": "CNY/share"}}}}}}

threading.Timer(
    0.1,
    lambda: os.kill(os.getpid(), signal.SIGTERM),
).start()
QualificationRunner(
    adapters=[ProviderAdapter("fixture", "direct", invoke=invoke)],
    cases=[case, case],
    execution_mode="direct",
).run(
    output_root=Path({str(tmp_path)!r}),
    run_id="health-sigterm",
)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "value-screener"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads(
        (tmp_path / "health-sigterm" / "manifest.json").read_text()
    )
    assert manifest["completion_status"] == "incomplete"
    assert manifest["stop_reason"] == "terminated"
    assert manifest["interrupted_cases"] == 1


def test_isolated_sigterm_preserves_incomplete_manifest(tmp_path):
    code = f"""
import os
import signal
import threading
from pathlib import Path

from scripts.provider_qualification import ProbeCase, QualificationRunner

case = ProbeCase(
    ticker="600519.SH",
    market="SH",
    security_type="consumer",
    method="quote",
    fields=("last_price",),
)
os.environ["PROVIDER_HEALTH_MODE"] = "interruptible"
threading.Timer(
    0.5,
    lambda: os.kill(os.getpid(), signal.SIGTERM),
).start()
QualificationRunner(
    adapter_module="tests.provider_health_adapters",
    cases=[case, case],
    execution_mode="isolated",
    case_timeout_seconds=5,
).run(
    output_root=Path({str(tmp_path)!r}),
    run_id="health-isolated-sigterm",
)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "value-screener"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    run_dir = tmp_path / "health-isolated-sigterm"
    manifest = json.loads((run_dir / "manifest.json").read_text())
    event = json.loads((run_dir / "events.ndjson").read_text().splitlines()[0])
    assert manifest["completion_status"] == "incomplete"
    assert manifest["stop_reason"] == "terminated"
    assert manifest["interrupted_cases"] == 1
    assert event["failure_class"] == "interrupted"


def test_callable_not_evaluable_provider_does_not_claim_no_runtime_adapter(
    tmp_path,
):
    result = QualificationRunner(
        adapters=[
            ProviderAdapter(
                "fixture",
                "callable",
                invoke=lambda _case: {
                    "last_price": 1.0,
                    "_fields": {},
                },
            )
        ],
        cases=[_case()],
        execution_mode="direct",
    ).run(output_root=tmp_path, run_id="health-not-evaluable")

    assert result["manifest"]["completion_status"] == "completed"
    assert result["manifest"]["stop_reason"] is None
    assert result["manifest"]["status_counts"] == {"not_evaluated": 1}


def test_interrupted_event_records_elapsed_time(tmp_path):
    code = f"""
import os
import signal
import threading
import time
from pathlib import Path

from scripts.provider_qualification import ProbeCase, ProviderAdapter, QualificationRunner

case = ProbeCase(
    ticker="600519.SH",
    market="SH",
    security_type="consumer",
    method="quote",
    fields=("last_price",),
)
def invoke(_case):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        time.sleep(0.01)
    return {{"last_price": 1.0, "_fields": {{"last_price": {{"unit": "CNY/share"}}}}}}
threading.Timer(
    0.1,
    lambda: os.kill(os.getpid(), signal.SIGTERM),
).start()
QualificationRunner(
    adapters=[ProviderAdapter("fixture", "direct", invoke=invoke)],
    cases=[case],
    execution_mode="direct",
).run(output_root=Path({str(tmp_path)!r}), run_id="health-interrupt-elapsed")
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "value-screener"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    event = json.loads(
        (
            tmp_path / "health-interrupt-elapsed" / "events.ndjson"
        ).read_text().splitlines()[0]
    )
    assert event["failure_class"] == "interrupted"
    assert event["elapsed_seconds"] > 0


def test_explicit_empty_adapter_list_fails_closed(tmp_path):
    runner = QualificationRunner(adapters=[], cases=[_case()])

    with pytest.raises(ValueError, match="at least one provider adapter"):
        runner.run(output_root=tmp_path, run_id="health-empty")


def test_incomplete_run_does_not_return_final_aggregate_evidence(
    tmp_path,
    monkeypatch,
):
    result = _isolated_runner(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        mode="slow",
        timeout=0.05,
    )

    assert result["comparison"] is None
    assert result["evidence"] is None


def test_unavailable_isolated_runner_reports_effective_direct_mode(tmp_path):
    result = QualificationRunner(
        adapters=[
            ProviderAdapter(
                "fixture",
                "unavailable",
                available=False,
                availability_reason="not configured",
            )
        ],
        cases=[_case()],
        execution_mode="isolated",
    ).run(output_root=tmp_path, run_id="health-unavailable")

    assert result["manifest"]["execution_mode"] == "direct"


def test_provider_failure_is_redacted_and_production_paths_are_untouched(
    tmp_path,
    monkeypatch,
):
    result = _isolated_runner(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        mode="failing",
        timeout=2,
    )

    manifest = result["manifest"]
    assert manifest["completion_status"] == "completed"
    assert manifest["status_counts"] == {"source_failed": 1}
    event = json.loads(
        (tmp_path / "health-failing" / "events.ndjson").read_text().splitlines()[0]
    )
    assert event["status"] == "source_failed"
    assert "secret-token" not in json.dumps(event)
    assert "user:pass@" not in json.dumps(event)
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "watchlist").exists()
    assert not (tmp_path / "debate").exists()


def test_success_payload_credentials_are_redacted_from_all_artifacts(
    tmp_path,
    monkeypatch,
):
    result = _isolated_runner(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        mode="secret_payload",
        timeout=2,
    )

    run_dir = Path(result["run_dir"])
    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in run_dir.iterdir()
        if path.is_file()
    )
    returned = json.dumps(result, ensure_ascii=False)
    assert "secret-token" not in persisted
    assert "user:pass@" not in persisted
    assert "secret-token" not in returned
    assert "user:pass@" not in returned


def test_oversized_isolated_child_payload_fails_closed(
    tmp_path,
    monkeypatch,
):
    result = _isolated_runner(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        mode="large_payload",
        timeout=2,
    )

    event = json.loads(
        (Path(result["run_dir"]) / "events.ndjson").read_text().splitlines()[0]
    )
    assert event["status"] == "source_failed"
    assert event["failure_class"] == "payload_too_large"


def test_direct_mode_keeps_local_closure_compatibility(tmp_path):
    def invoke(case: ProbeCase):
        return {
            "last_price": 1.0,
            "_fields": {
                "last_price": {
                    "unit": "CNY/share",
                    "as_of": "2026-08-05",
                }
            },
        }

    result = QualificationRunner(
        adapters=[ProviderAdapter("fixture", "direct", invoke=invoke)],
        cases=[_case()],
        execution_mode="direct",
    ).run(output_root=tmp_path, run_id="health-direct")

    assert result["manifest"]["completion_status"] == "completed"
    assert result["manifest"]["execution_mode"] == "direct"
    assert (tmp_path / "health-direct" / "evidence.json").exists()


def test_manifest_is_persisted_after_each_terminal_case(tmp_path):
    second_case_started = threading.Event()
    release_second_case = threading.Event()
    calls = 0

    def invoke(case: ProbeCase):
        nonlocal calls
        calls += 1
        if calls == 2:
            second_case_started.set()
            assert release_second_case.wait(timeout=5)
        return {
            "last_price": 1.0,
            "_fields": {
                "last_price": {
                    "unit": "CNY/share",
                    "as_of": "2026-08-05",
                }
            },
        }

    runner = QualificationRunner(
        adapters=[ProviderAdapter("fixture", "direct", invoke=invoke)],
        cases=[_case("quote"), _case("calc_indexes")],
        execution_mode="direct",
    )
    result_holder: dict[str, dict] = {}

    def run():
        result_holder["result"] = runner.run(
            output_root=tmp_path,
            run_id="health-progress",
        )

    worker = threading.Thread(target=run)
    worker.start()
    assert second_case_started.wait(timeout=5)

    partial_manifest = json.loads(
        (tmp_path / "health-progress" / "manifest.json").read_text()
    )
    assert partial_manifest["completion_status"] == "running"
    assert partial_manifest["completed_cases"] == 1
    assert partial_manifest["not_started_cases"] == 1

    release_second_case.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert result_holder["result"]["manifest"]["completion_status"] == "completed"


def test_cli_defaults_to_bounded_isolated_execution():
    args = build_parser().parse_args([])

    assert args.execution_mode == "isolated"
    assert args.case_timeout_seconds == 60.0
    assert args.stop_policy == "continue"


def test_cli_accepts_explicit_execution_options():
    args = build_parser().parse_args(
        [
            "--execution-mode",
            "direct",
            "--case-timeout-seconds",
            "2.5",
            "--stop-policy",
            "stop_on_timeout",
        ]
    )

    assert args.execution_mode == "direct"
    assert args.case_timeout_seconds == 2.5
    assert args.stop_policy == "stop_on_timeout"


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf"])
def test_cli_rejects_non_positive_or_non_finite_timeout(timeout):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--case-timeout-seconds", timeout])
