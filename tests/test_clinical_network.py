import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from signalai.clinical_network import (
    approve_public_listing,
    review_clinic_intake,
    submit_clinic_intake,
    validate_clinical_network_references,
)
from signalai.clinical_network_export import export_clinical_network
from signalai.schemas import (
    CapabilityLevel,
    Clinic,
    ClinicalNetworkState,
    ClinicProgramMatch,
    JurisdictionFit,
    MatchStatus,
    PartnerRole,
    PartnerStatus,
    Physician,
    PublicClinicalNetwork,
    ReviewStatus,
    SignalState,
    TherapeuticAssetWorkspace,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)


def _states():
    scientific = SignalState.model_validate_json(
        (ROOT / "state" / "signal-state.json").read_text(encoding="utf-8")
    )
    workspace = TherapeuticAssetWorkspace.model_validate_json(
        (ROOT / "state" / "asset-development.json").read_text(encoding="utf-8")
    )
    return scientific, workspace


def _clinic(**updates) -> Clinic:
    values = {
        "clinic_id": "clinic-test",
        "name": "Test Clinic",
        "city": "Test City",
        "country": "Test Country",
        "region": "Test Region",
        "contact_email": "private@example.org",
        "physicians": [
            Physician(
                physician_id="physician-test",
                name="Test Physician",
                specialty="Neurology",
                clinic_id="clinic-test",
                public_profile_enabled=True,
            )
        ],
        "specialties": ["Neurology"],
        "languages": ["English"],
        "modalities_offered": ["Supportive care"],
        "regenerative_experience": CapabilityLevel.MODERATE,
        "intranasal_experience": CapabilityLevel.LIMITED,
        "research_experience": CapabilityLevel.STRONG,
        "outcomes_tracking_capability": CapabilityLevel.STRONG,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(updates)
    return Clinic(**values)


def test_clinic_and_physician_relationship_validation() -> None:
    clinic = _clinic()
    assert clinic.physicians[0].clinic_id == clinic.clinic_id

    with pytest.raises(ValidationError, match="containing clinic"):
        _clinic(
            physicians=[
                Physician(
                    physician_id="physician-other",
                    name="Other Physician",
                    specialty="Neurology",
                    clinic_id="clinic-other",
                )
            ]
        )


def test_public_listing_requires_explicit_human_approval() -> None:
    with pytest.raises(ValidationError, match="approved partner status"):
        _clinic(public_profile_enabled=True)

    approved = approve_public_listing(
        _clinic(), approved_by="reviewer-1", roles=[PartnerRole.LISTED_PARTNER], approved_at=NOW
    )
    assert approved.partner_status is PartnerStatus.APPROVED
    assert approved.public_profile_enabled is True
    assert approved.approved_by == "reviewer-1"


def test_intake_submission_and_review_are_separate_from_public_approval() -> None:
    submission = submit_clinic_intake(
        {
            "clinic_name": "Submitted Clinic",
            "physician_name": "Submitted Physician",
            "city": "City",
            "country": "Country",
            "website": "https://example.org",
            "email": "contact@example.org",
            "specialty": "Neurology",
            "modalities_offered": ["Rehabilitation"],
            "interest_categories": ["evaluate_future_programs"],
            "notes": "Requests review.",
        },
        submitted_at=NOW,
    )
    review = review_clinic_intake(
        submission, approved=True, reviewed_by="reviewer-1", reviewed_at=NOW
    )
    assert submission.status is ReviewStatus.SUBMITTED
    assert review.status is ReviewStatus.APPROVED
    assert not hasattr(review, "public_profile_enabled")


def test_program_match_uses_qualitative_dimensions() -> None:
    match = ClinicProgramMatch(
        match_id="match-test-sgl001",
        clinic_id="clinic-test",
        program_id="SGL-001",
        match_status=MatchStatus.CANDIDATE,
        jurisdiction_fit=JurisdictionFit.UNRESOLVED,
        regenerative_experience=CapabilityLevel.MODERATE,
        relevant_specialty_fit=CapabilityLevel.STRONG,
        research_infrastructure_fit=CapabilityLevel.MODERATE,
        readiness_notes="Requires jurisdiction and operational review.",
        recommended_role=PartnerRole.EVALUATION_SITE,
        rationale="Capabilities appear relevant, subject to human verification.",
        created_at=NOW,
        updated_at=NOW,
    )
    assert match.jurisdiction_fit is JurisdictionFit.UNRESOLVED
    assert "score" not in match.model_dump()


def test_program_match_requires_human_approval_before_publication() -> None:
    scientific, workspace = _states()
    approved_clinic = approve_public_listing(
        _clinic(), approved_by="reviewer-1", roles=[PartnerRole.LISTED_PARTNER], approved_at=NOW
    )
    candidate = ClinicProgramMatch(
        match_id="match-candidate",
        clinic_id=approved_clinic.clinic_id,
        program_id="SGL-001",
        match_status=MatchStatus.CANDIDATE,
        jurisdiction_fit=JurisdictionFit.UNRESOLVED,
        regenerative_experience=CapabilityLevel.MODERATE,
        relevant_specialty_fit=CapabilityLevel.STRONG,
        research_infrastructure_fit=CapabilityLevel.MODERATE,
        rationale="Candidate assessment pending human review.",
        created_at=NOW,
        updated_at=NOW,
    )
    private_projection = export_clinical_network(
        ClinicalNetworkState(
            generated_at=NOW, clinics=[approved_clinic], program_matches=[candidate]
        ),
        scientific,
        workspace,
    )
    assert private_projection.program_matches == []

    with pytest.raises(ValidationError, match="human approval provenance"):
        ClinicProgramMatch.model_validate(
            {**candidate.model_dump(mode="python"), "match_status": MatchStatus.APPROVED}
        )

    approved_match = ClinicProgramMatch.model_validate(
        {
            **candidate.model_dump(mode="python"),
            "match_status": MatchStatus.APPROVED,
            "approved_by": "reviewer-2",
            "approved_at": NOW,
        }
    )
    public_projection = export_clinical_network(
        ClinicalNetworkState(
            generated_at=NOW,
            clinics=[approved_clinic],
            program_matches=[approved_match],
        ),
        scientific,
        workspace,
    )
    assert [item.match_id for item in public_projection.program_matches] == [
        "match-candidate"
    ]


def test_public_export_hides_unapproved_clinics_and_private_email() -> None:
    scientific, workspace = _states()
    approved = approve_public_listing(
        _clinic(), approved_by="reviewer-1", roles=[PartnerRole.LISTED_PARTNER], approved_at=NOW
    )
    network = ClinicalNetworkState(
        generated_at=NOW,
        clinics=[_clinic(clinic_id="private-clinic", physicians=[]), approved],
    )
    public = export_clinical_network(network, scientific, workspace)
    assert public.summary.total_clinics == 2
    assert public.summary.public_clinics == 1
    assert [item.clinic_id for item in public.clinic_profiles] == ["clinic-test"]
    assert public.clinic_profiles[0].public_contact_email is None
    assert "private@example.org" not in public.model_dump_json(by_alias=True)


def test_public_email_requires_explicit_public_flag() -> None:
    scientific, workspace = _states()
    approved = approve_public_listing(
        _clinic(), approved_by="reviewer-1", roles=[PartnerRole.LISTED_PARTNER], approved_at=NOW
    )
    explicitly_public = Clinic.model_validate(
        {**approved.model_dump(mode="python"), "contact_email_public": True}
    )
    public = export_clinical_network(
        ClinicalNetworkState(generated_at=NOW, clinics=[explicitly_public]),
        scientific,
        workspace,
    )
    assert public.clinic_profiles[0].public_contact_email == "private@example.org"


def test_network_cross_references_and_empty_serialization() -> None:
    scientific, workspace = _states()
    network = ClinicalNetworkState.model_validate_json(
        (ROOT / "state" / "clinical-network.json").read_text(encoding="utf-8")
    )
    validate_clinical_network_references(network, scientific, workspace)
    public = export_clinical_network(network, scientific, workspace)
    payload = json.loads(public.model_dump_json(by_alias=True))
    PublicClinicalNetwork.model_validate(payload)
    assert payload["summary"] == {
        "totalClinics": 0,
        "publicClinics": 0,
        "approvedPartners": 0,
        "pendingReview": 0,
        "programMatches": 0,
    }
    assert payload["clinicProfiles"] == []
    assert payload["countriesRepresented"] == []
    assert payload["jurisdictionsRepresented"] == []
    assert payload["programMatches"] == []
    assert len(payload["intelligence"]) == 1
