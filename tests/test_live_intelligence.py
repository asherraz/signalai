import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar, cast

import pytest
from pydantic import BaseModel

from signalai.live import LiveRunOrchestrator
from signalai.client import (
    MalformedStructuredOutputError,
    StructuredOutputError,
)
from signalai.live_selector import select_current_matter, select_reviewers
from signalai.material_change import public_payload_has_material_change
from signalai.schemas import ApprovalStatus, SignalState
from signalai.schemas.live import (
    DevelopmentDocket,
    LiveAdversaryReview,
    LiveAnalysis,
    LiveChairRecommendation,
    LiveRunHistory,
    LiveVerification,
    MatterStatus,
    ReviewerRole,
)


ROOT = Path(__file__).resolve().parents[1]
OutputT = TypeVar("OutputT", bound=BaseModel)
NOW = datetime(2026, 9, 11, 8, 0, tzinfo=timezone.utc)


def _outputs(*, material_change: bool = False) -> dict[type[BaseModel], BaseModel]:
    matter_id = "matter-cross-species-cns-delivery"
    evidence = [
        "ev-zhuang-2011-intranasal-exosome",
        "ev-driedonks-2022-macaque-biodistribution",
    ]
    analysis = LiveAnalysis(
        matter_id=matter_id,
        objective="Assess whether current cross-species delivery evidence clears the route gate.",
        reviewer_conclusions=[
            {
                "reviewer_role": "delivery",
                "conclusion": "Rodent findings support feasibility, but the macaque record does not establish reproducible brain exposure.",
                "evidence_ids": evidence,
                "claim_ids": ["claim-rodent-cns-delivery", "claim-large-animal-delivery-uncertain"],
                "limitations": ["The records do not establish human exposure."],
            },
            {
                "reviewer_role": "translational",
                "conclusion": "The route remains a translational gate rather than a validated product attribute.",
                "evidence_ids": evidence,
                "limitations": ["Cross-species comparability is unresolved."],
            },
            {
                "reviewer_role": "preclinical",
                "conclusion": "A formulation-controlled biodistribution study is required before efficacy-model escalation.",
                "evidence_ids": evidence,
                "limitations": ["Existing models and formulations are heterogeneous."],
            },
        ],
        strongest_support_summary="Rodent studies report intranasal delivery-associated CNS biological activity.",
        strongest_supporting_evidence_ids=["ev-zhuang-2011-intranasal-exosome"],
        strongest_contradiction_summary="The available macaque biodistribution record does not demonstrate a robust brain-exposure bridge.",
        strongest_contradictory_evidence_ids=["ev-driedonks-2022-macaque-biodistribution"],
        proposed_next_action="Define a formulation-controlled cross-species biodistribution protocol with label controls and predeclared acceptance criteria.",
    )
    verification = LiveVerification(
        matter_id=matter_id,
        conclusion="The cited records support uncertainty, not a conclusion of human CNS delivery.",
        verified_evidence_ids=evidence,
        unsupported_assertions=[],
        supports_state_change=False,
    )
    adversary = LiveAdversaryReview(
        matter_id=matter_id,
        strongest_objection="Observed signal could reflect label behavior, nasal retention, or formulation-specific effects rather than intact EV brain delivery.",
        assumptions_challenged=["Rodent CNS observations translate across species."],
        disconfirming_evidence_ids=["ev-driedonks-2022-macaque-biodistribution"],
        falsification_conditions=["A controlled larger-species study fails predefined CNS exposure criteria."],
        supports_state_change=False,
    )
    proposed_changes = {}
    if material_change:
        proposed_changes["next_action"] = analysis.proposed_next_action
    chair = LiveChairRecommendation(
        matter_id=matter_id,
        findings=["Current evidence does not resolve cross-species delivery."],
        evidence_assessment="Rodent feasibility is offset by unresolved larger-species exposure.",
        supporting_evidence_ids=evidence,
        objections=["Human CNS exposure is not established."],
        recommendation="Retain the delivery gate and define the controlled next study.",
        proposed_changes=proposed_changes,
    )
    return {
        LiveAnalysis: analysis,
        LiveVerification: verification,
        LiveAdversaryReview: adversary,
        LiveChairRecommendation: chair,
    }


class ScriptedClient:
    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = []

    def generate(self, *, instructions: str, input_text: str, output_type: type[OutputT]) -> OutputT:
        assert instructions and input_text
        self.calls.append(output_type)
        return cast(OutputT, self.outputs[output_type])


class FailingClient:
    def generate(self, **kwargs):
        raise RuntimeError("model unavailable")


class ChairRetryClient(ScriptedClient):
    def __init__(self, outputs, *, retry_succeeds: bool) -> None:
        super().__init__(outputs)
        self.retry_succeeds = retry_succeeds
        self.chair_attempts = 0
        self.repair_instructions = ""
        self.usage_records = [
            {
                "stage": "LiveAnalysis",
                "attempt": "initial",
                "model": "test-model",
                "status": "completed",
                "incomplete_reason": None,
                "max_output_tokens": 2500,
                "input_tokens": 100,
                "cached_input_tokens": 20,
                "output_tokens": 40,
                "reasoning_tokens": 10,
                "estimated_api_cost_usd": 0.0001,
            }
        ]

    def generate(self, *, instructions: str, input_text: str, output_type: type[OutputT]) -> OutputT:
        if output_type is LiveChairRecommendation:
            self.calls.append(output_type)
            self.chair_attempts += 1
            raise MalformedStructuredOutputError(
                "LiveChairRecommendation failed semantic validation",
                conflicts=[
                    "proposed_changes: no_material_change conflicts with scientific updates"
                ],
            )
        return super().generate(
            instructions=instructions, input_text=input_text, output_type=output_type
        )

    def repair(self, *, instructions: str, input_text: str, output_type: type[OutputT]) -> OutputT:
        assert "Repair" in instructions
        self.repair_instructions = instructions
        self.calls.append(output_type)
        self.chair_attempts += 1
        if not self.retry_succeeds:
            raise MalformedStructuredOutputError(
                "LiveChairRecommendation returned malformed structured output",
                conflicts=[
                    "proposed_changes: no_material_change conflicts with scientific updates"
                ],
            )
        return cast(OutputT, self.outputs[output_type])


def _prepare_root(tmp_path: Path) -> Path:
    for directory in ("state", "runs", "public"):
        (tmp_path / directory).mkdir()
    for name in (
        "signal-state.json",
        "asset-development.json",
        "clinical-network.json",
        "development-docket.json",
        "live-runs.json",
    ):
        shutil.copy2(ROOT / "state" / name, tmp_path / "state" / name)
    docket_path = tmp_path / "state" / "development-docket.json"
    docket = DevelopmentDocket.model_validate_json(docket_path.read_text())
    matters = []
    for matter in docket.matters:
        data = matter.model_dump(mode="python")
        if matter.matter_id == "matter-cross-species-cns-delivery":
            data.update(
                status=MatterStatus.OPEN,
                selected_at=None,
                completed_at=None,
                determination=None,
                next_action=None,
            )
        matters.append(data)
    docket_path.write_text(
        DevelopmentDocket.model_validate(
            {**docket.model_dump(mode="python"), "matters": matters}
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    (tmp_path / "state" / "live-runs.json").write_text(
        LiveRunHistory(program_id="SGL-001", updated_at=NOW).model_dump_json(indent=2),
        encoding="utf-8",
    )
    state = SignalState.model_validate_json((tmp_path / "state" / "signal-state.json").read_text())
    shutil.copytree(ROOT / "runs" / state.run_id, tmp_path / "runs" / state.run_id)
    shutil.copy2(ROOT / "public" / "signal-state.json", tmp_path / "public" / "signal-state.json")
    return tmp_path


def test_matter_prioritization_and_reviewer_selection() -> None:
    docket = DevelopmentDocket.model_validate_json((ROOT / "state" / "development-docket.json").read_text())
    matters = []
    for matter in docket.matters:
        data = matter.model_dump(mode="python")
        if matter.matter_id == "matter-cross-species-cns-delivery":
            data.update(status=MatterStatus.OPEN, selected_at=None, completed_at=None, determination=None, next_action=None)
        matters.append(data)
    docket = DevelopmentDocket.model_validate({**docket.model_dump(mode="python"), "matters": matters})
    selected, reason = select_current_matter(docket)
    reviewers = select_reviewers(selected)
    assert selected.matter_id == "matter-cross-species-cns-delivery"
    assert "program-invalidating" in reason
    assert reviewers == [
        ReviewerRole.DELIVERY,
        ReviewerRole.TRANSLATIONAL,
        ReviewerRole.PRECLINICAL,
        ReviewerRole.VERIFIER,
        ReviewerRole.ADVERSARY,
        ReviewerRole.CHAIR,
    ]


def test_no_material_change_run_persists_and_exports_live_intelligence(tmp_path: Path) -> None:
    root = _prepare_root(tmp_path)
    before = (root / "state" / "signal-state.json").read_text()
    run = LiveRunOrchestrator(
        client=ScriptedClient(_outputs()), root=root, now_factory=lambda: NOW
    ).run(run_id="run-live-no-change")
    assert not run.state_changed
    assert (root / "state" / "signal-state.json").read_text() == before
    assert run.selected_matter.status is MatterStatus.COMPLETED
    files = {item.name for item in (root / "runs" / run.run_id).iterdir()}
    assert files == {
        "00-run-start.json", "01-compact-state.json", "02-development-docket.json",
        "03-selected-matter.json", "04-reviewer-panel.json", "05-analysis.json",
        "06-verification.json", "07-adversary.json", "08-chair-determination.json",
        "09-live-run.json", "10-updated-state.json", "11-updated-docket.json",
        "12-public-signal-state.json", "99-run-complete.json",
    }
    payload = json.loads((root / "public" / "signal-state.json").read_text())
    assert payload["liveIntelligence"]["latestRun"]["runId"] == run.run_id
    assert payload["liveIntelligence"]["recentRuns"][0]["stateChanged"] is False
    assert payload["intelligenceFeed"][0]["type"] == "no_material_change"
    serialized = json.dumps(payload).lower()
    for forbidden in ("raw_prompt", "chain-of-thought", "api_key", "response_id", "contact_email"):
        assert forbidden not in serialized


def test_state_change_is_validated_and_human_approval_is_preserved(tmp_path: Path) -> None:
    root = _prepare_root(tmp_path)
    run = LiveRunOrchestrator(
        client=ScriptedClient(_outputs(material_change=True)), root=root, now_factory=lambda: NOW
    ).run(run_id="run-live-state-change")
    state = SignalState.model_validate_json((root / "state" / "signal-state.json").read_text())
    assert run.state_changed
    assert run.chair_determination == "no_material_change"
    assert run.change_scope.value == "operational_next_action"
    assert not run.scientific_state_changed
    assert run.operational_state_changed
    assert state.run_id == run.run_id
    assert state.program.next_proposed_action == run.next_action
    assert state.decision.requires_human_approval
    assert state.decision.approval_status is ApprovalStatus.PENDING


def test_failed_run_does_not_overwrite_valid_state_or_public_payload(tmp_path: Path) -> None:
    root = _prepare_root(tmp_path)
    state_before = (root / "state" / "signal-state.json").read_bytes()
    public_before = (root / "public" / "signal-state.json").read_bytes()
    with pytest.raises(RuntimeError, match="model unavailable"):
        LiveRunOrchestrator(client=FailingClient(), root=root, now_factory=lambda: NOW).run(
            run_id="run-live-failed"
        )
    assert (root / "state" / "signal-state.json").read_bytes() == state_before
    assert (root / "public" / "signal-state.json").read_bytes() == public_before
    assert (root / "runs" / "run-live-failed" / "99-run-failed.json").exists()


def test_semantic_chair_failure_retries_once_without_rerunning_reviewers(tmp_path: Path) -> None:
    root = _prepare_root(tmp_path)
    client = ChairRetryClient(_outputs(), retry_succeeds=True)

    run = LiveRunOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(
        run_id="run-live-chair-repaired"
    )

    assert run.chair_determination == "no_material_change"
    assert client.calls == [
        LiveAnalysis,
        LiveVerification,
        LiveAdversaryReview,
        LiveChairRecommendation,
        LiveChairRecommendation,
    ]
    assert client.chair_attempts == 2
    assert "no_material_change conflicts with scientific updates" in client.repair_instructions
    assert (root / "runs" / run.run_id / "08-chair-repair.json").exists()
    usage = json.loads((root / "runs" / run.run_id / "98-private-usage.json").read_text())
    assert usage["totals"]["cached_input_tokens"] == 20
    assert usage["totals"]["reasoning_tokens"] == 10
    assert usage["totals"]["estimated_api_cost_usd"] == 0.0001
    assert "estimated_api_cost_usd" not in (root / "public" / "signal-state.json").read_text()


def test_failed_chair_retry_preserves_public_state_and_writes_private_failure(
    tmp_path: Path,
) -> None:
    root = _prepare_root(tmp_path)
    client = ChairRetryClient(_outputs(), retry_succeeds=False)
    public_before = (root / "public" / "signal-state.json").read_bytes()
    state_before = (root / "state" / "signal-state.json").read_bytes()

    with pytest.raises(StructuredOutputError, match="failed after one repair attempt"):
        LiveRunOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(
            run_id="run-live-chair-retry-failed"
        )

    assert client.chair_attempts == 2
    assert (root / "public" / "signal-state.json").read_bytes() == public_before
    assert (root / "state" / "signal-state.json").read_bytes() == state_before
    run_dir = root / "runs" / "run-live-chair-retry-failed"
    private_failure = json.loads((run_dir / "08-private-chair-failure.json").read_text())
    assert private_failure == {
        "attempts": 2,
        "reason": "incomplete_or_malformed_structured_output",
        "stage": "LiveChairDetermination",
        "status": "failed",
        "validation_conflicts": [
            "proposed_changes: no_material_change conflicts with scientific updates",
            "proposed_changes: no_material_change conflicts with scientific updates",
        ],
    }
    assert (run_dir / "99-run-failed.json").exists()
    assert (run_dir / "98-private-usage.json").exists()


def test_timestamp_only_public_change_is_not_material() -> None:
    before = '{"generatedAt":"2026-09-10T00:00:00Z","status":"active"}'
    after = '{"generatedAt":"2026-09-11T00:00:00Z","status":"active"}'
    changed = '{"generatedAt":"2026-09-11T00:00:00Z","status":"changed"}'
    assert not public_payload_has_material_change(before, after)
    assert public_payload_has_material_change(before, changed)


def test_live_history_requires_independent_review_roles() -> None:
    history = LiveRunHistory.model_validate_json((ROOT / "state" / "live-runs.json").read_text())
    for run in history.runs:
        assert {ReviewerRole.VERIFIER, ReviewerRole.ADVERSARY, ReviewerRole.CHAIR}.issubset(
            run.reviewers_convened
        )
