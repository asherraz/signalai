import json
from datetime import datetime, timezone
from pathlib import Path

from signalai.publisher import build_current_public_state, publish_current_public_state
from signalai.schemas import PublicSignalState


ROOT = Path(__file__).resolve().parents[1]
FIXED_EXPORT_TIME = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def test_complete_public_state_is_rebuilt_without_using_public_json() -> None:
    state = build_current_public_state(ROOT, generated_at=FIXED_EXPORT_TIME)

    assert state.generated_at == FIXED_EXPORT_TIME
    assert state.latest_run is not None
    assert state.latest_run.run_id == state.loop.run_id
    assert state.airb is not None
    assert state.airb.run_id == state.loop.run_id
    assert state.cargo is not None
    assert state.formulation is not None
    assert state.jurisdictions is not None
    assert state.clinical_network is not None
    assert state.product is not None
    assert state.current_hypothesis is not None
    assert state.intelligence_feed


def test_complete_public_state_publishes_atomically_to_requested_path(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "signal-state.json"
    expected = publish_current_public_state(
        ROOT,
        destination=destination,
        generated_at=FIXED_EXPORT_TIME,
    )
    payload = json.loads(destination.read_text(encoding="utf-8"))
    validated = PublicSignalState.model_validate(payload)

    assert validated == expected
    assert payload["generatedAt"] == "2026-09-10T12:00:00Z"
    assert {
        "clinicalNetwork",
        "cargo",
        "formulation",
        "jurisdictions",
        "aiRB",
        "product",
        "intelligenceFeed",
        "currentHypothesis",
        "latestRun",
    } <= set(payload)
