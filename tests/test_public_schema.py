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
}


def test_generated_public_payload_matches_frontend_contract() -> None:
    path = Path(__file__).resolve().parents[1] / "public" / "signal-state.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert set(payload) == EXPECTED_TOP_LEVEL_FIELDS
    validated = PublicSignalState.model_validate(payload)
    assert validated.program.program_id == "SGL-001"
    assert isinstance(validated.changes, list)
    assert isinstance(validated.evidence, list)
    assert isinstance(validated.hypotheses, list)
    assert isinstance(validated.risks, list)
    assert isinstance(validated.decisions, list)


def test_public_payload_rejects_an_unexpected_top_level_field() -> None:
    path = Path(__file__).resolve().parents[1] / "public" / "signal-state.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = True

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PublicSignalState.model_validate(payload)
