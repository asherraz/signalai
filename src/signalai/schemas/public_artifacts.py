"""Sanitized frontend projections of validated development-run artifacts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from signalai.schemas.models import (
    ApprovalStatus,
    ClaimStatus,
    EvidenceConfidence,
    EvidenceKind,
    HypothesisStatus,
    Identifier,
    NonEmptyText,
    SignalModel,
    _require_timezone,
)


class PublicEvidencePosition(StrEnum):
    SUPPORTIVE = "supportive"
    CONTRADICTORY = "contradictory"
    NEUTRAL = "neutral"


class PublicEvidenceArtifact(SignalModel):
    evidence_id: Identifier = Field(alias="evidenceId")
    title: str | None = None
    source_identifier: str | None = Field(default=None, alias="sourceIdentifier")
    evidence_type: EvidenceKind = Field(alias="evidenceType")
    species: str | None = None
    route: str | None = None
    model_or_indication: str | None = Field(default=None, alias="modelOrIndication")
    position: PublicEvidencePosition
    relevance: list[str] = Field(default_factory=list)
    finding_summary: str | None = Field(default=None, alias="findingSummary")
    supported_claim_ids: list[Identifier] = Field(
        default_factory=list, alias="supportedClaimIds"
    )
    contradicted_claim_ids: list[Identifier] = Field(
        default_factory=list, alias="contradictedClaimIds"
    )


class PublicClaimArtifact(SignalModel):
    claim_id: Identifier = Field(alias="claimId")
    statement: NonEmptyText
    status: ClaimStatus
    supporting_evidence_ids: list[Identifier] = Field(
        default_factory=list, alias="supportingEvidenceIds"
    )
    contradicting_evidence_ids: list[Identifier] = Field(
        default_factory=list, alias="contradictingEvidenceIds"
    )
    evidence_strength: str | None = Field(default=None, alias="evidenceStrength")


class PublicHypothesisArtifact(SignalModel):
    hypothesis_id: Identifier = Field(alias="hypothesisId")
    statement: NonEmptyText
    status: HypothesisStatus
    evidence_confidence: EvidenceConfidence = Field(alias="evidenceConfidence")
    supporting_claim_ids: list[Identifier] = Field(
        default_factory=list, alias="supportingClaimIds"
    )
    contradicting_claim_ids: list[Identifier] = Field(
        default_factory=list, alias="contradictingClaimIds"
    )
    previous_hypothesis: str | None = Field(default=None, alias="previousHypothesis")
    what_changed: str | None = Field(default=None, alias="whatChanged")


class PublicCritiqueArtifact(SignalModel):
    strongest_objection: NonEmptyText = Field(alias="strongestObjection")
    assumptions_challenged: list[str] = Field(
        default_factory=list, alias="assumptionsChallenged"
    )
    translational_concerns: list[str] = Field(
        default_factory=list, alias="translationalConcerns"
    )
    experimental_confounders: list[str] = Field(
        default_factory=list, alias="experimentalConfounders"
    )
    disconfirming_evidence_ids: list[Identifier] = Field(
        default_factory=list, alias="disconfirmingEvidenceIds"
    )
    falsification_conditions: list[str] = Field(
        default_factory=list, alias="falsificationConditions"
    )


class PublicDecisionArtifact(SignalModel):
    decision_id: Identifier = Field(alias="decisionId")
    question: NonEmptyText
    recommendation: str | None = None
    rationale: str | None = None
    linked_hypothesis_ids: list[Identifier] = Field(
        default_factory=list, alias="linkedHypothesisIds"
    )
    linked_claim_ids: list[Identifier] = Field(
        default_factory=list, alias="linkedClaimIds"
    )
    linked_evidence_ids: list[Identifier] = Field(
        default_factory=list, alias="linkedEvidenceIds"
    )
    human_approval_required: bool = Field(alias="humanApprovalRequired")
    approval_status: ApprovalStatus = Field(alias="approvalStatus")


class PublicNextActionArtifact(SignalModel):
    action: NonEmptyText
    objective: NonEmptyText
    priority_reason: NonEmptyText = Field(alias="priorityReason")
    uncertainty_to_resolve: NonEmptyText = Field(alias="uncertaintyToResolve")
    success_criteria: str | None = Field(default=None, alias="successCriteria")
    status: NonEmptyText


class PublicSelectedTask(SignalModel):
    agenda_item_id: Identifier = Field(alias="agendaItemId")
    type: NonEmptyText
    question: NonEmptyText
    priority: NonEmptyText
    rationale: NonEmptyText
    selection_reason: NonEmptyText = Field(alias="selectionReason")


class PublicRunStages(SignalModel):
    evidence: list[PublicEvidenceArtifact]
    claims: list[PublicClaimArtifact]
    hypothesis: PublicHypothesisArtifact
    critique: PublicCritiqueArtifact
    decision: PublicDecisionArtifact
    next_action: PublicNextActionArtifact = Field(alias="nextAction")


class PublicLatestRun(SignalModel):
    run_id: Identifier = Field(alias="runId")
    started_at: datetime = Field(alias="startedAt")
    completed_at: datetime = Field(alias="completedAt")
    selected_task: PublicSelectedTask = Field(alias="selectedTask")
    stages: PublicRunStages

    @model_validator(mode="after")
    def validate_timestamps(self) -> PublicLatestRun:
        object.__setattr__(self, "started_at", _require_timezone(self.started_at, "started_at"))
        object.__setattr__(
            self, "completed_at", _require_timezone(self.completed_at, "completed_at")
        )
        if self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        return self
