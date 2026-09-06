import json
from pathlib import Path
from typing import TypeVar, cast

from pydantic import BaseModel

from signalai.daily import DailyRunOrchestrator
from signalai.public_export import export_completed_run
from signalai.schemas import (
    AgendaStatus,
    DailyAnalysis,
    DailyCritique,
    DailySynthesis,
    DevelopmentAgenda,
    Risk,
    SignalState,
    PublicEvidenceArtifact,
)
from signalai.selector import select_highest_value_task


OutputT = TypeVar("OutputT", bound=BaseModel)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_STATE = (
    PROJECT_ROOT
    / "runs"
    / "run-20260903T143924Z-adf75688b589"
    / "06-signal-state.json"
)


class DailyScriptedClient:
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
        assert instructions and input_text
        self.calls.append(output_type)
        key = {
            DailyAnalysis: "analysis",
            DailyCritique: "critique",
            DailySynthesis: "synthesis",
        }[output_type]
        return cast(OutputT, output_type.model_validate(self.outputs[key]))


def _outputs() -> dict[str, object]:
    path = PROJECT_ROOT / "tests" / "fixtures" / "daily_outputs.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _prepare_current_files(tmp_path: Path) -> tuple[Path, Path]:
    state_path = tmp_path / "state" / "signal-state.json"
    agenda_path = tmp_path / "state" / "development-agenda.json"
    state_path.parent.mkdir()
    state_path.write_text(BASELINE_STATE.read_text(encoding="utf-8"), encoding="utf-8")
    source_agenda = DevelopmentAgenda.model_validate_json(
        (PROJECT_ROOT / "state" / "development-agenda.json").read_text(encoding="utf-8")
    )
    normalized_items = []
    for item in source_agenda.items:
        item_data = item.model_dump(mode="python")
        if item.agenda_item_id == "agenda-cross-species-cns-delivery":
            item_data.update(status=AgendaStatus.OPEN, last_evaluated_at=None, resolution=None)
        normalized_items.append(item_data)
    normalized_agenda = DevelopmentAgenda.model_validate(
        {
            **source_agenda.model_dump(mode="python"),
            "items": normalized_items,
        }
    )
    agenda_path.write_text(normalized_agenda.model_dump_json(indent=2), encoding="utf-8")
    return state_path, agenda_path


def test_no_material_change_run_persists_all_stages(tmp_path: Path) -> None:
    state_path, agenda_path = _prepare_current_files(tmp_path)
    before = SignalState.model_validate_json(state_path.read_text())
    client = DailyScriptedClient(_outputs())
    orchestrator = DailyRunOrchestrator(
        client=client,
        state_path=state_path,
        agenda_path=agenda_path,
        runs_root=tmp_path / "runs",
        public_state_path=tmp_path / "public" / "signal-state.json",
        workspace_path=PROJECT_ROOT / "state" / "asset-development.json",
    )

    state, agenda = orchestrator.run(run_id="run-daily-test")

    assert client.calls == [DailyAnalysis, DailyCritique, DailySynthesis]
    assert state.claims == before.claims
    assert state.hypothesis == before.hypothesis
    assert state.risks == before.risks
    assert state.decision == before.decision
    assert state.decision.approval_status.value == "pending"
    selected = next(
        item
        for item in agenda.items
        if item.agenda_item_id == "agenda-cross-species-cns-delivery"
    )
    assert selected.status is AgendaStatus.DEFERRED
    assert selected.last_evaluated_at is not None
    assert set(path.name for path in (tmp_path / "runs" / "run-daily-test").iterdir()) == {
        "00-run-start.json",
        "01-current-state.json",
        "02-current-agenda.json",
        "03-selected-task.json",
        "04-analysis.json",
        "05-critique.json",
        "06-synthesis.json",
        "07-updated-state.json",
        "08-updated-agenda.json",
        "09-what-changed.json",
        "10-public-signal-state.json",
        "99-run-complete.json",
    }
    public_payload = json.loads(
        (tmp_path / "public" / "signal-state.json").read_text(encoding="utf-8")
    )
    latest = public_payload["latestRun"]
    assert set(latest["stages"]) == {
        "evidence",
        "claims",
        "hypothesis",
        "critique",
        "decision",
        "nextAction",
    }
    assert latest["runId"] == state.run_id
    assert public_payload["cargo"]["focusCandidates"] == ["cargo-native-msc-ev-secretome"]
    assert public_payload["formulation"]["candidates"]
    assert public_payload["jurisdictions"]["summaryCounts"]["restrictive"] == 3
    assert public_payload["currentHypothesis"]["hypothesisId"] == state.hypothesis.hypothesis_id


def test_public_artifacts_export_from_completed_run_and_match_canonical_ids(
    tmp_path: Path,
) -> None:
    state_path, agenda_path = _prepare_current_files(tmp_path)
    orchestrator = DailyRunOrchestrator(
        client=DailyScriptedClient(_outputs()),
        state_path=state_path,
        agenda_path=agenda_path,
        runs_root=tmp_path / "runs",
        public_state_path=tmp_path / "public" / "signal-state.json",
    )
    state, _ = orchestrator.run(run_id="run-export-test")

    exported = export_completed_run(tmp_path / "runs" / "run-export-test")

    assert exported.run_id == state.run_id
    assert {item.evidence_id for item in exported.stages.evidence} == {
        item.evidence_id for item in state.evidence
    }
    assert {item.claim_id for item in exported.stages.claims} == {
        item.claim_id for item in state.claims
    }
    assert exported.stages.hypothesis.hypothesis_id == state.hypothesis.hypothesis_id
    assert exported.stages.decision.decision_id == state.decision.decision_id


def test_public_artifacts_omit_sensitive_internal_fields_and_allow_optional_values(
    tmp_path: Path,
) -> None:
    state_path, agenda_path = _prepare_current_files(tmp_path)
    orchestrator = DailyRunOrchestrator(
        client=DailyScriptedClient(_outputs()),
        state_path=state_path,
        agenda_path=agenda_path,
        runs_root=tmp_path / "runs",
        public_state_path=tmp_path / "public" / "signal-state.json",
    )
    orchestrator.run(run_id="run-sanitization-test")
    payload = json.loads(
        (tmp_path / "public" / "signal-state.json").read_text(encoding="utf-8")
    )
    serialized = json.dumps(payload).lower()

    for forbidden in (
        "rawprompt",
        "raw_prompt",
        "chain-of-thought",
        "chain_of_thought",
        "api_key",
        "authorization",
        "response_id",
        "model_metadata",
    ):
        assert forbidden not in serialized
    evidence = payload["latestRun"]["stages"]["evidence"]
    assert any(item["modelOrIndication"] is None for item in evidence)
    assert all("source_uri" not in item and "metadata" not in item for item in evidence)

    minimal = {
        "evidenceId": "evidence-minimal",
        "evidenceType": "other",
        "position": "neutral",
    }
    validated = PublicEvidenceArtifact.model_validate(minimal)
    assert validated.title is None
    assert validated.route is None
    assert validated.model_or_indication is None


def test_state_update_is_revalidated(tmp_path: Path) -> None:
    state = SignalState.model_validate_json(BASELINE_STATE.read_text())
    updated_risk = Risk.model_validate(
        {
            **state.risks[0].model_dump(mode="python"),
            "severity": "high",
        }
    )
    synthesis = DailySynthesis(
        agenda_item_id="agenda-cross-species-cns-delivery",
        material_change=True,
        rationale="A validated update is available.",
        risk_updates=[updated_risk],
        next_action="Confirm the revised risk assessment with a human reviewer.",
        agenda_status=AgendaStatus.OPEN,
        what_changed="Updated one risk assessment and next action.",
    )

    updated = DailyRunOrchestrator._apply_synthesis(
        state,
        synthesis,
        "run-state-update-test",
        state.generated_at,
    )

    assert updated.risks[0].severity.value == "high"
    assert "human reviewer" in (updated.program.next_proposed_action or "")


def test_agenda_item_can_be_resolved() -> None:
    agenda = DevelopmentAgenda.model_validate_json(
        (PROJECT_ROOT / "state" / "development-agenda.json").read_text()
    )
    task = select_highest_value_task(agenda)
    synthesis = DailySynthesis(
        agenda_item_id=task.item.agenda_item_id,
        material_change=False,
        rationale="The question was resolved without changing scientific entities.",
        agenda_status=AgendaStatus.RESOLVED,
        agenda_resolution="Resolution documented by a human-approved external result.",
        what_changed="Resolved one agenda item without changing scientific state.",
    )

    updated = DailyRunOrchestrator._update_agenda(
        agenda, task, synthesis, agenda.updated_at
    )

    item = next(entry for entry in updated.items if entry.agenda_item_id == task.item.agenda_item_id)
    assert item.status is AgendaStatus.RESOLVED
    assert item.resolution is not None
