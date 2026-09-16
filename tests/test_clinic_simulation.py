from datetime import date

import pytest

from signalai.clinic_simulation import advance_simulation, export_clinic_simulation, load_simulation
from signalai.schemas.clinic_simulation import SimulationDeterminationType


def test_simulation_is_synthetic_isolated_and_reproducible(tmp_path) -> None:
    state = advance_simulation(tmp_path, simulated_date=date(2026, 9, 16))
    assert state.data_classification == "synthetic_demo_only"
    assert "NOT CLINICAL DATA" in state.disclaimer
    assert state.protocol.program_id == "SGL-001"
    assert state.protocol.dose.startswith("Simulation token")
    assert len(state.days) == 1
    assert len(state.days[0].observations) == 6
    assert (tmp_path / "state" / "clinic-simulation.json").exists()
    assert len(list((tmp_path / "simulation-runs").iterdir())) == 1
    assert not (tmp_path / "state" / "signal-state.json").exists()
    loaded = load_simulation(tmp_path / "state" / "clinic-simulation.json")
    assert loaded == state
    public = export_clinic_simulation(loaded)
    assert public.total_simulated_days == 1
    assert public.latest_day == state.days[0]


def test_simulation_rejects_duplicate_or_reverse_dates(tmp_path) -> None:
    advance_simulation(tmp_path, simulated_date=date(2026, 9, 16))
    with pytest.raises(ValueError, match="already exists"):
        advance_simulation(tmp_path, simulated_date=date(2026, 9, 16))
    with pytest.raises(ValueError, match="must follow"):
        advance_simulation(tmp_path, simulated_date=date(2026, 9, 15))


def test_generated_observations_never_claim_clinical_evidence(tmp_path) -> None:
    state = advance_simulation(tmp_path, simulated_date=date(2026, 9, 16))
    day = state.days[0]
    assert day.determination.determination_type in set(SimulationDeterminationType)
    assert "canonical SGL-001 state" in day.review.chair_rationale
    assert "cannot establish safety, efficacy" in day.review.adversary_objection
    assert all("Synthetic" in item.note for item in day.observations)
