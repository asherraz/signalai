"""Frontend-safe contracts for SignalAI's network and intelligence product."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pydantic import Field, model_validator

from signalai.schemas.models import (
    ApprovalStatus,
    EvidenceConfidence,
    Identifier,
    NonEmptyText,
    ProgramStatus,
    SignalModel,
    _require_timezone,
)
from signalai.schemas.public_clinical_network import (
    PublicClinicOpportunitySummary,
    PublicClinicProfile,
    PublicRegenerativeClinicThesis,
)


class AccessTier(StrEnum):
    PUBLIC = "public"
    PARTNER = "partner"
    PRO = "pro"


class IntelligenceModuleStatus(StrEnum):
    AVAILABLE = "available"
    DEVELOPING = "developing"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"


class FoundingNetworkStatus(StrEnum):
    FORMING = "forming"
    ACTIVE = "active"


class IntelligenceFeedType(StrEnum):
    EVIDENCE_UPDATE = "evidence_update"
    FORMULATION_UPDATE = "formulation_update"
    CARGO_UPDATE = "cargo_update"
    JURISDICTION_UPDATE = "jurisdiction_update"
    AIRB_DETERMINATION = "airb_determination"
    PROGRAM_STATE_CHANGE = "program_state_change"
    NETWORK_UPDATE = "network_update"


class IntelligenceImportance(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class DataOrigin(StrEnum):
    PUBLIC_SOURCE = "public_source"
    OPERATOR_CURATED = "operator_curated"
    PARTNER_CONTRIBUTED = "partner_contributed"
    FUTURE_OPT_IN = "future_opt_in"


class ProductLayerStatus(StrEnum):
    AVAILABLE = "available"
    ACTIVE = "active"
    READY = "ready"
    EMPTY = "empty"
    FUTURE = "future"


class PublicSignalNarrative(SignalModel):
    company_thesis: NonEmptyText = Field(alias="companyThesis")
    what_signal_is: NonEmptyText = Field(alias="whatSignalIs")
    fragmented_problem: NonEmptyText = Field(alias="fragmentedProblem")
    how_ai_creates_value: NonEmptyText = Field(alias="howAiCreatesValue")
    network_contribution: NonEmptyText = Field(alias="networkContribution")
    program_emergence: NonEmptyText = Field(alias="programEmergence")
    sgl001_proof_point: NonEmptyText = Field(alias="sgl001ProofPoint")


class PublicEcosystemDomain(SignalModel):
    domain_id: Identifier = Field(alias="domainId")
    title: NonEmptyText
    summary: NonEmptyText
    entity_count: int = Field(ge=0, alias="entityCount")
    status: ProductLayerStatus
    record_counts_by_origin: dict[DataOrigin, int] = Field(
        default_factory=dict, alias="recordCountsByOrigin"
    )
    partner_contribution_opt_in_required: bool = Field(
        default=True, alias="partnerContributionOptInRequired"
    )


class PublicEcosystem(SignalModel):
    clinics: PublicEcosystemDomain
    therapies: PublicEcosystemDomain
    products: PublicEcosystemDomain
    jurisdictions: PublicEcosystemDomain
    evidence_sources: PublicEcosystemDomain = Field(alias="evidenceSources")


class PublicIntelligenceCategory(SignalModel):
    category_id: Identifier = Field(alias="categoryId")
    title: NonEmptyText
    summary: NonEmptyText
    module_ids: list[Identifier] = Field(default_factory=list, alias="moduleIds")
    input_origins: list[DataOrigin] = Field(default_factory=list, alias="inputOrigins")
    status: ProductLayerStatus


class PublicLearningLoopStage(SignalModel):
    sequence: int = Field(ge=1, le=7)
    stage_id: Identifier = Field(alias="stageId")
    title: NonEmptyText
    summary: NonEmptyText
    status: ProductLayerStatus
    data_origins: list[DataOrigin] = Field(default_factory=list, alias="dataOrigins")
    current_record_count: int = Field(ge=0, alias="currentRecordCount")
    opt_in_required: bool = Field(default=False, alias="optInRequired")


class PublicLearningLoop(SignalModel):
    summary: NonEmptyText
    stages: list[PublicLearningLoopStage] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def validate_sequence(self) -> PublicLearningLoop:
        if [item.sequence for item in self.stages] != list(range(1, 8)):
            raise ValueError("learning-loop stages must be ordered from 1 through 7")
        return self


class PublicContributionPolicy(SignalModel):
    partner_contribution_opt_in_required: bool = Field(
        alias="partnerContributionOptInRequired"
    )
    default_partner_data_visibility: NonEmptyText = Field(alias="defaultPartnerDataVisibility")
    public_source_provenance_required: bool = Field(alias="publicSourceProvenanceRequired")
    partner_provenance_required: bool = Field(alias="partnerProvenanceRequired")
    outcome_data_status: ProductLayerStatus = Field(alias="outcomeDataStatus")
    outcome_privacy_standard: NonEmptyText = Field(alias="outcomePrivacyStandard")
    contribution_types: list[NonEmptyText] = Field(alias="contributionTypes")


class PublicPartnerIntelligence(SignalModel):
    summary: NonEmptyText
    reference_ids: list[Identifier] = Field(default_factory=list, alias="referenceIds")
    available_fields: list[NonEmptyText] = Field(default_factory=list, alias="availableFields")
    access_tier: AccessTier = Field(default=AccessTier.PARTNER, alias="accessTier")


class PublicIntelligenceModule(SignalModel):
    module_id: Identifier = Field(alias="moduleId")
    title: NonEmptyText
    summary: NonEmptyText
    last_updated: datetime = Field(alias="lastUpdated")
    status: IntelligenceModuleStatus
    public_preview: NonEmptyText = Field(alias="publicPreview")
    access_tier: AccessTier = Field(alias="accessTier")
    key_metrics: dict[str, int | str] = Field(default_factory=dict, alias="keyMetrics")
    recent_changes: list[NonEmptyText] = Field(default_factory=list, alias="recentChanges")
    partner_intelligence: PublicPartnerIntelligence = Field(alias="partnerIntelligence")

    @model_validator(mode="after")
    def validate_last_updated(self) -> PublicIntelligenceModule:
        object.__setattr__(
            self, "last_updated", _require_timezone(self.last_updated, "last_updated")
        )
        return self


class PublicProductNetwork(SignalModel):
    niche_description: NonEmptyText = Field(
        default=(
            "Regenerative medicine clinics working with stem cells, exosomes and "
            "cell-derived therapies."
        ),
        alias="nicheDescription",
    )
    approved_public_clinic_count: int = Field(ge=0, alias="approvedPublicClinicCount")
    countries_represented: list[str] = Field(default_factory=list, alias="countriesRepresented")
    jurisdictions_represented: list[Identifier] = Field(
        default_factory=list, alias="jurisdictionsRepresented"
    )
    partner_status_counts: dict[str, int] = Field(
        default_factory=dict, alias="partnerStatusCounts"
    )
    founding_network_status: FoundingNetworkStatus = Field(alias="foundingNetworkStatus")
    public_clinic_cards: list[PublicClinicProfile] = Field(
        default_factory=list, alias="publicClinicCards"
    )
    sgl001_interested_clinic_ids: list[Identifier] = Field(
        default_factory=list, alias="sgl001InterestedClinicIds"
    )
    recent_network_addition_ids: list[Identifier] = Field(
        default_factory=list, alias="recentNetworkAdditionIds"
    )
    network_thesis: PublicRegenerativeClinicThesis | None = Field(
        default=None, alias="networkThesis"
    )
    clinic_archetype_counts: dict[str, int] = Field(
        default_factory=dict, alias="clinicArchetypeCounts"
    )
    opportunity_summaries: list[PublicClinicOpportunitySummary] = Field(
        default_factory=list, alias="opportunitySummaries"
    )


class PublicIntelligenceIndex(SignalModel):
    modules: list[PublicIntelligenceModule]
    clinic_view: PublicClinicIntelligenceView = Field(alias="clinicView")
    categories: list[PublicIntelligenceCategory] = Field(default_factory=list)


class PublicAirbDetermination(SignalModel):
    decision_id: Identifier = Field(alias="decisionId")
    determination: str | None = None
    approval_status: ApprovalStatus = Field(alias="approvalStatus")
    human_approval_required: bool = Field(alias="humanApprovalRequired")


class PublicProductProgram(SignalModel):
    program_id: Identifier = Field(alias="programId")
    name: NonEmptyText
    development_focus: str | None = Field(default=None, alias="developmentFocus")
    current_hypothesis: NonEmptyText = Field(alias="currentHypothesis")
    evidence_confidence: EvidenceConfidence = Field(alias="evidenceConfidence")
    development_stage: ProgramStatus = Field(alias="developmentStage")
    current_blocker: str | None = Field(default=None, alias="currentBlocker")
    next_action: str | None = Field(default=None, alias="nextAction")
    current_airb_determination: PublicAirbDetermination = Field(
        alias="currentAiRBDetermination"
    )
    interested_clinic_count: int = Field(ge=0, alias="interestedClinicCount")
    approved_clinic_partner_count: int = Field(ge=0, alias="approvedClinicPartnerCount")
    program_number: str | None = Field(default=None, alias="programNumber")
    role_in_signal: str | None = Field(default=None, alias="roleInSignal")


class PublicProgramsIndex(SignalModel):
    programs: list[PublicProductProgram]
    summary: str | None = None
    supports_future_programs: bool = Field(default=True, alias="supportsFuturePrograms")


class PublicAccessDefinition(SignalModel):
    tier: AccessTier
    title: NonEmptyText
    description: NonEmptyText
    currently_enforced_server_side: bool = Field(alias="currentlyEnforcedServerSide")


class PublicAccessModel(SignalModel):
    tiers: list[PublicAccessDefinition]
    billing_enabled: bool = Field(default=False, alias="billingEnabled")
    authentication_enabled: bool = Field(default=False, alias="authenticationEnabled")


class PublicClinicIntelligenceView(SignalModel):
    personalization_status: NonEmptyText = Field(alias="personalizationStatus")
    relevant_program_ids: list[Identifier] = Field(default_factory=list, alias="relevantProgramIds")
    recent_changes: list[NonEmptyText] = Field(default_factory=list, alias="recentChanges")
    relevant_jurisdiction_ids: list[Identifier] = Field(
        default_factory=list, alias="relevantJurisdictionIds"
    )
    evidence_confidence_by_program: dict[Identifier, EvidenceConfidence] = Field(
        default_factory=dict, alias="evidenceConfidenceByProgram"
    )
    major_risks: list[NonEmptyText] = Field(default_factory=list, alias="majorRisks")
    available_actions: list[NonEmptyText] = Field(default_factory=list, alias="availableActions")


class PublicProduct(SignalModel):
    network: PublicProductNetwork
    intelligence: PublicIntelligenceIndex
    programs: PublicProgramsIndex
    access: PublicAccessModel
    thesis: PublicSignalNarrative | None = None
    ecosystem: PublicEcosystem | None = None
    learning_loop: PublicLearningLoop | None = Field(default=None, alias="learningLoop")
    contribution_policy: PublicContributionPolicy | None = Field(
        default=None, alias="contributionPolicy"
    )


class PublicIntelligenceFeedItem(SignalModel):
    item_id: Identifier = Field(alias="itemId")
    type: IntelligenceFeedType
    title: NonEmptyText
    summary: NonEmptyText
    domain: NonEmptyText
    program_id: Identifier | None = Field(default=None, alias="programId")
    jurisdiction_id: Identifier | None = Field(default=None, alias="jurisdictionId")
    importance: IntelligenceImportance
    access_tier: AccessTier = Field(alias="accessTier")
    created_at: datetime = Field(alias="createdAt")
    linked_artifact_ids: list[Identifier] = Field(default_factory=list, alias="linkedArtifactIds")
    linked_review_ids: list[Identifier] = Field(default_factory=list, alias="linkedReviewIds")
    linked_decision_ids: list[Identifier] = Field(default_factory=list, alias="linkedDecisionIds")

    @model_validator(mode="after")
    def validate_created_at(self) -> PublicIntelligenceFeedItem:
        object.__setattr__(
            self, "created_at", _require_timezone(self.created_at, "created_at")
        )
        return self
