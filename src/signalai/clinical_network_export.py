"""Privacy-preserving public export for the clinical partner network."""

from __future__ import annotations

from collections import Counter

from signalai.clinical_network import validate_clinical_network_references
from signalai.schemas.clinical_network import ClinicalNetworkState, PartnerStatus, ReviewStatus
from signalai.schemas.models import SignalState
from signalai.schemas.public_clinical_network import (
    PublicClinicalIntelligence,
    PublicClinicalNetwork,
    PublicClinicalNetworkSummary,
    PublicClinicProfile,
    PublicClinicProgramMatch,
    PublicPhysician,
)
from signalai.schemas.workspace import JurisdictionVerificationStatus, TherapeuticAssetWorkspace


def export_clinical_network(
    network: ClinicalNetworkState,
    scientific_state: SignalState,
    workspace: TherapeuticAssetWorkspace,
    *,
    what_changed_recently: str | None = None,
) -> PublicClinicalNetwork:
    validate_clinical_network_references(network, scientific_state, workspace)
    public_clinics = [
        clinic
        for clinic in network.clinics
        if clinic.public_profile_enabled and clinic.partner_status is PartnerStatus.APPROVED
    ]
    public_ids = {clinic.clinic_id for clinic in public_clinics}
    matches = [
        match
        for match in network.program_matches
        if match.clinic_id in public_ids
        and match.match_status.value == "approved"
        and match.approved_by
        and match.approved_at is not None
    ]
    pending = sum(
        clinic.partner_status is PartnerStatus.UNDER_REVIEW for clinic in network.clinics
    ) + sum(
        interest.status in {ReviewStatus.SUBMITTED, ReviewStatus.UNDER_REVIEW}
        for interest in network.partnership_interests
    )
    status_counts = Counter(clinic.partner_status.value for clinic in public_clinics)

    verified_jurisdictions = sum(
        item.verification_status is JurisdictionVerificationStatus.VERIFIED_PRIMARY
        for item in workspace.jurisdictions.jurisdictions
    )
    total_jurisdictions = len(workspace.jurisdictions.jurisdictions)
    jurisdiction_relevance = (
        f"{verified_jurisdictions} of {total_jurisdictions} jurisdiction assessments "
        "currently have primary-source verification; clinic participation remains "
        "subject to jurisdiction-specific review."
    )
    human_evidence = (
        "human_evidence_present"
        if any(bool(item.metadata.get("human_efficacy")) for item in scientific_state.evidence)
        else "no_human_efficacy_evidence"
    )
    return PublicClinicalNetwork(
        summary=PublicClinicalNetworkSummary(
            totalClinics=len(network.clinics),
            publicClinics=len(public_clinics),
            approvedPartners=sum(
                clinic.partner_status is PartnerStatus.APPROVED for clinic in network.clinics
            ),
            pendingReview=pending,
            programMatches=len(matches),
        ),
        clinicProfiles=[
            PublicClinicProfile(
                clinicId=clinic.clinic_id,
                name=clinic.name,
                city=clinic.city,
                country=clinic.country,
                region=clinic.region,
                website=clinic.website,
                publicContactEmail=clinic.contact_email if clinic.contact_email_public else None,
                physicians=[
                    PublicPhysician(
                        physicianId=physician.physician_id,
                        name=physician.name,
                        title=physician.title,
                        specialty=physician.specialty,
                        credentials=physician.credentials,
                        profileSummary=physician.profile_summary,
                        profileUrl=physician.profile_url,
                    )
                    for physician in clinic.physicians
                    if physician.public_profile_enabled
                ],
                specialties=clinic.specialties,
                languages=clinic.languages,
                modalitiesOffered=clinic.modalities_offered,
                regenerativeExperience=clinic.regenerative_experience,
                intranasalExperience=clinic.intranasal_experience,
                researchExperience=clinic.research_experience,
                outcomesTrackingCapability=clinic.outcomes_tracking_capability,
                jurisdictionId=clinic.jurisdiction_id,
                verificationStatus=clinic.verification_status,
                partnerStatus=clinic.partner_status,
                partnerRoles=clinic.partner_roles,
            )
            for clinic in public_clinics
        ],
        countriesRepresented=sorted({clinic.country for clinic in public_clinics}),
        jurisdictionsRepresented=sorted(
            {clinic.jurisdiction_id for clinic in public_clinics if clinic.jurisdiction_id}
        ),
        programMatches=[
            PublicClinicProgramMatch(
                matchId=item.match_id,
                clinicId=item.clinic_id,
                programId=item.program_id,
                matchStatus=item.match_status,
                jurisdictionFit=item.jurisdiction_fit,
                regenerativeExperience=item.regenerative_experience,
                relevantSpecialtyFit=item.relevant_specialty_fit,
                researchInfrastructureFit=item.research_infrastructure_fit,
                readinessNotes=item.readiness_notes,
                recommendedRole=item.recommended_role,
                rationale=item.rationale,
            )
            for item in matches
        ],
        partnerStatusCounts=dict(sorted(status_counts.items())),
        intelligence=[
            PublicClinicalIntelligence(
                programId=scientific_state.program.program_id,
                therapeuticProgram=scientific_state.program.name,
                currentEvidenceConfidence=scientific_state.program.evidence_confidence,
                developmentStage=scientific_state.program.status,
                humanEvidenceLevel=human_evidence,
                majorUnresolvedRisk=scientific_state.program.largest_unresolved_risk,
                jurisdictionRelevance=jurisdiction_relevance,
                whatChangedRecently=what_changed_recently,
            )
        ],
    )
