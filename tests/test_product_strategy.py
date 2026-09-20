import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from signalai.product_strategy import (
    ProductStrategyOrchestrator, initial_product_strategy, score_dimension,
    strategy_input_fingerprint,
)
from signalai.product_strategy_export import export_product_strategy
from signalai.publisher import build_current_public_state
from signalai.schemas.product_strategy import (
    ArchitectureDimension, AssessmentSourceType, DIMENSION_WEIGHTS,
    HardGateState, ProductStrategyWorkspace, StrategyAdversaryReview,
    StrategyCandidateInput, StrategyChairRecommendation, StrategyConfidence,
    StrategyDeterminationType, StrategySpecialistAssessment,
)
from signalai.storage import publish_json


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def prepare(tmp_path):
    for name in ("state", "runs", "public", "data", "design-runs", "simulation-runs"):
        source = ROOT / name
        if source.exists():
            shutil.copytree(source, tmp_path / name)
    (tmp_path / "strategy-runs").mkdir()
    workspace = initial_product_strategy(tmp_path, now=NOW)
    publish_json(tmp_path / "state/product-strategy.json", workspace)
    return tmp_path, workspace


class StrategyClient:
    def __init__(self):
        self.calls = []

    def generate(self, *, instructions, input_text, output_type):
        self.calls.append(output_type)
        payload = json.loads(input_text)
        if output_type is StrategySpecialistAssessment:
            role = instructions.split("Role: ")[-1]
            dimension = next(item for item in ArchitectureDimension if item.value.replace("_", " ") in instructions.casefold() or role)
            # Role names map one-to-one and arrive in enum order in the orchestrator.
            dimension = list(ArchitectureDimension)[sum(x is StrategySpecialistAssessment for x in self.calls) - 1]
            return StrategySpecialistAssessment(
                role=role, dimension=dimension,
                candidates=[StrategyCandidateInput(
                    candidate_id=item["candidate_id"], rating=item["dimension_assessments"][list(ArchitectureDimension).index(dimension)]["rating"],
                    confidence=item["dimension_assessments"][list(ArchitectureDimension).index(dimension)]["confidence"],
                    evidence_status="No new candidate-specific evidence.",
                    rationale="Retain the conservative source-bounded assessment.",
                    uncertainty="Candidate-specific evidence remains incomplete.",
                    evidence_ids=item["dimension_assessments"][list(ArchitectureDimension).index(dimension)]["evidence_ids"],
                    source_type="inference",
                ) for item in payload["candidates"]],
            )
        if output_type is StrategyAdversaryReview:
            return StrategyAdversaryReview(
                strongest_objection="Low-confidence assumptions and unresolved hard gates limit the ranking."
            )
        return StrategyChairRecommendation(
            determination="human_decision_required",
            recommended_candidate_id="sgl001-architecture-b",
            rationale="No autonomous lead change is justified.",
            changed_inputs=["Canonical upstream state changed; ratings remained conservative."],
            evidence_ids=[],
        )


def test_initial_five_candidates_and_deterministic_ranking():
    workspace = initial_product_strategy(ROOT, now=NOW)
    assert [item.designation for item in workspace.candidates] == [
        "SGL-001A", "SGL-001B", "SGL-001C", "SGL-001D", "SGL-001E"
    ]
    assert sum(workspace.dimension_weights.values()) == 100
    assert workspace.current_provisional_lead_candidate_id == "sgl001-architecture-a"
    assert workspace.latest_determination.proposed_ranking[0] == "sgl001-architecture-b"
    assert workspace.latest_determination.determination == "human_decision_required"
    assert all(g.status is HardGateState.UNRESOLVED for c in workspace.candidates for g in c.hard_gates)


def test_weight_rating_and_confidence_adjustment_are_deterministic():
    assessment = score_dimension(
        candidate_id="candidate", dimension=ArchitectureDimension.HUMAN_FEASIBILITY,
        rating=4, confidence=StrategyConfidence.MODERATE, evidence_status="Indirect",
        rationale="Bounded rationale", uncertainty="Uncertain", evidence_ids=[],
        source_type=AssessmentSourceType.INFERENCE,
    )
    assert assessment.potential_contribution == 16
    assert assessment.confidence_adjusted_contribution == 12
    payload = assessment.model_dump(mode="python")
    payload["rating"] = 6
    with pytest.raises(ValidationError):
        type(assessment).model_validate(payload)


def test_weights_must_total_canonical_100():
    workspace = initial_product_strategy(ROOT, now=NOW)
    payload = workspace.model_dump(mode="python")
    payload["dimension_weights"][ArchitectureDimension.SAFETY] = 19
    with pytest.raises(ValidationError, match="totaling 100"):
        ProductStrategyWorkspace.model_validate(payload)


def test_failed_gate_cannot_be_provisional_lead():
    candidate = initial_product_strategy(ROOT, now=NOW).candidates[0]
    gates = list(candidate.hard_gates)
    gates[0] = type(gates[0]).model_validate({
        **gates[0].model_dump(mode="python"), "status": "failed"
    })
    with pytest.raises(ValidationError, match="failed hard gate"):
        type(candidate).model_validate({**candidate.model_dump(mode="python"), "hard_gates": gates})


def test_public_strategy_is_sanitized_and_integrated():
    workspace = initial_product_strategy(ROOT, now=NOW)
    public = export_product_strategy(workspace).model_dump(mode="json", by_alias=True)
    assert public["candidateLeaderboard"]
    assert "not probabilities" in public["disclaimer"]
    serialized = json.dumps(public).casefold()
    for forbidden in ("prompt", "chain_of_thought", "api_key", "model_metadata"):
        assert forbidden not in serialized
    complete = build_current_public_state(ROOT, generated_at=NOW)
    assert complete.product_strategy.program_id == "SGL-001"


def test_two_cycle_idempotency_and_append_only_history(tmp_path):
    root, initial = prepare(tmp_path)
    forced = initial.model_copy(update={"input_fingerprint": "outdated-fingerprint"})
    publish_json(root / "state/product-strategy.json", forced)
    client = StrategyClient()
    first = ProductStrategyOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(run_id="strategy-run-one")
    assert len(first.assessment_history) == len(initial.assessment_history) + 1
    assert len(client.calls) == 9
    before = (root / "state/product-strategy.json").read_bytes()
    second_client = StrategyClient()
    second = ProductStrategyOrchestrator(client=second_client, root=root, now_factory=lambda: NOW).run(run_id="strategy-run-two")
    assert second == first
    assert second_client.calls == []
    assert (root / "state/product-strategy.json").read_bytes() == before
    assert len(second.assessment_history) == len(first.assessment_history)
    assert strategy_input_fingerprint(root) == second.input_fingerprint
    public = json.loads((root / "public/signal-state.json").read_text())
    assert public["productStrategy"]["currentCouncilReview"]["run_id"] == "strategy-run-one"


def test_malformed_specialist_coverage_fails_without_overwriting_state(tmp_path):
    root, initial = prepare(tmp_path)
    publish_json(root / "state/product-strategy.json", initial.model_copy(update={"input_fingerprint": "old"}))
    before = (root / "state/product-strategy.json").read_bytes()

    class Broken(StrategyClient):
        def generate(self, **kwargs):
            value = super().generate(**kwargs)
            if isinstance(value, StrategySpecialistAssessment):
                return value.model_copy(update={"candidates": value.candidates[:-1]})
            return value

    with pytest.raises(ValueError, match="does not cover"):
        ProductStrategyOrchestrator(client=Broken(), root=root, now_factory=lambda: NOW).run(run_id="strategy-bad")
    assert (root / "state/product-strategy.json").read_bytes() == before


def test_evidence_provenance_rejects_unknown_ids():
    workspace = initial_product_strategy(ROOT, now=NOW)
    candidate = workspace.candidates[0]
    assessment = candidate.dimension_assessments[0].model_copy(update={"evidence_ids": ["invented"]})
    candidate = candidate.model_copy(update={"dimension_assessments": [assessment, *candidate.dimension_assessments[1:]]})
    from signalai.product_strategy import validate_strategy_evidence
    with pytest.raises(ValueError, match="unknown canonical evidence"):
        validate_strategy_evidence(workspace.model_copy(update={"candidates": [candidate, *workspace.candidates[1:]]}), set())


def test_workflow_remains_backward_compatible_and_strategy_is_explicit():
    workflow = (ROOT / ".github/workflows/daily-signalai.yml").read_text()
    assert "python -m signalai daily" in workflow
    assert "python -m signalai design-lab" in workflow
    assert "python -m signalai clinic-simulate" in workflow
    main = (ROOT / "src/signalai/__main__.py").read_text()
    assert '"strategy"' in main
