"""Deterministic matter prioritization and reviewer-panel selection."""

from signalai.schemas.live import (
    AdvancementValue,
    DevelopmentDocket,
    DevelopmentMatter,
    MatterDomain,
    MatterPriority,
    MatterStatus,
    ReviewerRole,
)


_PRIORITY = {value: index for index, value in enumerate(MatterPriority)}
_VALUE = {
    AdvancementValue.CRITICAL: 0,
    AdvancementValue.HIGH: 1,
    AdvancementValue.MODERATE: 2,
    AdvancementValue.LOW: 3,
}
_DOMAIN_REVIEWERS = {
    MatterDomain.EVIDENCE: [ReviewerRole.EVIDENCE, ReviewerRole.LITERATURE],
    MatterDomain.CARGO: [ReviewerRole.CARGO, ReviewerRole.EVIDENCE],
    MatterDomain.FORMULATION: [ReviewerRole.FORMULATION, ReviewerRole.CMC],
    MatterDomain.DELIVERY: [ReviewerRole.DELIVERY, ReviewerRole.TRANSLATIONAL, ReviewerRole.PRECLINICAL],
    MatterDomain.CMC_MANUFACTURING: [ReviewerRole.CMC, ReviewerRole.MANUFACTURING],
    MatterDomain.TRANSLATIONAL: [ReviewerRole.TRANSLATIONAL, ReviewerRole.PRECLINICAL, ReviewerRole.CLINICAL],
    MatterDomain.JURISDICTION: [ReviewerRole.JURISDICTION, ReviewerRole.CLINICAL],
    MatterDomain.CLINICAL_DEPLOYMENT: [ReviewerRole.CLINICAL, ReviewerRole.JURISDICTION, ReviewerRole.COMMERCIAL],
    MatterDomain.COMMERCIAL: [ReviewerRole.COMMERCIAL, ReviewerRole.JURISDICTION],
}


class NoOpenMattersError(RuntimeError):
    pass


def select_current_matter(docket: DevelopmentDocket) -> tuple[DevelopmentMatter, str]:
    open_matters = [item for item in docket.matters if item.status is MatterStatus.OPEN]
    if not open_matters:
        raise NoOpenMattersError("development docket has no open matters")
    selected = min(
        open_matters,
        key=lambda item: (
            _PRIORITY[item.priority],
            _VALUE[item.advancement_value],
            item.matter_id,
        ),
    )
    reason = (
        f"Selected {selected.priority.value} matter with "
        f"{selected.advancement_value.value} advancement value. Deterministic ranking "
        "favors program-invalidating issues, then real-world stage blockers, product "
        "definition, deployment, quality, contradictions, experiment design, and refinement."
    )
    return selected, reason


def select_reviewers(matter: DevelopmentMatter) -> list[ReviewerRole]:
    ordered = [*_DOMAIN_REVIEWERS[matter.domain], *matter.required_reviewer_roles]
    ordered.extend([ReviewerRole.VERIFIER, ReviewerRole.ADVERSARY, ReviewerRole.CHAIR])
    return list(dict.fromkeys(ordered))
