"""Deterministic lifecycle classification for validated Chair recommendations."""

from __future__ import annotations

from signalai.schemas.agenda import AgendaStatus
from signalai.schemas.daily import DailySynthesis
from signalai.schemas.live import (
    ChangeScope,
    DeterminationKind,
    LiveChairDetermination,
    LiveChairRecommendation,
    MaterialChangeDetermination,
    NoMaterialChangeDetermination,
)
from signalai.schemas.models import SignalState


def derive_chair_determination(
    recommendation: LiveChairRecommendation,
    state: SignalState,
) -> LiveChairDetermination:
    """Normalize no-ops and classify lifecycle semantics without model discretion."""

    proposed = recommendation.proposed_changes
    claims_by_id = {item.claim_id: item for item in state.claims}
    risks_by_id = {item.risk_id: item for item in state.risks}
    claim_updates = [
        item for item in proposed.claim_updates if claims_by_id.get(item.claim_id) != item
    ]
    risk_updates = [
        item for item in proposed.risk_updates if risks_by_id.get(item.risk_id) != item
    ]
    hypothesis_update = (
        proposed.hypothesis_update
        if proposed.hypothesis_update is not None
        and proposed.hypothesis_update != state.hypothesis
        else None
    )
    confidence_update = (
        proposed.evidence_confidence_update
        if proposed.evidence_confidence_update is not None
        and proposed.evidence_confidence_update != state.program.evidence_confidence
        else None
    )
    status_update = (
        proposed.program_status_update
        if proposed.program_status_update is not None
        and proposed.program_status_update != state.program.status
        else None
    )
    decision_update = (
        proposed.decision_update
        if proposed.decision_update is not None and proposed.decision_update != state.decision
        else None
    )
    next_action = (
        proposed.next_action
        if proposed.next_action is not None
        and proposed.next_action != state.program.next_proposed_action
        else None
    )
    scientific_change = bool(
        claim_updates
        or hypothesis_update
        or risk_updates
        or confidence_update
        or status_update
    )
    decision_change = decision_update is not None
    operational_change = next_action is not None
    material_change = scientific_change or decision_change

    if scientific_change:
        what_changed = "Validated scientific state updates were proposed with linked evidence."
    elif decision_change:
        what_changed = "A validated development decision update was proposed."
    elif operational_change:
        what_changed = "The operational next action was clarified; scientific belief state is unchanged."
    elif proposed.editorial_clarification:
        what_changed = proposed.editorial_clarification
    else:
        what_changed = "No validated scientific, decision, or operational state change was proposed."

    synthesis = DailySynthesis(
        agenda_item_id=recommendation.matter_id,
        material_change=material_change,
        rationale=recommendation.evidence_assessment,
        claim_updates=claim_updates,
        hypothesis_update=hypothesis_update,
        risk_updates=risk_updates,
        decision_proposal=decision_update,
        evidence_confidence_update=confidence_update,
        program_status_update=status_update,
        next_action=next_action,
        agenda_status=AgendaStatus.DEFERRED,
        what_changed=what_changed,
    )

    if not material_change:
        scope = (
            ChangeScope.OPERATIONAL
            if operational_change
            else ChangeScope.EDITORIAL
            if proposed.editorial_clarification
            else ChangeScope.NONE
        )
        result = NoMaterialChangeDetermination(
            determination=DeterminationKind.NO_MATERIAL_CHANGE,
            change_scope=scope,
            operational_state_changed=operational_change,
            synthesis=synthesis,
        )
    else:
        if decision_change and decision_update.requires_human_approval:
            kind = DeterminationKind.HUMAN_DECISION_REQUIRED
            scope = ChangeScope.DECISION
        elif decision_change and not scientific_change:
            kind = DeterminationKind.DECISION_UPDATE
            scope = ChangeScope.DECISION
        else:
            kind = DeterminationKind.STATE_UPDATE
            scope = ChangeScope.SCIENTIFIC
        result = MaterialChangeDetermination(
            determination=kind,
            change_scope=scope,
            scientific_state_changed=scientific_change,
            operational_state_changed=operational_change,
            synthesis=synthesis,
        )
    return LiveChairDetermination(
        matter_id=recommendation.matter_id,
        recommendation=recommendation,
        result=result,
    )
