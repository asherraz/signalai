"""Frontend-safe projection of public-source clinic intelligence."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from signalai.schemas.clinic_intelligence import ClinicFitLevel, ClinicRoute, ClinicTherapy
from signalai.schemas.models import Identifier, SignalModel


class PublicClinicIntelligenceSummary(SignalModel):
    clinics_indexed: int = Field(alias="clinicsIndexed")
    clinics_enriched: int = Field(default=0, alias="clinicsEnriched")
    stem_cell_clinics: int = Field(default=0, alias="stemCellClinics")
    clinics_by_country: dict[str, int] = Field(default_factory=dict, alias="clinicsByCountry")
    clinics_by_region: dict[str, int] = Field(default_factory=dict, alias="clinicsByRegion")
    clinics_by_therapy: dict[str, int] = Field(default_factory=dict, alias="clinicsByTherapy")
    countries: int
    exosome_clinics: int = Field(alias="exosomeClinics")
    neuro_relevant_clinics: int = Field(alias="neuroRelevantClinics")


class PublicBasicClinic(SignalModel):
    clinic_id: Identifier = Field(alias="clinicId")
    name: str | None = None
    website: str
    city: str | None = None
    country: str | None = None
    region: str | None = None
    profile_state: str = Field(default="indexed", alias="profileState")


class PublicIndexedClinic(SignalModel):
    clinic_id: Identifier = Field(alias="clinicId")
    name: str | None = None
    website: str
    profile_state: str = Field(default="enriched", alias="profileState")
    country: str | None = None
    city: str | None = None
    region: str | None = None
    therapies_offered: list[ClinicTherapy] = Field(alias="therapiesOffered")
    routes_of_administration: list[ClinicRoute] = Field(alias="routesOfAdministration")
    indications: list[str]
    exosome_or_ev_offering: bool | None = Field(alias="exosomeOrEvOffering")
    confidence: str
    review_status: str = Field(alias="reviewStatus")
    source_urls: list[str] = Field(alias="sourceUrls")
    last_checked_at: datetime = Field(alias="lastCheckedAt")
    sgl001_relevance: ClinicFitLevel = Field(alias="sgl001Relevance")
    outreach_priority: ClinicFitLevel = Field(alias="outreachPriority")


class PublicClinicIntelligence(SignalModel):
    summary: PublicClinicIntelligenceSummary
    clinics: list[PublicIndexedClinic | PublicBasicClinic] = Field(default_factory=list)
    top_matches: list[PublicIndexedClinic] = Field(default_factory=list, alias="topMatches")
    recently_indexed: list[PublicIndexedClinic | PublicBasicClinic] = Field(default_factory=list, alias="recentlyIndexed")
