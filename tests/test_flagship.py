"""Flagship presentation derives from real records without advancing scientific state."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from signalai.flagship_export import concise, export_flagship_program
from signalai.publisher import build_current_public_state
from signalai.schemas.models import SignalState, RiskLevel, RiskStatus
from signalai.schemas.public import PublicSignalState
from signalai.schemas.public_flagship import PublicFlagshipProgram


ROOT = Path(__file__).resolve().parents[1]


def _source():
    return SignalState.model_validate_json((ROOT / "state/signal-state.json").read_text())


def test_flagship_generated_and_links_latest_review():
    public = build_current_public_state(ROOT)
    payload = public.model_dump(mode="json", by_alias=True)
    validated = PublicSignalState.model_validate(payload)
    flagship = validated.flagship_program
    assert flagship.program_id == "SGL-001"
    assert flagship.name == flagship.display_name == "SGL-001"
    assert flagship.signal_rb_review_id == validated.signal_rb.latest_review.review_id
    assert flagship.current_determination == concise(validated.signal_rb.latest_review.determination)
    assert flagship.human_decision_required == validated.signal_rb.latest_review.human_decision_required
    assert flagship.verification_status == validated.signal_rb.latest_review.verification_status
    assert flagship.evidence_confidence == _source().program.evidence_confidence.value
    assert flagship.thesis.route == "intranasal"


def test_gate_mapping_is_conservative_not_literature_progress():
    public = build_current_public_state(ROOT)
    source = _source()
    # Exercise stable conditions, not the outcome of whichever daily run is newest.
    source = source.model_copy(update={
        "program": source.program.model_copy(update={"current_formulation_hypothesis": "Intranasal MSC-EV product hypothesis; cargo remains to be selected."}),
        "risks": [
            source.risks[0].model_copy(update={"risk_id": "risk-cross-species-cns-delivery", "title": "Cross-species intranasal delivery", "description": "Intact-EV exposure remains uncertain.", "severity": RiskLevel.HIGH, "status": RiskStatus.OPEN}),
            source.risks[1].model_copy(update={"risk_id": "risk-cmc-identity-potency", "title": "Potency and identity", "description": "Analytics are not validated.", "severity": RiskLevel.HIGH, "status": RiskStatus.OPEN}),
            *source.risks[2:],
        ],
    })
    # model_copy deliberately bypasses validation; normalize typed enums before use.
    source = SignalState.model_validate(source.model_dump())
    current = public.signal_rb.latest_review.model_copy(update={
        "matter_title": "First clinic pathway", "matter_question": "Which jurisdiction supports a clinic pathway?",
        "human_decision_required": True,
    })
    board = public.signal_rb.model_copy(update={"latest_review": current})
    flagship = export_flagship_program(source, board)
    gates = {g.name: g for g in flagship.development_gates}
    assert {name: gate.status for name, gate in gates.items()} == {
        "Product Definition": "partially_defined",
        "Potency / Identity": "blocked",
        "Intranasal Delivery": "blocked",
        "Mechanism / Active Biology": "unresolved",
        "Chassis Decision": "unresolved",
        "Translational Readiness": "human_decision",
    }
    assert "risk-cmc-identity-potency" in gates["Potency / Identity"].sources.risk_ids
    assert "risk-cross-species-cns-delivery" in gates["Intranasal Delivery"].sources.risk_ids
    assert not gates["Chassis Decision"].what_is_known
    assert gates["Chassis Decision"].next_action is None
    assert all(g.status != "supported" for g in gates.values())


def test_pivots_require_recorded_failure_conditions():
    state = _source()
    public = build_current_public_state(ROOT)
    flagship = public.flagship_program
    assert flagship.pivot_criteria
    reviews = {r.review_id: r for r in public.signal_rb.recent_reviews}
    for criterion in flagship.pivot_criteria:
        assert criterion.condition in reviews[criterion.review_id].conditions
    serialized = json.dumps(flagship.model_dump(mode="json"))
    assert "synthetic delivery preserves" not in serialized
    assert "small defined cargo set" not in serialized
    assert not export_flagship_program(state, None).pivot_criteria
    runs = [r.model_copy(update={"conditions": []}) for r in public.signal_rb.recent_reviews]
    board = public.signal_rb.model_copy(update={"recent_reviews": runs, "latest_review": runs[0]})
    assert not export_flagship_program(state, board).pivot_criteria


def test_history_deduplicated_and_chronological():
    public = build_current_public_state(ROOT)
    board = public.signal_rb
    duplicated = board.model_copy(update={"recent_reviews": board.recent_reviews + board.recent_reviews})
    flagship = export_flagship_program(_source(), duplicated)
    history = flagship.program_history
    assert len(history) == len({r.run_id for r in board.recent_reviews})
    assert [h.date for h in history] == sorted(h.date for h in history)
    assert history[-1].review_id == flagship.signal_rb_review_id


def test_timestamp_is_source_timestamp_not_publish_time():
    earlier = build_current_public_state(ROOT, generated_at=datetime(2026, 9, 15, tzinfo=timezone.utc))
    later = build_current_public_state(ROOT, generated_at=datetime(2026, 9, 16, tzinfo=timezone.utc))
    assert earlier.flagship_program == later.flagship_program


def test_missing_optional_data_is_not_invented():
    state = _source()
    program = state.program.model_copy(update={"current_formulation_hypothesis": None, "next_proposed_action": None})
    empty = state.model_copy(update={"program": program, "claims": [], "risks": []})
    flagship = export_flagship_program(empty, None)
    assert flagship.thesis.biology is None
    assert flagship.thesis.product_hypothesis is None
    assert flagship.current_determination is None
    assert flagship.current_next_action is None
    assert not flagship.program_history
    assert all(g.status == "unresolved" for g in flagship.development_gates)


def test_private_data_does_not_leak_and_inputs_are_unchanged():
    state = _source()
    public = build_current_public_state(ROOT)
    before = state.model_dump_json()
    review = public.signal_rb.latest_review.model_copy(update={"api_metadata": {"secret": "private-value"}})
    board = public.signal_rb.model_copy(update={"latest_review": review})
    flagship = export_flagship_program(state, board)
    serialized = flagship.model_dump_json()
    for forbidden in ("private-value", "api_metadata", "usage_records", "input_tokens", "prompt", "chain-of-thought", "contact_email"):
        assert forbidden not in serialized
    assert state.model_dump_json() == before
    with pytest.raises(ValidationError):
        PublicFlagshipProgram.model_validate({**flagship.model_dump(by_alias=True), "api_metadata": {}})


def test_public_payload_rejects_unsourced_pivot_and_unknown_refs():
    public = build_current_public_state(ROOT).model_dump(mode="json", by_alias=True)
    public["flagshipProgram"]["pivotCriteria"][0]["condition"] = "Synthetic delivery is proven superior."
    with pytest.raises(ValidationError, match="recorded SignalRB condition"):
        PublicSignalState.model_validate(public)
    public = build_current_public_state(ROOT).model_dump(mode="json", by_alias=True)
    public["flagshipProgram"]["developmentGates"][0]["sources"]["evidence_ids"] = ["invented-evidence"]
    with pytest.raises(ValidationError, match="canonical state"):
        PublicSignalState.model_validate(public)


def test_source_less_claims_do_not_become_new_biology():
    state = _source()
    without_claims = state.model_copy(update={"claims": []})
    assert export_flagship_program(without_claims, None).thesis.biology is None


def test_concision_does_not_truncate_qualifiers():
    source = "A long preclinical result " * 15 + "does not establish human efficacy."
    assert concise(source) == source
