"""Frontend-safe clinical-network contracts."""

from __future__ import annotations

from pydantic import Field, HttpUrl

from signalai.schemas.clinical_network import (
    BiologicalRelationship,
    CapabilityLevel,
    ClinicOpportunityPriority,
    ClinicVerificationStatus,
    DocumentationStatus,
    JurisdictionFit,
    ManipulationLevel,
    MatchStatus,
    PartnerRole,
    PartnerStatus,
    RegenerativeClinicArchetype,
)
from signalai.schemas.models import EvidenceConfidence, Identifier, NonEmptyText, ProgramStatus, SignalModel


class PublicPhysician(SignalModel):
    physician_id: Identifier = Field(alias="physicianId")
    name: NonEmptyText
    title: str | None = None
    specialty: NonEmptyText
    credentials: list[str] = Field(default_factory=list)
    profile_summary: str | None = Field(default=None, alias="profileSummary")
    profile_url: HttpUrl | None = Field(default=None, alias="profileUrl")


class PublicProductDocumentation(SignalModel):
    product_name: NonEmptyText = Field(alias="productName")
    identity_characterization: DocumentationStatus = Field(alias="identityCharacterization")
    sterility_safety_documentation: DocumentationStatus = Field(
        alias="sterilitySafetyDocumentation"
    )
    manufacturing_documentation: DocumentationStatus = Field(alias="manufacturingDocumentation")
    evidence_documentation: DocumentationStatus = Field(alias="evidenceDocumentation")


class PublicRegenerativeClinicPriority(SignalModel):
    rank: int = Field(ge=1, le=3)
    archetype: RegenerativeClinicArchetype
    description: NonEmptyText


class PublicRegenerativeClinicThesis(SignalModel):
    thesis_id: Identifier = Field(alias="thesisId")
    niche: NonEmptyText
    exosome_subdomain_role: NonEmptyText = Field(alias="exosomeSubdomainRole")
    target_priorities: list[PublicRegenerativeClinicPriority] = Field(alias="targetPriorities")


class PublicClinicOpportunitySummary(SignalModel):
    assessment_id: Identifier = Field(alias="assessmentId")
    clinic_id: Identifier = Field(alias="clinicId")
    archetype: RegenerativeClinicArchetype
    priority: ClinicOpportunityPriority
    sgl001_fit: CapabilityLevel = Field(alias="sgl001Fit")
    recommended_first_value_offer: NonEmptyText = Field(alias="recommendedFirstValueOffer")
    recommended_relationship_path: NonEmptyText = Field(alias="recommendedRelationshipPath")


class PublicClinicProfile(SignalModel):
    clinic_id: Identifier = Field(alias="clinicId")
    name: NonEmptyText
    city: NonEmptyText
    country: NonEmptyText
    region: NonEmptyText
    website: HttpUrl | None = None
    public_contact_email: str | None = Field(default=None, alias="publicContactEmail")
    physicians: list[PublicPhysician] = Field(default_factory=list)
    specialties: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    modalities_offered: list[str] = Field(default_factory=list, alias="modalitiesOffered")
    regenerative_experience: CapabilityLevel = Field(alias="regenerativeExperience")
    intranasal_experience: CapabilityLevel = Field(alias="intranasalExperience")
    research_experience: CapabilityLevel = Field(alias="researchExperience")
    outcomes_tracking_capability: CapabilityLevel = Field(alias="outcomesTrackingCapability")
    jurisdiction_id: Identifier | None = Field(default=None, alias="jurisdictionId")
    verification_status: ClinicVerificationStatus = Field(alias="verificationStatus")
    partner_status: PartnerStatus = Field(alias="partnerStatus")
    partner_roles: list[PartnerRole] = Field(default_factory=list, alias="partnerRoles")
    regenerative_archetype: RegenerativeClinicArchetype | None = Field(
        default=None, alias="regenerativeArchetype"
    )
    stem_cell_therapies_offered: list[str] = Field(
        default_factory=list, alias="stemCellTherapiesOffered"
    )
    exosome_ev_therapies_offered: list[str] = Field(
        default_factory=list, alias="exosomeEvTherapiesOffered"
    )
    secretome_cell_derived_products: list[str] = Field(
        default_factory=list, alias="secretomeCellDerivedProducts"
    )
    cell_sources: list[str] = Field(default_factory=list, alias="cellSources")
    tissue_sources: list[str] = Field(default_factory=list, alias="tissueSources")
    biological_relationships: list[BiologicalRelationship] = Field(
        default_factory=list, alias="biologicalRelationships"
    )
    manipulation_levels: list[ManipulationLevel] = Field(
        default_factory=list, alias="manipulationLevels"
    )
    routes_of_administration: list[str] = Field(
        default_factory=list, alias="routesOfAdministration"
    )
    marketed_indications: list[str] = Field(default_factory=list, alias="marketedIndications")
    suppliers_manufacturers: list[str] = Field(
        default_factory=list, alias="suppliersManufacturers"
    )
    product_documentation: list[PublicProductDocumentation] = Field(
        default_factory=list, alias="productDocumentation"
    )
    treatment_volume_summary: str | None = Field(default=None, alias="treatmentVolumeSummary")


class PublicClinicProgramMatch(SignalModel):
    match_id: Identifier = Field(alias="matchId")
    clinic_id: Identifier = Field(alias="clinicId")
    program_id: Identifier = Field(alias="programId")
    match_status: MatchStatus = Field(alias="matchStatus")
    jurisdiction_fit: JurisdictionFit = Field(alias="jurisdictionFit")
    regenerative_experience: CapabilityLevel = Field(alias="regenerativeExperience")
    relevant_specialty_fit: CapabilityLevel = Field(alias="relevantSpecialtyFit")
    research_infrastructure_fit: CapabilityLevel = Field(alias="researchInfrastructureFit")
    readiness_notes: str | None = Field(default=None, alias="readinessNotes")
    recommended_role: PartnerRole | None = Field(default=None, alias="recommendedRole")
    rationale: NonEmptyText


class PublicClinicalIntelligence(SignalModel):
    program_id: Identifier = Field(alias="programId")
    therapeutic_program: NonEmptyText = Field(alias="therapeuticProgram")
    current_evidence_confidence: EvidenceConfidence = Field(alias="currentEvidenceConfidence")
    development_stage: ProgramStatus = Field(alias="developmentStage")
    human_evidence_level: NonEmptyText = Field(alias="humanEvidenceLevel")
    major_unresolved_risk: str | None = Field(default=None, alias="majorUnresolvedRisk")
    jurisdiction_relevance: NonEmptyText = Field(alias="jurisdictionRelevance")
    what_changed_recently: str | None = Field(default=None, alias="whatChangedRecently")


class PublicClinicalNetworkSummary(SignalModel):
    total_clinics: int = Field(ge=0, alias="totalClinics")
    public_clinics: int = Field(ge=0, alias="publicClinics")
    approved_partners: int = Field(ge=0, alias="approvedPartners")
    pending_review: int = Field(ge=0, alias="pendingReview")
    program_matches: int = Field(ge=0, alias="programMatches")


class PublicClinicalNetwork(SignalModel):
    summary: PublicClinicalNetworkSummary
    clinic_profiles: list[PublicClinicProfile] = Field(default_factory=list, alias="clinicProfiles")
    countries_represented: list[str] = Field(default_factory=list, alias="countriesRepresented")
    jurisdictions_represented: list[Identifier] = Field(default_factory=list, alias="jurisdictionsRepresented")
    program_matches: list[PublicClinicProgramMatch] = Field(default_factory=list, alias="programMatches")
    partner_status_counts: dict[str, int] = Field(default_factory=dict, alias="partnerStatusCounts")
    intelligence: list[PublicClinicalIntelligence] = Field(default_factory=list)
    network_thesis: PublicRegenerativeClinicThesis | None = Field(
        default=None, alias="networkThesis"
    )
    opportunity_summaries: list[PublicClinicOpportunitySummary] = Field(
        default_factory=list, alias="opportunitySummaries"
    )
