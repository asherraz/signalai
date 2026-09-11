"""Canonical contracts for live autonomous therapeutic-development work."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from signalai.schemas.daily import DailySynthesis
from signalai.schemas.models import (
    Claim,
    Decision,
    EvidenceConfidence,
    Hypothesis,
    Identifier,
    NonEmptyText,
    ProgramStatus,
    Risk,
    SignalModel,
    _require_timezone,
)


class MatterDomain(StrEnum):
    EVIDENCE = "evidence"
    CARGO = "cargo"
    FORMULATION = "formulation"
    DELIVERY = "delivery"
    CMC_MANUFACTURING = "cmc_manufacturing"
    TRANSLATIONAL = "translational"
    JURISDICTION = "jurisdiction"
    CLINICAL_DEPLOYMENT = "clinical_deployment"
    COMMERCIAL = "commercial"


class MatterPriority(StrEnum):
    PROGRAM_INVALIDATING = "program_invalidating"
    STAGE_BLOCKING = "stage_blocking"
    PRODUCT_DEFINITION = "product_definition"
    DEPLOYMENT_BLOCKING = "deployment_blocking"
    QUALITY_BLOCKING = "quality_blocking"
    CONTRADICTORY_EVIDENCE = "contradictory_evidence"
    EXPERIMENT_DESIGN = "experiment_design"
    SCIENTIFIC_REFINEMENT = "scientific_refinement"


class AdvancementValue(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class MatterStatus(StrEnum):
    OPEN = "open"
    SELECTED = "selected"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    DEFERRED = "deferred"


class ReviewerRole(StrEnum):
    EVIDENCE = "evidence"
    LITERATURE = "literature"
    CARGO = "cargo"
    FORMULATION = "formulation"
    DELIVERY = "delivery"
    CMC = "cmc"
    MANUFACTURING = "manufacturing"
    TRANSLATIONAL = "translational"
    PRECLINICAL = "preclinical"
    JURISDICTION = "jurisdiction"
    CLINICAL = "clinical"
    COMMERCIAL = "commercial"
    VERIFIER = "verifier"
    ADVERSARY = "adversary"
    CHAIR = "chair"


class DevelopmentMatter(SignalModel):
    matter_id: Identifier
    program_id: Identifier
    title: NonEmptyText
    question: NonEmptyText
    domain: MatterDomain
    why_it_matters: NonEmptyText
    priority: MatterPriority
    advancement_value: AdvancementValue
    blocking_stage: str | None = None
    linked_hypothesis_ids: list[Identifier] = Field(default_factory=list)
    linked_risk_ids: list[Identifier] = Field(default_factory=list)
    linked_evidence_ids: list[Identifier] = Field(default_factory=list)
    required_reviewer_roles: list[ReviewerRole] = Field(min_length=1)
    status: MatterStatus = MatterStatus.OPEN
    selected_at: datetime | None = None
    completed_at: datetime | None = None
    determination: str | None = None
    next_action: str | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> DevelopmentMatter:
        if len(self.required_reviewer_roles) != len(set(self.required_reviewer_roles)):
            raise ValueError("required reviewer roles must be unique")
        for field in ("selected_at", "completed_at"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _require_timezone(value, field))
        if self.status is MatterStatus.OPEN and self.selected_at is not None:
            raise ValueError("open matters cannot have selected_at")
        if self.status is MatterStatus.COMPLETED:
            if self.completed_at is None or not self.determination or not self.next_action:
                raise ValueError("completed matters require completion, determination, and next action")
        elif self.completed_at is not None or self.determination is not None:
            raise ValueError("only completed matters may have completion or determination")
        return self


CurrentMatter = DevelopmentMatter


class DevelopmentDocket(SignalModel):
    program_id: Identifier
    version: str = "1.0"
    updated_at: datetime
    matters: list[DevelopmentMatter] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_docket(self) -> DevelopmentDocket:
        object.__setattr__(self, "updated_at", _require_timezone(self.updated_at, "updated_at"))
        ids = [item.matter_id for item in self.matters]
        if len(ids) != len(set(ids)):
            raise ValueError("development docket contains duplicate matter IDs")
        if any(item.program_id != self.program_id for item in self.matters):
            raise ValueError("all matters must belong to the docket program")
        return self


class ReviewerConclusion(SignalModel):
    reviewer_role: ReviewerRole
    conclusion: NonEmptyText
    evidence_ids: list[Identifier] = Field(default_factory=list)
    claim_ids: list[Identifier] = Field(default_factory=list)
    limitations: list[NonEmptyText] = Field(default_factory=list)


class LiveAnalysis(SignalModel):
    matter_id: Identifier
    objective: NonEmptyText
    reviewer_conclusions: list[ReviewerConclusion] = Field(min_length=1)
    strongest_support_summary: NonEmptyText
    strongest_supporting_evidence_ids: list[Identifier] = Field(default_factory=list)
    strongest_contradiction_summary: NonEmptyText
    strongest_contradictory_evidence_ids: list[Identifier] = Field(default_factory=list)
    proposed_next_action: NonEmptyText


class LiveVerification(SignalModel):
    matter_id: Identifier
    conclusion: NonEmptyText
    verified_evidence_ids: list[Identifier] = Field(default_factory=list)
    unsupported_assertions: list[NonEmptyText] = Field(default_factory=list)
    supports_state_change: bool


class LiveAdversaryReview(SignalModel):
    matter_id: Identifier
    strongest_objection: NonEmptyText
    assumptions_challenged: list[NonEmptyText] = Field(min_length=1)
    disconfirming_evidence_ids: list[Identifier] = Field(default_factory=list)
    falsification_conditions: list[NonEmptyText] = Field(min_length=1)
    supports_state_change: bool


class ChairProposedChanges(SignalModel):
    """Model proposals split into editorial, operational, scientific, and decision scopes."""

    editorial_clarification: str | None = None
    next_action: str | None = None
    claim_updates: list[Claim] = Field(default_factory=list)
    hypothesis_update: Hypothesis | None = None
    risk_updates: list[Risk] = Field(default_factory=list)
    evidence_confidence_update: EvidenceConfidence | None = None
    program_status_update: ProgramStatus | None = None
    decision_update: Decision | None = None

    @property
    def has_scientific_change(self) -> bool:
        return bool(
            self.claim_updates
            or self.hypothesis_update
            or self.risk_updates
            or self.evidence_confidence_update
            or self.program_status_update
        )


class LiveChairRecommendation(SignalModel):
    """Typed model output containing science, not lifecycle self-classification."""

    matter_id: Identifier
    findings: list[NonEmptyText] = Field(min_length=1, max_length=5)
    evidence_assessment: NonEmptyText
    supporting_evidence_ids: list[Identifier] = Field(default_factory=list)
    objections: list[NonEmptyText] = Field(min_length=1, max_length=5)
    recommendation: NonEmptyText
    proposed_changes: ChairProposedChanges = Field(default_factory=ChairProposedChanges)

    @model_validator(mode="after")
    def require_provenance_for_scientific_change(self) -> LiveChairRecommendation:
        if self.proposed_changes.has_scientific_change and not self.supporting_evidence_ids:
            raise ValueError("scientific proposed changes require supporting_evidence_ids")
        return self


class DeterminationKind(StrEnum):
    NO_MATERIAL_CHANGE = "no_material_change"
    STATE_UPDATE = "state_update"
    DECISION_UPDATE = "decision_update"
    HUMAN_DECISION_REQUIRED = "human_decision_required"


class ChangeScope(StrEnum):
    NONE = "none"
    EDITORIAL = "editorial_clarification"
    OPERATIONAL = "operational_next_action"
    SCIENTIFIC = "scientific_state"
    DECISION = "decision"


class NoMaterialChangeDetermination(SignalModel):
    determination: Literal[DeterminationKind.NO_MATERIAL_CHANGE]
    change_scope: Literal[ChangeScope.NONE, ChangeScope.EDITORIAL, ChangeScope.OPERATIONAL]
    scientific_state_changed: Literal[False] = False
    operational_state_changed: bool = False
    synthesis: DailySynthesis

    @model_validator(mode="after")
    def reject_mutations(self) -> NoMaterialChangeDetermination:
        if self.synthesis.material_change:
            raise ValueError("no_material_change cannot contain scientific mutations")
        if (
            self.synthesis.claim_updates
            or self.synthesis.hypothesis_update
            or self.synthesis.risk_updates
            or self.synthesis.evidence_confidence_update
            or self.synthesis.program_status_update
        ):
            raise ValueError("no_material_change scientific update fields must be empty")
        if self.synthesis.decision_proposal is not None:
            raise ValueError("no_material_change cannot contain a decision update")
        if self.change_scope is ChangeScope.OPERATIONAL and not self.synthesis.next_action:
            raise ValueError("operational change requires next_action")
        return self


class MaterialChangeDetermination(SignalModel):
    determination: Literal[
        DeterminationKind.STATE_UPDATE,
        DeterminationKind.DECISION_UPDATE,
        DeterminationKind.HUMAN_DECISION_REQUIRED,
    ]
    change_scope: Literal[ChangeScope.SCIENTIFIC, ChangeScope.DECISION]
    scientific_state_changed: bool
    operational_state_changed: bool = False
    synthesis: DailySynthesis

    @model_validator(mode="after")
    def require_mutation(self) -> MaterialChangeDetermination:
        if not self.synthesis.material_change:
            raise ValueError("material determination requires a material synthesis")
        if self.determination is DeterminationKind.STATE_UPDATE and not self.scientific_state_changed:
            raise ValueError("state_update requires a scientific state mutation")
        if self.determination in {
            DeterminationKind.DECISION_UPDATE,
            DeterminationKind.HUMAN_DECISION_REQUIRED,
        } and self.synthesis.decision_proposal is None:
            raise ValueError("decision determination requires a decision update")
        return self


DeterminationResult = Annotated[
    NoMaterialChangeDetermination | MaterialChangeDetermination,
    Field(discriminator="determination"),
]


class LiveChairDetermination(SignalModel):
    """Application-derived, structurally consistent Chair lifecycle result."""

    matter_id: Identifier
    recommendation: LiveChairRecommendation
    result: DeterminationResult

    @model_validator(mode="after")
    def validate_alignment(self) -> LiveChairDetermination:
        if self.recommendation.matter_id != self.matter_id:
            raise ValueError("chair recommendation references a different matter")
        if self.result.synthesis.agenda_item_id != self.matter_id:
            raise ValueError("chair synthesis references a different matter")
        return self


class LiveRun(SignalModel):
    run_id: Identifier
    program_id: Identifier
    started_at: datetime
    completed_at: datetime
    selected_matter: DevelopmentMatter
    why_selected: NonEmptyText
    reviewers_convened: list[ReviewerRole] = Field(min_length=4)
    reviewer_conclusions: list[ReviewerConclusion] = Field(min_length=1)
    strongest_supporting_evidence_ids: list[Identifier] = Field(default_factory=list)
    strongest_contradictory_evidence_ids: list[Identifier] = Field(default_factory=list)
    adversary_objection: NonEmptyText
    chair_determination: NonEmptyText
    state_changed: bool
    change_scope: ChangeScope = ChangeScope.NONE
    scientific_state_changed: bool = False
    operational_state_changed: bool = False
    what_changed: NonEmptyText
    next_action: NonEmptyText
    artifact_ids: list[Identifier] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_run(self) -> LiveRun:
        object.__setattr__(self, "started_at", _require_timezone(self.started_at, "started_at"))
        object.__setattr__(self, "completed_at", _require_timezone(self.completed_at, "completed_at"))
        if self.completed_at < self.started_at:
            raise ValueError("live run cannot complete before it starts")
        if self.selected_matter.program_id != self.program_id:
            raise ValueError("selected matter belongs to a different program")
        required = {ReviewerRole.VERIFIER, ReviewerRole.ADVERSARY, ReviewerRole.CHAIR}
        if not required.issubset(self.reviewers_convened):
            raise ValueError("live runs require independent verifier, adversary, and chair roles")
        if len(self.reviewers_convened) != len(set(self.reviewers_convened)):
            raise ValueError("reviewers convened must be unique")
        return self


class LiveRunHistory(SignalModel):
    program_id: Identifier
    updated_at: datetime
    runs: list[LiveRun] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_history(self) -> LiveRunHistory:
        object.__setattr__(self, "updated_at", _require_timezone(self.updated_at, "updated_at"))
        ids = [run.run_id for run in self.runs]
        if len(ids) != len(set(ids)):
            raise ValueError("live run history contains duplicate IDs")
        if any(run.program_id != self.program_id for run in self.runs):
            raise ValueError("live run history mixes programs")
        return self
