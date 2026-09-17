"""Sanitized Product Design Lab public contracts."""

from datetime import datetime

from pydantic import Field

from signalai.schemas.design_lab import (
    CausalChain, DesignDetermination, DesignDomain, ExperimentProposal,
    ProductSignatureCandidate, ReviewerFinding,
)
from signalai.schemas.models import Identifier, NonEmptyText, SignalModel


DESIGN_LAB_DISCLAIMER = (
    "AI-generated, evidence-linked product hypotheses. These are not validated "
    "mechanisms, manufacturing specifications, experimental results, or evidence of clinical efficacy."
)


class PublicDesignHypothesis(SignalModel):
    hypothesis_id: Identifier = Field(alias="hypothesisId")
    run_id: Identifier = Field(alias="runId")
    title: NonEmptyText
    design_question: NonEmptyText = Field(alias="designQuestion")
    primary_domain: DesignDomain = Field(alias="primaryDomain")
    proposed_product_change_or_attribute: NonEmptyText = Field(alias="proposedProductChangeOrAttribute")
    biological_rationale: NonEmptyText = Field(alias="biologicalRationale")
    manufacturing_rationale: NonEmptyText = Field(alias="manufacturingRationale")
    expected_measurable_effect: NonEmptyText = Field(alias="expectedMeasurableEffect")
    supporting_evidence_ids: list[Identifier] = Field(alias="supportingEvidenceIds")
    contradicting_evidence_ids: list[Identifier] = Field(alias="contradictingEvidenceIds")
    causal_chain: CausalChain = Field(alias="causalChain")
    reviewer_findings: list[ReviewerFinding] = Field(alias="reviewerFindings")
    adversary_objection: NonEmptyText = Field(alias="adversaryObjection")
    chair_rationale: NonEmptyText = Field(alias="chairRationale")
    determination: DesignDetermination
    created_at: datetime = Field(alias="createdAt")


class PublicDesignLabSummary(SignalModel):
    reviewed: int
    proposed_for_testing: int = Field(alias="proposedForTesting")
    needs_evidence: int = Field(alias="needsEvidence")
    parked: int
    rejected: int


class PublicDesignLab(SignalModel):
    disclaimer: str
    current_design_question: str | None = Field(alias="currentDesignQuestion")
    latest_reviewed_hypothesis: PublicDesignHypothesis | None = Field(alias="latestReviewedHypothesis")
    recent_hypotheses: list[PublicDesignHypothesis] = Field(alias="recentHypotheses")
    product_signature_candidates: list[ProductSignatureCandidate] = Field(alias="productSignatureCandidates")
    proposed_mechanism_chain: CausalChain | None = Field(alias="proposedMechanismChain")
    proposed_experiment: ExperimentProposal | None = Field(alias="proposedExperiment")
    open_design_gaps: list[dict] = Field(alias="openDesignGaps")
    parked_ideas: list[Identifier] = Field(alias="parkedIdeas")
    rejected_ideas: list[Identifier] = Field(alias="rejectedIdeas")
    summary_counts: PublicDesignLabSummary = Field(alias="summaryCounts")
    updated_at: datetime = Field(alias="updatedAt")
