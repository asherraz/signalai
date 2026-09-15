import json
import shutil
import subprocess
import sys
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


class AnalysisRetryClient(ScriptedClient):
    def __init__(self, initial: LiveAnalysis, repaired: LiveAnalysis, outputs, *, fail=False):
        super().__init__(outputs)
        self.initial = initial
        self.repaired = repaired
        self.fail = fail
        self.repair_instructions = ""
        self.repair_input = None
        self.inputs = []

    def generate(self, *, instructions, input_text, output_type):
        self.inputs.append(json.loads(input_text))
        if output_type is LiveAnalysis:
            self.calls.append(output_type)
            return self.initial
        return super().generate(instructions=instructions, input_text=input_text, output_type=output_type)

    def repair(self, *, instructions, input_text, output_type):
        assert output_type is LiveAnalysis
        self.repair_instructions = instructions
        self.repair_input = json.loads(input_text)
        self.calls.append(output_type)
        if self.fail:
            raise RuntimeError("analysis repair failed")
        return self.repaired


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
    for source in (ROOT / "runs").iterdir():
        if source.is_dir() and (source / "09-what-changed.json").exists():
            shutil.copytree(source, tmp_path / "runs" / source.name)
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
    assert payload["signalRB"]["latestReview"]["run_id"] == run.run_id
    assert payload["flagshipProgram"]["signalRBReviewId"] == payload["signalRB"]["latestReview"]["review_id"]
    assert payload["signalRB"]["latestReview"]["determination_type"] == "no_material_change"
    assert payload["signalRB"]["recentReviews"][0] == payload["signalRB"]["latestReview"]
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


@pytest.mark.parametrize("invalid_ids", [["invented-one"], ["invented-one", "invented-two"]])
def test_unknown_evidence_ids_trigger_analysis_only_repair(tmp_path: Path, invalid_ids):
    root = _prepare_root(tmp_path)
    outputs = _outputs()
    initial = outputs[LiveAnalysis].model_copy(deep=True)
    initial.reviewer_conclusions[0].evidence_ids.extend(invalid_ids)
    client = AnalysisRetryClient(initial, outputs[LiveAnalysis], outputs)

    run = LiveRunOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(
        run_id="run-analysis-repaired"
    )

    assert client.calls == [LiveAnalysis, LiveAnalysis, LiveVerification, LiveAdversaryReview, LiveChairRecommendation]
    for invalid_id in invalid_ids:
        assert invalid_id in client.repair_instructions
    assert "Use only these allowed IDs:" in client.repair_instructions
    assert "allowed_evidence_ids" in client.inputs[0]
    assert all(item in client.inputs[0]["allowed_evidence_ids"] for item in outputs[LiveAnalysis].reviewer_conclusions[0].evidence_ids)
    assert (root / "runs" / run.run_id / "05-private-invalid-analysis.json").exists()
    public = json.loads((root / "public" / "signal-state.json").read_text())
    assert all("private-" not in item for item in public["liveIntelligence"]["latestRun"]["linkedArtifactIds"])
    assert all("private-" not in item for item in public["intelligenceFeed"][0]["linkedArtifactIds"])
    accepted = LiveAnalysis.model_validate_json((root / "runs" / run.run_id / "05-analysis.json").read_text())
    assert not set(invalid_ids).intersection(accepted.reviewer_conclusions[0].evidence_ids)


def test_evidence_gap_is_accepted_without_invented_reference(tmp_path: Path):
    root = _prepare_root(tmp_path)
    outputs = _outputs()
    gap = outputs[LiveAnalysis].model_copy(deep=True)
    gap.reviewer_conclusions[0].evidence_ids = []
    gap.reviewer_conclusions[0].unsupported = True
    gap.reviewer_conclusions[0].evidence_gap = "Human CNS exposure is not established."
    gap.reviewer_conclusions[0].search_needed = True
    gap.reviewer_conclusions[0].requested_evidence = ["Controlled human biodistribution evidence"]
    outputs[LiveAnalysis] = gap
    run = LiveRunOrchestrator(client=ScriptedClient(outputs), root=root, now_factory=lambda: NOW).run(run_id="run-gap")
    assert not run.state_changed
    assert run.chair_determination == "evidence_gap"


def test_repair_must_mark_conclusion_unsupported_if_only_citation_was_invalid(tmp_path: Path):
    root = _prepare_root(tmp_path)
    outputs = _outputs()
    initial = outputs[LiveAnalysis].model_copy(deep=True)
    initial.reviewer_conclusions[0].evidence_ids = ["invented-one"]
    repaired = outputs[LiveAnalysis].model_copy(deep=True)
    repaired.reviewer_conclusions[0].evidence_ids = []
    client = AnalysisRetryClient(initial, repaired, outputs)
    with pytest.raises(ValueError, match="removed a citation without marking an evidence gap"):
        LiveRunOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(run_id="run-repair-unsupported")
    assert (root / "runs" / "run-repair-unsupported" / "99-run-failed.json").exists()


def test_repair_can_report_evidence_gap_instead_of_inventing_citation(tmp_path: Path):
    root = _prepare_root(tmp_path)
    outputs = _outputs()
    initial = outputs[LiveAnalysis].model_copy(deep=True)
    initial.reviewer_conclusions[0].evidence_ids = ["invented-one"]
    repaired = outputs[LiveAnalysis].model_copy(deep=True)
    repaired.reviewer_conclusions[0].evidence_ids = []
    repaired.reviewer_conclusions[0].unsupported = True
    repaired.reviewer_conclusions[0].evidence_gap = "No canonical human exposure study is available."
    repaired.reviewer_conclusions[0].search_needed = True
    repaired.reviewer_conclusions[0].requested_evidence = ["Human exposure study"]
    client = AnalysisRetryClient(initial, repaired, outputs)
    run = LiveRunOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(run_id="run-repair-gap")
    accepted = LiveAnalysis.model_validate_json((root / "runs" / run.run_id / "05-analysis.json").read_text())
    assert accepted.reviewer_conclusions[0].unsupported
    assert accepted.reviewer_conclusions[0].search_needed
    assert "invented-one" not in (root / "runs" / run.run_id / "05-analysis.json").read_text()


def test_analysis_validation_reports_invalid_ids_across_fields(tmp_path: Path):
    root = _prepare_root(tmp_path)
    outputs = _outputs()
    initial = outputs[LiveAnalysis].model_copy(deep=True)
    initial.reviewer_conclusions[0].evidence_ids.append("invented-one")
    initial.strongest_contradictory_evidence_ids.append("invented-two")
    client = AnalysisRetryClient(initial, outputs[LiveAnalysis], outputs)
    LiveRunOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(run_id="run-multi-field")
    assert "['invented-one', 'invented-two']" in client.repair_instructions


def test_failed_analysis_repair_preserves_scientific_and_public_state(tmp_path: Path):
    root = _prepare_root(tmp_path)
    outputs = _outputs()
    initial = outputs[LiveAnalysis].model_copy(deep=True)
    initial.strongest_supporting_evidence_ids = ["invented-one"]
    client = AnalysisRetryClient(initial, outputs[LiveAnalysis], outputs, fail=True)
    state_before = (root / "state" / "signal-state.json").read_bytes()
    public_before = (root / "public" / "signal-state.json").read_bytes()
    with pytest.raises(RuntimeError, match="analysis repair failed"):
        LiveRunOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(run_id="run-analysis-failed")
    assert client.calls == [LiveAnalysis, LiveAnalysis]
    assert (root / "state" / "signal-state.json").read_bytes() == state_before
    assert (root / "public" / "signal-state.json").read_bytes() == public_before
    failure = json.loads((root / "runs" / "run-analysis-failed" / "05-private-analysis-failure.json").read_text())
    assert failure["invalid_evidence_ids"] == ["invented-one"]
    assert (root / "runs" / "run-analysis-failed" / "99-run-failed.json").exists()


def test_unsupported_analysis_cannot_drive_scientific_mutation(tmp_path: Path):
    root = _prepare_root(tmp_path)
    outputs = _outputs()
    analysis = outputs[LiveAnalysis].model_copy(deep=True)
    analysis.reviewer_conclusions[0].unsupported = True
    analysis.reviewer_conclusions[0].evidence_gap = "Necessary supporting record is absent."
    outputs[LiveAnalysis] = analysis
    chair = outputs[LiveChairRecommendation].model_copy(deep=True)
    chair.proposed_changes.evidence_confidence_update = "high"
    outputs[LiveChairRecommendation] = chair
    state_before = (root / "state" / "signal-state.json").read_bytes()
    run = LiveRunOrchestrator(client=ScriptedClient(outputs), root=root, now_factory=lambda: NOW).run(run_id="run-unsupported")
    assert (root / "state" / "signal-state.json").read_bytes() == state_before
    assert run.chair_determination == "evidence_gap"
    assert not run.state_changed and run.previous_state_preserved
    public = json.loads((root / "public" / "signal-state.json").read_text())
    review = public["signalRB"]["latestReview"]
    assert review["determination_type"] == "evidence_gap"
    assert review["state_change"] is False
    assert review["previous_state_preserved"] is True
    assert review["verification_status"] == "unsupported_assertions"
    assert "not sufficiently evidence-supported" in review["determination"]
    assert (root / "runs" / run.run_id / "99-run-complete.json").exists()
    assert not (root / "runs" / run.run_id / "99-run-failed.json").exists()


def _unsupported_outputs():
    outputs = _outputs()
    analysis = outputs[LiveAnalysis].model_copy(deep=True)
    analysis.reviewer_conclusions[0].unsupported = True
    analysis.reviewer_conclusions[0].evidence_gap = "Required supporting record is absent."
    analysis.reviewer_conclusions[0].conclusion = "PRIVATE_UNSUPPORTED_DIAGNOSTIC: unsupported scientific proposal."
    outputs[LiveAnalysis] = analysis
    outputs[LiveChairRecommendation].proposed_changes.evidence_confidence_update = "high"
    return outputs


def test_one_analysis_repair_receives_exact_conclusions_and_degrades_safely(tmp_path):
    root = _prepare_root(tmp_path)
    outputs = _unsupported_outputs()
    initial = outputs[LiveAnalysis]
    client = AnalysisRetryClient(initial, initial, outputs)
    before = (root / "state/signal-state.json").read_bytes()
    run = LiveRunOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(run_id="run-gap-repair")
    assert client.calls == [LiveAnalysis, LiveAnalysis, LiveVerification, LiveAdversaryReview, LiveChairRecommendation]
    assert "Unsupported".lower() in client.repair_instructions.lower()
    assert client.repair_input["unsupported_conclusions"][0]["conclusion"] == initial.reviewer_conclusions[0].conclusion
    assert client.repair_input["allowed_evidence_ids"] == client.inputs[0]["allowed_evidence_ids"]
    # Capture the repair payload as well as its constraints.
    private = json.loads((root / "runs" / run.run_id / "05-private-unsupported-analysis.json").read_text())
    assert private["unsupported_conclusions"][0]["conclusion"] == initial.reviewer_conclusions[0].conclusion
    assert (root / "state/signal-state.json").read_bytes() == before
    assert run.chair_determination == "evidence_gap"
    rejected = json.loads((root / "runs" / run.run_id / "08-private-rejected-proposal.json").read_text())
    assert rejected["rejected_recommendation"]["proposed_changes"]["evidence_confidence_update"] == "high"
    public_text = (root / "public/signal-state.json").read_text()
    assert "PRIVATE_UNSUPPORTED_DIAGNOSTIC" not in public_text
    assert "private-unsupported" not in public_text and "private-rejected" not in public_text
    public = json.loads(public_text)
    assert public["intelligenceFeed"][0]["type"] == "evidence_gap"
    assert "state updated" not in public["intelligenceFeed"][0]["title"]
    assert public["liveIntelligence"]["latestRun"]["reviewerConclusions"][0]["unsupported"] is True
    docket = DevelopmentDocket.model_validate_json((root / "state/development-docket.json").read_text())
    assert next(m for m in docket.matters if m.matter_id == run.selected_matter.matter_id).status is MatterStatus.OPEN


def test_supported_repair_is_independently_verified_before_mutation(tmp_path):
    root = _prepare_root(tmp_path)
    outputs = _unsupported_outputs()
    repaired = _outputs()[LiveAnalysis]
    outputs[LiveVerification].supports_state_change = True
    client = AnalysisRetryClient(outputs[LiveAnalysis], repaired, outputs)
    run = LiveRunOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(run_id="run-supported-repair")
    assert run.scientific_state_changed
    assert client.inputs[1]["analysis"] == repaired.model_dump(mode="json")
    assert client.calls.count(LiveVerification) == client.calls.count(LiveAdversaryReview) == 1
    assert not run.previous_state_preserved


def test_repair_without_support_cannot_clear_unsupported_status(tmp_path):
    root = _prepare_root(tmp_path)
    outputs = _unsupported_outputs()
    repaired = _outputs()[LiveAnalysis]
    repaired.reviewer_conclusions[0].evidence_ids = []
    outputs[LiveVerification].supports_state_change = True
    client = AnalysisRetryClient(outputs[LiveAnalysis], repaired, outputs)
    before = (root / "state/signal-state.json").read_bytes()
    run = LiveRunOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(run_id="run-unsupported-label-cleared")
    assert run.chair_determination == "evidence_gap"
    assert run.reviewer_conclusions[0].unsupported
    assert (root / "state/signal-state.json").read_bytes() == before


def test_analysis_repair_reuses_unaffected_conclusions(tmp_path):
    root = _prepare_root(tmp_path)
    outputs = _unsupported_outputs()
    repaired = outputs[LiveAnalysis].model_copy(deep=True)
    repaired.reviewer_conclusions[1].conclusion = "This out-of-scope revision must not be accepted."
    client = AnalysisRetryClient(outputs[LiveAnalysis], repaired, outputs)
    run = LiveRunOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(run_id="run-bounded-reviewers")
    assert run.reviewer_conclusions[1] == outputs[LiveAnalysis].reviewer_conclusions[1]
    assert run.chair_determination == "evidence_gap"


def test_unknown_reference_repair_shares_the_single_analysis_budget(tmp_path):
    root = _prepare_root(tmp_path)
    outputs = _unsupported_outputs()
    initial = outputs[LiveAnalysis].model_copy(deep=True)
    initial.reviewer_conclusions[0].evidence_ids.append("invented-id")
    client = AnalysisRetryClient(initial, outputs[LiveAnalysis], outputs)
    run = LiveRunOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(run_id="run-shared-repair")
    assert client.calls.count(LiveAnalysis) == 2
    assert run.chair_determination == "evidence_gap"
    assert "invented-id" not in (root / "public/signal-state.json").read_text()


def test_unverified_scientific_update_is_an_expected_evidence_gap(tmp_path):
    root = _prepare_root(tmp_path)
    outputs = _outputs()
    outputs[LiveChairRecommendation].proposed_changes.evidence_confidence_update = "high"
    client = ScriptedClient(outputs)
    before = (root / "state/signal-state.json").read_bytes()
    run = LiveRunOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(run_id="run-unverified-gap")
    assert run.chair_determination == "evidence_gap"
    assert client.calls.count(LiveAnalysis) == 1
    assert (root / "state/signal-state.json").read_bytes() == before


def test_verifier_objection_cannot_be_overridden_by_boolean_support(tmp_path):
    root = _prepare_root(tmp_path)
    outputs = _outputs()
    outputs[LiveVerification].supports_state_change = True
    outputs[LiveVerification].unsupported_assertions = ["The proposed confidence increase is not supported."]
    outputs[LiveChairRecommendation].proposed_changes.evidence_confidence_update = "high"
    before = (root / "state/signal-state.json").read_bytes()
    run = LiveRunOrchestrator(client=ScriptedClient(outputs), root=root, now_factory=lambda: NOW).run(run_id="run-conflicting-verifier")
    assert run.chair_determination == "evidence_gap"
    assert (root / "state/signal-state.json").read_bytes() == before


def test_evidence_gap_rejects_decision_and_operational_changes_too(tmp_path):
    root = _prepare_root(tmp_path)
    state = SignalState.model_validate_json((root / "state/signal-state.json").read_text())
    outputs = _unsupported_outputs()
    outputs[LiveChairRecommendation].proposed_changes.next_action = "A proposed different operational next step."
    outputs[LiveChairRecommendation].proposed_changes.decision_update = state.decision.model_copy(update={"question": "Proposed revision to the pending decision"})
    before = (root / "state/signal-state.json").read_bytes()
    run = LiveRunOrchestrator(client=ScriptedClient(outputs), root=root, now_factory=lambda: NOW).run(run_id="run-all-mutations-rejected")
    assert run.chair_determination == "evidence_gap"
    assert (root / "state/signal-state.json").read_bytes() == before
    public = json.loads((root / "public/signal-state.json").read_text())
    assert public["signalRB"]["pendingHumanDecisions"][0]["question"] == state.decision.question


@pytest.mark.parametrize("failure", [RuntimeError("network unavailable"), MalformedStructuredOutputError("invalid structured analysis")])
def test_infrastructure_or_schema_error_during_repair_still_aborts(tmp_path, failure):
    root = _prepare_root(tmp_path)
    outputs = _unsupported_outputs()
    class BrokenRepair(AnalysisRetryClient):
        def repair(self, **kwargs):
            raise failure
    client = BrokenRepair(outputs[LiveAnalysis], outputs[LiveAnalysis], outputs)
    state_before = (root / "state/signal-state.json").read_bytes()
    public_before = (root / "public/signal-state.json").read_bytes()
    with pytest.raises(type(failure)):
        LiveRunOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(run_id="run-actual-failure")
    assert (root / "state/signal-state.json").read_bytes() == state_before
    assert (root / "public/signal-state.json").read_bytes() == public_before
    assert (root / "runs/run-actual-failure/99-run-failed.json").exists()


def test_gap_publication_preserves_clinic_intelligence(tmp_path):
    root = _prepare_root(tmp_path)
    (root / "data/clinics").mkdir(parents=True)
    shutil.copy2(ROOT / "data/clinics/clinics.json", root / "data/clinics/clinics.json")
    before = json.loads((root / "public/signal-state.json").read_text())["clinicIntelligence"]
    run = LiveRunOrchestrator(client=ScriptedClient(_unsupported_outputs()), root=root, now_factory=lambda: NOW).run(run_id="run-gap-clinics")
    after = json.loads((root / "public/signal-state.json").read_text())["clinicIntelligence"]
    assert run.chair_determination == "evidence_gap"
    assert before == after


@pytest.mark.parametrize("mode,expected_code", [("unsupported", 0), ("network", 1), ("schema", 1), ("corrupt_state", 1)])
def test_daily_cli_exit_classification(tmp_path, mode, expected_code):
    root = _prepare_root(tmp_path)
    if mode == "corrupt_state":
        (root / "state/signal-state.json").write_text("{not-valid-json")
    script = f"""
import runpy, sys
from unittest.mock import patch
sys.path.insert(0, {str(ROOT / 'tests')!r})
import test_live_intelligence as t
mode = {mode!r}
class InvalidSchema:
    def generate(self, **kwargs):
        raise t.MalformedStructuredOutputError('invalid schema after repair')
client = t.FailingClient() if mode == 'network' else InvalidSchema() if mode == 'schema' else t.ScriptedClient(t._unsupported_outputs())
sys.argv = ['signalai', 'daily']
with patch('signalai.cli.OpenAIResponsesClient.from_env', return_value=client):
    runpy.run_module('signalai', run_name='__main__')
"""
    result = subprocess.run([sys.executable, "-c", script], cwd=root, capture_output=True, text=True)
    assert result.returncode == expected_code, result.stderr
    if expected_code == 0:
        assert "Completed live run" in result.stdout
        public = json.loads((root / "public/signal-state.json").read_text())
        assert public["signalRB"]["latestReview"]["determination_type"] == "evidence_gap"
    else:
        assert "Traceback" in result.stderr
