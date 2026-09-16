"""Public-safe Manufacturing/CMC serialization."""

from signalai.schemas.manufacturing import ManufacturingApprovalState, ManufacturingState, ManufacturingStateLevel
from signalai.schemas.public_manufacturing import (
    PublicFlagshipManufacturingSummary, PublicManufacturingAction,
    PublicManufacturingCounts, PublicManufacturingItem, PublicManufacturingRefs,
    PublicManufacturingRisk, PublicManufacturingState, PublicPotencyStatus,
    PublicProductDefinition, PublicReadinessItem,
    PublicVerifiedCoa, PublicVerifiedLot,
)


def _refs(value):
    return PublicManufacturingRefs(evidenceIds=value.evidence_ids, claimIds=value.claim_ids,
        riskIds=value.risk_ids, decisionIds=value.decision_ids, agendaItemIds=value.agenda_item_ids,
        matterIds=value.matter_ids, runIds=value.run_ids)


def export_manufacturing(value: ManufacturingState) -> PublicManufacturingState:
    p = value.product_definition
    readiness = {item.readiness_id.removeprefix("readiness-"): item.state for item in value.readiness}
    latest = value.potency_strategy.latest_determination_run_id
    return PublicManufacturingState(
        programId=value.program_id,
        productDefinition=PublicProductDefinition(id=p.product_definition_id, route=p.route,
            biologicalConcept=p.biological_concept, evFractionRole=p.ev_fraction_role,
            drugSubstanceIdentity=p.drug_substance_identity,
            purificationFractionationState=p.purification_fractionation_state,
            doseDefinition=p.dose_definition, vehicleStabilizer=p.vehicle_stabilizer,
            state=p.state, unresolvedDecisions=p.unresolved_decisions, refs=_refs(p.refs)),
        processStages=[PublicManufacturingItem(id=item.process_stage_id, name=item.name,
            state=item.state, summary=item.current_definition,
            missingInformation=item.missing_information, refs=_refs(item.refs)) for item in value.process_stages],
        qualityAttributes=[PublicManufacturingItem(id=item.quality_attribute_id, name=item.name,
            state=item.state, summary=item.target,
            missingInformation=[] if item.numeric_acceptance_limits_defined else ["Numeric acceptance limits are not defined."],
            refs=_refs(item.refs)) for item in value.quality_attributes],
        potency=PublicPotencyStatus(state=value.potency_strategy.state,
            strategy=value.potency_strategy.strategy,
            particleCountIsEstablishedPotency=value.potency_strategy.particle_count_is_established_potency,
            validatedAcceptanceCriteria=value.potency_strategy.validated_acceptance_criteria,
            gaps=value.potency_strategy.gaps, latestDeterminationRunId=latest,
            latestDeterminationId=value.potency_strategy.latest_determination_id,
            priorStatePreserved=value.potency_strategy.prior_state_preserved,
            refs=_refs(value.potency_strategy.refs)),
        readiness=[PublicReadinessItem(id=item.readiness_id, dimension=item.dimension,
            state=item.state, rationale=item.rationale, refs=_refs(item.refs)) for item in value.readiness],
        risks=[PublicManufacturingRisk(id=item.risk_id, title=item.title,
            description=item.description, mitigation=item.mitigation, owner=item.owner,
            state=item.state, refs=_refs(item.refs)) for item in value.risks],
        nextActions=[PublicManufacturingAction(id=item.action_id, action=item.action,
            status=item.status, requiresHumanApproval=item.requires_human_approval,
            refs=_refs(item.refs)) for item in value.next_actions],
        latestRelevantDeterminationId=value.potency_strategy.latest_determination_id,
        verifiedPublicLots=[PublicVerifiedLot(lotId=item.lot_id,
            processVersion=item.process_version, manufactureDate=item.manufacture_date.isoformat(),
            materialType=item.material_type, releaseDisposition=item.release_disposition)
            for item in value.lots if item.manufacturing_state is ManufacturingStateLevel.VERIFIED
            and item.testing_state is ManufacturingStateLevel.VERIFIED and item.release_disposition == "released"],
        verifiedPublicCoas=[PublicVerifiedCoa(coaId=item.coa_id, lotId=item.lot_id,
            version=item.version, releaseDisposition=item.release_disposition)
            for item in value.coa_records if item.approval_state is ManufacturingApprovalState.APPROVED],
        stabilityStatus=readiness.get("stability-program", ManufacturingStateLevel.NOT_ASSESSED),
        counts=PublicManufacturingCounts(realLots=len(value.lots), testResults=len(value.test_results),
            proposedSpecifications=sum(x.approval_state is ManufacturingApprovalState.PROPOSED for x in value.specifications),
            approvedReleaseSpecifications=sum(x.approval_state is ManufacturingApprovalState.APPROVED for x in value.specifications),
            validatedPotencyAssays=sum(x.validation_status is ManufacturingStateLevel.VERIFIED and "potency" in x.purpose.casefold() for x in value.test_methods),
            stabilityPrograms=len(value.stability_programs),
            verifiedShelfLifeRecords=sum(x.shelf_life_state is ManufacturingStateLevel.VERIFIED for x in value.stability_programs),
            coaRecords=len(value.coa_records)),
        lastMeaningfulUpdate=value.updated_at,
    )


def export_flagship_manufacturing(value: ManufacturingState) -> PublicFlagshipManufacturingSummary:
    readiness = {item.readiness_id.removeprefix("readiness-"): item.state for item in value.readiness}
    return PublicFlagshipManufacturingSummary(
        productDefinitionState=value.product_definition.state,
        potencyState=value.potency_strategy.state,
        reproducibilityState=readiness["lot-reproducibility"],
        stabilityState=readiness["stability-program"],
        primaryCmcBlocker=value.risks[0].title if value.risks else "No canonical CMC blocker recorded.",
        nextManufacturingAction=value.next_actions[0].action if value.next_actions else "No manufacturing action recorded.",
        latestRelevantDeterminationId=value.potency_strategy.latest_determination_id,
    )
