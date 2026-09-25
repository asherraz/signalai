"""Governed molecular-atlas contracts for public omics and literature discovery."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, HttpUrl, model_validator

from signalai.schemas.models import Identifier, NonEmptyText, SignalModel, _require_timezone


class AtlasLayer(StrEnum):
    CELL_SOURCE = "cell_source"
    MANUFACTURING_PROCESS = "manufacturing_process"
    SURFACE_CHEMISTRY = "surface_chemistry"
    RNA_CARGO = "rna_cargo"
    PROTEIN_CARGO = "protein_cargo"
    LIPID_AND_METABOLITE_CARGO = "lipid_and_metabolite_cargo"
    SOLUBLE_SECRETOME = "soluble_secretome"
    FUNCTIONAL_POTENCY = "functional_potency"
    PRODUCT_SIGNATURE = "product_signature"


class AtlasSourceKind(StrEnum):
    PAPER = "paper"
    PUBLIC_OMICS_DATASET = "public_omics_dataset"
    CONTRIBUTED_DATASET = "contributed_dataset"


class AtlasReviewStatus(StrEnum):
    DISCOVERED = "discovered"
    TRIAGE_REQUIRED = "triage_required"
    ELIGIBLE_FOR_REVIEW = "eligible_for_review"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class AtlasCoverage(StrEnum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class MolecularAtlasSource(SignalModel):
    source_id: Identifier
    source_name: NonEmptyText
    source_kind: AtlasSourceKind
    record_id: NonEmptyText
    title: NonEmptyText
    source_url: HttpUrl
    publication_date: str | None = None
    authors: list[str] = Field(default_factory=list)
    dataset_accession: str | None = None
    layers: list[AtlasLayer] = Field(default_factory=list)
    search_query: NonEmptyText
    discovered_at: datetime
    review_status: AtlasReviewStatus = AtlasReviewStatus.DISCOVERED
    provenance_note: NonEmptyText
    data_use_note: NonEmptyText

    @model_validator(mode="after")
    def validate_source(self):
        object.__setattr__(self, "discovered_at", _require_timezone(self.discovered_at, "discovered_at"))
        if self.source_kind is AtlasSourceKind.CONTRIBUTED_DATASET:
            raise ValueError("researcher contributions must never be created by internet discovery")
        return self


class AtlasCoverageItem(SignalModel):
    layer: AtlasLayer
    label: NonEmptyText
    coverage: AtlasCoverage
    main_gap: NonEmptyText
    reviewed_source_count: int = Field(default=0, ge=0)
    candidate_source_count: int = Field(default=0, ge=0)


class MolecularAtlasWorkspace(SignalModel):
    schema_version: NonEmptyText = "1.0"
    atlas_id: Identifier = "sgl001-molecular-atlas"
    program_id: Identifier = "SGL-001"
    sources: list[MolecularAtlasSource] = Field(default_factory=list)
    coverage: list[AtlasCoverageItem]
    search_queries: list[NonEmptyText]
    last_discovery_at: datetime | None = None
    discovery_errors: list[NonEmptyText] = Field(default_factory=list)
    updated_at: datetime

    @model_validator(mode="after")
    def validate_workspace(self):
        object.__setattr__(self, "updated_at", _require_timezone(self.updated_at, "updated_at"))
        if self.last_discovery_at is not None:
            object.__setattr__(self, "last_discovery_at", _require_timezone(self.last_discovery_at, "last_discovery_at"))
        if self.program_id != "SGL-001":
            raise ValueError("the molecular atlas must describe SGL-001")
        ids = [item.source_id for item in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("molecular-atlas source IDs must be unique")
        if [item.layer for item in self.coverage] != list(AtlasLayer):
            raise ValueError("molecular-atlas coverage must contain every layer in display order")
        return self


class AtlasContributionField(SignalModel):
    field_id: Identifier
    label: NonEmptyText
    required: bool
    help_text: NonEmptyText


class PublicAtlasDiscovery(SignalModel):
    source_id: Identifier
    source_name: NonEmptyText
    source_kind: AtlasSourceKind
    record_id: NonEmptyText
    title: NonEmptyText
    source_url: HttpUrl
    publication_date: str | None = None
    dataset_accession: str | None = None
    layers: list[AtlasLayer]
    review_status: AtlasReviewStatus


class PublicMolecularAtlas(SignalModel):
    title: NonEmptyText
    subtitle: NonEmptyText
    disclaimer: NonEmptyText
    layers: list[AtlasCoverageItem]
    current_questions: list[NonEmptyText]
    discovery_counts: dict[str, int]
    source_status: NonEmptyText
    recent_discoveries: list[PublicAtlasDiscovery]
    contribution_headline: NonEmptyText
    contribution_description: NonEmptyText
    contribution_fields: list[AtlasContributionField]
    contribution_steps: list[NonEmptyText]
    accepted_data_types: list[NonEmptyText]
    prohibited_submission: NonEmptyText
    cta_primary: NonEmptyText
    cta_secondary: NonEmptyText
    last_discovery_at: datetime | None = None
