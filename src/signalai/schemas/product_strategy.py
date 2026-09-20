"""Canonical evidence-weighted SGL-001 product architecture strategy."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from signalai.schemas.models import ApprovalStatus, Identifier, NonEmptyText, SignalModel, _require_timezone


class StrategyConfidence(StrEnum):
    MISSING = "missing"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class AssessmentSourceType(StrEnum):
    EVIDENCE = "evidence"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"
    DECISION = "decision"


class ArchitectureDimension(StrEnum):
    HUMAN_FEASIBILITY = "near_term_human_data_feasibility"
    SAFETY = "safety_readiness"
    PRODUCT_QC = "product_definition_and_qc"
    BIOLOGY = "biological_rationale_and_impact"
    MANUFACTURING = "manufacturing_readiness"
    SCALABILITY = "scalability_and_economics"
    REGULATORY = "regulatory_clarity_and_data_portability"


DIMENSION_WEIGHTS = {
    ArchitectureDimension.HUMAN_FEASIBILITY: 20,
    ArchitectureDimension.SAFETY: 20,
    ArchitectureDimension.PRODUCT_QC: 15,
    ArchitectureDimension.BIOLOGY: 15,
    ArchitectureDimension.MANUFACTURING: 10,
    ArchitectureDimension.SCALABILITY: 10,
    ArchitectureDimension.REGULATORY: 10,
}
CONFIDENCE_FACTORS = {
    StrategyConfidence.MISSING: 0.0,
    StrategyConfidence.LOW: 0.5,
    StrategyConfidence.MODERATE: 0.75,
    StrategyConfidence.HIGH: 1.0,
}


class ArchitectureDisposition(StrEnum):
    PROVISIONAL_LEAD = "provisional_lead"
    ACTIVE_COMPARATOR = "active_comparator"
    RESEARCH_ONLY = "research_only"
    BLOCKED = "blocked"
    WATCHLIST = "watchlist"
    PARKED = "parked"
    REJECTED = "rejected"


class HardGateState(StrEnum):
    PASSED = "passed"
    UNRESOLVED = "unresolved"
    FAILED = "failed"


class StrategyDeterminationType(StrEnum):
    NO_MATERIAL_CHANGE = "no_material_change"
    LEAD_STRATEGY_PROPOSED = "lead_strategy_proposed"
    HUMAN_DECISION_REQUIRED = "human_decision_required"
    EVIDENCE_GAP = "evidence_gap"
    ARCHITECTURE_PARKED = "architecture_parked"
    ARCHITECTURE_REJECTED = "architecture_rejected"


class TherapeuticObjective(SignalModel):
    objective_id: Identifier
    program_id: Identifier
    statement: NonEmptyText
    intended_strategy: NonEmptyText
    disclaimer: NonEmptyText
    evidence_ids: list[Identifier] = Field(default_factory=list)


class ArchitectureDimensionAssessment(SignalModel):
    assessment_id: Identifier
    candidate_id: Identifier
    dimension: ArchitectureDimension
    weight: int = Field(ge=0, le=100)
    rating: int = Field(ge=0, le=5)
    confidence: StrategyConfidence
    evidence_status: NonEmptyText
    rationale: NonEmptyText
    uncertainty: NonEmptyText
    evidence_ids: list[Identifier] = Field(default_factory=list)
    source_type: AssessmentSourceType
    potential_contribution: float = Field(ge=0, le=100)
    confidence_adjusted_contribution: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_calculation(self):
        expected_weight = DIMENSION_WEIGHTS[self.dimension]
        potential = expected_weight * self.rating / 5
        adjusted = potential * CONFIDENCE_FACTORS[self.confidence]
        if self.weight != expected_weight:
            raise ValueError("dimension weight does not match canonical strategy weights")
        if abs(self.potential_contribution - potential) > 1e-6:
            raise ValueError("potential contribution is not deterministically calculated")
        if abs(self.confidence_adjusted_contribution - adjusted) > 1e-6:
            raise ValueError("confidence-adjusted contribution is not deterministically calculated")
        return self


class ArchitectureAssessment(SignalModel):
    assessment_id: Identifier
    run_id: Identifier
    candidate_id: Identifier
    assessed_at: datetime
    dimension_assessments: list[ArchitectureDimensionAssessment]
    raw_potential_score: float = Field(ge=0, le=100)
    confidence_adjusted_decision_score: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_assessment(self):
        object.__setattr__(self, "assessed_at", _require_timezone(self.assessed_at, "assessed_at"))
        dimensions = [item.dimension for item in self.dimension_assessments]
        if set(dimensions) != set(ArchitectureDimension) or len(dimensions) != len(set(dimensions)):
            raise ValueError("architecture assessment requires each weighted dimension exactly once")
        potential = sum(item.potential_contribution for item in self.dimension_assessments)
        adjusted = sum(item.confidence_adjusted_contribution for item in self.dimension_assessments)
        if abs(self.raw_potential_score - potential) > 1e-6 or abs(self.confidence_adjusted_decision_score - adjusted) > 1e-6:
            raise ValueError("architecture totals are not deterministic assessment sums")
        return self


class ArchitectureHardGate(SignalModel):
    gate_id: Identifier
    candidate_id: Identifier
    name: NonEmptyText
    status: HardGateState
    rationale: NonEmptyText
    evidence_ids: list[Identifier] = Field(default_factory=list)


class ProductArchitectureCandidate(SignalModel):
    candidate_id: Identifier
    program_id: Identifier
    designation: NonEmptyText
    name: NonEmptyText
    short_description: NonEmptyText
    architecture_class: NonEmptyText
    strategic_role: NonEmptyText
    lifecycle_status: ArchitectureDisposition
    current_disposition: ArchitectureDisposition
    hard_gates: list[ArchitectureHardGate]
    dimension_assessments: list[ArchitectureDimensionAssessment]
    raw_potential_score: float = Field(ge=0, le=100)
    confidence_adjusted_decision_score: float = Field(ge=0, le=100)
    overall_confidence: StrategyConfidence
    principal_advantage: NonEmptyText
    largest_obstacle: NonEmptyText
    critical_unknowns: list[NonEmptyText]
    next_discriminating_action: NonEmptyText
    evidence_ids: list[Identifier] = Field(default_factory=list)
    last_assessed_at: datetime

    @model_validator(mode="after")
    def validate_candidate(self):
        object.__setattr__(self, "last_assessed_at", _require_timezone(self.last_assessed_at, "last_assessed_at"))
        dimensions = [item.dimension for item in self.dimension_assessments]
        if set(dimensions) != set(ArchitectureDimension) or len(dimensions) != len(set(dimensions)):
            raise ValueError("candidate requires each strategy dimension exactly once")
        if any(item.candidate_id != self.candidate_id for item in self.dimension_assessments):
            raise ValueError("dimension assessment candidate mismatch")
        if any(item.candidate_id != self.candidate_id for item in self.hard_gates):
            raise ValueError("hard gate candidate mismatch")
        if any(g.status is HardGateState.FAILED for g in self.hard_gates) and self.current_disposition is ArchitectureDisposition.PROVISIONAL_LEAD:
            raise ValueError("failed hard gate prevents provisional lead disposition")
        return self


class StrategyDetermination(SignalModel):
    determination_id: Identifier
    run_id: Identifier
    program_id: Identifier
    determination: StrategyDeterminationType
    recommended_candidate_id: Identifier | None = None
    prior_lead_candidate_id: Identifier | None = None
    proposed_ranking: list[Identifier]
    rationale: NonEmptyText
    adversary_summary: NonEmptyText
    unresolved_gates: list[Identifier] = Field(default_factory=list)
    human_approval_required: bool = True
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime

    @model_validator(mode="after")
    def validate_determination(self):
        object.__setattr__(self, "created_at", _require_timezone(self.created_at, "created_at"))
        if not self.human_approval_required or self.approval_status is not ApprovalStatus.PENDING:
            raise ValueError("strategy lead determinations remain pending human approval")
        return self


class StrategyAssessmentHistoryEntry(SignalModel):
    history_entry_id: Identifier
    run_id: Identifier
    assessed_at: datetime
    prior_scores: dict[Identifier, float]
    new_scores: dict[Identifier, float]
    prior_ranking: list[Identifier]
    proposed_ranking: list[Identifier]
    score_deltas: dict[Identifier, float]
    changed_inputs: list[NonEmptyText]
    evidence_ids: list[Identifier] = Field(default_factory=list)
    determination: StrategyDeterminationType
    human_approval_status: ApprovalStatus

    @model_validator(mode="after")
    def validate_time(self):
        object.__setattr__(self, "assessed_at", _require_timezone(self.assessed_at, "assessed_at"))
        return self


class ProductStrategyWorkspace(SignalModel):
    schema_version: str = "1.0"
    program_id: Identifier = "SGL-001"
    therapeutic_objective: TherapeuticObjective
    dimension_weights: dict[ArchitectureDimension, int]
    candidates: list[ProductArchitectureCandidate]
    current_provisional_lead_candidate_id: Identifier | None = None
    latest_determination: StrategyDetermination
    assessment_history: list[StrategyAssessmentHistoryEntry] = Field(default_factory=list)
    input_fingerprint: NonEmptyText
    updated_at: datetime

    @model_validator(mode="after")
    def validate_workspace(self):
        object.__setattr__(self, "updated_at", _require_timezone(self.updated_at, "updated_at"))
        if self.dimension_weights != DIMENSION_WEIGHTS or sum(self.dimension_weights.values()) != 100:
            raise ValueError("strategy dimension weights must match canonical weights totaling 100")
        ids = [item.candidate_id for item in self.candidates]
        if len(ids) != len(set(ids)) or len(self.candidates) != 5:
            raise ValueError("strategy workspace requires five unique architecture candidates")
        if self.current_provisional_lead_candidate_id not in set(ids):
            raise ValueError("current provisional lead must reference a candidate")
        expected = sorted(self.candidates, key=lambda item: (-item.confidence_adjusted_decision_score, item.candidate_id))
        if self.latest_determination.proposed_ranking != [item.candidate_id for item in expected]:
            raise ValueError("strategy ranking must be deterministically score ordered")
        if len({item.run_id for item in self.assessment_history}) != len(self.assessment_history):
            raise ValueError("strategy assessment history run IDs must be unique")
        return self


class StrategyCandidateInput(SignalModel):
    candidate_id: Identifier
    rating: int = Field(ge=0, le=5)
    confidence: StrategyConfidence
    evidence_status: NonEmptyText
    rationale: NonEmptyText
    uncertainty: NonEmptyText
    evidence_ids: list[Identifier] = Field(default_factory=list)
    source_type: AssessmentSourceType


class StrategySpecialistAssessment(SignalModel):
    role: NonEmptyText
    dimension: ArchitectureDimension
    candidates: list[StrategyCandidateInput]


class StrategyAdversaryReview(SignalModel):
    strongest_objection: NonEmptyText
    unsupported_rating_candidate_ids: list[Identifier] = Field(default_factory=list)
    hidden_gate_ids: list[Identifier] = Field(default_factory=list)
    evidence_double_counting_concerns: list[NonEmptyText] = Field(default_factory=list)
    incomparable_assumptions: list[NonEmptyText] = Field(default_factory=list)
    regulatory_overconfidence_concerns: list[NonEmptyText] = Field(default_factory=list)


class StrategyChairRecommendation(SignalModel):
    determination: StrategyDeterminationType
    recommended_candidate_id: Identifier | None = None
    rationale: NonEmptyText
    changed_inputs: list[NonEmptyText] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(default_factory=list)

