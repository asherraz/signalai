"""Strict contracts for the fictional SGL-001 clinic demonstration."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from signalai.schemas.models import Identifier, NonEmptyText, SignalModel, _require_timezone


class SimulationDeterminationType(StrEnum):
    NO_MATERIAL_CHANGE = "no_material_change"
    HUMAN_DECISION_REQUIRED = "human_decision_required"
    EVIDENCE_GAP = "evidence_gap"
    BLOCKED = "blocked"


class SyntheticParticipant(SignalModel):
    participant_id: Identifier
    cohort: NonEmptyText
    status: Literal["active", "paused", "completed", "withdrawn"] = "active"


class SyntheticObservation(SignalModel):
    observation_id: Identifier
    participant_id: Identifier
    protocol_day: int = Field(ge=1)
    adherence: Literal["recorded", "missed", "not_assessed"]
    nasal_tolerability_score: int | None = Field(default=None, ge=0, le=10)
    cognitive_task_index: int | None = Field(default=None, ge=0, le=100)
    reported_wellbeing_score: int | None = Field(default=None, ge=0, le=10)
    synthetic_safety_flag: Literal["none", "review", "pause"] = "none"
    note: NonEmptyText


class SimulationReview(SignalModel):
    operations_finding: NonEmptyText
    safety_finding: NonEmptyText
    data_quality_finding: NonEmptyText
    adversary_objection: NonEmptyText
    chair_rationale: NonEmptyText


class SimulationDetermination(SignalModel):
    determination_type: SimulationDeterminationType
    summary: NonEmptyText
    protocol_state_changed: bool
    human_review_required: bool
    next_action: NonEmptyText


class SyntheticProtocolDay(SignalModel):
    run_id: Identifier
    simulated_date: date
    protocol_day: int = Field(ge=1)
    observations: list[SyntheticObservation]
    review: SimulationReview
    determination: SimulationDetermination
    generated_at: datetime

    @model_validator(mode="after")
    def validate_day(self):
        object.__setattr__(self, "generated_at", _require_timezone(self.generated_at, "generated_at"))
        if len({item.observation_id for item in self.observations}) != len(self.observations):
            raise ValueError("observation IDs must be unique")
        return self


class SyntheticClinicProtocol(SignalModel):
    protocol_id: Identifier = "demo-protocol-SGL-001"
    title: NonEmptyText = "Fictional SGL-001 intranasal secretome protocol simulation"
    program_id: Identifier = "SGL-001"
    status: Literal["simulation_only"] = "simulation_only"
    intervention: NonEmptyText = "Fictional intranasal SGL-001 secretome nasal-spray scenario"
    dose: NonEmptyText = "Simulation token only; no clinical dose is specified"
    purpose: NonEmptyText = "Demonstrate Signal review, provenance, escalation, and protocol-state handling"


class ClinicSimulationState(SignalModel):
    simulation_id: Identifier = "clinic-simulation-SGL-001"
    data_classification: Literal["synthetic_demo_only"] = "synthetic_demo_only"
    disclaimer: NonEmptyText = (
        "SIMULATED — NOT CLINICAL DATA. SGL-001 is preclinical and has not been administered "
        "to these fictional participants. This demo must not inform medical or development decisions."
    )
    clinic_name: NonEmptyText = "Signal Demonstration Clinic (fictional)"
    protocol: SyntheticClinicProtocol = Field(default_factory=SyntheticClinicProtocol)
    participants: list[SyntheticParticipant]
    days: list[SyntheticProtocolDay] = Field(default_factory=list)
    updated_at: datetime

    @model_validator(mode="after")
    def validate_state(self):
        object.__setattr__(self, "updated_at", _require_timezone(self.updated_at, "updated_at"))
        participant_ids = {item.participant_id for item in self.participants}
        if len(participant_ids) != len(self.participants):
            raise ValueError("participant IDs must be unique")
        if any(obs.participant_id not in participant_ids for day in self.days for obs in day.observations):
            raise ValueError("observations must reference synthetic participants")
        dates = [item.simulated_date for item in self.days]
        if dates != sorted(dates) or len(dates) != len(set(dates)):
            raise ValueError("simulation dates must be unique and chronological")
        if [item.protocol_day for item in self.days] != list(range(1, len(self.days) + 1)):
            raise ValueError("protocol days must be contiguous")
        return self


class PublicClinicSimulation(SignalModel):
    simulation_id: Identifier = Field(alias="simulationId")
    data_classification: Literal["synthetic_demo_only"] = Field(alias="dataClassification")
    disclaimer: NonEmptyText
    clinic_name: NonEmptyText = Field(alias="clinicName")
    protocol: SyntheticClinicProtocol
    participants: list[SyntheticParticipant]
    latest_day: SyntheticProtocolDay | None = Field(default=None, alias="latestDay")
    recent_days: list[SyntheticProtocolDay] = Field(default_factory=list, alias="recentDays")
    total_simulated_days: int = Field(ge=0, alias="totalSimulatedDays")
    updated_at: datetime = Field(alias="updatedAt")

    @model_validator(mode="after")
    def validate_public(self):
        object.__setattr__(self, "updated_at", _require_timezone(self.updated_at, "updated_at"))
        return self
