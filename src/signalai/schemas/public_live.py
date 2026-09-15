"""Sanitized public contracts for live autonomous intelligence."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from signalai.schemas.live import (
    AdvancementValue,
    ChangeScope,
    DevelopmentMatter,
    LiveRun,
    MatterDomain,
    MatterPriority,
    MatterStatus,
    ReviewerRole,
)
from signalai.schemas.models import Identifier, NonEmptyText, SignalModel, _require_timezone


class LiveIntelligenceStatus(StrEnum):
    ACTIVE = "active"
    IDLE = "idle"


class PublicCurrentMatter(SignalModel):
    matter_id: Identifier = Field(alias="matterId")
    program_id: Identifier = Field(alias="programId")
    title: NonEmptyText
    question: NonEmptyText
    domain: MatterDomain
    why_it_matters: NonEmptyText = Field(alias="whyItMatters")
    priority: MatterPriority
    advancement_value: AdvancementValue = Field(alias="advancementValue")
    blocking_stage: str | None = Field(default=None, alias="blockingStage")
    linked_hypothesis_ids: list[Identifier] = Field(default_factory=list, alias="linkedHypothesisIds")
    linked_risk_ids: list[Identifier] = Field(default_factory=list, alias="linkedRiskIds")
    linked_evidence_ids: list[Identifier] = Field(default_factory=list, alias="linkedEvidenceIds")
    required_reviewer_roles: list[ReviewerRole] = Field(alias="requiredReviewerRoles")
    status: MatterStatus
    selected_at: datetime | None = Field(default=None, alias="selectedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    determination: str | None = None
    next_action: str | None = Field(default=None, alias="nextAction")

    @classmethod
    def from_internal(cls, matter: DevelopmentMatter) -> PublicCurrentMatter:
        return cls(
            matterId=matter.matter_id,
            programId=matter.program_id,
            title=matter.title,
            question=matter.question,
            domain=matter.domain,
            whyItMatters=matter.why_it_matters,
            priority=matter.priority,
            advancementValue=matter.advancement_value,
            blockingStage=matter.blocking_stage,
            linkedHypothesisIds=matter.linked_hypothesis_ids,
            linkedRiskIds=matter.linked_risk_ids,
            linkedEvidenceIds=matter.linked_evidence_ids,
            requiredReviewerRoles=matter.required_reviewer_roles,
            status=matter.status,
            selectedAt=matter.selected_at,
            completedAt=matter.completed_at,
            determination=matter.determination,
            nextAction=matter.next_action,
        )


class PublicReviewerConclusion(SignalModel):
    reviewer_role: ReviewerRole = Field(alias="reviewerRole")
    conclusion: NonEmptyText
    evidence_ids: list[Identifier] = Field(default_factory=list, alias="evidenceIds")
    claim_ids: list[Identifier] = Field(default_factory=list, alias="claimIds")
    limitations: list[NonEmptyText] = Field(default_factory=list)
    unsupported: bool = False
    evidence_gap: str | None = Field(default=None, alias="evidenceGap")


class PublicLiveRun(SignalModel):
    run_id: Identifier = Field(alias="runId")
    program_id: Identifier = Field(alias="programId")
    started_at: datetime = Field(alias="startedAt")
    completed_at: datetime = Field(alias="completedAt")
    selected_matter: PublicCurrentMatter = Field(alias="selectedMatter")
    why_selected: NonEmptyText = Field(alias="whySelected")
    reviewers_convened: list[ReviewerRole] = Field(alias="reviewersConvened")
    reviewer_conclusions: list[PublicReviewerConclusion] = Field(alias="reviewerConclusions")
    strongest_supporting_evidence_ids: list[Identifier] = Field(alias="strongestSupportingEvidenceIds")
    strongest_contradictory_evidence_ids: list[Identifier] = Field(alias="strongestContradictoryEvidenceIds")
    adversary_objection: NonEmptyText = Field(alias="adversaryObjection")
    chair_determination: NonEmptyText = Field(alias="chairDetermination")
    state_changed: bool = Field(alias="stateChanged")
    change_scope: ChangeScope = Field(default=ChangeScope.NONE, alias="changeScope")
    scientific_state_changed: bool = Field(default=False, alias="scientificStateChanged")
    operational_state_changed: bool = Field(default=False, alias="operationalStateChanged")
    previous_state_preserved: bool | Literal["not_recorded"] = Field(default="not_recorded", alias="previousStatePreserved")
    what_changed: NonEmptyText = Field(alias="whatChanged")
    next_action: NonEmptyText = Field(alias="nextAction")
    linked_artifact_ids: list[Identifier] = Field(default_factory=list, alias="linkedArtifactIds")

    @model_validator(mode="after")
    def validate_dates(self) -> PublicLiveRun:
        object.__setattr__(self, "started_at", _require_timezone(self.started_at, "started_at"))
        object.__setattr__(self, "completed_at", _require_timezone(self.completed_at, "completed_at"))
        return self

    @classmethod
    def from_internal(cls, run: LiveRun) -> PublicLiveRun:
        return cls(
            runId=run.run_id,
            programId=run.program_id,
            startedAt=run.started_at,
            completedAt=run.completed_at,
            selectedMatter=PublicCurrentMatter.from_internal(run.selected_matter),
            whySelected=run.why_selected,
            reviewersConvened=run.reviewers_convened,
            reviewerConclusions=[
                PublicReviewerConclusion(
                    reviewerRole=item.reviewer_role,
                    conclusion=("This conclusion was not accepted as sufficiently evidence-supported."
                                if item.unsupported or item.evidence_gap else item.conclusion),
                    evidenceIds=item.evidence_ids,
                    claimIds=item.claim_ids,
                    limitations=["Supporting canonical evidence is insufficient."] if item.unsupported or item.evidence_gap else item.limitations,
                    unsupported=item.unsupported or bool(item.evidence_gap),
                    evidenceGap="Supporting canonical evidence is insufficient." if item.unsupported or item.evidence_gap else None,
                )
                for item in run.reviewer_conclusions
            ],
            strongestSupportingEvidenceIds=run.strongest_supporting_evidence_ids,
            strongestContradictoryEvidenceIds=run.strongest_contradictory_evidence_ids,
            adversaryObjection=run.adversary_objection,
            chairDetermination=run.chair_determination,
            stateChanged=run.state_changed,
            changeScope=run.change_scope,
            scientificStateChanged=run.scientific_state_changed,
            operationalStateChanged=run.operational_state_changed,
            previousStatePreserved=run.previous_state_preserved,
            whatChanged=run.what_changed,
            nextAction=run.next_action,
            linkedArtifactIds=[item for item in run.artifact_ids if "private-" not in item],
        )


class PublicLiveIntelligence(SignalModel):
    status: LiveIntelligenceStatus
    current_matter: PublicCurrentMatter | None = Field(default=None, alias="currentMatter")
    latest_run: PublicLiveRun | None = Field(default=None, alias="latestRun")
    recent_runs: list[PublicLiveRun] = Field(default_factory=list, alias="recentRuns")
