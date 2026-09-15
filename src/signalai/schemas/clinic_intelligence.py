"""Public-source clinic intelligence, separate from approved partner state."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import AliasChoices, Field, HttpUrl, model_validator

from signalai.schemas.models import Identifier, NonEmptyText, SignalModel, _require_timezone


class ClinicConfidence(StrEnum):
    UNKNOWN = "unknown"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class ClinicReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    UNDER_REVIEW = "under_review"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class ClinicProfileState(StrEnum):
    INDEXED = "indexed"
    ENRICHED = "enriched"


class ClinicSeed(SignalModel):
    name_hint: str | None = None
    url: HttpUrl = Field(validation_alias=AliasChoices("url", "website"))
    city_hint: str | None = None
    country_hint: str | None = None
    discovery_source: NonEmptyText
    enabled: bool = True
    priority: int = Field(default=3, ge=1, le=5)
    region: str | None = None
    category_hint: str | None = None
    source_url: HttpUrl | None = None
    discovered_at: date | None = None
    verification_status: str | None = None


class ClinicTherapy(StrEnum):
    STEM_CELLS_UNSPECIFIED = "stem_cells_unspecified"
    AUTOLOGOUS_STEM_CELLS = "autologous_stem_cells"
    ALLOGENEIC_STEM_CELLS = "allogeneic_stem_cells"
    MSC = "msc"
    BONE_MARROW = "bone_marrow"
    ADIPOSE = "adipose"
    UMBILICAL_BIRTH_TISSUE = "umbilical_birth_tissue"
    EXOSOMES_EVS = "exosomes_evs"
    SECRETOME_CONDITIONED_MEDIA = "secretome_conditioned_media"
    PRP = "prp"
    PEPTIDES = "peptides"
    OTHER_REGENERATIVE = "other_regenerative"


class ClinicRoute(StrEnum):
    IV = "iv"
    INTRA_ARTICULAR = "intra_articular"
    INTRATHECAL = "intrathecal"
    INTRANASAL = "intranasal"
    LOCAL_INJECTION = "local_injection"
    TOPICAL = "topical"
    OTHER = "other"


class SourceField(SignalModel):
    field: NonEmptyText
    value: str | bool
    source_url: HttpUrl
    source_excerpt: NonEmptyText
    confidence: ClinicConfidence = ClinicConfidence.MODERATE


class ClinicProfile(SignalModel):
    clinic_id: Identifier
    profile_state: ClinicProfileState = ClinicProfileState.ENRICHED
    discovery_sources: list[str] = Field(default_factory=list)
    discovery_records: list[ClinicSeed] = Field(default_factory=list)
    name: str | None = None
    website: HttpUrl
    country: str | None = None
    city: str | None = None
    region: str | None = None
    address: str | None = None
    physicians: list[str] = Field(default_factory=list)
    specialties: list[str] = Field(default_factory=list)
    therapies_offered: list[ClinicTherapy] = Field(default_factory=list)
    routes_of_administration: list[ClinicRoute] = Field(default_factory=list)
    indications: list[str] = Field(default_factory=list)
    cell_sources: list[str] = Field(default_factory=list)
    exosome_or_ev_offering: bool | None = None
    secretome_offering: bool | None = None
    product_or_supplier_names: list[str] = Field(default_factory=list)
    manufacturing_or_quality_claims: list[str] = Field(default_factory=list)
    evidence_claims: list[str] = Field(default_factory=list)
    research_or_publication_links: list[HttpUrl] = Field(default_factory=list)
    regulatory_or_licensing_claims: list[str] = Field(default_factory=list)
    price_information: list[str] = Field(default_factory=list)
    contact_page: HttpUrl | None = None
    source_urls: list[HttpUrl] = Field(default_factory=list)
    provenance: list[SourceField] = Field(default_factory=list)
    last_checked_at: datetime
    confidence: ClinicConfidence = ClinicConfidence.UNKNOWN
    review_status: ClinicReviewStatus = ClinicReviewStatus.UNREVIEWED

    @model_validator(mode="after")
    def validate_provenance(self) -> ClinicProfile:
        object.__setattr__(self, "last_checked_at", _require_timezone(self.last_checked_at, "last_checked_at"))
        sourced = {(item.field, str(item.value)) for item in self.provenance}
        exempt = {"clinic_id", "profile_state", "discovery_sources", "discovery_records", "website", "source_urls", "provenance", "last_checked_at", "confidence", "review_status"}
        discovery_fields = {"name": "name_hint", "city": "city_hint", "country": "country_hint", "region": "region"}
        for field, value in self.model_dump(mode="python").items():
            if field in exempt or value is None or value == []:
                continue
            values = value if isinstance(value, list) else [value]
            for element in values:
                if field in discovery_fields and any(getattr(seed, discovery_fields[field]) == element for seed in self.discovery_records):
                    continue  # Discovery metadata is not a verified treatment claim.
                if (field, str(element)) not in sourced:
                    raise ValueError(f"{field} value lacks field-level public provenance")
        if any(str(item.source_url) not in {str(url) for url in self.source_urls} for item in self.provenance):
            raise ValueError("field provenance source must be in source_urls")
        if self.profile_state is ClinicProfileState.INDEXED:
            cell_therapies = set(ClinicTherapy) - {ClinicTherapy.PRP, ClinicTherapy.PEPTIDES, ClinicTherapy.OTHER_REGENERATIVE}
            if not self.name or not (self.discovery_records or set(self.therapies_offered).intersection(cell_therapies)):
                raise ValueError("indexed clinic requires a sourced canonical name and cell-therapy offering")
        return self


class ClinicExtraction(SignalModel):
    """One bounded model response; fields are accepted only after source verification."""

    fields: list[SourceField] = Field(default_factory=list)


class ClinicFitLevel(StrEnum):
    UNKNOWN = "unknown"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class ClinicFitAssessment(SignalModel):
    clinic_id: Identifier
    program_id: Identifier = "SGL-001"
    regenerative_medicine_fit: ClinicFitLevel
    sgl001_relevance: ClinicFitLevel
    advisory_partner_fit: ClinicFitLevel
    evaluation_site_fit: ClinicFitLevel
    outreach_priority: ClinicFitLevel
    rationale: list[NonEmptyText] = Field(default_factory=list)
    jurisdiction_fit: Literal["not_assessed"] = "not_assessed"
    assessed_at: datetime

    @model_validator(mode="after")
    def validate_assessed_at(self) -> ClinicFitAssessment:
        object.__setattr__(self, "assessed_at", _require_timezone(self.assessed_at, "assessed_at"))
        return self


class OutreachRelationship(StrEnum):
    INTELLIGENCE_PROSPECT = "intelligence_prospect"
    LISTED_PARTNER = "listed_partner"
    ADVISORY_PARTNER = "advisory_partner"
    EVALUATION_SITE_CANDIDATE = "evaluation_site_candidate"
    FUTURE_PILOT_SITE_CANDIDATE = "future_pilot_site_candidate"


class ClinicOutreachCandidate(SignalModel):
    clinic_id: Identifier
    why_relevant: NonEmptyText
    sgl001_fit: ClinicFitLevel
    recommended_ask: NonEmptyText
    recommended_relationship_level: OutreachRelationship
    priority: ClinicFitLevel
    status: Literal["pending_human_approval", "approved", "declined"] = "pending_human_approval"
    approved_by: str | None = None
    approved_at: datetime | None = None

    @model_validator(mode="after")
    def approval_gate(self) -> ClinicOutreachCandidate:
        if self.status == "approved" and (not self.approved_by or not self.approved_at):
            raise ValueError("outreach approval requires a human approver and timestamp")
        return self


class ClinicIntelligenceDataset(SignalModel):
    version: str = "1.0"
    profiles: list[ClinicProfile] = Field(default_factory=list)
    fits: list[ClinicFitAssessment] = Field(default_factory=list)
    outreach_queue: list[ClinicOutreachCandidate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_links(self) -> ClinicIntelligenceDataset:
        ids = [item.clinic_id for item in self.profiles]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate clinic_id")
        if any(item.clinic_id not in ids for item in [*self.fits, *self.outreach_queue]):
            raise ValueError("fit or outreach record references unknown clinic")
        return self
