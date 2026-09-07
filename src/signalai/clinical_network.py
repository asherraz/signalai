"""Clinical-network intake lifecycle and reference validation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from signalai.schemas.clinical_network import (
    Clinic,
    ClinicIntakeReview,
    ClinicIntakeSubmission,
    ClinicalNetworkState,
    ClinicProgramMatch,
    ClinicVerificationStatus,
    PartnerRole,
    PartnerStatus,
    ReviewStatus,
)
from signalai.schemas.models import SignalState
from signalai.schemas.workspace import TherapeuticAssetWorkspace


def submit_clinic_intake(
    payload: Mapping[str, Any], *, submitted_at: datetime | None = None
) -> ClinicIntakeSubmission:
    """Validate a prospective-clinic submission without persisting or publishing it."""

    return ClinicIntakeSubmission.model_validate(
        {
            **payload,
            "submission_id": payload.get("submission_id", f"intake-{uuid4().hex}"),
            "status": ReviewStatus.SUBMITTED,
            "submitted_at": submitted_at or datetime.now(timezone.utc),
        }
    )


def review_clinic_intake(
    submission: ClinicIntakeSubmission,
    *,
    approved: bool,
    reviewed_by: str,
    reviewed_at: datetime | None = None,
    notes: str | None = None,
) -> ClinicIntakeReview:
    """Record a human intake decision; approval does not itself publish a clinic."""

    return ClinicIntakeReview(
        review_id=f"review-{uuid4().hex}",
        submission_id=submission.submission_id,
        status=ReviewStatus.APPROVED if approved else ReviewStatus.DECLINED,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at or datetime.now(timezone.utc),
        notes=notes,
    )


def approve_public_listing(
    clinic: Clinic,
    *,
    approved_by: str,
    roles: list[PartnerRole],
    approved_at: datetime | None = None,
) -> Clinic:
    """Apply the separate human gate required to represent a clinic publicly."""

    timestamp = approved_at or datetime.now(timezone.utc)
    return Clinic.model_validate(
        {
            **clinic.model_dump(mode="python"),
            "verification_status": ClinicVerificationStatus.VERIFIED,
            "partner_status": PartnerStatus.APPROVED,
            "partner_roles": roles,
            "public_profile_enabled": True,
            "approved_by": approved_by,
            "approved_at": timestamp,
            "updated_at": timestamp,
        }
    )


def validate_clinical_network_references(
    network: ClinicalNetworkState,
    scientific_state: SignalState,
    workspace: TherapeuticAssetWorkspace,
) -> None:
    """Validate program and jurisdiction links across canonical states."""

    program_ids = {scientific_state.program.program_id}
    jurisdiction_ids = {
        item.jurisdiction_id for item in workspace.jurisdictions.jurisdictions
    }
    for clinic in network.clinics:
        if clinic.jurisdiction_id and clinic.jurisdiction_id not in jurisdiction_ids:
            raise ValueError("clinic references an unknown jurisdiction")
    for interest in network.partnership_interests:
        if set(interest.program_ids) - program_ids:
            raise ValueError("partnership interest references an unknown program")
    for match in network.program_matches:
        if match.program_id not in program_ids:
            raise ValueError("clinic/program match references an unknown program")


def match_clinic_to_program(match: ClinicProgramMatch) -> ClinicProgramMatch:
    """Typed interface for a reviewed qualitative match assessment."""

    return ClinicProgramMatch.model_validate(match.model_dump(mode="python"))
