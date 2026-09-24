"""Deterministic Clinical Network recruitment configuration and public projection."""

from datetime import datetime, timezone

from signalai.schemas.clinical_network_recruitment import (
    ACKNOWLEDGEMENT_STATEMENTS, ClinicalNetworkIntakeDefinition,
    ClinicalNetworkOpportunity, ClinicalNetworkPublicProjection,
    ClinicalNetworkRecruitmentConfiguration, OpportunityAvailability,
    RecruitmentAcknowledgement, RecruitmentCapability, RecruitmentCtaLabels,
    RecruitmentInterest, RecruitmentOrganizationType, RecruitmentProfessionalRole,
    RecruitmentReviewStage,
)


def initial_recruitment_configuration(*, updated_at: datetime | None = None) -> ClinicalNetworkRecruitmentConfiguration:
    timestamp = updated_at or datetime.now(timezone.utc)
    organizations = list(RecruitmentOrganizationType)
    common_disclaimer = (
        "Participation concerns intelligence and future scientific evaluation only; it does not provide product access or authorize clinical use."
    )
    available = [
        ("intelligence-updates", "Signal Intelligence updates", RecruitmentInterest.SIGNAL_INTELLIGENCE),
        ("evidence-briefings", "Evidence and development briefings", RecruitmentInterest.DEVELOPMENT_UPDATES),
        ("manufacturing-intelligence", "Manufacturing and product-quality intelligence", RecruitmentInterest.MANUFACTURING_COLLABORATION),
        ("scientific-discussions", "Scientific discussions", RecruitmentInterest.PRODUCT_DEVELOPMENT_FEEDBACK),
        ("protocol-demonstrations", "Protocol-review demonstrations", RecruitmentInterest.CLINICAL_FEASIBILITY),
        ("design-lab-updates", "Product Design Lab updates", RecruitmentInterest.DEVELOPMENT_UPDATES),
    ]
    future = [
        ("scientific-advisory", "Scientific advisory participation", RecruitmentInterest.SCIENTIFIC_ADVISORY),
        ("feasibility-assessment", "Feasibility assessment", RecruitmentInterest.CLINICAL_FEASIBILITY),
        ("research-collaboration", "Research collaboration", RecruitmentInterest.ANALYTICAL_COLLABORATION),
        ("preclinical-collaboration", "Preclinical collaboration", RecruitmentInterest.PRECLINICAL_RESEARCH),
        ("regulated-study-consideration", "Future regulated-study consideration", RecruitmentInterest.FUTURE_REGULATED_STUDY),
        ("site-assessment-consideration", "Future site-assessment consideration", RecruitmentInterest.FUTURE_SITE_ASSESSMENT),
    ]
    opportunities = [ClinicalNetworkOpportunity(
        opportunity_id=f"clinical-network-{identifier}", title=title,
        short_description=("Available now as an informational network activity." if availability is OpportunityAvailability.AVAILABLE_NOW
                           else "A future possibility requiring separate scientific, professional, jurisdictional, and human review."),
        availability=availability, eligible_organization_types=organizations,
        participation_categories=[interest], disclaimer=common_disclaimer,
    ) for availability, records in ((OpportunityAvailability.AVAILABLE_NOW, available),
                                     (OpportunityAvailability.FUTURE_GATED, future))
      for identifier, title, interest in records]
    intake = ClinicalNetworkIntakeDefinition(
        schema_version="1.0", title="Join the Signal Clinical Network",
        short_introduction="For licensed physicians, researchers, and regenerative-medicine organizations interested in responsible therapeutic development.",
        eligibility_statement="Applicants should represent a legitimate medical, research, laboratory, manufacturing, or development organization and be authorized to provide its information.",
        organization_types=list(RecruitmentOrganizationType),
        professional_roles=list(RecruitmentProfessionalRole),
        capability_options=list(RecruitmentCapability), interest_options=list(RecruitmentInterest),
        required_acknowledgements=[RecruitmentAcknowledgement(
            acknowledgement_id=f"clinical-network-ack-{index}", statement=statement,
        ) for index, statement in enumerate(ACKNOWLEDGEMENT_STATEMENTS, start=1)],
        communication_consent_language="I separately consent to receive communications from Signal about the interests I select; I may withdraw this consent.",
        privacy_notice_reference=None, submission_label="Submit application",
        confirmation_message="Application received for review. Submission does not create a partnership, qualification, participation guarantee, or product access.",
        review_stages=list(RecruitmentReviewStage), updated_at=timestamp,
    )
    return ClinicalNetworkRecruitmentConfiguration(
        configuration_id="clinical-network-recruitment-sgl001", headline="Help shape the clinical path for regenerative therapeutics.",
        value_proposition="Join a network of physicians, researchers, and regenerative-medicine organizations interested in evidence, product quality, responsible translation, and future clinical development.",
        opportunities=opportunities,
        eligibility_summary="Open to licensed physicians, researchers, and qualified regenerative-medicine, research, laboratory, manufacturing, and development organizations, subject to review.",
        intake_definition=intake,
        required_disclaimers=[
            "SGL-001 is preclinical and investigational, unavailable for clinical use, unavailable for commercial use, not approved, not proven safe or effective, and not an established treatment.",
            "Joining does not create a partnership or exclusivity, qualify a clinical site, guarantee research or study participation, provide priority product access, authorize clinical use, or imply endorsement by Signal.",
            "Do not submit patient information. Applications must be handled by a separate secure intake service, not repository or public state.",
        ],
        cta_labels=RecruitmentCtaLabels(primary="Apply to join", secondary="Explore Signal Intelligence",
                                        sgl001="Register clinical interest", submission="Submit application"),
        review_process_disclaimer="The stages are informational, applicants may stop at any stage, and every later stage requires separate review.",
        contact_reference=None, privacy_policy_reference=None, updated_at=timestamp,
    )


def export_recruitment_configuration(value: ClinicalNetworkRecruitmentConfiguration) -> ClinicalNetworkPublicProjection:
    return ClinicalNetworkPublicProjection(
        headline=value.headline, value_proposition=value.value_proposition,
        available_now=[x for x in value.opportunities if x.active and x.availability is OpportunityAvailability.AVAILABLE_NOW],
        future_gated=[x for x in value.opportunities if x.active and x.availability is OpportunityAvailability.FUTURE_GATED],
        eligibility_summary=value.eligibility_summary, application_definition=value.intake_definition,
        required_disclaimers=value.required_disclaimers, cta_labels=value.cta_labels,
        review_process=value.intake_definition.review_stages,
        review_process_disclaimer=value.review_process_disclaimer,
        contact_reference=value.contact_reference, privacy_policy_reference=value.privacy_policy_reference,
    )
