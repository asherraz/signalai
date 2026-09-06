"""Frontend-safe contracts for the therapeutic asset workspace."""

from __future__ import annotations

from pydantic import Field

from signalai.schemas.models import Identifier, SignalModel
from signalai.schemas.workspace import (
    ActionStatus,
    DevelopmentDisposition,
    EnforcementIntensity,
    EvidenceLevel,
    JurisdictionVerdict,
    PriorityLevel,
    ScoreLevel,
)


class PublicDomainAction(SignalModel):
    action_id: Identifier = Field(alias="actionId")
    action: str
    objective: str
    uncertainty: str
    success_criteria: list[str] = Field(default_factory=list, alias="successCriteria")
    status: ActionStatus
    requires_human_approval: bool = Field(alias="requiresHumanApproval")


class PublicCargoCandidate(SignalModel):
    id: Identifier
    name: str
    cargo_type: str = Field(alias="cargoType")
    source: str
    mechanism: str
    pathway_ids: list[Identifier] = Field(alias="pathwayIds")
    relevant_tissues: list[str] = Field(alias="relevantTissues")
    evidence_ids: list[Identifier] = Field(alias="evidenceIds")
    supportive_evidence_ids: list[Identifier] = Field(alias="supportiveEvidenceIds")
    contradictory_evidence_ids: list[Identifier] = Field(alias="contradictoryEvidenceIds")
    evidence_level: EvidenceLevel = Field(alias="evidenceLevel")
    evidence_rank: int | None = Field(default=None, alias="evidenceRank")
    rationale: str
    status: DevelopmentDisposition
    exclusion_reason: str | None = Field(default=None, alias="exclusionReason")
    uncertainty: str
    biological_targets: list[str] = Field(default_factory=list, alias="biologicalTargets")
    evidence_annotation: str | None = Field(default=None, alias="evidenceAnnotation")
    source_citation: str | None = Field(default=None, alias="sourceCitation")
    context_dependent: bool = Field(default=False, alias="contextDependent")


class PublicPathway(SignalModel):
    id: Identifier
    name: str
    description: str
    candidate_count: int = Field(ge=0, alias="candidateCount")
    evidence_ids: list[Identifier] = Field(alias="evidenceIds")


class PublicCargoPathwayLink(SignalModel):
    candidate_id: Identifier = Field(alias="candidateId")
    pathway_id: Identifier = Field(alias="pathwayId")
    evidence_ids: list[Identifier] = Field(alias="evidenceIds")


class PublicCargoState(SignalModel):
    operator_focus_candidate_ids: list[Identifier] = Field(alias="operatorFocusCandidateIds")
    ranking_methodology: str = Field(alias="rankingMethodology")
    candidates: list[PublicCargoCandidate]
    pathways: list[PublicPathway]
    candidate_pathway_links: list[PublicCargoPathwayLink] = Field(alias="candidatePathwayLinks")
    filters: dict[str, list[str]]
    focus_candidates: list[Identifier] = Field(alias="focusCandidates")
    benchmarks: list[Identifier]
    next_actions: list[PublicDomainAction] = Field(alias="nextActions")


class PublicFormulationScore(SignalModel):
    mechanism: ScoreLevel
    evidence: ScoreLevel
    manufacturability: ScoreLevel
    regulatory_deployment: ScoreLevel = Field(alias="regulatoryDeployment")
    total_score: int = Field(alias="totalScore")
    methodology: str


class PublicFormulationCandidate(SignalModel):
    id: Identifier
    name: str
    modality: str
    active_cargo_strategy: str = Field(alias="activeCargoStrategy")
    route: str
    score: PublicFormulationScore
    status: DevelopmentDisposition
    rationale: str
    tradeoffs: list[str]
    evidence_ids: list[Identifier] = Field(alias="evidenceIds")
    exclusion_reason: str | None = Field(default=None, alias="exclusionReason")
    legacy_scores: dict[str, int] = Field(default_factory=dict, alias="legacyScores")


class PublicExcipientCandidate(SignalModel):
    id: Identifier
    name: str
    functional_role: str = Field(alias="functionalRole")
    proposed_concentration: str | None = Field(default=None, alias="proposedConcentration")
    ev_compatibility: ScoreLevel = Field(alias="evCompatibility")
    intranasal_precedent: ScoreLevel = Field(alias="intranasalPrecedent")
    human_precedent: ScoreLevel = Field(alias="humanPrecedent")
    regulatory_precedent: ScoreLevel = Field(alias="regulatoryPrecedent")
    formulation_value: ScoreLevel = Field(alias="formulationValue")
    risk: str
    evidence_ids: list[Identifier] = Field(alias="evidenceIds")
    status: DevelopmentDisposition
    precedent_summary: str | None = Field(default=None, alias="precedentSummary")
    tradeoff: str | None = None
    legacy_precedent_strength: int | None = Field(default=None, alias="legacyPrecedentStrength")
    legacy_ev_stability: int | None = Field(default=None, alias="legacyEvStability")


class PublicPresentationCandidate(SignalModel):
    id: Identifier
    format: str
    shelf_life: str = Field(alias="shelfLife")
    cold_chain: str = Field(alias="coldChain")
    user_steps: str = Field(alias="userSteps")
    verdict: str
    status: DevelopmentDisposition


class PublicFormulationState(SignalModel):
    scoring_methodology: str = Field(alias="scoringMethodology")
    score_dimensions: list[str] = Field(alias="scoreDimensions")
    candidates: list[PublicFormulationCandidate]
    excipients: list[PublicExcipientCandidate]
    presentations: list[PublicPresentationCandidate] = Field(default_factory=list)
    functional_role_filters: list[str] = Field(alias="functionalRoleFilters")
    next_actions: list[PublicDomainAction] = Field(alias="nextActions")


class PublicJurisdictionCard(SignalModel):
    id: Identifier
    jurisdiction: str
    country: str
    region: str
    verdict: JurisdictionVerdict
    enforcement_intensity: EnforcementIntensity = Field(alias="enforcementIntensity")
    confidence: EvidenceLevel
    priority: PriorityLevel
    product_classification: str = Field(alias="productClassification")
    private_clinic_path: str = Field(alias="privateClinicPath")
    concise_rationale: str = Field(alias="conciseRationale")
    source_document_ids: list[Identifier] = Field(alias="sourceDocumentIds")
    unresolved_questions: list[str] = Field(alias="unresolvedQuestions")
    next_action: PublicDomainAction = Field(alias="nextAction")
    verification_status: str = Field(
        default="legacy_import_unverified", alias="verificationStatus"
    )
    legacy_priority_rank: int | None = Field(default=None, alias="legacyPriorityRank")
    permitted_activities: list[str] = Field(default_factory=list, alias="permittedActivities")
    grey_areas: list[str] = Field(default_factory=list, alias="greyAreas")
    prohibited_activities: list[str] = Field(default_factory=list, alias="prohibitedActivities")


class PublicJurisdictionState(SignalModel):
    disclaimer: str
    summary_counts: dict[str, int] = Field(alias="summaryCounts")
    jurisdictions: list[PublicJurisdictionCard]
    next_actions: list[PublicDomainAction] = Field(alias="nextActions")
