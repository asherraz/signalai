import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from signalai.schemas import PublicSignalState


EXPECTED_TOP_LEVEL_FIELDS = {
    "generatedAt",
    "version",
    "status",
    "program",
    "changes",
    "loop",
    "evidence",
    "hypotheses",
    "risks",
    "decisions",
    "currentHypothesis",
    "latestRun",
}


def test_generated_public_payload_matches_frontend_contract() -> None:
    path = Path(__file__).resolve().parents[1] / "public" / "signal-state.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert set(payload) == EXPECTED_TOP_LEVEL_FIELDS
    validated = PublicSignalState.model_validate(payload)
    assert validated.program.program_id == "SGL-001"
    assert len(validated.program.claims) >= 3
    assert validated.program.current_formulation_hypothesis
    assert validated.program.development_focus == "Neuroregeneration and cognitive function"
    assert validated.program.lead_indication == "Not yet selected"
    assert validated.program.largest_unresolved_risk
    assert validated.program.next_proposed_action
    assert len(validated.changes) == 1
    assert isinstance(validated.changes, list)
    assert isinstance(validated.evidence, list)
    assert isinstance(validated.hypotheses, list)
    assert 2 <= len(validated.risks) <= 3
    assert isinstance(validated.decisions, list)
    assert validated.current_hypothesis is not None
    assert validated.latest_run is not None
    assert set(validated.latest_run.stages.model_dump(by_alias=True)) == {
        "evidence",
        "claims",
        "hypothesis",
        "critique",
        "decision",
        "nextAction",
    }


def test_public_payload_rejects_an_unexpected_top_level_field() -> None:
    path = Path(__file__).resolve().parents[1] / "public" / "signal-state.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = True

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PublicSignalState.model_validate(payload)
