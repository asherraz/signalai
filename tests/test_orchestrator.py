import json
from pathlib import Path
from typing import TypeVar, cast

import pytest
from pydantic import BaseModel

from signalai.orchestrator import MilestoneOneOrchestrator
from signalai.schemas import (
    ApprovalStatus,
    ClaimSet,
    CritiqueResult,
    DecisionProposal,
    HypothesisProposal,
    PublicSignalState,
    SignalState,
)


OutputT = TypeVar("OutputT", bound=BaseModel)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ScriptedClient:
    def __init__(self, outputs: dict[str, object]) -> None:
        self.outputs = outputs
        self.calls: list[type[BaseModel]] = []

    def generate(
        self,
        *,
        instructions: str,
        input_text: str,
        output_type: type[OutputT],
    ) -> OutputT:
        assert instructions
        assert input_text
        self.calls.append(output_type)
        key = {
            ClaimSet: "claims",
            HypothesisProposal: "hypothesis",
            CritiqueResult: "critique",
            DecisionProposal: "decision",
        }[output_type]
        return cast(OutputT, output_type.model_validate(self.outputs[key]))


def _outputs() -> dict[str, object]:
    path = PROJECT_ROOT / "tests" / "fixtures" / "model_outputs.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_milestone_one_run_persists_every_stage_and_public_state(tmp_path: Path) -> None:
    client = ScriptedClient(_outputs())
    runs_root = tmp_path / "runs"
    public_path = tmp_path / "public" / "signal-state.json"
    orchestrator = MilestoneOneOrchestrator(
        client=client,
        evidence_path=PROJECT_ROOT / "evidence" / "fixtures" / "sgl-001.json",
        runs_root=runs_root,
        public_state_path=public_path,
    )

    state = orchestrator.run(run_id="run-test-001")

    assert client.calls == [ClaimSet, HypothesisProposal, CritiqueResult, DecisionProposal]
    assert len(state.claims) >= 3
    assert all(claim.status.value == "supported" for claim in state.claims)
    assert state.hypothesis.status.value == "active"
    assert len(state.risks) == 3
    assert state.decision.approval_status is ApprovalStatus.PENDING
    assert state.program.current_formulation_hypothesis
    assert state.program.development_focus == "Neuroregeneration and cognitive function"
    assert state.program.lead_indication == "Not yet selected"
    assert state.program.indication is None
    assert state.program.evidence_confidence.value == "moderate"
    assert state.program.largest_unresolved_risk
    assert state.program.next_proposed_action
    assert all(risk.likelihood.value in {"low", "moderate", "high", "critical"} for risk in state.risks)
    assert all(risk.severity.value in {"low", "moderate", "high", "critical"} for risk in state.risks)
    run_path = runs_root / "run-test-001"
    assert {path.name for path in run_path.iterdir()} == {
        "00-run-start.json",
        "01-evidence.json",
        "02-claims.json",
        "03-hypothesis.json",
        "04-critique.json",
        "05-decision.json",
        "06-signal-state.json",
        "07-public-signal-state.json",
        "99-run-complete.json",
    }
    public_payload = json.loads(public_path.read_text())
    assert set(public_payload) == {
        "generatedAt",
        "version",
        "status",
        "program",
        "changes",
        "loop",
        "evidence",
        "hypotheses",
        "risks",
        "decisions",
        "currentHypothesis",
        "latestRun",
        "cargo",
        "formulation",
        "jurisdictions",
        "clinicalNetwork",
    }
    public_state = PublicSignalState.model_validate(public_payload)
    assert public_state.loop.run_id == state.run_id
    assert public_state.hypotheses == [state.hypothesis]
    assert public_state.risks == state.risks
    assert len(public_state.changes) == 1
    assert public_state.program.claims == state.claims

    evidence_ids = {item.evidence_id for item in state.evidence}
    claim_ids = {item.claim_id for item in state.claims}
    assert all(set(claim.evidence_ids) <= evidence_ids for claim in state.claims)
    assert set(state.hypothesis.supporting_claim_ids) <= claim_ids
    assert set(state.hypothesis.contradicting_claim_ids) <= claim_ids
    assert set(state.hypothesis.evidence_ids) <= evidence_ids
    assert all(set(risk.evidence_ids) <= evidence_ids for risk in state.risks)
    assert set(state.decision.supporting_claim_ids) <= claim_ids
    assert set(state.decision.evidence_ids) <= evidence_ids


def test_invalid_model_reference_is_rejected_and_failure_is_persisted(
    tmp_path: Path,
) -> None:
    outputs = _outputs()
    claims = cast(dict[str, object], outputs["claims"])
    first_claim = cast(list[dict[str, object]], claims["claims"])[0]
    first_claim["evidence_ids"] = ["unknown-evidence"]
    runs_root = tmp_path / "runs"
    orchestrator = MilestoneOneOrchestrator(
        client=ScriptedClient(outputs),
        evidence_path=PROJECT_ROOT / "evidence" / "fixtures" / "sgl-001.json",
        runs_root=runs_root,
        public_state_path=tmp_path / "public" / "signal-state.json",
    )

    with pytest.raises(ValueError, match="unknown evidence IDs"):
        orchestrator.run(run_id="run-test-failed")

    run_path = runs_root / "run-test-failed"
    assert (run_path / "99-run-failed.json").exists()
    assert not (tmp_path / "public" / "signal-state.json").exists()
