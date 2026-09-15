import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from signalai.publisher import build_current_public_state
from signalai.schemas.public import PublicSignalState
from signalai.schemas.signalrb import PublicSignalRB, SignalReviewBoardDetermination
from signalai.schemas.live import LiveRunHistory
from signalai.schemas.models import SignalState
from signalai.signalrb import export_signalrb

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("alias", ["aiRB", "airb", "aiRB determination"])
def test_legacy_board_aliases_load(alias):
    payload = json.loads((ROOT / "public/signal-state.json").read_text())
    payload.pop("signalRB", None)
    payload.pop("flagshipProgram", None)
    payload[alias] = payload.pop("aiRB")
    state = PublicSignalState.model_validate(payload)
    assert state.signal_rb.latest_review.run_id == state.airb.run_id
    assert state.signal_rb.latest_review.verification_status == "not_recorded"
    assert state.signal_rb.latest_review.state_change == "not_recorded"


def test_signalrb_latest_single_run_and_evidence_integrity():
    state = build_current_public_state(ROOT)
    board = state.signal_rb
    assert board.latest_review == board.recent_reviews[0]
    assert len({r.run_id for r in board.recent_reviews}) == len(board.recent_reviews)
    assert [r.created_at for r in board.recent_reviews] == sorted((r.created_at for r in board.recent_reviews), reverse=True)
    allowed = {e.evidence_id for e in state.evidence}
    assert all(set(r.evidence_ids) <= allowed for r in board.recent_reviews)
    assert board.latest_review.run_id == state.live_intelligence.latest_run.run_id
    assert all(d.approval_status == "pending" for d in board.pending_human_decisions)
    payload = json.dumps(board.model_dump(mode="json", by_alias=True))
    for private in ("input_tokens", "api_key", "usage_records", "source_excerpt", "prompt", "estimated_api_cost", "contact_email"):
        assert private not in payload


def test_duplicate_reviews_rejected_and_safety_invariants():
    review = build_current_public_state(ROOT).signal_rb.latest_review
    with pytest.raises(ValidationError, match="deduplicated"):
        PublicSignalRB(latestReview=review, recentReviews=[review, review])
    values = review.model_dump()
    values.update(determination_type="no_material_change", state_change=True)
    with pytest.raises(ValidationError, match="scientific state change"):
        SignalReviewBoardDetermination.model_validate(values)
    values.update(determination_type="human_decision_required", state_change=False, human_decision_required=False)
    with pytest.raises(ValidationError, match="approval gate"):
        SignalReviewBoardDetermination.model_validate(values)


def test_human_decision_required_preserved():
    values = build_current_public_state(ROOT).signal_rb.latest_review.model_dump()
    values.update(determination_type="human_decision_required", human_decision_required=True, state_change=False)
    assert SignalReviewBoardDetermination.model_validate(values).human_decision_required


def test_unknown_evidence_is_rejected():
    state = SignalState.model_validate_json((ROOT / "state/signal-state.json").read_text())
    history = LiveRunHistory.model_validate_json((ROOT / "state/live-runs.json").read_text())
    invalid_run = history.runs[-1].model_copy(update={"strongest_supporting_evidence_ids": ["invented-evidence"]})
    invalid_history = history.model_copy(update={"runs": [invalid_run]})
    with pytest.raises(ValueError, match="unknown canonical evidence"):
        export_signalrb(ROOT, state, invalid_history)


def test_private_metadata_not_accepted_in_review_schema():
    values = build_current_public_state(ROOT).signal_rb.latest_review.model_dump()
    values["usage_records"] = {"input_tokens": 42}
    with pytest.raises(ValidationError):
        SignalReviewBoardDetermination.model_validate(values)
