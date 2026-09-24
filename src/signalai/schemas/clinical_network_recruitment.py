"""Typed, public-safe Clinical Network recruitment configuration."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from signalai.schemas.models import Identifier, NonEmptyText, SignalModel, _require_timezone


class OpportunityAvailability(StrEnum):
    AVAILABLE_NOW = "available_now"
    FUTURE_GATED = "future_gated"


class RecruitmentOrganizationType(StrEnum):
    LICENSED_MEDICAL_CLINIC = "licensed_medical_clinic"
    RESEARCH_SITE = "research_site"
    HOSPITAL_OR_ACADEMIC_CENTER = "hospital_or_academic_center"
    LABORATORY = "laboratory"
    MANUFACTURING_ORGANIZATION = "manufacturing_organization"
    REGULATORY_OR_DEVELOPMENT_CONSULTANCY = "regulatory_or_development_consultancy"
    OTHER = "other"


class RecruitmentProfessionalRole(StrEnum):
    PHYSICIAN = "physician"
    MEDICAL_DIRECTOR = "medical_director"
    RESEARCHER = "researcher"
    PRINCIPAL_INVESTIGATOR = "principal_investigator"
    CLINIC_OPERATOR = "clinic_operator"
    LABORATORY_LEAD = "laboratory_lead"
    MANUFACTURING_LEAD = "manufacturing_lead"
    REGULATORY_PROFESSIONAL = "regulatory_professional"
    OTHER = "other"


class RecruitmentCapability(StrEnum):
    STEM_CELL_CLINICAL_EXPERIENCE = "stem_cell_clinical_experience"
    EV_OR_EXOSOME_EXPERIENCE = "ev_or_exosome_experience"
    CLINICAL_RESEARCH = "clinical_research"
    GCP_SITE_OPERATIONS = "gcp_site_operations"
    SAMPLE_COLLECTION = "sample_collection"
    IMAGING = "imaging"
    LABORATORY_ANALYTICS = "laboratory_analytics"
    PHARMACOVIGILANCE = "pharmacovigilance"
    MANUFACTURING = "manufacturing"
    QUALITY_CONTROL = "quality_control"
    REGULATORY_DEVELOPMENT = "regulatory_development"
    NONE_OF_THE_ABOVE = "none_of_the_above"


class RecruitmentInterest(StrEnum):
    SIGNAL_INTELLIGENCE = "signal_intelligence"
    DEVELOPMENT_UPDATES = "development_updates"
    SCIENTIFIC_ADVISORY = "scientific_advisory"
    PRODUCT_DEVELOPMENT_FEEDBACK = "product_development_feedback"
    MANUFACTURING_COLLABORATION = "manufacturing_collaboration"
    ANALYTICAL_COLLABORATION = "analytical_collaboration"
    PRECLINICAL_RESEARCH = "preclinical_research"
    CLINICAL_FEASIBILITY = "clinical_feasibility"
    FUTURE_REGULATED_STUDY = "future_regulated_study"
    FUTURE_SITE_ASSESSMENT = "future_site_assessment"


class RecruitmentReviewStage(StrEnum):
    APPLICATION_RECEIVED = "application_received"
    IDENTITY_REVIEW = "identity_review"
    PROFESSIONAL_REVIEW = "professional_review"
    CAPABILITY_REVIEW = "capability_review"
    JURISDICTION_REVIEW = "jurisdiction_review"
    INTELLIGENCE_MEMBERSHIP = "intelligence_membership"
    ADVISORY_CANDIDATE = "advisory_candidate"
    RESEARCH_CANDIDATE = "research_candidate"
    FUTURE_SITE_ASSESSMENT_CANDIDATE = "future_site_assessment_candidate"


ACKNOWLEDGEMENT_STATEMENTS = [
    "SGL-001 is a preclinical investigational program and is unavailable for clinical or commercial use.",
    "Submission does not create a partnership, qualify a site, guarantee participation, or provide product access.",
    "No patient information should be submitted.",
    "Information is accurate to the submitter's knowledge.",
    "The submitter is authorized to provide the organization information.",
    "Communication consent and privacy consent are separate and explicit.",
]


class RecruitmentAcknowledgement(SignalModel):
    acknowledgement_id: Identifier
    statement: NonEmptyText
    required: bool = True


class RecruitmentCtaLabels(SignalModel):
    primary: NonEmptyText
    secondary: NonEmptyText
    sgl001: NonEmptyText
    submission: NonEmptyText


class ClinicalNetworkOpportunity(SignalModel):
    opportunity_id: Identifier
    title: NonEmptyText
    short_description: NonEmptyText
    availability: OpportunityAvailability
    eligible_organization_types: list[RecruitmentOrganizationType]
    participation_categories: list[RecruitmentInterest]
    disclaimer: NonEmptyText
    active: bool = True


class ClinicalNetworkIntakeDefinition(SignalModel):
    schema_version: NonEmptyText
    title: NonEmptyText
    short_introduction: NonEmptyText
    eligibility_statement: NonEmptyText
    organization_types: list[RecruitmentOrganizationType]
    professional_roles: list[RecruitmentProfessionalRole]
    capability_options: list[RecruitmentCapability]
    interest_options: list[RecruitmentInterest]
    required_acknowledgements: list[RecruitmentAcknowledgement]
    communication_consent_language: NonEmptyText
    privacy_notice_reference: str | None = None
    submission_label: NonEmptyText
    confirmation_message: NonEmptyText
    review_stages: list[RecruitmentReviewStage]
    updated_at: datetime

    @model_validator(mode="after")
    def validate_definition(self):
        object.__setattr__(self, "updated_at", _require_timezone(self.updated_at, "updated_at"))
        for label, actual, expected in (
            ("organization types", self.organization_types, list(RecruitmentOrganizationType)),
            ("professional roles", self.professional_roles, list(RecruitmentProfessionalRole)),
            ("capabilities", self.capability_options, list(RecruitmentCapability)),
            ("interests", self.interest_options, list(RecruitmentInterest)),
            ("review stages", self.review_stages, list(RecruitmentReviewStage)),
        ):
            if actual != expected:
                raise ValueError(f"recruitment {label} must contain the complete ordered enum")
        statements = [item.statement for item in self.required_acknowledgements]
        if statements != ACKNOWLEDGEMENT_STATEMENTS or not all(item.required for item in self.required_acknowledgements):
            raise ValueError("required recruitment acknowledgements must match the approved statements")
        return self


class ClinicalNetworkRecruitmentConfiguration(SignalModel):
    configuration_id: Identifier
    headline: NonEmptyText
    value_proposition: NonEmptyText
    opportunities: list[ClinicalNetworkOpportunity]
    eligibility_summary: NonEmptyText
    intake_definition: ClinicalNetworkIntakeDefinition
    required_disclaimers: list[NonEmptyText]
    cta_labels: RecruitmentCtaLabels
    review_process_disclaimer: NonEmptyText
    contact_reference: str | None = None
    privacy_policy_reference: str | None = None
    updated_at: datetime

    @model_validator(mode="after")
    def validate_positioning(self):
        object.__setattr__(self, "updated_at", _require_timezone(self.updated_at, "updated_at"))
        ids = [item.opportunity_id for item in self.opportunities]
        if len(ids) != len(set(ids)):
            raise ValueError("clinical-network opportunity IDs must be unique")
        text = " ".join([self.headline, self.value_proposition, self.eligibility_summary,
                         *self.required_disclaimers, *(item.title + " " + item.short_description + " " + item.disclaimer for item in self.opportunities)]).casefold()
        required = ["preclinical", "investigational", "unavailable for clinical use",
                    "unavailable for commercial use", "not approved", "not proven safe or effective",
                    "not an established treatment"]
        if any(term not in text for term in required):
            raise ValueError("clinical-network recruitment must preserve all SGL-001 positioning disclaimers")
        prohibited = ["purchase sgl-001", "prescribe sgl-001", "administer sgl-001",
                      "distribute sgl-001", "obtain sgl-001", "receive priority product access",
                      "guarantees product access", "regulatory loophole"]
        if any(term in text for term in prohibited):
            raise ValueError("clinical-network recruitment contains prohibited access or loophole language")
        return self


class ClinicalNetworkPublicProjection(SignalModel):
    headline: NonEmptyText
    value_proposition: NonEmptyText
    available_now: list[ClinicalNetworkOpportunity]
    future_gated: list[ClinicalNetworkOpportunity]
    eligibility_summary: NonEmptyText
    application_definition: ClinicalNetworkIntakeDefinition
    required_disclaimers: list[NonEmptyText]
    cta_labels: RecruitmentCtaLabels
    review_process: list[RecruitmentReviewStage]
    review_process_disclaimer: NonEmptyText
    contact_reference: str | None = None
    privacy_policy_reference: str | None = None
