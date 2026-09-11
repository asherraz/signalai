"""Create concise public projections from validated, authoritative run artifacts."""

from __future__ import annotations

from pathlib import Path

from signalai.schemas import (
    AgentRun,
    DailyAnalysis,
    DailyCritique,
    DailySynthesis,
    PublicClaimArtifact,
    PublicAiRBState,
    PublicCritiqueArtifact,
    PublicDecisionArtifact,
    PublicEvidenceArtifact,
    PublicEvidencePosition,
    PublicHypothesisArtifact,
    PublicLatestRun,
    PublicNextActionArtifact,
    PublicRunStages,
    PublicSelectedTask,
    RunStatus,
    SelectedTask,
    SignalState,
    WhatChanged,
)


def _read(run_dir: Path, filename: str, model_type):
    return model_type.model_validate_json((run_dir / filename).read_text(encoding="utf-8"))


def _source_metadata(value: object, key: str) -> str | None:
    if not isinstance(value, dict):
        return None
    item = value.get(key)
    return item if isinstance(item, str) and item.strip() else None


def build_public_latest_run(
    *,
    started: AgentRun,
    completed: AgentRun,
    selected: SelectedTask,
    analysis: DailyAnalysis,
    critique: DailyCritique,
    synthesis: DailySynthesis,
    input_state: SignalState,
    updated_state: SignalState,
    changed: WhatChanged,
) -> PublicLatestRun:
    """Join validated internal artifacts without exposing prompts or API metadata."""
    if completed.status is not RunStatus.SUCCEEDED:
        raise ValueError("public artifacts require a successful completed run")
    if started.run_id != completed.run_id or updated_state.run_id != completed.run_id:
        raise ValueError("run artifact IDs do not match")
    if started.started_at is None or completed.completed_at is None:
        raise ValueError("completed run timestamps are required")

    contradictory_claims = set(updated_state.hypothesis.contradicting_claim_ids)
    evidence_artifacts: list[PublicEvidenceArtifact] = []
    for evidence in updated_state.evidence:
        supported = [
            claim.claim_id for claim in updated_state.claims if evidence.evidence_id in claim.evidence_ids
        ]
        contradictory = bool(set(supported) & contradictory_claims)
        roles = evidence.metadata.get("evidence_role", [])
        relevance = [str(role) for role in roles] if isinstance(roles, list) else []
        evidence_artifacts.append(
            PublicEvidenceArtifact(
                evidenceId=evidence.evidence_id,
                title=evidence.title,
                sourceIdentifier=evidence.source_identifier,
                evidenceType=evidence.kind,
                species=_source_metadata(evidence.metadata, "species"),
                route=_source_metadata(evidence.metadata, "route"),
                modelOrIndication=_source_metadata(evidence.metadata, "model_or_indication"),
                position=(
                    PublicEvidencePosition.CONTRADICTORY
                    if contradictory
                    else PublicEvidencePosition.SUPPORTIVE
                    if supported
                    else PublicEvidencePosition.NEUTRAL
                ),
                relevance=relevance,
                findingSummary=evidence.excerpt,
                supportedClaimIds=supported,
                contradictedClaimIds=[],
            )
        )

    claim_artifacts = [
        PublicClaimArtifact(
            claimId=claim.claim_id,
            statement=claim.statement,
            status=claim.status,
            supportingEvidenceIds=claim.evidence_ids,
            contradictingEvidenceIds=[],
            evidenceStrength=None,
        )
        for claim in updated_state.claims
    ]

    previous = input_state.hypothesis
    hypothesis_changed = previous.model_dump() != updated_state.hypothesis.model_dump()
    public_hypothesis = PublicHypothesisArtifact(
        hypothesisId=updated_state.hypothesis.hypothesis_id,
        statement=updated_state.hypothesis.statement,
        status=updated_state.hypothesis.status,
        evidenceConfidence=updated_state.program.evidence_confidence,
        supportingClaimIds=updated_state.hypothesis.supporting_claim_ids,
        contradictingClaimIds=updated_state.hypothesis.contradicting_claim_ids,
        previousHypothesis=previous.statement if hypothesis_changed else None,
        whatChanged=changed.summary,
    )

    disconfirming_ids = sorted(
        {
            evidence_id
            for claim in updated_state.claims
            if claim.claim_id in contradictory_claims
            for evidence_id in claim.evidence_ids
        }
        & set(critique.evidence_ids)
    )
    public_critique = PublicCritiqueArtifact(
        strongestObjection=critique.challenge,
        assumptionsChallenged=critique.limitations,
        translationalConcerns=[updated_state.critique.summary],
        experimentalConfounders=updated_state.critique.challenges,
        disconfirmingEvidenceIds=disconfirming_ids,
        falsificationConditions=(
            [updated_state.hypothesis.test_plan]
            if updated_state.hypothesis.test_plan
            else []
        ),
    )

    decision = synthesis.decision_proposal or updated_state.decision
    public_decision = PublicDecisionArtifact(
        decisionId=decision.decision_id,
        question=decision.question,
        recommendation=decision.outcome,
        rationale=decision.rationale,
        linkedHypothesisIds=selected.item.linked_hypothesis_ids,
        linkedClaimIds=decision.supporting_claim_ids,
        linkedEvidenceIds=decision.evidence_ids,
        humanApprovalRequired=decision.requires_human_approval,
        approvalStatus=decision.approval_status,
    )

    action = (
        synthesis.next_action
        or analysis.proposed_next_action
        or updated_state.program.next_proposed_action
    )
    if not action:
        raise ValueError("completed daily run must expose a next development action")
    next_action = PublicNextActionArtifact(
        action=action,
        objective=analysis.objective,
        priorityReason=selected.selection_reason,
        uncertaintyToResolve=selected.item.question,
        successCriteria=None,
        status="proposed",
    )

    return PublicLatestRun(
        runId=completed.run_id,
        startedAt=started.started_at,
        completedAt=completed.completed_at,
        selectedTask=PublicSelectedTask(
            agendaItemId=selected.item.agenda_item_id,
            type=selected.item.type.value,
            question=selected.item.question,
            priority=selected.item.priority.value,
            rationale=selected.item.rationale,
            selectionReason=selected.selection_reason,
        ),
        stages=PublicRunStages(
            evidence=evidence_artifacts,
            claims=claim_artifacts,
            hypothesis=public_hypothesis,
            critique=public_critique,
            decision=public_decision,
            nextAction=next_action,
        ),
    )


def export_completed_run(run_dir: Path) -> PublicLatestRun:
    """Load a completed run directory and return its validated public projection."""
    return build_public_latest_run(
        started=_read(run_dir, "00-run-start.json", AgentRun),
        completed=_read(run_dir, "99-run-complete.json", AgentRun),
        selected=_read(run_dir, "03-selected-task.json", SelectedTask),
        analysis=_read(run_dir, "04-analysis.json", DailyAnalysis),
        critique=_read(run_dir, "05-critique.json", DailyCritique),
        synthesis=_read(run_dir, "06-synthesis.json", DailySynthesis),
        input_state=_read(run_dir, "01-current-state.json", SignalState),
        updated_state=_read(run_dir, "07-updated-state.json", SignalState),
        changed=_read(run_dir, "09-what-changed.json", WhatChanged),
    )


def build_public_airb(latest_run: PublicLatestRun, program_id: str) -> PublicAiRBState:
    """Expose the latest sanitized critique and determination as a convenience section."""

    decision = latest_run.stages.decision
    return PublicAiRBState(
        reviewId=f"airb-{latest_run.run_id}",
        runId=latest_run.run_id,
        programId=program_id,
        status=decision.approval_status,
        critique=latest_run.stages.critique,
        determination=decision,
        lastUpdated=latest_run.completed_at,
    )
