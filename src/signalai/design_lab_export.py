"""Frontend-safe Product Design Lab projection."""

from signalai.schemas.design_lab import DesignDetermination, DesignHypothesis, DesignLabWorkspace
from signalai.schemas.public_design_lab import (
    DESIGN_LAB_DISCLAIMER, PublicDesignHypothesis, PublicDesignHypothesisSummary,
    PublicDesignLab, PublicDesignLabSummary, PublicDesignTheme,
)


def _hypothesis(item: DesignHypothesis) -> PublicDesignHypothesis:
    return PublicDesignHypothesis(
        hypothesisId=item.hypothesis_id, runId=item.run_id, title=item.title,
        designQuestion=item.design_question, primaryDomain=item.primary_domain,
        proposedProductChangeOrAttribute=item.proposed_product_change_or_attribute,
        biologicalRationale=item.biological_rationale,
        manufacturingRationale=item.manufacturing_rationale,
        expectedMeasurableEffect=item.expected_measurable_effect,
        supportingEvidenceIds=item.supporting_evidence_ids,
        contradictingEvidenceIds=item.contradicting_evidence_ids,
        causalChain=item.causal_chain, reviewerFindings=item.reviewer_findings,
        adversaryObjection=item.adversary_objection, chairRationale=item.chair_rationale,
        determination=item.determination, createdAt=item.created_at,
        noveltyStatement=item.novelty_statement,
        themeId=item.theme_id or item.selected_gap_id,
        sequenceWithinTheme=item.sequence_within_theme,
    )


def export_design_lab(workspace: DesignLabWorkspace) -> PublicDesignLab | None:
    """Return null until a complete reviewed hypothesis exists."""
    if not workspace.reviewed_hypotheses:
        return None
    recent = sorted(workspace.reviewed_hypotheses, key=lambda x: x.created_at, reverse=True)
    latest = recent[0]
    counts = {value: sum(x.determination is value for x in recent) for value in DesignDetermination}
    return PublicDesignLab(
        disclaimer=DESIGN_LAB_DISCLAIMER,
        currentDesignQuestion=workspace.current_design_question,
        latestReviewedHypothesis=_hypothesis(latest),
        recentHypotheses=[_hypothesis(item) for item in recent[:30]],
        olderHypotheses=[PublicDesignHypothesisSummary(
            hypothesisId=item.hypothesis_id, title=item.title,
            themeId=item.theme_id or item.selected_gap_id,
            determination=item.determination, createdAt=item.created_at,
        ) for item in recent[30:]],
        persistentDesignThemes=[PublicDesignTheme(
            themeId=theme.gap_id, title=theme.title, question=theme.question,
            domain=theme.domain, priority=theme.human_priority_override or theme.priority,
            timesExplored=theme.times_explored, lastExploredAt=theme.last_explored_at,
            latestHypothesisId=theme.latest_hypothesis_id,
            openQuestions=theme.open_questions, explorable=True,
        ) for theme in workspace.design_gaps],
        productSignatureCandidates=workspace.product_signature_candidates,
        proposedMechanismChain=latest.causal_chain,
        proposedExperiment=latest.minimum_discriminating_experiment,
        openDesignGaps=[{
            "gapId": gap.gap_id, "title": gap.title, "question": gap.question,
            "domain": gap.domain.value, "status": gap.status,
        } for gap in workspace.design_gaps],
        parkedIdeas=workspace.parked_hypothesis_ids,
        rejectedIdeas=workspace.rejected_hypothesis_ids,
        summaryCounts=PublicDesignLabSummary(
            reviewed=len(recent),
            proposedForTesting=counts[DesignDetermination.PROPOSED_FOR_TESTING],
            needsEvidence=counts[DesignDetermination.NEEDS_EVIDENCE],
            parked=counts[DesignDetermination.PARKED],
            rejected=counts[DesignDetermination.REJECTED],
            totalHypotheses=len(recent), latestHypothesisDate=latest.created_at,
        ),
        updatedAt=workspace.updated_at,
    )


def validate_design_lab_evidence(workspace: DesignLabWorkspace, allowed: set[str]) -> None:
    refs: list[str] = []
    refs.extend(eid for gap in workspace.design_gaps for eid in gap.evidence_ids)
    refs.extend(eid for item in workspace.proposed_experiments for eid in item.evidence_ids)
    refs.extend(eid for item in workspace.product_signature_candidates for eid in item.evidence_ids)
    for item in workspace.reviewed_hypotheses:
        refs.extend(item.supporting_evidence_ids)
        refs.extend(item.contradicting_evidence_ids)
        refs.extend(eid for edge in item.causal_chain.edges for eid in edge.evidence_ids)
        refs.extend(eid for finding in item.reviewer_findings for eid in finding.evidence_ids)
        if item.minimum_discriminating_experiment:
            refs.extend(item.minimum_discriminating_experiment.evidence_ids)
    unknown = sorted(set(refs) - allowed)
    if unknown:
        raise ValueError(f"Design Lab references unknown canonical evidence: {unknown}")
