"""Validate and sanitize the canonical therapeutic asset workspace."""

from __future__ import annotations

from signalai.schemas.agenda import DevelopmentAgenda
from signalai.schemas.models import SignalState
from signalai.schemas.public_workspace import (
    PublicCargoCandidate,
    PublicCargoPathwayLink,
    PublicCargoState,
    PublicDomainAction,
    PublicExcipientCandidate,
    PublicFormulationCandidate,
    PublicFormulationScore,
    PublicFormulationState,
    PublicJurisdictionCard,
    PublicJurisdictionState,
    PublicMoaStep,
    PublicPathway,
    PublicPresentationCandidate,
    PublicTheoreticalMoa,
)
from signalai.schemas.workspace import DevelopmentAction, TherapeuticAssetWorkspace


def validate_workspace_references(
    workspace: TherapeuticAssetWorkspace,
    state: SignalState,
    agenda: DevelopmentAgenda,
) -> None:
    if workspace.program_id != state.program.program_id or agenda.program_id != workspace.program_id:
        raise ValueError("workspace, agenda, and scientific state must belong to one program")
    evidence_ids = {item.evidence_id for item in state.evidence}
    hypothesis_ids = {state.hypothesis.hypothesis_id}
    risk_ids = {item.risk_id for item in state.risks}
    decision_ids = {state.decision.decision_id}
    agenda_ids = {item.agenda_item_id for item in agenda.items}

    def validate_links(links) -> None:
        if set(links.hypothesis_ids) - hypothesis_ids:
            raise ValueError("workspace links unknown hypotheses")
        if set(links.risk_ids) - risk_ids:
            raise ValueError("workspace links unknown risks")
        if set(links.decision_ids) - decision_ids:
            raise ValueError("workspace links unknown decisions")
        if set(links.agenda_item_ids) - agenda_ids:
            raise ValueError("workspace links unknown agenda items")
        for action in links.next_actions:
            if set(action.linked_hypothesis_ids) - hypothesis_ids:
                raise ValueError("workspace action links unknown hypotheses")
            if set(action.linked_risk_ids) - risk_ids:
                raise ValueError("workspace action links unknown risks")
            if set(action.linked_decision_ids) - decision_ids:
                raise ValueError("workspace action links unknown decisions")
            if set(action.linked_agenda_item_ids) - agenda_ids:
                raise ValueError("workspace action links unknown agenda items")

    for links in (workspace.cargo.links, workspace.formulation.links, workspace.jurisdictions.links):
        validate_links(links)
    cargo_evidence = {
        evidence_id
        for candidate in workspace.cargo.candidates
        for evidence_id in candidate.evidence_ids
    } | {link.evidence_id for link in workspace.cargo.evidence_links}
    formulation_evidence = {
        evidence_id
        for candidate in workspace.formulation.candidates
        for evidence_id in candidate.evidence_ids
    } | {
        evidence_id
        for excipient in workspace.formulation.excipients
        for evidence_id in excipient.evidence_ids
    }
    if (cargo_evidence | formulation_evidence) - evidence_ids:
        raise ValueError("workspace references unknown scientific evidence")
    if workspace.manufacturing:
        if workspace.manufacturing.program_id != workspace.program_id:
            raise ValueError("manufacturing belongs to another program")
        refs = []
        manufacturing = workspace.manufacturing
        refs.extend([manufacturing.product_definition.refs, manufacturing.potency_strategy.refs])
        refs.extend(item.refs for group in (
            manufacturing.process_stages, manufacturing.quality_attributes,
            manufacturing.test_methods, manufacturing.specifications,
            manufacturing.test_results, manufacturing.lots,
            manufacturing.stability_programs, manufacturing.readiness,
            manufacturing.risks, manufacturing.next_actions,
        ) for item in group)
        if any(set(ref.evidence_ids) - evidence_ids for ref in refs):
            raise ValueError("manufacturing references unknown scientific evidence")
        if any(set(ref.claim_ids) - {item.claim_id for item in state.claims} for ref in refs):
            raise ValueError("manufacturing references unknown scientific claims")
        if any(set(ref.risk_ids) - risk_ids for ref in refs):
            raise ValueError("manufacturing references unknown risks")
        if any(set(ref.decision_ids) - decision_ids for ref in refs):
            raise ValueError("manufacturing references unknown decisions")
        if any(set(ref.agenda_item_ids) - agenda_ids for ref in refs):
            raise ValueError("manufacturing references unknown agenda items")


def _action(value: DevelopmentAction) -> PublicDomainAction:
    return PublicDomainAction(
        actionId=value.action_id,
        action=value.action,
        objective=value.objective,
        uncertainty=value.uncertainty,
        successCriteria=value.success_criteria,
        status=value.status,
        requiresHumanApproval=value.requires_human_approval,
    )


def export_workspace(workspace: TherapeuticAssetWorkspace):
    pathway_counts = {
        pathway.pathway_id: len(
            {
                link.cargo_candidate_id
                for link in workspace.cargo.pathway_links
                if link.pathway_id == pathway.pathway_id
            }
        )
        for pathway in workspace.cargo.pathways
    }
    cargo = PublicCargoState(
        operatorFocusCandidateIds=workspace.cargo.operator_focus_candidate_ids,
        rankingMethodology=workspace.cargo.ranking_methodology,
        candidates=[
            PublicCargoCandidate(
                id=item.cargo_candidate_id,
                name=item.name,
                cargoType=item.cargo_type.value,
                source=item.source,
                mechanism=item.mechanism,
                pathwayIds=item.target_pathway_ids,
                relevantTissues=item.relevant_tissues,
                evidenceIds=item.evidence_ids,
                supportiveEvidenceIds=item.supportive_evidence_ids,
                contradictoryEvidenceIds=item.contradictory_evidence_ids,
                evidenceLevel=item.evidence_level,
                evidenceRank=item.evidence_rank,
                rationale=item.rationale,
                status=item.development_status,
                exclusionReason=item.exclusion_reason,
                uncertainty=item.uncertainty,
                biologicalTargets=item.biological_targets,
                evidenceAnnotation=item.evidence_annotation,
                sourceCitation=item.source_citation,
                contextDependent=item.context_dependent,
            )
            for item in workspace.cargo.candidates
        ],
        pathways=[
            PublicPathway(
                id=item.pathway_id,
                name=item.name,
                description=item.description,
                candidateCount=pathway_counts[item.pathway_id],
                evidenceIds=item.evidence_ids,
            )
            for item in workspace.cargo.pathways
        ],
        candidatePathwayLinks=[
            PublicCargoPathwayLink(
                candidateId=item.cargo_candidate_id,
                pathwayId=item.pathway_id,
                evidenceIds=item.evidence_ids,
            )
            for item in workspace.cargo.pathway_links
        ],
        filters={
            "cargoTypes": sorted({item.cargo_type.value for item in workspace.cargo.candidates}),
            "statuses": sorted({item.development_status.value for item in workspace.cargo.candidates}),
            "tissues": sorted(
                {tissue for item in workspace.cargo.candidates for tissue in item.relevant_tissues}
            ),
        },
        focusCandidates=workspace.cargo.operator_focus_candidate_ids,
        benchmarks=[
            item.cargo_candidate_id
            for item in workspace.cargo.candidates
            if item.development_status.value == "benchmark"
        ],
        nextActions=[_action(item) for item in workspace.cargo.links.next_actions],
        theoreticalMoa=PublicTheoreticalMoa(
            title="Theoretical SGL-001 mechanism of action",
            subtitle="From manufactured cargo to a proposed regenerative tissue response",
            disclaimer=(
                "This is a testable mechanism hypothesis, not an established SGL-001 mechanism. "
                "Each transition must be demonstrated experimentally for the final product."
            ),
            steps=[
                PublicMoaStep(
                    step=1, phase="Product identity", title="Reproducible miRNA cargo",
                    description="A manufactured SGL-001 lot contains a defined and reproducible miRNA signature.",
                    evidenceStatus="Unconfirmed for SGL-001",
                    validationGate="Quantify absolute miRNA copies across multiple released lots.",
                ),
                PublicMoaStep(
                    step=2, phase="Product identity", title="Functional EV association",
                    description="Candidate miRNA is protected within functional EVs rather than free, degraded, or co-isolated material.",
                    evidenceStatus="Unconfirmed for SGL-001",
                    validationGate="Demonstrate vesicular localization with orthogonal separation and protection assays.",
                ),
                PublicMoaStep(
                    step=3, phase="Delivery", title="Intranasal exposure",
                    description="The formulation remains stable after dosing and reaches a biologically relevant nasal or CNS target compartment.",
                    evidenceStatus="Translational gap",
                    validationGate="Measure biodistribution and exposure in a relevant large-animal model.",
                ),
                PublicMoaStep(
                    step=4, phase="Delivery", title="Target-cell uptake",
                    description="Relevant recipient cells internalize SGL-001 EVs or their active cargo.",
                    evidenceStatus="Plausible; product-specific evidence absent",
                    validationGate="Show cell-specific uptake using traceable, artifact-controlled methods.",
                ),
                PublicMoaStep(
                    step=5, phase="Intracellular action", title="Endosomal escape",
                    description="Internalized miRNA reaches the cytoplasm instead of remaining trapped or being degraded.",
                    evidenceStatus="Critical untested assumption",
                    validationGate="Demonstrate cytosolic delivery and functional accessibility.",
                ),
                PublicMoaStep(
                    step=6, phase="Intracellular action", title="RISC engagement at sufficient dose",
                    description="Delivered miRNA loads into Argonaute/RISC at a concentration capable of regulating gene expression.",
                    evidenceStatus="Established general biology; unconfirmed for SGL-001",
                    validationGate="Measure Ago loading, intracellular copy number, and dose-response.",
                ),
                PublicMoaStep(
                    step=7, phase="Molecular effect", title="Direct target repression",
                    description="The engaged miRNA reduces a defined target mRNA or protein, such as a pathway inhibitor.",
                    evidenceStatus="Candidate-dependent",
                    validationGate="Confirm direct target engagement and rescue the effect by blocking the miRNA.",
                ),
                PublicMoaStep(
                    step=8, phase="Molecular effect", title="Pathway modulation",
                    description="Target repression changes a relevant signaling system such as PTEN/PI3K-AKT, NF-kB, or TGF-beta/SMAD.",
                    evidenceStatus="Hypothesis assembled from analog evidence",
                    validationGate="Measure pathway direction, magnitude, timing, and cell specificity.",
                ),
                PublicMoaStep(
                    step=9, phase="Biological outcome", title="Regenerative tissue response",
                    description="Pathway changes produce a reproducible phenotype such as neural plasticity, inflammatory resolution, or tissue repair.",
                    evidenceStatus="Not demonstrated for SGL-001",
                    validationGate="Link the phenotype causally to cargo, target, and pathway using loss-of-function controls.",
                ),
            ],
            exampleRoute=[
                "miR-133b cargo", "recipient-cell delivery", "RISC engagement",
                "RhoA / CTGF repression", "growth-inhibitory signaling reduced",
                "proposed neurite remodeling",
            ],
            conclusion=(
                "SGL-001 currently has a proposed multi-component paracrine mechanism. No specific miRNA, "
                "target, pathway, or clinical effect has yet been established as its mechanism of action."
            ),
        ),
    )

    formulation = PublicFormulationState(
        scoringMethodology=workspace.formulation.scoring_methodology,
        scoreDimensions=["mechanism", "evidence", "manufacturability", "regulatoryDeployment"],
        candidates=[
            PublicFormulationCandidate(
                id=item.formulation_candidate_id,
                name=item.name,
                modality=item.modality,
                activeCargoStrategy=item.active_cargo_strategy,
                route=item.route,
                score=PublicFormulationScore(
                    mechanism=item.score.mechanism,
                    evidence=item.score.evidence,
                    manufacturability=item.score.manufacturability,
                    regulatoryDeployment=item.score.regulatory_deployment,
                    totalScore=item.score.total_score,
                    methodology=item.score.methodology,
                ),
                status=item.status,
                rationale=item.rationale,
                tradeoffs=item.tradeoffs,
                evidenceIds=item.evidence_ids,
                exclusionReason=item.exclusion_reason,
                legacyScores=item.legacy_scores,
            )
            for item in workspace.formulation.candidates
        ],
        excipients=[
            PublicExcipientCandidate(
                id=item.excipient_candidate_id,
                name=item.name,
                functionalRole=item.functional_role,
                proposedConcentration=item.proposed_concentration,
                evCompatibility=item.ev_compatibility,
                intranasalPrecedent=item.intranasal_precedent,
                humanPrecedent=item.human_precedent,
                regulatoryPrecedent=item.regulatory_precedent,
                formulationValue=item.formulation_value,
                risk=item.risk,
                evidenceIds=item.evidence_ids,
                status=item.inclusion_status,
                precedentSummary=item.precedent_summary,
                tradeoff=item.tradeoff,
                legacyPrecedentStrength=item.legacy_precedent_strength,
                legacyEvStability=item.legacy_ev_stability,
            )
            for item in workspace.formulation.excipients
        ],
        presentations=[
            PublicPresentationCandidate(
                id=item.presentation_id,
                format=item.format,
                shelfLife=item.shelf_life,
                coldChain=item.cold_chain,
                userSteps=item.user_steps,
                verdict=item.verdict,
                status=item.status,
            )
            for item in workspace.formulation.presentations
        ],
        functionalRoleFilters=sorted(
            {item.functional_role for item in workspace.formulation.excipients}
        ),
        nextActions=[_action(item) for item in workspace.formulation.links.next_actions],
    )

    counts = {verdict: 0 for verdict in ("viable", "grey", "restrictive", "prohibited", "unresolved")}
    for item in workspace.jurisdictions.jurisdictions:
        counts[item.verdict.value] += 1
    jurisdictions = PublicJurisdictionState(
        disclaimer=workspace.jurisdictions.disclaimer,
        summaryCounts=counts,
        jurisdictions=[
            PublicJurisdictionCard(
                id=item.jurisdiction_id,
                jurisdiction=item.jurisdiction,
                country=item.country,
                region=item.region,
                verdict=item.verdict,
                enforcementIntensity=item.enforcement_intensity,
                confidence=item.evidence_confidence,
                priority=item.priority,
                productClassification=item.product_classification,
                privateClinicPath=item.private_clinic_path,
                conciseRationale=item.concise_rationale,
                sourceDocumentIds=item.source_document_ids,
                unresolvedQuestions=item.unresolved_questions,
                nextAction=_action(item.next_action),
                verificationStatus=item.verification_status.value,
                legacyPriorityRank=item.legacy_priority_rank,
                permittedActivities=item.permitted_activities,
                greyAreas=item.grey_areas,
                prohibitedActivities=item.prohibited_activities,
            )
            for item in workspace.jurisdictions.jurisdictions
        ],
        nextActions=[_action(item) for item in workspace.jurisdictions.links.next_actions],
    )
    return cargo, formulation, jurisdictions
