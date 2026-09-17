"""Canonical, review-gated SGL-001 Product Design Lab contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from signalai.schemas.models import Identifier, NonEmptyText, SignalModel, _require_timezone


class DesignDomain(StrEnum):
    CELL_SOURCE = "cell_source"
    PRODUCT_IDENTITY = "product_identity"
    CARGO = "cargo"
    PROCESS = "process"
    FRACTIONATION = "fractionation"
    FORMULATION = "formulation"
    MANUFACTURING = "manufacturing"
    POTENCY = "potency"
    MECHANISM = "mechanism"
    REPRODUCIBILITY = "reproducibility"
    STABILITY = "stability"
    DELIVERY = "delivery"


class EvidenceState(StrEnum):
    DIRECT = "direct_observation"
    INDIRECT = "indirect_support"
    INFERENCE = "inference"
    CONTRADICTED = "contradicted"
    GAP = "evidence_gap"


class AttributeRole(StrEnum):
    EXPLORATORY = "exploratory_characterization_candidate"
    CANDIDATE_CQA = "candidate_critical_quality_attribute"
    PROPOSED_IPC = "proposed_in_process_control"
    PROPOSED_RELEASE = "proposed_release_test"
    VALIDATED_RELEASE = "validated_release_test"


class AttributeGroup(StrEnum):
    IDENTITY = "identity_markers"
    SURFACE = "surface_phenotype"
    CARGO = "cargo_profile"
    NON_EV = "non_ev_composition"
    IMPURITY = "process_related_impurities"
    PHYSICAL = "physical_attributes"
    POTENCY = "functional_potency"
    FINGERPRINT = "manufacturing_fingerprint"
    STABILITY = "stability_attributes"


class DesignDetermination(StrEnum):
    PROPOSED_FOR_TESTING = "proposed_for_testing"
    NEEDS_EVIDENCE = "needs_evidence"
    NEEDS_MANUFACTURING = "needs_manufacturing_assessment"
    HUMAN_DECISION = "human_decision_required"
    PARKED = "parked"
    REJECTED = "rejected"
    PROMOTED = "promoted_to_experiment"
    INCORPORATED = "incorporated_into_product_definition"


AUTONOMOUS_DETERMINATIONS = {
    DesignDetermination.PROPOSED_FOR_TESTING,
    DesignDetermination.NEEDS_EVIDENCE,
    DesignDetermination.NEEDS_MANUFACTURING,
    DesignDetermination.HUMAN_DECISION,
    DesignDetermination.PARKED,
    DesignDetermination.REJECTED,
}


class DesignGap(SignalModel):
    gap_id: Identifier
    title: NonEmptyText
    question: NonEmptyText
    domain: DesignDomain
    blocking_value: int = Field(ge=1, le=5)
    testability: int = Field(ge=1, le=5)
    product_definition_relevance: int = Field(ge=1, le=5)
    manufacturing_relevance: int = Field(ge=1, le=5)
    evidence_availability: int = Field(ge=1, le=5)
    discriminating_value: int = Field(ge=1, le=5)
    rationale: NonEmptyText
    evidence_ids: list[Identifier] = Field(default_factory=list)
    status: str = Field(default="open", pattern="^(open|selected|reviewed|parked)$")


class CausalNode(SignalModel):
    node_id: Identifier
    stage: str = Field(pattern="^(product_attribute|molecular_interaction|cellular_response|tissue_response|cns_relevant_effect|proposed_therapeutic_relevance)$")
    statement: NonEmptyText


class CausalEdge(SignalModel):
    edge_id: Identifier
    source_node_id: Identifier
    target_node_id: Identifier
    evidence_state: EvidenceState
    evidence_ids: list[Identifier] = Field(default_factory=list)
    relation_type: str = Field(pattern="^(direct_observation|inference)$")
    model_or_species: str | None = None
    uncertainty: NonEmptyText
    competing_explanation: str | None = None
    missing_experiment: str | None = None


class CausalChain(SignalModel):
    nodes: list[CausalNode] = Field(default_factory=list)
    edges: list[CausalEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self):
        ids = [node.node_id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate causal node ID")
        allowed = set(ids)
        if any(edge.source_node_id not in allowed or edge.target_node_id not in allowed for edge in self.edges):
            raise ValueError("causal edge references unknown node")
        return self


class ProductSignatureCandidate(SignalModel):
    attribute_id: Identifier
    name: NonEmptyText
    group: AttributeGroup
    role: AttributeRole
    rationale: NonEmptyText
    evidence_ids: list[Identifier] = Field(default_factory=list)
    uncertainty: NonEmptyText
    source_hypothesis_id: Identifier
    human_approved: bool = False

    @model_validator(mode="after")
    def autonomous_cannot_validate(self):
        if self.role is AttributeRole.VALIDATED_RELEASE and not self.human_approved:
            raise ValueError("validated release tests require explicit human approval")
        return self


class ExperimentProposal(SignalModel):
    experiment_id: Identifier
    question: NonEmptyText
    hypothesis_tested: NonEmptyText
    required_material: list[NonEmptyText]
    comparator: NonEmptyText
    control: NonEmptyText
    assay: NonEmptyText
    primary_readout: NonEmptyText
    secondary_readouts: list[NonEmptyText] = Field(default_factory=list)
    success_criterion: NonEmptyText
    failure_criterion: NonEmptyText
    falsification_outcome: NonEmptyText
    dependencies: list[NonEmptyText] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(default_factory=list)
    complexity: str = Field(pattern="^(low|moderate|high|not_assessed)$")
    human_approval_state: str = Field(pattern="^(pending|approved|rejected)$")
    execution_status: str = Field(default="proposed", pattern="^proposed$")


class ReviewerFinding(SignalModel):
    role: str = Field(pattern="^(evidence_verifier|cmc_manufacturing|mechanism)$")
    conclusion: NonEmptyText
    supported: bool
    evidence_ids: list[Identifier] = Field(default_factory=list)
    evidence_gap: str | None = None
    concerns: list[NonEmptyText] = Field(default_factory=list)


class DesignHypothesis(SignalModel):
    hypothesis_id: Identifier
    program_id: Identifier
    run_id: Identifier
    created_at: datetime
    title: NonEmptyText
    design_question: NonEmptyText
    primary_domain: DesignDomain
    secondary_domains: list[DesignDomain] = Field(default_factory=list)
    selected_gap_id: Identifier
    proposed_product_change_or_attribute: NonEmptyText
    biological_rationale: NonEmptyText
    manufacturing_rationale: NonEmptyText
    causal_chain: CausalChain
    expected_measurable_effect: NonEmptyText
    supporting_evidence_ids: list[Identifier] = Field(default_factory=list)
    contradicting_evidence_ids: list[Identifier] = Field(default_factory=list)
    explicit_inferences: list[NonEmptyText] = Field(default_factory=list)
    assumptions: list[NonEmptyText] = Field(default_factory=list)
    competing_explanations: list[NonEmptyText] = Field(default_factory=list)
    manufacturability_assessment: NonEmptyText
    measurement_strategy: NonEmptyText
    candidate_quality_attributes_affected: list[Identifier] = Field(default_factory=list)
    proposed_potency_relationship: NonEmptyText
    principal_risks: list[NonEmptyText]
    falsification_criteria: list[NonEmptyText]
    minimum_discriminating_experiment: ExperimentProposal | None
    dependencies: list[NonEmptyText] = Field(default_factory=list)
    human_decisions_required: list[NonEmptyText] = Field(default_factory=list)
    reviewer_findings: list[ReviewerFinding]
    adversary_objection: NonEmptyText
    chair_rationale: NonEmptyText
    determination: DesignDetermination
    status: str = Field(pattern="^(reviewed|parked|rejected)$")
    promotion_human_approved: bool = False

    @model_validator(mode="after")
    def validate_record(self):
        object.__setattr__(self, "created_at", _require_timezone(self.created_at, "created_at"))
        if self.determination not in AUTONOMOUS_DETERMINATIONS and not self.promotion_human_approved:
            raise ValueError("promotion requires explicit human approval")
        if self.determination is not DesignDetermination.REJECTED and self.minimum_discriminating_experiment is None:
            raise ValueError("non-rejected hypotheses require a discriminating experiment")
        return self


class DesignRunSummary(SignalModel):
    run_id: Identifier
    hypothesis_id: Identifier
    gap_id: Identifier
    determination: DesignDetermination
    created_at: datetime

    @model_validator(mode="after")
    def validate_time(self):
        object.__setattr__(self, "created_at", _require_timezone(self.created_at, "created_at"))
        return self


class DesignLabWorkspace(SignalModel):
    schema_version: str = "1.0"
    program_id: Identifier = "SGL-001"
    current_design_question: str | None = None
    reviewed_hypotheses: list[DesignHypothesis] = Field(default_factory=list)
    proposed_experiments: list[ExperimentProposal] = Field(default_factory=list)
    parked_hypothesis_ids: list[Identifier] = Field(default_factory=list)
    rejected_hypothesis_ids: list[Identifier] = Field(default_factory=list)
    product_signature_candidates: list[ProductSignatureCandidate] = Field(default_factory=list)
    design_gaps: list[DesignGap] = Field(default_factory=list)
    recent_runs: list[DesignRunSummary] = Field(default_factory=list)
    updated_at: datetime

    @model_validator(mode="after")
    def validate_workspace(self):
        object.__setattr__(self, "updated_at", _require_timezone(self.updated_at, "updated_at"))
        for label, values in {
            "hypothesis": [x.hypothesis_id for x in self.reviewed_hypotheses],
            "experiment": [x.experiment_id for x in self.proposed_experiments],
            "signature": [x.attribute_id for x in self.product_signature_candidates],
            "gap": [x.gap_id for x in self.design_gaps],
            "run": [x.run_id for x in self.recent_runs],
        }.items():
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} ID")
        known = {x.hypothesis_id for x in self.reviewed_hypotheses}
        if set(self.parked_hypothesis_ids + self.rejected_hypothesis_ids) - known:
            raise ValueError("workspace categorization references unknown hypothesis")
        return self


# Bounded model outputs; application code assembles the canonical hypothesis.
class DesignProposal(SignalModel):
    title: NonEmptyText
    design_question: NonEmptyText
    primary_domain: DesignDomain
    secondary_domains: list[DesignDomain] = Field(default_factory=list)
    proposed_product_change_or_attribute: NonEmptyText
    biological_rationale: NonEmptyText
    manufacturing_rationale: NonEmptyText
    causal_chain: CausalChain
    expected_measurable_effect: NonEmptyText
    supporting_evidence_ids: list[Identifier] = Field(default_factory=list)
    contradicting_evidence_ids: list[Identifier] = Field(default_factory=list)
    explicit_inferences: list[NonEmptyText] = Field(default_factory=list)
    assumptions: list[NonEmptyText] = Field(default_factory=list)
    competing_explanations: list[NonEmptyText] = Field(default_factory=list)
    manufacturability_assessment: NonEmptyText
    measurement_strategy: NonEmptyText
    candidate_quality_attributes: list[ProductSignatureCandidate] = Field(default_factory=list)
    proposed_potency_relationship: NonEmptyText
    principal_risks: list[NonEmptyText]
    falsification_criteria: list[NonEmptyText]
    experiment: ExperimentProposal
    dependencies: list[NonEmptyText] = Field(default_factory=list)
    human_decisions_required: list[NonEmptyText] = Field(default_factory=list)


class DesignReview(SignalModel):
    conclusion: NonEmptyText
    supported: bool
    evidence_ids: list[Identifier] = Field(default_factory=list)
    evidence_gap: str | None = None
    concerns: list[NonEmptyText] = Field(default_factory=list)


class DesignAdversaryReview(SignalModel):
    strongest_objection: NonEmptyText
    failure_modes: list[NonEmptyText]
    evidence_ids: list[Identifier] = Field(default_factory=list)


class DesignChairClassification(SignalModel):
    determination: DesignDetermination
    rationale: NonEmptyText

    @model_validator(mode="after")
    def restrict_autonomy(self):
        if self.determination not in AUTONOMOUS_DETERMINATIONS:
            raise ValueError("autonomous Chair cannot promote a design hypothesis")
        return self
