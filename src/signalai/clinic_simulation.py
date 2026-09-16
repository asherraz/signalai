"""Deterministic, isolated fictional clinic simulation for the public demo."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from pathlib import Path

from signalai.schemas.clinic_simulation import (
    ClinicSimulationState, PublicClinicSimulation, SimulationDetermination,
    SimulationDeterminationType, SimulationReview, SyntheticObservation,
    SyntheticParticipant, SyntheticProtocolDay,
)
from signalai.storage import RunStore, new_run_id, publish_json


def _initial_state(now: datetime) -> ClinicSimulationState:
    return ClinicSimulationState(
        participants=[SyntheticParticipant(participant_id=f"SIM-{i:03d}", cohort="fictional-demo-cohort") for i in range(1, 7)],
        updated_at=now,
    )


def load_simulation(path: Path, *, now: datetime | None = None) -> ClinicSimulationState:
    if path.exists():
        return ClinicSimulationState.model_validate_json(path.read_text(encoding="utf-8"))
    return _initial_state(now or datetime.now(timezone.utc))


def _value(day: int, participant_id: str, label: str, modulus: int) -> int:
    digest = hashlib.sha256(f"{day}:{participant_id}:{label}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % modulus


def _observations(state: ClinicSimulationState, protocol_day: int) -> list[SyntheticObservation]:
    observations = []
    for participant in state.participants:
        missed = _value(protocol_day, participant.participant_id, "adherence", 19) == 0
        flag_value = _value(protocol_day, participant.participant_id, "safety", 41)
        # The autonomous demo may request human review but never invents a
        # severe clinical event or permanently blocks its own daily feed.
        safety_flag = "review" if flag_value in {0, 1, 2} else "none"
        observations.append(SyntheticObservation(
            observation_id=f"synthetic-observation-day-{protocol_day}-{participant.participant_id}",
            participant_id=participant.participant_id,
            protocol_day=protocol_day,
            adherence="missed" if missed else "recorded",
            nasal_tolerability_score=None if missed else _value(protocol_day, participant.participant_id, "tolerability", 4),
            cognitive_task_index=None if missed else 42 + _value(protocol_day, participant.participant_id, "cognitive", 17),
            reported_wellbeing_score=None if missed else 4 + _value(protocol_day, participant.participant_id, "wellbeing", 4),
            synthetic_safety_flag=safety_flag,
            note="Synthetic record withheld because the fictional visit was missed." if missed else "Synthetic demonstration observation; values are generated and are not clinical measurements.",
        ))
    return observations


def _review(observations: list[SyntheticObservation]) -> tuple[SimulationReview, SimulationDetermination]:
    missed = sum(item.adherence == "missed" for item in observations)
    pauses = sum(item.synthetic_safety_flag == "pause" for item in observations)
    reviews = sum(item.synthetic_safety_flag == "review" for item in observations)
    if pauses:
        kind, summary = SimulationDeterminationType.BLOCKED, "The fictional protocol is paused pending simulated human safety review."
        next_action, changed, human = "A human reviewer must resolve the synthetic pause flag before another protocol day is generated.", True, True
    elif reviews:
        kind, summary = SimulationDeterminationType.HUMAN_DECISION_REQUIRED, "Synthetic observations require human review; no efficacy or program conclusion is permitted."
        next_action, changed, human = "Review the flagged fictional observations and record a simulation-only disposition.", False, True
    elif missed >= 2:
        kind, summary = SimulationDeterminationType.EVIDENCE_GAP, "Missing synthetic observations prevent a complete daily interpretation."
        next_action, changed, human = "Record the fictional follow-up outcome; preserve the prior simulated protocol state.", False, False
    else:
        kind, summary = SimulationDeterminationType.NO_MATERIAL_CHANGE, "The synthetic day completed without a protocol-changing signal."
        next_action, changed, human = "Continue the fictional protocol schedule and generate the next synthetic day.", False, False
    review = SimulationReview(
        operations_finding=f"{len(observations) - missed} of {len(observations)} fictional daily records were complete.",
        safety_finding=f"Synthetic flags: {reviews} review and {pauses} pause; these are generated demo events.",
        data_quality_finding=f"{missed} synthetic records were missing.",
        adversary_objection="Generated observations cannot establish safety, efficacy, potency, exposure, or clinical feasibility for SGL-001.",
        chair_rationale="The determination is limited to operating the fictional demo and cannot update canonical SGL-001 state.",
    )
    return review, SimulationDetermination(determination_type=kind, summary=summary, protocol_state_changed=changed, human_review_required=human, next_action=next_action)


def advance_simulation(root: Path, *, simulated_date: date | None = None) -> ClinicSimulationState:
    now = datetime.now(timezone.utc)
    state_path = root / "state" / "clinic-simulation.json"
    state = load_simulation(state_path, now=now)
    target_date = simulated_date or now.date()
    if any(item.simulated_date == target_date for item in state.days):
        raise ValueError(f"a synthetic protocol day already exists for {target_date.isoformat()}")
    if state.days and target_date <= state.days[-1].simulated_date:
        raise ValueError("the next synthetic date must follow the latest simulated day")
    if state.days and state.days[-1].determination.determination_type == SimulationDeterminationType.BLOCKED:
        raise ValueError("the fictional protocol is blocked pending simulated human review")
    protocol_day = len(state.days) + 1
    run_id = new_run_id(now).replace("run-", "sim-run-", 1)
    observations = _observations(state, protocol_day)
    review, determination = _review(observations)
    day = SyntheticProtocolDay(run_id=run_id, simulated_date=target_date, protocol_day=protocol_day, observations=observations, review=review, determination=determination, generated_at=now)
    store = RunStore(root / "simulation-runs", run_id)
    store.write_json("00-simulation-input.json", {"simulationId": state.simulation_id, "simulatedDate": target_date.isoformat(), "protocolDay": protocol_day})
    store.write_json("01-synthetic-observations.json", observations)
    store.write_json("02-simulation-review.json", review)
    store.write_json("03-simulation-determination.json", determination)
    updated = state.model_copy(update={"days": [*state.days, day], "updated_at": now})
    publish_json(state_path, updated)
    store.write_json("99-simulation-complete.json", day)
    return updated


def export_clinic_simulation(state: ClinicSimulationState) -> PublicClinicSimulation:
    return PublicClinicSimulation(
        simulationId=state.simulation_id, dataClassification=state.data_classification,
        disclaimer=state.disclaimer, clinicName=state.clinic_name, protocol=state.protocol,
        participants=state.participants, latestDay=state.days[-1] if state.days else None,
        recentDays=list(reversed(state.days[-14:])), totalSimulatedDays=len(state.days), updatedAt=state.updated_at,
    )
