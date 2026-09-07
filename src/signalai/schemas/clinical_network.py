"""Canonical contracts for the SignalAI clinical partner network."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, HttpUrl, model_validator

from signalai.schemas.models import Identifier, NonEmptyText, SignalModel, _require_timezone


EmailAddress = Annotated[
    str,
    Field(min_length=3, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"),
]


class CapabilityLevel(StrEnum):
    NOT_ASSESSED = "not_assessed"
    NONE = "none"
    LIMITED = "limited"
    MODERATE = "moderate"
    STRONG = "strong"


class ClinicVerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    UNDER_REVIEW = "under_review"
    VERIFIED = "verified"
    REJECTED = "rejected"


class PartnerStatus(StrEnum):
    PROSPECTIVE = "prospective"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    INACTIVE = "inactive"


class PartnerRole(StrEnum):
    LISTED_PARTNER = "listed_partner"
    ADVISORY_PARTNER = "advisory_partner"
    EVALUATION_SITE = "evaluation_site"
    PILOT_SITE_CANDIDATE = "pilot_site_candidate"


class InterestCategory(StrEnum):
    LISTED_IN_NETWORK = "listed_in_network"
    RECEIVE_SIGNAL_INTELLIGENCE = "receive_signal_intelligence"
    ADVISE_THERAPEUTIC_PROGRAMS = "advise_therapeutic_programs"
    EVALUATE_FUTURE_PROGRAMS = "evaluate_future_programs"
    POTENTIAL_PILOT_SITE = "potential_pilot_site"


class ReviewStatus(StrEnum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    DECLINED = "declined"


class MatchStatus(StrEnum):
    NOT_ASSESSED = "not_assessed"
    CANDIDATE = "candidate"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    DECLINED = "declined"


class JurisdictionFit(StrEnum):
    NOT_ASSESSED = "not_assessed"
    UNRESOLVED = "unresolved"
    RESTRICTIVE = "restrictive"
    CONDITIONAL = "conditional"
    FAVORABLE = "favorable"


class Physician(SignalModel):
    physician_id: Identifier
    name: NonEmptyText
    title: str | None = None
    specialty: NonEmptyText
    clinic_id: Identifier
    credentials: list[NonEmptyText] = Field(default_factory=list)
    profile_summary: str | None = None
    profile_url: HttpUrl | None = None
    public_profile_enabled: bool = False


class Clinic(SignalModel):
    clinic_id: Identifier
    name: NonEmptyText
    city: NonEmptyText
    country: NonEmptyText
    region: NonEmptyText
    website: HttpUrl | None = None
    contact_email: EmailAddress | None = None
    contact_email_public: bool = False
    physicians: list[Physician] = Field(default_factory=list)
    specialties: list[NonEmptyText] = Field(default_factory=list)
    languages: list[NonEmptyText] = Field(default_factory=list)
    modalities_offered: list[NonEmptyText] = Field(default_factory=list)
    regenerative_experience: CapabilityLevel = CapabilityLevel.NOT_ASSESSED
    intranasal_experience: CapabilityLevel = CapabilityLevel.NOT_ASSESSED
    research_experience: CapabilityLevel = CapabilityLevel.NOT_ASSESSED
    outcomes_tracking_capability: CapabilityLevel = CapabilityLevel.NOT_ASSESSED
    jurisdiction_id: Identifier | None = None
    verification_status: ClinicVerificationStatus = ClinicVerificationStatus.UNVERIFIED
    partner_status: PartnerStatus = PartnerStatus.PROSPECTIVE
    partner_roles: list[PartnerRole] = Field(default_factory=list)
    public_profile_enabled: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_relationships_and_approval(self) -> Clinic:
        object.__setattr__(self, "created_at", _require_timezone(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _require_timezone(self.updated_at, "updated_at"))
        if self.approved_at is not None:
            object.__setattr__(
                self, "approved_at", _require_timezone(self.approved_at, "approved_at")
            )
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        if any(item.clinic_id != self.clinic_id for item in self.physicians):
            raise ValueError("every physician must reference the containing clinic")
        physician_ids = {item.physician_id for item in self.physicians}
        if len(physician_ids) != len(self.physicians):
            raise ValueError("physician IDs must be unique within a clinic")
        approved = self.partner_status is PartnerStatus.APPROVED
        if self.partner_roles and not approved:
            raise ValueError("partner roles require approved partner status")
        if approved and (
            self.verification_status is not ClinicVerificationStatus.VERIFIED
            or not self.approved_by
            or self.approved_at is None
        ):
            raise ValueError("approved partners require verification and human approval provenance")
        if self.public_profile_enabled and not approved:
            raise ValueError("public clinic profiles require approved partner status")
        if self.public_profile_enabled and not self.partner_roles:
            raise ValueError("public clinic profiles require at least one approved partner role")
        if self.contact_email_public and (not self.public_profile_enabled or not self.contact_email):
            raise ValueError("public contact email requires an approved public profile and email")
        return self


class PartnershipInterest(SignalModel):
    interest_id: Identifier
    clinic_id: Identifier
    categories: Annotated[list[InterestCategory], Field(min_length=1)]
    program_ids: list[Identifier] = Field(default_factory=list)
    notes: str | None = None
    status: ReviewStatus = ReviewStatus.SUBMITTED
    submitted_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None

    @model_validator(mode="after")
    def validate_review(self) -> PartnershipInterest:
        object.__setattr__(
            self, "submitted_at", _require_timezone(self.submitted_at, "submitted_at")
        )
        if self.reviewed_at is not None:
            object.__setattr__(
                self, "reviewed_at", _require_timezone(self.reviewed_at, "reviewed_at")
            )
        reviewed = self.status in {ReviewStatus.APPROVED, ReviewStatus.DECLINED}
        if reviewed != bool(self.reviewed_at and self.reviewed_by):
            raise ValueError("completed interest reviews require reviewer and timestamp")
        return self


class ClinicProgramMatch(SignalModel):
    match_id: Identifier
    clinic_id: Identifier
    program_id: Identifier
    match_status: MatchStatus = MatchStatus.NOT_ASSESSED
    jurisdiction_fit: JurisdictionFit = JurisdictionFit.NOT_ASSESSED
    regenerative_experience: CapabilityLevel = CapabilityLevel.NOT_ASSESSED
    relevant_specialty_fit: CapabilityLevel = CapabilityLevel.NOT_ASSESSED
    research_infrastructure_fit: CapabilityLevel = CapabilityLevel.NOT_ASSESSED
    readiness_notes: str | None = None
    recommended_role: PartnerRole | None = None
    rationale: NonEmptyText
    requires_human_approval: bool = True
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_match(self) -> ClinicProgramMatch:
        object.__setattr__(self, "created_at", _require_timezone(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _require_timezone(self.updated_at, "updated_at"))
        if self.approved_at is not None:
            object.__setattr__(
                self, "approved_at", _require_timezone(self.approved_at, "approved_at")
            )
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        if not self.requires_human_approval:
            raise ValueError("clinic/program matches always require human approval")
        if self.match_status is MatchStatus.APPROVED and (
            not self.approved_by or self.approved_at is None
        ):
            raise ValueError("approved matches require human approval provenance")
        return self


class ClinicIntakeSubmission(SignalModel):
    submission_id: Identifier
    clinic_name: NonEmptyText
    physician_name: NonEmptyText
    city: NonEmptyText
    country: NonEmptyText
    website: HttpUrl | None = None
    email: EmailAddress
    specialty: NonEmptyText
    modalities_offered: list[NonEmptyText] = Field(default_factory=list)
    interest_categories: Annotated[list[InterestCategory], Field(min_length=1)]
    notes: str | None = None
    status: ReviewStatus = ReviewStatus.SUBMITTED
    submitted_at: datetime

    @model_validator(mode="after")
    def validate_submitted_at(self) -> ClinicIntakeSubmission:
        object.__setattr__(
            self, "submitted_at", _require_timezone(self.submitted_at, "submitted_at")
        )
        if self.status is not ReviewStatus.SUBMITTED:
            raise ValueError("new intake submissions must begin in submitted status")
        return self


class ClinicIntakeReview(SignalModel):
    review_id: Identifier
    submission_id: Identifier
    status: ReviewStatus
    reviewed_by: NonEmptyText
    reviewed_at: datetime
    notes: str | None = None

    @model_validator(mode="after")
    def validate_review(self) -> ClinicIntakeReview:
        object.__setattr__(
            self, "reviewed_at", _require_timezone(self.reviewed_at, "reviewed_at")
        )
        if self.status not in {ReviewStatus.APPROVED, ReviewStatus.DECLINED}:
            raise ValueError("intake review must approve or decline the submission")
        return self


class ClinicalNetworkState(SignalModel):
    schema_version: str = "1.0"
    generated_at: datetime
    clinics: list[Clinic] = Field(default_factory=list)
    partnership_interests: list[PartnershipInterest] = Field(default_factory=list)
    program_matches: list[ClinicProgramMatch] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_state(self) -> ClinicalNetworkState:
        object.__setattr__(
            self, "generated_at", _require_timezone(self.generated_at, "generated_at")
        )
        clinic_ids = {item.clinic_id for item in self.clinics}
        if len(clinic_ids) != len(self.clinics):
            raise ValueError("clinic IDs must be unique")
        interest_ids = {item.interest_id for item in self.partnership_interests}
        match_ids = {item.match_id for item in self.program_matches}
        if len(interest_ids) != len(self.partnership_interests):
            raise ValueError("partnership interest IDs must be unique")
        if len(match_ids) != len(self.program_matches):
            raise ValueError("clinic/program match IDs must be unique")
        for interest in self.partnership_interests:
            if interest.clinic_id not in clinic_ids:
                raise ValueError("partnership interest references an unknown clinic")
        for match in self.program_matches:
            if match.clinic_id not in clinic_ids:
                raise ValueError("clinic/program match references an unknown clinic")
        return self
