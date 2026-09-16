"""Sanitized frontend projection of canonical Manufacturing/CMC state."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from signalai.schemas.manufacturing import ManufacturingApprovalState, ManufacturingStateLevel
from signalai.schemas.models import Identifier, SignalModel, _require_timezone


class PublicManufacturingRefs(SignalModel):
    evidence_ids: list[Identifier] = Field(default_factory=list, alias="evidenceIds")
    claim_ids: list[Identifier] = Field(default_factory=list, alias="claimIds")
    risk_ids: list[Identifier] = Field(default_factory=list, alias="riskIds")
    decision_ids: list[Identifier] = Field(default_factory=list, alias="decisionIds")
    agenda_item_ids: list[Identifier] = Field(default_factory=list, alias="agendaItemIds")
    matter_ids: list[Identifier] = Field(default_factory=list, alias="matterIds")
    run_ids: list[Identifier] = Field(default_factory=list, alias="runIds")


class PublicProductDefinition(SignalModel):
    id: Identifier
    route: str
    biological_concept: str = Field(alias="biologicalConcept")
    ev_fraction_role: str = Field(alias="evFractionRole")
    drug_substance_identity: str | None = Field(alias="drugSubstanceIdentity")
    purification_fractionation_state: str | None = Field(alias="purificationFractionationState")
    dose_definition: str | None = Field(alias="doseDefinition")
    vehicle_stabilizer: str | None = Field(alias="vehicleStabilizer")
    state: ManufacturingStateLevel
    unresolved_decisions: list[str] = Field(alias="unresolvedDecisions")
    refs: PublicManufacturingRefs


class PublicManufacturingItem(SignalModel):
    id: Identifier
    name: str
    state: ManufacturingStateLevel
    summary: str | None = None
    missing_information: list[str] = Field(default_factory=list, alias="missingInformation")
    refs: PublicManufacturingRefs


class PublicReadinessItem(SignalModel):
    id: Identifier
    dimension: str
    state: ManufacturingStateLevel
    rationale: str
    refs: PublicManufacturingRefs


class PublicManufacturingRisk(SignalModel):
    id: Identifier
    title: str
    description: str
    mitigation: str
    owner: str | None = None
    state: ManufacturingStateLevel
    refs: PublicManufacturingRefs


class PublicManufacturingAction(SignalModel):
    id: Identifier
    action: str
    status: ManufacturingApprovalState
    requires_human_approval: bool = Field(alias="requiresHumanApproval")
    refs: PublicManufacturingRefs


class PublicPotencyStatus(SignalModel):
    state: ManufacturingStateLevel
    strategy: str
    particle_count_is_established_potency: bool = Field(alias="particleCountIsEstablishedPotency")
    validated_acceptance_criteria: bool = Field(alias="validatedAcceptanceCriteria")
    gaps: list[str]
    latest_determination_run_id: Identifier | None = Field(alias="latestDeterminationRunId")
    latest_determination_id: Identifier | None = Field(alias="latestDeterminationId")
    prior_state_preserved: bool | None = Field(alias="priorStatePreserved")
    refs: PublicManufacturingRefs


class PublicManufacturingCounts(SignalModel):
    real_lots: int = Field(alias="realLots")
    test_results: int = Field(alias="testResults")
    proposed_specifications: int = Field(alias="proposedSpecifications")
    approved_release_specifications: int = Field(alias="approvedReleaseSpecifications")
    validated_potency_assays: int = Field(alias="validatedPotencyAssays")
    stability_programs: int = Field(alias="stabilityPrograms")
    verified_shelf_life_records: int = Field(alias="verifiedShelfLifeRecords")
    coa_records: int = Field(alias="coaRecords")


class PublicVerifiedLot(SignalModel):
    lot_id: Identifier = Field(alias="lotId")
    process_version: str = Field(alias="processVersion")
    manufacture_date: str = Field(alias="manufactureDate")
    material_type: str = Field(alias="materialType")
    release_disposition: str = Field(alias="releaseDisposition")


class PublicVerifiedCoa(SignalModel):
    coa_id: Identifier = Field(alias="coaId")
    lot_id: Identifier = Field(alias="lotId")
    version: str
    release_disposition: str = Field(alias="releaseDisposition")


class PublicManufacturingState(SignalModel):
    program_id: Identifier = Field(alias="programId")
    product_definition: PublicProductDefinition = Field(alias="productDefinition")
    process_stages: list[PublicManufacturingItem] = Field(alias="processStages")
    quality_attributes: list[PublicManufacturingItem] = Field(alias="qualityAttributes")
    potency: PublicPotencyStatus
    readiness: list[PublicReadinessItem]
    risks: list[PublicManufacturingRisk]
    next_actions: list[PublicManufacturingAction] = Field(alias="nextActions")
    latest_relevant_determination_id: Identifier | None = Field(alias="latestRelevantDeterminationId")
    verified_public_lots: list[PublicVerifiedLot] = Field(default_factory=list, alias="verifiedPublicLots")
    verified_public_coas: list[PublicVerifiedCoa] = Field(default_factory=list, alias="verifiedPublicCoas")
    stability_status: ManufacturingStateLevel = Field(alias="stabilityStatus")
    counts: PublicManufacturingCounts
    last_meaningful_update: datetime = Field(alias="lastMeaningfulUpdate")

    @model_validator(mode="after")
    def validate_update(self):
        object.__setattr__(self, "last_meaningful_update", _require_timezone(self.last_meaningful_update, "last_meaningful_update"))
        return self


class PublicFlagshipManufacturingSummary(SignalModel):
    product_definition_state: ManufacturingStateLevel = Field(alias="productDefinitionState")
    potency_state: ManufacturingStateLevel = Field(alias="potencyState")
    reproducibility_state: ManufacturingStateLevel = Field(alias="reproducibilityState")
    stability_state: ManufacturingStateLevel = Field(alias="stabilityState")
    primary_cmc_blocker: str = Field(alias="primaryCmcBlocker")
    next_manufacturing_action: str = Field(alias="nextManufacturingAction")
    latest_relevant_determination_id: Identifier | None = Field(alias="latestRelevantDeterminationId")
