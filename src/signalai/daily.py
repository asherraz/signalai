"""Autonomous daily therapeutic-development orchestration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter

from signalai.agents.daily_prompts import (
    DAILY_ANALYSIS_INSTRUCTIONS,
    DAILY_CRITIQUE_INSTRUCTIONS,
    DAILY_SYNTHESIS_INSTRUCTIONS,
)
from signalai.client import ModelClient
from signalai.schemas import (
    AgentRun,
    AgendaItem,
    AgendaStatus,
    Claim,
    DailyAnalysis,
    DailyCritique,
    DailySynthesis,
    DevelopmentAgenda,
    PublicChange,
    PublicSignalState,
    Risk,
    RunStatus,
    SelectedTask,
    SignalState,
    WhatChanged,
)
from signalai.selector import select_highest_value_task
from signalai.storage import RunStore, new_run_id, publish_json


RecordT = TypeVar("RecordT", bound=BaseModel)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load(path: Path, model_type: type[RecordT]) -> RecordT:
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))


def _json(value: Any) -> str:
    payload = TypeAdapter(Any).dump_python(value, mode="json")
    return json.dumps(payload, indent=2, sort_keys=True)


def _merge_records(
    current: list[RecordT], updates: list[RecordT], id_field: str
) -> list[RecordT]:
    merged = {getattr(item, id_field): item for item in current}
    for update in updates:
        merged[getattr(update, id_field)] = update
    return list(merged.values())


class DailyRunOrchestrator:
    def __init__(
        self,
        *,
        client: ModelClient,
        state_path: Path,
        agenda_path: Path,
        runs_root: Path,
        public_state_path: Path,
    ) -> None:
        self.client = client
        self.state_path = state_path
        self.agenda_path = agenda_path
        self.runs_root = runs_root
        self.public_state_path = public_state_path

    def run(self, *, run_id: str | None = None) -> tuple[SignalState, DevelopmentAgenda]:
        active_run_id = run_id or new_run_id()
        started_at = _utc_now()
        store = RunStore(self.runs_root, active_run_id)
        artifacts: list[str] = []

        start = AgentRun(
            run_id=active_run_id,
            agent_name="daily-therapeutic-development",
            program_id="SGL-001",
            status=RunStatus.RUNNING,
            started_at=started_at,
        )
        artifacts.append(str(store.write_json("00-run-start.json", start)))

        try:
            current_state = _load(self.state_path, SignalState)
            agenda = _load(self.agenda_path, DevelopmentAgenda)
            self._validate_agenda_references(agenda, current_state)
            artifacts.append(str(store.write_json("01-current-state.json", current_state)))
            artifacts.append(str(store.write_json("02-current-agenda.json", agenda)))

            selected = select_highest_value_task(agenda)
            artifacts.append(str(store.write_json("03-selected-task.json", selected)))

            analysis = self.client.generate(
                instructions=DAILY_ANALYSIS_INSTRUCTIONS,
                input_text=_json({"task": selected, "state": current_state}),
                output_type=DailyAnalysis,
            )
            self._validate_analysis(analysis, selected, current_state)
            artifacts.append(str(store.write_json("04-analysis.json", analysis)))

            critique = self.client.generate(
                instructions=DAILY_CRITIQUE_INSTRUCTIONS,
                input_text=_json(
                    {"task": selected, "state": current_state, "analysis": analysis}
                ),
                output_type=DailyCritique,
            )
            self._validate_critique(critique, selected, current_state)
            artifacts.append(str(store.write_json("05-critique.json", critique)))

            synthesis = self.client.generate(
                instructions=DAILY_SYNTHESIS_INSTRUCTIONS,
                input_text=_json(
                    {
                        "task": selected,
                        "state": current_state,
                        "analysis": analysis,
                        "critique": critique,
                    }
                ),
                output_type=DailySynthesis,
            )
            self._validate_synthesis(synthesis, selected, current_state)
            artifacts.append(str(store.write_json("06-synthesis.json", synthesis)))

            now = _utc_now()
            updated_state = self._apply_synthesis(
                current_state, synthesis, active_run_id, now
            )
            updated_agenda = self._update_agenda(agenda, selected, synthesis, now)
            changed = WhatChanged(
                run_id=active_run_id,
                agenda_item_id=selected.item.agenda_item_id,
                material_change=synthesis.material_change,
                summary=synthesis.what_changed,
                created_at=now,
            )
            public_state = PublicSignalState.from_internal(
                updated_state,
                changes=[
                    PublicChange(
                        changeId=f"{active_run_id}-daily-change",
                        summary=synthesis.what_changed,
                    )
                ],
                completed_stages=["selection", "analysis", "critique", "synthesis"],
            )

            artifacts.append(str(store.write_json("07-updated-state.json", updated_state)))
            artifacts.append(str(store.write_json("08-updated-agenda.json", updated_agenda)))
            artifacts.append(str(store.write_json("09-what-changed.json", changed)))
            artifacts.append(
                str(store.write_json("10-public-signal-state.json", public_state))
            )

            publish_json(self.state_path, updated_state)
            publish_json(self.agenda_path, updated_agenda)
            publish_json(self.public_state_path, public_state)

            completed = AgentRun(
                run_id=active_run_id,
                agent_name="daily-therapeutic-development",
                program_id="SGL-001",
                status=RunStatus.SUCCEEDED,
                started_at=started_at,
                completed_at=_utc_now(),
                input_artifact_paths=artifacts[1:3],
                intermediate_artifact_paths=artifacts[3:7],
                output_artifact_paths=artifacts[7:]
                + [str(self.state_path), str(self.agenda_path), str(self.public_state_path)],
            )
            store.write_json("99-run-complete.json", completed)
            return updated_state, updated_agenda
        except Exception as exc:
            failed = AgentRun(
                run_id=active_run_id,
                agent_name="daily-therapeutic-development",
                program_id="SGL-001",
                status=RunStatus.FAILED,
                started_at=started_at,
                completed_at=_utc_now(),
                intermediate_artifact_paths=artifacts[1:],
                error=f"{type(exc).__name__}: {exc}",
            )
            store.write_json("99-run-failed.json", failed)
            raise

    @staticmethod
    def _validate_agenda_references(
        agenda: DevelopmentAgenda, state: SignalState
    ) -> None:
        if agenda.program_id != state.program.program_id:
            raise ValueError("agenda and scientific state belong to different programs")
        known_claims = {item.claim_id for item in state.claims}
        known_evidence = {item.evidence_id for item in state.evidence}
        known_hypotheses = {state.hypothesis.hypothesis_id}
        known_risks = {item.risk_id for item in state.risks}
        for item in agenda.items:
            if set(item.linked_claim_ids) - known_claims:
                raise ValueError(f"agenda item {item.agenda_item_id} links unknown claims")
            if set(item.linked_evidence_ids) - known_evidence:
                raise ValueError(f"agenda item {item.agenda_item_id} links unknown evidence")
            if set(item.linked_hypothesis_ids) - known_hypotheses:
                raise ValueError(f"agenda item {item.agenda_item_id} links unknown hypotheses")
            if set(item.linked_risk_ids) - known_risks:
                raise ValueError(f"agenda item {item.agenda_item_id} links unknown risks")

    @staticmethod
    def _validate_analysis(
        analysis: DailyAnalysis, selected: SelectedTask, state: SignalState
    ) -> None:
        if analysis.agenda_item_id != selected.item.agenda_item_id:
            raise ValueError("analysis references a different agenda item")
        DailyRunOrchestrator._validate_references(
            analysis.claim_ids, analysis.evidence_ids, state
        )

    @staticmethod
    def _validate_critique(
        critique: DailyCritique, selected: SelectedTask, state: SignalState
    ) -> None:
        if critique.agenda_item_id != selected.item.agenda_item_id:
            raise ValueError("critique references a different agenda item")
        DailyRunOrchestrator._validate_references([], critique.evidence_ids, state)

    @staticmethod
    def _validate_synthesis(
        synthesis: DailySynthesis, selected: SelectedTask, state: SignalState
    ) -> None:
        if synthesis.agenda_item_id != selected.item.agenda_item_id:
            raise ValueError("synthesis references a different agenda item")
        known_evidence = {item.evidence_id for item in state.evidence}
        for claim in synthesis.claim_updates:
            if set(claim.evidence_ids) - known_evidence:
                raise ValueError("claim update references unknown evidence")
        if synthesis.hypothesis_update and (
            set(synthesis.hypothesis_update.evidence_ids) - known_evidence
        ):
            raise ValueError("hypothesis update references unknown evidence")
        for risk in synthesis.risk_updates:
            if set(risk.evidence_ids) - known_evidence:
                raise ValueError("risk update references unknown evidence")
        if synthesis.decision_proposal and (
            set(synthesis.decision_proposal.evidence_ids) - known_evidence
        ):
            raise ValueError("decision proposal references unknown evidence")

    @staticmethod
    def _validate_references(
        claim_ids: list[str], evidence_ids: list[str], state: SignalState
    ) -> None:
        if set(claim_ids) - {item.claim_id for item in state.claims}:
            raise ValueError("daily output references unknown claims")
        if set(evidence_ids) - {item.evidence_id for item in state.evidence}:
            raise ValueError("daily output references unknown evidence")

    @staticmethod
    def _apply_synthesis(
        state: SignalState,
        synthesis: DailySynthesis,
        run_id: str,
        now: datetime,
    ) -> SignalState:
        claims = _merge_records(state.claims, synthesis.claim_updates, "claim_id")
        risks = _merge_records(state.risks, synthesis.risk_updates, "risk_id")
        hypothesis = synthesis.hypothesis_update or state.hypothesis
        decision = synthesis.decision_proposal or state.decision

        program_data = state.program.model_dump(mode="python")
        program_data.update(
            updated_at=now,
            claim_ids=[claim.claim_id for claim in claims],
            hypothesis_ids=list(
                dict.fromkeys(state.program.hypothesis_ids + [hypothesis.hypothesis_id])
            ),
            risk_ids=[risk.risk_id for risk in risks],
            decision_ids=list(
                dict.fromkeys(state.program.decision_ids + [decision.decision_id])
            ),
        )
        if synthesis.next_action is not None:
            program_data["next_proposed_action"] = synthesis.next_action

        return SignalState.model_validate(
            {
                "schema_version": state.schema_version,
                "run_id": run_id,
                "generated_at": now,
                "program": program_data,
                "evidence": state.evidence,
                "claims": claims,
                "hypothesis": hypothesis,
                "critique": state.critique,
                "risks": risks,
                "decision": decision,
            }
        )

    @staticmethod
    def _update_agenda(
        agenda: DevelopmentAgenda,
        selected: SelectedTask,
        synthesis: DailySynthesis,
        now: datetime,
    ) -> DevelopmentAgenda:
        items: list[AgendaItem] = []
        for item in agenda.items:
            if item.agenda_item_id != selected.item.agenda_item_id:
                items.append(item)
                continue
            item_data = item.model_dump(mode="python")
            item_data.update(
                status=synthesis.agenda_status,
                last_evaluated_at=now,
                resolution=synthesis.agenda_resolution,
            )
            items.append(AgendaItem.model_validate(item_data))
        return DevelopmentAgenda(
            program_id=agenda.program_id,
            version=agenda.version,
            updated_at=now,
            items=items,
        )
