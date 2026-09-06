"""Canonical biology-to-product-to-market workspace contracts."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import Field, HttpUrl, model_validator

from signalai.schemas.models import Identifier, NonEmptyText, SignalModel, _require_timezone


class EvidenceLevel(StrEnum):
    NOT_ASSESSED = "not_assessed"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class DevelopmentDisposition(StrEnum):
    FOCUS = "focus"
    CANDIDATE = "candidate"
    BENCHMARK = "benchmark"
    EXCLUDED = "excluded"


class CargoType(StrEnum):
    NATIVE_SECRETOME = "native_secretome"
    MIRNA = "mirna"
    PROTEIN = "protein"
    ENGINEERED_CARGO = "engineered_cargo"
    PEPTIDE = "peptide"
    SMALL_MOLECULE = "small_molecule"
    BENCHMARK_MODALITY = "benchmark_modality"
    OTHER = "other"


class EvidenceRelationship(StrEnum):
    SUPPORTIVE = "supportive"
    CONTRADICTORY = "contradictory"
    NEUTRAL = "neutral"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    DEFERRED = "deferred"


class DevelopmentAction(SignalModel):
    action_id: Identifier
    action: NonEmptyText
    objective: NonEmptyText
    rationale: NonEmptyText
    uncertainty: NonEmptyText
    success_criteria: list[NonEmptyText] = Field(default_factory=list)
    status: ActionStatus = ActionStatus.PROPOSED
    requires_human_approval: bool = True
    linked_hypothesis_ids: list[Identifier] = Field(default_factory=list)
    linked_risk_ids: list[Identifier] = Field(default_factory=list)
    linked_decision_ids: list[Identifier] = Field(default_factory=list)
    linked_agenda_item_ids: list[Identifier] = Field(default_factory=list)


class DomainLinks(SignalModel):
    hypothesis_ids: list[Identifier] = Field(default_factory=list)
    risk_ids: list[Identifier] = Field(default_factory=list)
    decision_ids: list[Identifier] = Field(default_factory=list)
    agenda_item_ids: list[Identifier] = Field(default_factory=list)
    next_actions: list[DevelopmentAction] = Field(default_factory=list)


class CargoCandidate(SignalModel):
    cargo_candidate_id: Identifier
    name: NonEmptyText
    cargo_type: CargoType
    source: NonEmptyText
    mechanism: NonEmptyText
    target_pathway_ids: list[Identifier] = Field(default_factory=list)
    relevant_tissues: list[NonEmptyText] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(default_factory=list)
    evidence_level: EvidenceLevel
    supportive_evidence_ids: list[Identifier] = Field(default_factory=list)
    contradictory_evidence_ids: list[Identifier] = Field(default_factory=list)
    rationale: NonEmptyText
    development_status: DevelopmentDisposition
    evidence_rank: int | None = Field(default=None, ge=1)
    exclusion_reason: str | None = None
    uncertainty: NonEmptyText
    biological_targets: list[NonEmptyText] = Field(default_factory=list)
    evidence_annotation: str | None = None
    source_citation: str | None = None
    context_dependent: bool = False
    legacy_source_file: str | None = None

    @model_validator(mode="after")
    def validate_disposition(self) -> CargoCandidate:
        if self.development_status is DevelopmentDisposition.EXCLUDED and not self.exclusion_reason:
            raise ValueError("excluded cargo candidates require exclusion_reason")
        if self.development_status is not DevelopmentDisposition.EXCLUDED and self.exclusion_reason:
            raise ValueError("exclusion_reason is only valid for excluded cargo candidates")
        linked = set(self.supportive_evidence_ids + self.contradictory_evidence_ids)
        if linked - set(self.evidence_ids):
            raise ValueError("supportive and contradictory evidence must be in evidence_ids")
        return self


class BiologicalPathway(SignalModel):
    pathway_id: Identifier
    name: NonEmptyText
    description: NonEmptyText
    evidence_ids: list[Identifier] = Field(default_factory=list)


class CargoEvidenceLink(SignalModel):
    cargo_candidate_id: Identifier
    evidence_id: Identifier
    relationship: EvidenceRelationship
    rationale: NonEmptyText


class CargoPathwayLink(SignalModel):
    cargo_candidate_id: Identifier
    pathway_id: Identifier
    evidence_ids: list[Identifier] = Field(default_factory=list)
    rationale: NonEmptyText


class CargoState(SignalModel):
    operator_focus_candidate_ids: list[Identifier] = Field(default_factory=list)
    ranking_methodology: NonEmptyText
    candidates: list[CargoCandidate] = Field(default_factory=list)
    pathways: list[BiologicalPathway] = Field(default_factory=list)
    evidence_links: list[CargoEvidenceLink] = Field(default_factory=list)
    pathway_links: list[CargoPathwayLink] = Field(default_factory=list)
    links: DomainLinks

    @model_validator(mode="after")
    def validate_relationships(self) -> CargoState:
        candidate_ids = {item.cargo_candidate_id for item in self.candidates}
        pathway_ids = {item.pathway_id for item in self.pathways}
        if len(candidate_ids) != len(self.candidates) or len(pathway_ids) != len(self.pathways):
            raise ValueError("cargo candidate and pathway IDs must be unique")
        if set(self.operator_focus_candidate_ids) - candidate_ids:
            raise ValueError("operator focus references unknown cargo candidates")
        for candidate in self.candidates:
            if set(candidate.target_pathway_ids) - pathway_ids:
                raise ValueError("cargo candidate references unknown pathways")
        for link in self.evidence_links:
            if link.cargo_candidate_id not in candidate_ids:
                raise ValueError("cargo evidence link references unknown candidate")
        for link in self.pathway_links:
            if link.cargo_candidate_id not in candidate_ids or link.pathway_id not in pathway_ids:
                raise ValueError("cargo pathway link references unknown entity")
        return self


class ScoreLevel(StrEnum):
    NOT_ASSESSED = "not_assessed"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


SCORE_POINTS = {
    ScoreLevel.NOT_ASSESSED: 0,
    ScoreLevel.LOW: 1,
    ScoreLevel.MODERATE: 2,
    ScoreLevel.HIGH: 3,
}


class FormulationScore(SignalModel):
    mechanism: ScoreLevel
    evidence: ScoreLevel
    manufacturability: ScoreLevel
    regulatory_deployment: ScoreLevel
    total_score: int = Field(ge=0, le=12)
    methodology: NonEmptyText

    @model_validator(mode="after")
    def validate_total(self) -> FormulationScore:
        expected = sum(
            SCORE_POINTS[value]
            for value in (
                self.mechanism,
                self.evidence,
                self.manufacturability,
                self.regulatory_deployment,
            )
        )
        if self.total_score != expected:
            raise ValueError(f"total_score must equal ordinal component sum ({expected})")
        return self


class FormulationCandidate(SignalModel):
    formulation_candidate_id: Identifier
    name: NonEmptyText
    modality: NonEmptyText
    active_cargo_strategy: NonEmptyText
    route: NonEmptyText
    score: FormulationScore
    status: DevelopmentDisposition
    rationale: NonEmptyText
    tradeoffs: list[NonEmptyText] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(default_factory=list)
    exclusion_reason: str | None = None
    legacy_scores: dict[str, int] = Field(default_factory=dict)
    legacy_source_file: str | None = None

    @model_validator(mode="after")
    def validate_exclusion(self) -> FormulationCandidate:
        if self.status is DevelopmentDisposition.EXCLUDED and not self.exclusion_reason:
            raise ValueError("excluded formulation candidates require exclusion_reason")
        if self.status is not DevelopmentDisposition.EXCLUDED and self.exclusion_reason:
            raise ValueError("exclusion_reason is only valid for excluded formulations")
        return self


class ExcipientCandidate(SignalModel):
    excipient_candidate_id: Identifier
    name: NonEmptyText
    functional_role: NonEmptyText
    proposed_concentration: str | None = None
    ev_compatibility: ScoreLevel
    intranasal_precedent: ScoreLevel
    human_precedent: ScoreLevel
    regulatory_precedent: ScoreLevel
    formulation_value: ScoreLevel
    risk: NonEmptyText
    evidence_ids: list[Identifier] = Field(default_factory=list)
    inclusion_status: DevelopmentDisposition
    exclusion_reason: str | None = None
    precedent_summary: str | None = None
    tradeoff: str | None = None
    legacy_precedent_strength: int | None = Field(default=None, ge=0)
    legacy_ev_stability: int | None = Field(default=None, ge=0)
    legacy_source_file: str | None = None

    @model_validator(mode="after")
    def validate_exclusion(self) -> ExcipientCandidate:
        if self.inclusion_status is DevelopmentDisposition.EXCLUDED and not self.exclusion_reason:
            raise ValueError("excluded excipients require exclusion_reason")
        return self


class FormulationAttribute(SignalModel):
    attribute_id: Identifier
    name: NonEmptyText
    target: str | None = None
    status: ActionStatus
    rationale: NonEmptyText
    evidence_ids: list[Identifier] = Field(default_factory=list)


class PresentationCandidate(SignalModel):
    presentation_id: Identifier
    format: NonEmptyText
    shelf_life: NonEmptyText
    cold_chain: NonEmptyText
    user_steps: NonEmptyText
    verdict: NonEmptyText
    status: DevelopmentDisposition
    legacy_source_file: str | None = None


class FormulationState(SignalModel):
    scoring_methodology: NonEmptyText
    candidates: list[FormulationCandidate] = Field(default_factory=list)
    excipients: list[ExcipientCandidate] = Field(default_factory=list)
    attributes: list[FormulationAttribute] = Field(default_factory=list)
    presentations: list[PresentationCandidate] = Field(default_factory=list)
    links: DomainLinks


class JurisdictionVerdict(StrEnum):
    VIABLE = "viable"
    GREY = "grey"
    RESTRICTIVE = "restrictive"
    PROHIBITED = "prohibited"
    UNRESOLVED = "unresolved"


class EnforcementIntensity(StrEnum):
    NOT_ASSESSED = "not_assessed"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class PriorityLevel(StrEnum):
    NOT_ASSESSED = "not_assessed"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class JurisdictionSourceDocument(SignalModel):
    source_document_id: Identifier
    title: NonEmptyText
    issuer: NonEmptyText
    source_uri: HttpUrl | None = None
    published_at: date | None = None
    accessed_at: datetime
    locator: str | None = None
    citation: str | None = None
    legacy_source_file: str | None = None

    @model_validator(mode="after")
    def validate_accessed_at(self) -> JurisdictionSourceDocument:
        object.__setattr__(
            self, "accessed_at", _require_timezone(self.accessed_at, "accessed_at")
        )
        if self.source_uri is None and not self.citation and not self.legacy_source_file:
            raise ValueError(
                "jurisdiction sources require source_uri, citation, or legacy source file"
            )
        return self


class JurisdictionVerificationStatus(StrEnum):
    VERIFIED_PRIMARY = "verified_primary"
    LEGACY_IMPORT_UNVERIFIED = "legacy_import_unverified"


class JurisdictionLegalBasis(SignalModel):
    instrument: NonEmptyText
    citation: str | None = None
    date: str | None = None
    summary: NonEmptyText


class EnforcementAction(SignalModel):
    date: NonEmptyText
    body: NonEmptyText
    target: NonEmptyText
    note: NonEmptyText


class Jurisdiction(SignalModel):
    jurisdiction_id: Identifier
    jurisdiction: NonEmptyText
    country: NonEmptyText
    region: NonEmptyText
    verdict: JurisdictionVerdict
    enforcement_intensity: EnforcementIntensity
    evidence_confidence: EvidenceLevel
    priority: PriorityLevel
    product_classification: NonEmptyText
    applicable_legal_framework: list[NonEmptyText] = Field(default_factory=list)
    private_clinic_path: NonEmptyText
    physician_use_path: NonEmptyText
    manufacturing_import_considerations: NonEmptyText
    cell_tissue_sourcing_rules: str | None = None
    advertising_constraints: NonEmptyText
    source_document_ids: list[Identifier] = Field(min_length=1)
    last_verified_at: datetime
    unresolved_questions: list[NonEmptyText] = Field(default_factory=list)
    next_action: DevelopmentAction
    concise_rationale: NonEmptyText
    verification_status: JurisdictionVerificationStatus = (
        JurisdictionVerificationStatus.LEGACY_IMPORT_UNVERIFIED
    )
    clinical_status: str | None = None
    cosmetic_status: str | None = None
    permitted_activities: list[str] = Field(default_factory=list)
    grey_areas: list[str] = Field(default_factory=list)
    prohibited_activities: list[str] = Field(default_factory=list)
    cell_source_rules: dict[str, str] = Field(default_factory=dict)
    enforcement_actions: list[EnforcementAction] = Field(default_factory=list)
    legacy_priority_rank: int | None = Field(default=None, ge=1)
    frontier: bool = False
    headline: str | None = None
    momentum: str | None = None
    tension: str | None = None
    through_line: str | None = None
    legacy_source_file: str | None = None
    legal_basis: list[JurisdictionLegalBasis] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_last_verified(self) -> Jurisdiction:
        object.__setattr__(
            self,
            "last_verified_at",
            _require_timezone(self.last_verified_at, "last_verified_at"),
        )
        return self


class JurisdictionState(SignalModel):
    disclaimer: NonEmptyText
    sources: list[JurisdictionSourceDocument] = Field(default_factory=list)
    jurisdictions: list[Jurisdiction] = Field(default_factory=list)
    links: DomainLinks

    @model_validator(mode="after")
    def validate_sources(self) -> JurisdictionState:
        source_ids = {item.source_document_id for item in self.sources}
        if len(source_ids) != len(self.sources):
            raise ValueError("jurisdiction source IDs must be unique")
        for jurisdiction in self.jurisdictions:
            if set(jurisdiction.source_document_ids) - source_ids:
                raise ValueError("jurisdiction references unknown source documents")
        return self


class TherapeuticAssetWorkspace(SignalModel):
    schema_version: str = "1.0"
    program_id: Identifier
    generated_at: datetime
    cargo: CargoState
    formulation: FormulationState
    jurisdictions: JurisdictionState

    @model_validator(mode="after")
    def validate_generated_at(self) -> TherapeuticAssetWorkspace:
        object.__setattr__(
            self, "generated_at", _require_timezone(self.generated_at, "generated_at")
        )
        return self
