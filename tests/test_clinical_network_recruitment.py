import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from signalai.clinical_network_recruitment import (
    export_recruitment_configuration, initial_recruitment_configuration,
)
from signalai.publisher import build_current_public_state
from signalai.schemas.clinical_network_recruitment import (
    ACKNOWLEDGEMENT_STATEMENTS, ClinicalNetworkRecruitmentConfiguration,
    OpportunityAvailability, RecruitmentCapability, RecruitmentInterest,
    RecruitmentOrganizationType, RecruitmentProfessionalRole, RecruitmentReviewStage,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)


def test_recruitment_schema_has_stable_ids_and_complete_enums():
    config = initial_recruitment_configuration(updated_at=NOW)
    assert config.configuration_id == "clinical-network-recruitment-sgl001"
    assert len(config.opportunities) == 12
    assert len({item.opportunity_id for item in config.opportunities}) == 12
    assert config.intake_definition.organization_types == list(RecruitmentOrganizationType)
    assert config.intake_definition.professional_roles == list(RecruitmentProfessionalRole)
    assert config.intake_definition.capability_options == list(RecruitmentCapability)
    assert config.intake_definition.interest_options == list(RecruitmentInterest)
    assert config.intake_definition.review_stages == list(RecruitmentReviewStage)


def test_required_acknowledgements_are_exact_and_mandatory():
    config = initial_recruitment_configuration(updated_at=NOW)
    acknowledgements = config.intake_definition.required_acknowledgements
    assert [item.statement for item in acknowledgements] == ACKNOWLEDGEMENT_STATEMENTS
    assert all(item.required for item in acknowledgements)
    bad = config.model_dump(mode="python")
    bad["intake_definition"]["required_acknowledgements"] = acknowledgements[:-1]
    with pytest.raises(ValidationError, match="approved statements"):
        ClinicalNetworkRecruitmentConfiguration.model_validate(bad)


def test_mandatory_preclinical_positioning_cannot_be_removed():
    config = initial_recruitment_configuration(updated_at=NOW)
    payload = config.model_dump(mode="python")
    payload["required_disclaimers"][0] = "SGL-001 is under development."
    with pytest.raises(ValidationError, match="positioning disclaimers"):
        ClinicalNetworkRecruitmentConfiguration.model_validate(payload)


@pytest.mark.parametrize("phrase", [
    "Purchase SGL-001", "Prescribe SGL-001", "Administer SGL-001",
    "Distribute SGL-001", "Obtain SGL-001", "Regulatory loophole",
])
def test_prohibited_access_or_loophole_language_is_rejected(phrase):
    config = initial_recruitment_configuration(updated_at=NOW)
    payload = config.model_dump(mode="python")
    payload["opportunities"][0]["short_description"] = phrase
    with pytest.raises(ValidationError, match="prohibited access"):
        ClinicalNetworkRecruitmentConfiguration.model_validate(payload)


def test_public_projection_is_concise_and_contains_no_submission_data():
    projection = export_recruitment_configuration(
        initial_recruitment_configuration(updated_at=NOW)
    ).model_dump(mode="json", by_alias=True)
    assert projection["headline"] == "Help shape the clinical path for regenerative therapeutics."
    assert len(projection["available_now"]) == 6
    assert len(projection["future_gated"]) == 6
    assert projection["cta_labels"] == {
        "primary": "Apply to join", "secondary": "Explore Signal Intelligence",
        "sgl001": "Register clinical interest", "submission": "Submit application",
    }
    serialized = json.dumps(projection).casefold()
    for forbidden in (
        "patient_name", "patient_information", "contact_email", "license_identifier",
        "submission_id", "private_review", "outreach_notes", "internal_risk",
        "chain-of-thought", "chain_of_thought", "raw_prompt", "api_key", "credential",
    ):
        assert forbidden not in serialized


def test_public_state_includes_recruitment_without_changing_clinical_network():
    public = build_current_public_state(ROOT, generated_at=NOW)
    assert public.clinical_network is not None
    assert public.clinical_network_opportunity is not None
    assert public.clinical_network_opportunity.application_definition.title == "Join the Signal Clinical Network"
    assert all(item.availability is OpportunityAvailability.AVAILABLE_NOW
               for item in public.clinical_network_opportunity.available_now)
    assert all(item.availability is OpportunityAvailability.FUTURE_GATED
               for item in public.clinical_network_opportunity.future_gated)


def test_generated_public_json_contains_safe_recruitment_configuration():
    payload = json.loads((ROOT / "public/signal-state.json").read_text())
    opportunity = payload["clinicalNetworkOpportunity"]
    assert opportunity["application_definition"]["review_stages"] == [
        item.value for item in RecruitmentReviewStage
    ]
    assert opportunity["application_definition"]["privacy_notice_reference"] is None
    assert opportunity["contact_reference"] is None
    assert opportunity["privacy_policy_reference"] is None
