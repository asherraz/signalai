"""Canonical Manufacturing/CMC records for therapeutic assets."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from signalai.schemas.models import Identifier, NonEmptyText, SignalModel, _require_timezone

LiteralReleaseDisposition = Literal["not_assessed", "pending", "released", "rejected"]


class ManufacturingStateLevel(StrEnum):
    NOT_DEFINED = "not_defined"
    PROPOSED = "proposed"
    IN_DEVELOPMENT = "in_development"
    PARTIALLY_SUPPORTED = "partially_supported"
    EVIDENCE_GAP = "evidence_gap"
    HUMAN_DECISION_REQUIRED = "human_decision_required"
    BLOCKED = "blocked"
    VERIFIED = "verified"
    NOT_ASSESSED = "not_assessed"


class ManufacturingApprovalState(StrEnum):
    PROPOSED = "proposed"
    PENDING_HUMAN_DECISION = "pending_human_decision"
    APPROVED = "approved"
    REJECTED = "rejected"


class ManufacturingRefs(SignalModel):
    evidence_ids: list[Identifier] = Field(default_factory=list)
    claim_ids: list[Identifier] = Field(default_factory=list)
    risk_ids: list[Identifier] = Field(default_factory=list)
    decision_ids: list[Identifier] = Field(default_factory=list)
    agenda_item_ids: list[Identifier] = Field(default_factory=list)
    matter_ids: list[Identifier] = Field(default_factory=list)
    run_ids: list[Identifier] = Field(default_factory=list)


class ProductDefinition(SignalModel):
    product_definition_id: Identifier
    program_id: Identifier
    route: NonEmptyText
    biological_concept: NonEmptyText
    ev_fraction_role: NonEmptyText
    drug_substance_identity: str | None = None
    purification_fractionation_state: str | None = None
    dose_definition: str | None = None
    vehicle_stabilizer: str | None = None
    state: ManufacturingStateLevel
    unresolved_decisions: list[NonEmptyText] = Field(default_factory=list)
    refs: ManufacturingRefs


class ProcessStage(SignalModel):
    process_stage_id: Identifier
    name: NonEmptyText
    sequence: int = Field(ge=1)
    state: ManufacturingStateLevel
    current_definition: str | None = None
    missing_information: list[NonEmptyText] = Field(default_factory=list)
    refs: ManufacturingRefs = Field(default_factory=ManufacturingRefs)


class QualityAttribute(SignalModel):
    quality_attribute_id: Identifier
    name: NonEmptyText
    target: str | None = None
    state: ManufacturingStateLevel
    proposed_requirements: list[NonEmptyText] = Field(default_factory=list)
    numeric_acceptance_limits_defined: bool = False
    refs: ManufacturingRefs

    @model_validator(mode="after")
    def verified_requires_defined_limits(self):
        if self.state is ManufacturingStateLevel.VERIFIED and not self.numeric_acceptance_limits_defined:
            raise ValueError("verified quality attributes require defined numeric acceptance limits")
        return self


class PotencyStrategy(SignalModel):
    potency_strategy_id: Identifier
    state: ManufacturingStateLevel
    strategy: NonEmptyText
    particle_count_is_established_potency: bool = False
    validated_acceptance_criteria: bool = False
    gaps: list[NonEmptyText] = Field(default_factory=list)
    latest_determination_run_id: Identifier | None = None
    latest_determination_id: Identifier | None = None
    prior_state_preserved: bool | None = None
    refs: ManufacturingRefs

    @model_validator(mode="after")
    def protect_potency_semantics(self):
        if self.particle_count_is_established_potency:
            raise ValueError("particle count cannot be represented as established SGL-001 potency")
        if self.state is ManufacturingStateLevel.VERIFIED and not self.validated_acceptance_criteria:
            raise ValueError("verified potency requires validated acceptance criteria")
        return self


class TestMethod(SignalModel):
    method_id: Identifier
    name: NonEmptyText
    purpose: NonEmptyText
    state: ManufacturingStateLevel
    validation_status: ManufacturingStateLevel = ManufacturingStateLevel.NOT_ASSESSED
    proprietary_details: dict[str, str] = Field(default_factory=dict)
    refs: ManufacturingRefs


class Specification(SignalModel):
    specification_id: Identifier
    name: NonEmptyText
    version: NonEmptyText
    approval_state: ManufacturingApprovalState
    method_ids: list[Identifier] = Field(default_factory=list)
    acceptance_criteria: list[NonEmptyText] = Field(default_factory=list)
    refs: ManufacturingRefs

    @model_validator(mode="after")
    def approval_requires_criteria(self):
        if self.approval_state is ManufacturingApprovalState.APPROVED and not self.acceptance_criteria:
            raise ValueError("approved specification requires acceptance criteria")
        return self


class ManufacturingLot(SignalModel):
    lot_id: Identifier
    process_version: NonEmptyText
    manufacture_date: date
    material_type: NonEmptyText
    manufacturing_state: ManufacturingStateLevel
    testing_state: ManufacturingStateLevel
    release_disposition: LiteralReleaseDisposition = "not_assessed"
    deviations: list[NonEmptyText] = Field(default_factory=list)
    comparability_state: ManufacturingStateLevel = ManufacturingStateLevel.NOT_ASSESSED
    stability_program_ids: list[Identifier] = Field(default_factory=list)
    refs: ManufacturingRefs

    @model_validator(mode="after")
    def provenance_required(self):
        if not (self.refs.evidence_ids or self.refs.run_ids):
            raise ValueError("manufacturing lot requires traceable provenance")
        return self


class TestResult(SignalModel):
    result_id: Identifier
    lot_id: Identifier
    method_id: Identifier
    specification_id: Identifier | None = None
    attribute: NonEmptyText
    value: NonEmptyText
    unit: str | None = None
    tested_at: datetime
    disposition: str | None = None
    refs: ManufacturingRefs

    @model_validator(mode="after")
    def validate_time(self):
        object.__setattr__(self, "tested_at", _require_timezone(self.tested_at, "tested_at"))
        if not (self.refs.evidence_ids or self.refs.run_ids):
            raise ValueError("test result requires traceable provenance")
        return self


class StabilityTimepoint(SignalModel):
    timepoint_id: Identifier
    label: NonEmptyText
    result_ids: list[Identifier] = Field(default_factory=list)
    excursion: str | None = None


class StabilityProgram(SignalModel):
    stability_program_id: Identifier
    lot_ids: list[Identifier]
    state: ManufacturingStateLevel
    conditions: list[NonEmptyText] = Field(default_factory=list)
    attributes: list[NonEmptyText] = Field(default_factory=list)
    timepoints: list[StabilityTimepoint] = Field(default_factory=list)
    shelf_life_state: ManufacturingStateLevel = ManufacturingStateLevel.NOT_DEFINED
    verified_shelf_life: str | None = None
    refs: ManufacturingRefs

    @model_validator(mode="after")
    def verified_shelf_life_requires_value(self):
        if self.shelf_life_state is ManufacturingStateLevel.VERIFIED and not self.verified_shelf_life:
            raise ValueError("verified shelf life requires a recorded value")
        return self


class CoaRecord(SignalModel):
    coa_id: Identifier
    lot_id: Identifier
    version: NonEmptyText
    approval_state: ManufacturingApprovalState
    result_ids: list[Identifier] = Field(min_length=1)
    method_ids: list[Identifier] = Field(min_length=1)
    specification_ids: list[Identifier] = Field(min_length=1)
    release_disposition: LiteralReleaseDisposition
    source_record_ids: list[Identifier] = Field(min_length=1)


class ReadinessItem(SignalModel):
    readiness_id: Identifier
    dimension: NonEmptyText
    state: ManufacturingStateLevel
    rationale: NonEmptyText
    refs: ManufacturingRefs = Field(default_factory=ManufacturingRefs)


class ManufacturingRisk(SignalModel):
    risk_id: Identifier
    title: NonEmptyText
    description: NonEmptyText
    mitigation: NonEmptyText
    owner: str | None = None
    state: ManufacturingStateLevel
    refs: ManufacturingRefs


class ManufacturingNextAction(SignalModel):
    action_id: Identifier
    action: NonEmptyText
    status: ManufacturingApprovalState
    requires_human_approval: bool = True
    refs: ManufacturingRefs


class ManufacturingState(SignalModel):
    program_id: Identifier
    product_definition: ProductDefinition
    process_stages: list[ProcessStage]
    quality_attributes: list[QualityAttribute] = Field(default_factory=list)
    potency_strategy: PotencyStrategy
    test_methods: list[TestMethod] = Field(default_factory=list)
    specifications: list[Specification] = Field(default_factory=list)
    test_results: list[TestResult] = Field(default_factory=list)
    lots: list[ManufacturingLot] = Field(default_factory=list)
    stability_programs: list[StabilityProgram] = Field(default_factory=list)
    coa_records: list[CoaRecord] = Field(default_factory=list)
    readiness: list[ReadinessItem]
    risks: list[ManufacturingRisk] = Field(default_factory=list)
    next_actions: list[ManufacturingNextAction] = Field(default_factory=list)
    updated_at: datetime

    @model_validator(mode="after")
    def validate_graph(self):
        object.__setattr__(self, "updated_at", _require_timezone(self.updated_at, "updated_at"))
        collections = {
            "process stage": [x.process_stage_id for x in self.process_stages],
            "quality attribute": [x.quality_attribute_id for x in self.quality_attributes],
            "method": [x.method_id for x in self.test_methods],
            "specification": [x.specification_id for x in self.specifications],
            "result": [x.result_id for x in self.test_results],
            "lot": [x.lot_id for x in self.lots],
            "stability program": [x.stability_program_id for x in self.stability_programs],
            "COA": [x.coa_id for x in self.coa_records],
            "readiness": [x.readiness_id for x in self.readiness],
            "action": [x.action_id for x in self.next_actions],
        }
        for label, values in collections.items():
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} ID")
        lots, methods, specs, results = map(set, (collections["lot"], collections["method"], collections["specification"], collections["result"]))
        programs = {x.stability_program_id for x in self.stability_programs}
        result_map = {x.result_id: x for x in self.test_results}
        if any(set(spec.method_ids) - methods for spec in self.specifications):
            raise ValueError("specification references unknown methods")
        if any(x.lot_id not in lots or x.method_id not in methods or (x.specification_id and x.specification_id not in specs) for x in self.test_results):
            raise ValueError("test result references unknown lot, method, or specification")
        for stability in self.stability_programs:
            if set(stability.lot_ids) - lots or any(set(tp.result_ids) - results for tp in stability.timepoints):
                raise ValueError("stability program references unknown lots or results")
        if any(set(lot.stability_program_ids) - programs for lot in self.lots):
            raise ValueError("lot references unknown stability program")
        for coa in self.coa_records:
            if coa.lot_id not in lots or set(coa.result_ids) - results or set(coa.method_ids) - methods or set(coa.specification_ids) - specs:
                raise ValueError("COA references unknown lot, results, methods, or specifications")
            if any(result_map[result_id].lot_id != coa.lot_id for result_id in coa.result_ids):
                raise ValueError("COA cannot contain cross-lot results")
            if any(result_map[result_id].method_id not in coa.method_ids for result_id in coa.result_ids):
                raise ValueError("COA results must reference listed methods")
            if any(result_map[result_id].specification_id and result_map[result_id].specification_id not in coa.specification_ids for result_id in coa.result_ids):
                raise ValueError("COA results must reference listed specifications")
        return self
