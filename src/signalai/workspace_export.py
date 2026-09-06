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
    PublicPathway,
    PublicPresentationCandidate,
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
