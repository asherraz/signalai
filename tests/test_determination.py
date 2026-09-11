from pathlib import Path

import pytest
from pydantic import ValidationError

from signalai.determination import derive_chair_determination
from signalai.schemas import SignalState
from signalai.schemas.agenda import AgendaStatus
from signalai.schemas.daily import DailySynthesis
from signalai.schemas.live import (
    ChangeScope,
    DeterminationKind,
    LiveChairRecommendation,
    NoMaterialChangeDetermination,
)


ROOT = Path(__file__).resolve().parents[1]


def _state() -> SignalState:
    return SignalState.model_validate_json((ROOT / "state" / "signal-state.json").read_text())


def _recommendation(**changes) -> LiveChairRecommendation:
    return LiveChairRecommendation(
        matter_id="matter-test",
        findings=["The current evidence was reviewed."],
        evidence_assessment="The cited evidence supports only the stated bounded conclusion.",
        supporting_evidence_ids=["ev-misev2023-quality-framework"],
        objections=["Translation remains uncertain."],
        recommendation="Retain the evidence gate and take the bounded next step.",
        proposed_changes=changes,
    )


def test_no_material_change_cannot_contain_scientific_mutation() -> None:
    state = _state()
    revised = state.risks[0].model_copy(update={"mitigation": "A revised mitigation."})
    synthesis = DailySynthesis(
        agenda_item_id="matter-test",
        material_change=True,
        rationale="Risk mitigation changed.",
        risk_updates=[revised],
        agenda_status=AgendaStatus.DEFERRED,
        what_changed="Risk updated.",
    )
    with pytest.raises(ValidationError, match="no_material_change cannot contain"):
        NoMaterialChangeDetermination(
            determination="no_material_change",
            change_scope="none",
            synthesis=synthesis,
        )


def test_editorial_clarification_is_allowed_without_state_mutation() -> None:
    result = derive_chair_determination(
        _recommendation(editorial_clarification="Clarified the existing rationale."),
        _state(),
    ).result
    assert result.determination is DeterminationKind.NO_MATERIAL_CHANGE
    assert result.change_scope is ChangeScope.EDITORIAL
    assert not result.scientific_state_changed
    assert not result.operational_state_changed


def test_changed_next_action_is_operational_not_scientific() -> None:
    result = derive_chair_determination(
        _recommendation(next_action="Draft a bounded protocol for human review."),
        _state(),
    ).result
    assert result.determination is DeterminationKind.NO_MATERIAL_CHANGE
    assert result.change_scope is ChangeScope.OPERATIONAL
    assert result.operational_state_changed
    assert not result.scientific_state_changed
    assert not result.synthesis.material_change


def test_material_hypothesis_update_is_classified_as_state_update() -> None:
    state = _state()
    hypothesis = state.hypothesis.model_copy(
        update={"statement": state.hypothesis.statement + " This is a validated revision."}
    )
    result = derive_chair_determination(
        _recommendation(hypothesis_update=hypothesis), state
    ).result
    assert result.determination is DeterminationKind.STATE_UPDATE
    assert result.change_scope is ChangeScope.SCIENTIFIC
    assert result.scientific_state_changed
    assert result.synthesis.hypothesis_update == hypothesis


def test_risk_update_is_classified_as_state_update() -> None:
    state = _state()
    risk = state.risks[0].model_copy(update={"mitigation": "Use a controlled bridge study."})
    result = derive_chair_determination(
        _recommendation(risk_updates=[risk]), state
    ).result
    assert result.determination is DeterminationKind.STATE_UPDATE
    assert result.synthesis.risk_updates == [risk]


def test_human_gated_decision_is_classified_as_human_decision_required() -> None:
    state = _state()
    decision = state.decision.model_copy(
        update={"outcome": "Propose the bounded package for human approval."}
    )
    result = derive_chair_determination(
        _recommendation(decision_update=decision), state
    ).result
    assert result.determination is DeterminationKind.HUMAN_DECISION_REQUIRED
    assert result.change_scope is ChangeScope.DECISION
    assert result.synthesis.decision_proposal is not None
    assert result.synthesis.decision_proposal.approval_status.value == "pending"
