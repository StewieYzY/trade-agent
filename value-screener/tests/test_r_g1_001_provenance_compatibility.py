from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.lib.field_qualification import FieldQualificationPolicy  # noqa: E402
from scripts.provider_qualification import (  # noqa: E402
    ProbeCase,
    ProviderAdapter,
    QualificationRunner,
)
from scripts.promote_provider_snapshot import (  # noqa: E402
    promote_provider_snapshot,
)


def test_runner_output_can_flow_through_evaluator_and_promotion(tmp_path):
    def invoke(_case: ProbeCase):
        return {
            "last_price": 123.4,
            "_fields": {
                "last_price": {
                    "unit": "CNY/share",
                    "currency": "CNY",
                    "as_of": "2026-08-06",
                }
            },
        }

    source_result = QualificationRunner(
        adapters=[ProviderAdapter("baseline", "fixture", invoke=invoke)],
        cases=[
            ProbeCase(
                ticker="600519.SH",
                market="SH",
                security_type="consumer",
                method="quote",
                fields=("last_price",),
            )
        ],
    ).run(output_root=tmp_path / "qualification", run_id="source-run")
    source_dir = Path(source_result["run_dir"])
    source_before = {
        path.name: path.read_bytes()
        for path in source_dir.iterdir()
        if path.is_file()
    }

    policy = FieldQualificationPolicy.from_mapping(
        version="test-policy-v1",
        tickers=("600519.SH",),
        methods={"quote": ("last_price",)},
        allowed_providers=("fixture",),
    )
    promotion = promote_provider_snapshot(
        source_dir,
        output_root=tmp_path / "promotions",
        policy=policy,
        run_id="promotion-run",
        evaluated_at=datetime.now(timezone.utc),
    )

    assert promotion["status"] == "qualified"
    run_dir = Path(promotion["run_dir"])
    assert json.loads((run_dir / "records.json").read_text())["600519.SH"][
        "last_price"
    ] == 123.4
    assert {
        path.name: path.read_bytes()
        for path in source_dir.iterdir()
        if path.is_file()
    } == source_before
