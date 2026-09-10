"""Deterministic opportunity assessments for regenerative-medicine clinics."""

from __future__ import annotations

from datetime import datetime, timezone

from signalai.schemas.clinical_network import (
    CapabilityLevel,
    Clinic,
    ClinicOpportunityAssessment,
    ClinicOpportunityPriority,
    ClinicProgramMatch,
    DocumentationStatus,
    ExosomeProductReview,
    MatchStatus,
    RegenerativeClinicArchetype,
)


def classify_regenerative_clinic(
    clinic: Clinic,
) -> tuple[RegenerativeClinicArchetype, ClinicOpportunityPriority]:
    """Classify from declared portfolio facts, without inferring clinical quality."""

    has_stem_cells = bool(clinic.stem_cell_therapies_offered)
    has_exosomes = bool(clinic.exosome_ev_therapies_offered)
    if has_stem_cells and has_exosomes:
        return RegenerativeClinicArchetype.STEM_CELL_AND_EXOSOME, ClinicOpportunityPriority.TIER_1
    if has_stem_cells and (
        clinic.evaluating_exosome_secretome or clinic.secretome_cell_derived_products
    ):
        return (
            RegenerativeClinicArchetype.STEM_CELL_EVALUATING_CELL_DERIVED,
            ClinicOpportunityPriority.TIER_2,
        )
    serious_exosome_program = has_exosomes and (
        clinic.research_experience in {CapabilityLevel.MODERATE, CapabilityLevel.STRONG}
        or clinic.outcomes_tracking_capability
        in {CapabilityLevel.MODERATE, CapabilityLevel.STRONG}
        or bool(clinic.product_documentation)
    )
    if serious_exosome_program:
        return RegenerativeClinicArchetype.EXOSOME_FOCUSED, ClinicOpportunityPriority.TIER_3
    return (
        RegenerativeClinicArchetype.OTHER_REGENERATIVE,
        ClinicOpportunityPriority.NOT_PRIORITIZED,
    )


def _diligence_gaps(clinic: Clinic) -> list[str]:
    gaps: list[str] = []
    if not clinic.product_documentation:
        gaps.append("Product characterization and documentation have not been assessed.")
    elif any(
        DocumentationStatus.NOT_ASSESSED
        in {
            item.identity_characterization,
            item.sterility_safety_documentation,
            item.manufacturing_documentation,
            item.evidence_documentation,
        }
        for item in clinic.product_documentation
    ):
        gaps.append("One or more offered products have incomplete diligence documentation.")
    if not clinic.suppliers_manufacturers:
        gaps.append("Supplier or manufacturer provenance has not been recorded.")
    if clinic.stem_cell_therapies_offered and not clinic.cell_sources:
        gaps.append("Cell source has not been recorded for offered stem-cell therapies.")
    if clinic.stem_cell_therapies_offered and not clinic.tissue_sources:
        gaps.append("Tissue source has not been recorded for offered stem-cell therapies.")
    if clinic.stem_cell_therapies_offered and not clinic.biological_relationships:
        gaps.append("Autologous versus allogeneic use has not been characterized.")
    if clinic.stem_cell_therapies_offered and not clinic.manipulation_levels:
        gaps.append("Expansion or manipulation level has not been characterized.")
    if not clinic.routes_of_administration:
        gaps.append("Routes of administration have not been recorded.")
    if clinic.treatment_volume is None:
        gaps.append("Treatment volume is unknown.")
    if clinic.outcomes_tracking_capability in {
        CapabilityLevel.NOT_ASSESSED,
        CapabilityLevel.NONE,
    }:
        gaps.append("Outcomes-tracking capability requires assessment.")
    return gaps


def _sgl001_fit(match: ClinicProgramMatch | None) -> CapabilityLevel:
    if match is None or match.program_id != "SGL-001":
        return CapabilityLevel.NOT_ASSESSED
    if match.match_status is MatchStatus.APPROVED:
        return CapabilityLevel.STRONG
    if match.match_status in {MatchStatus.CANDIDATE, MatchStatus.UNDER_REVIEW}:
        return CapabilityLevel.MODERATE
    if match.match_status is MatchStatus.DECLINED:
        return CapabilityLevel.NONE
    return CapabilityLevel.NOT_ASSESSED


def assess_clinic_opportunity(
    clinic: Clinic,
    *,
    assessment_id: str,
    relevant_jurisdiction_ids: list[str],
    sgl001_match: ClinicProgramMatch | None = None,
    exosome_product_reviews: list[ExosomeProductReview] | None = None,
    created_at: datetime | None = None,
) -> ClinicOpportunityAssessment:
    """Build an inspectable opportunity record from supplied clinic facts."""

    archetype, priority = classify_regenerative_clinic(clinic)
    modules = ["therapeutic-programs", "evidence", "jurisdictions"]
    if clinic.exosome_ev_therapies_offered or clinic.secretome_cell_derived_products:
        modules.extend(["cargo", "formulation", "exosome-product-review"])

    first_offer = {
        RegenerativeClinicArchetype.STEM_CELL_AND_EXOSOME: (
            "Portfolio and product-evidence diligence across the clinic's stem-cell and "
            "exosome offerings, linked to relevant jurisdiction intelligence."
        ),
        RegenerativeClinicArchetype.STEM_CELL_EVALUATING_CELL_DERIVED: (
            "An evidence and product-readiness briefing for evaluating exosome or "
            "secretome additions to the established stem-cell portfolio."
        ),
        RegenerativeClinicArchetype.EXOSOME_FOCUSED: (
            "An exosome-specific product review covering characterization, evidence, "
            "supplier provenance, and jurisdiction questions."
        ),
        RegenerativeClinicArchetype.OTHER_REGENERATIVE: (
            "A regenerative-portfolio discovery review before proposing program access."
        ),
        RegenerativeClinicArchetype.NOT_ASSESSED: "Complete clinic portfolio diligence.",
    }[archetype]
    relationship_path = {
        ClinicOpportunityPriority.TIER_1: "Begin with intelligence partnership; evaluate advisory or future pilot-site fit after diligence.",
        ClinicOpportunityPriority.TIER_2: "Begin with an evaluation briefing; consider listed or advisory partnership after portfolio review.",
        ClinicOpportunityPriority.TIER_3: "Begin with exosome product diligence; consider listed partnership after verification.",
        ClinicOpportunityPriority.NOT_PRIORITIZED: "Complete qualification before proposing a partner role.",
    }[priority]
    portfolio = list(
        dict.fromkeys(
            clinic.stem_cell_therapies_offered
            + clinic.exosome_ev_therapies_offered
            + clinic.secretome_cell_derived_products
            + clinic.modalities_offered
        )
    )
    return ClinicOpportunityAssessment(
        assessment_id=assessment_id,
        clinic_id=clinic.clinic_id,
        archetype=archetype,
        priority=priority,
        current_therapeutic_portfolio=portfolio,
        product_evidence_diligence_gaps=_diligence_gaps(clinic),
        relevant_jurisdiction_ids=relevant_jurisdiction_ids,
        relevant_intelligence_module_ids=modules,
        sgl001_fit=_sgl001_fit(sgl001_match),
        recommended_first_value_offer=first_offer,
        recommended_relationship_path=relationship_path,
        exosome_product_reviews=exosome_product_reviews or [],
        created_at=created_at or datetime.now(timezone.utc),
    )
