"""One-matter autonomous therapeutic-development review cycle."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from signalai.agents.live_prompts import (
    LIVE_ADVERSARY_INSTRUCTIONS,
    LIVE_ANALYSIS_INSTRUCTIONS,
    LIVE_CHAIR_INSTRUCTIONS,
    LIVE_CHAIR_REPAIR_INSTRUCTIONS,
    LIVE_VERIFIER_INSTRUCTIONS,
)
from signalai.client import ModelClient, StructuredOutputError
from signalai.daily import DailyRunOrchestrator
from signalai.determination import derive_chair_determination
from signalai.live_selector import select_current_matter, select_reviewers
from signalai.publisher import build_current_public_state
from signalai.schemas import AgentRun, RunStatus, SignalState
from signalai.schemas.live import (
    DevelopmentDocket,
    DevelopmentMatter,
    LiveAdversaryReview,
    LiveAnalysis,
    LiveChairDetermination,
    LiveChairRecommendation,
    LiveRun,
    LiveRunHistory,
    LiveVerification,
    MatterStatus,
    ReviewerRole,
)
from signalai.storage import RunStore, new_run_id, publish_json


T = TypeVar("T", bound=BaseModel)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load(path: Path, model: type[T]) -> T:
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def _json(value: Any) -> str:
    return json.dumps(TypeAdapter(Any).dump_python(value, mode="json"), sort_keys=True)


def _usage_payload(run_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    numeric_fields = (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_tokens",
    )
    totals = {
        field: sum(int(item.get(field) or 0) for item in records) for field in numeric_fields
    }
    costs = [item.get("estimated_api_cost_usd") for item in records]
    totals["estimated_api_cost_usd"] = (
        round(sum(float(value) for value in costs if value is not None), 8)
        if any(value is not None for value in costs)
        else None
    )
    return {
        "run_id": run_id,
        "currency": "USD",
        "estimate_only": True,
        "attempts": records,
        "totals": totals,
    }


def _semantic_conflicts(error: Exception) -> list[str]:
    if isinstance(error, StructuredOutputError) and error.conflicts:
        return error.conflicts
    if isinstance(error, ValidationError):
        return [
            f"{'.'.join(str(part) for part in item.get('loc', ())) or 'output'}: "
            f"{item.get('msg', 'invalid value')}"
            for item in error.errors(include_input=False, include_url=False)
        ]
    return [str(error)]


def _compact_context(state: SignalState, matter: DevelopmentMatter) -> dict[str, Any]:
    evidence_ids = set(matter.linked_evidence_ids)
    risk_ids = set(matter.linked_risk_ids)
    hypothesis_ids = set(matter.linked_hypothesis_ids)
    return {
        "program": state.program,
        "matter": matter,
        "evidence": [item for item in state.evidence if item.evidence_id in evidence_ids],
        "claims": [
            item for item in state.claims if evidence_ids.intersection(item.evidence_ids)
        ],
        "hypothesis": state.hypothesis if state.hypothesis.hypothesis_id in hypothesis_ids else None,
        "risks": [item for item in state.risks if item.risk_id in risk_ids],
    }


class LiveRunOrchestrator:
    """Run a bounded panel and publish only after every artifact validates."""

    def __init__(
        self,
        *,
        client: ModelClient,
        root: Path,
        now_factory=_now,
    ) -> None:
        self.client = client
        self.root = root
        self.now_factory = now_factory

    def run(self, *, run_id: str | None = None) -> LiveRun:
        active_id = run_id or new_run_id()
        started_at = self.now_factory()
        store = RunStore(self.root / "runs", active_id)
        artifacts: list[str] = []
        start = AgentRun(
            run_id=active_id,
            agent_name="live-autonomous-intelligence",
            program_id="SGL-001",
            status=RunStatus.RUNNING,
            started_at=started_at,
        )
        artifacts.append(str(store.write_json("00-run-start.json", start)))
        try:
            state = _load(self.root / "state" / "signal-state.json", SignalState)
            docket = _load(self.root / "state" / "development-docket.json", DevelopmentDocket)
            history_path = self.root / "state" / "live-runs.json"
            history = (
                _load(history_path, LiveRunHistory)
                if history_path.exists()
                else LiveRunHistory(program_id=state.program.program_id, updated_at=started_at)
            )
            self._validate_docket(docket, state)
            selected, why = select_current_matter(docket)
            reviewers = select_reviewers(selected)
            context = _compact_context(state, selected)
            artifacts.extend(
                [
                    str(store.write_json("01-compact-state.json", context)),
                    str(store.write_json("02-development-docket.json", docket)),
                    str(store.write_json("03-selected-matter.json", selected)),
                    str(store.write_json("04-reviewer-panel.json", {"reviewers": reviewers, "why_selected": why})),
                ]
            )
            analysis = self.client.generate(
                instructions=LIVE_ANALYSIS_INSTRUCTIONS,
                input_text=_json({"context": context, "reviewers": reviewers[:-3]}),
                output_type=LiveAnalysis,
            )
            self._validate_analysis(analysis, selected, reviewers, state)
            artifacts.append(str(store.write_json("05-analysis.json", analysis)))
            verification = self.client.generate(
                instructions=LIVE_VERIFIER_INSTRUCTIONS,
                input_text=_json({"context": context, "analysis": analysis}),
                output_type=LiveVerification,
            )
            self._validate_evidence_refs(verification.verified_evidence_ids, state)
            if verification.matter_id != selected.matter_id:
                raise ValueError("verification references a different matter")
            artifacts.append(str(store.write_json("06-verification.json", verification)))
            adversary = self.client.generate(
                instructions=LIVE_ADVERSARY_INSTRUCTIONS,
                input_text=_json({"context": context, "analysis": analysis, "verification": verification}),
                output_type=LiveAdversaryReview,
            )
            self._validate_evidence_refs(adversary.disconfirming_evidence_ids, state)
            if adversary.matter_id != selected.matter_id:
                raise ValueError("adversary references a different matter")
            artifacts.append(str(store.write_json("07-adversary.json", adversary)))
            chair_input = _json(
                {
                    "matter": selected,
                    "current_ids": {
                        "hypothesis": state.hypothesis.hypothesis_id,
                        "risks": [item.risk_id for item in state.risks],
                        "decision": state.decision.decision_id,
                        "evidence": selected.linked_evidence_ids,
                    },
                    "analysis": analysis,
                    "verification": verification,
                    "adversary": adversary,
                }
            )
            try:
                recommendation, chair_retried, repair_conflicts = self._generate_chair(
                    chair_input
                )
            except StructuredOutputError as exc:
                artifacts.append(
                    str(
                        store.write_json(
                            "08-private-chair-failure.json",
                            {
                                "stage": "LiveChairDetermination",
                                "attempts": 2,
                                "status": "failed",
                                "reason": "incomplete_or_malformed_structured_output",
                                "validation_conflicts": exc.conflicts,
                            },
                        )
                    )
                )
                raise
            if recommendation.matter_id != selected.matter_id:
                raise ValueError("chair references a different matter")
            self._validate_evidence_refs(recommendation.supporting_evidence_ids, state)
            chair = derive_chair_determination(recommendation, state)
            synthesis = chair.result.synthesis
            DailyRunOrchestrator._validate_synthesis(
                synthesis, _matter_as_selected(selected), state
            )
            artifacts.append(str(store.write_json("08-chair-determination.json", chair)))
            if chair_retried:
                artifacts.append(
                    str(
                        store.write_json(
                            "08-chair-repair.json",
                            {
                                "attempts": 2,
                                "result": "validated",
                                "schema": "LiveChairRecommendation",
                                "validation_conflicts": repair_conflicts,
                            },
                        )
                    )
                )

            completed_at = self.now_factory()
            updated_state = (
                DailyRunOrchestrator._apply_synthesis(state, synthesis, active_id, completed_at)
                if synthesis.material_change or chair.result.operational_state_changed
                else state
            )
            completed_matter = DevelopmentMatter.model_validate(
                {
                    **selected.model_dump(mode="python"),
                    "status": MatterStatus.COMPLETED,
                    "selected_at": started_at,
                    "completed_at": completed_at,
                    "determination": chair.result.determination,
                    "next_action": synthesis.next_action or analysis.proposed_next_action,
                }
            )
            updated_docket = DevelopmentDocket(
                program_id=docket.program_id,
                version=docket.version,
                updated_at=completed_at,
                matters=[completed_matter if item.matter_id == selected.matter_id else item for item in docket.matters],
            )
            run = LiveRun(
                run_id=active_id,
                program_id=state.program.program_id,
                started_at=started_at,
                completed_at=completed_at,
                selected_matter=completed_matter,
                why_selected=why,
                reviewers_convened=reviewers,
                reviewer_conclusions=analysis.reviewer_conclusions,
                strongest_supporting_evidence_ids=analysis.strongest_supporting_evidence_ids,
                strongest_contradictory_evidence_ids=analysis.strongest_contradictory_evidence_ids,
                adversary_objection=adversary.strongest_objection,
                chair_determination=chair.result.determination,
                state_changed=synthesis.material_change or chair.result.operational_state_changed,
                change_scope=chair.result.change_scope,
                scientific_state_changed=chair.result.scientific_state_changed,
                operational_state_changed=chair.result.operational_state_changed,
                what_changed=synthesis.what_changed,
                next_action=synthesis.next_action or analysis.proposed_next_action,
                artifact_ids=[f"{active_id}:{Path(item).name}" for item in artifacts[1:]],
            )
            updated_history = LiveRunHistory(
                program_id=history.program_id,
                updated_at=completed_at,
                runs=[*history.runs, run],
            )
            artifacts.extend(
                [
                    str(store.write_json("09-live-run.json", run)),
                    str(store.write_json("10-updated-state.json", updated_state)),
                    str(store.write_json("11-updated-docket.json", updated_docket)),
                ]
            )
            usage = getattr(self.client, "usage_records", None)
            if usage:
                artifacts.append(
                    str(
                        store.write_json(
                            "98-private-usage.json", _usage_payload(active_id, usage)
                        )
                    )
                )

            public = self._build_staged_public(updated_state, updated_docket, updated_history)
            artifacts.append(str(store.write_json("12-public-signal-state.json", public)))
            completed = AgentRun(
                run_id=active_id,
                agent_name="live-autonomous-intelligence",
                program_id=state.program.program_id,
                status=RunStatus.SUCCEEDED,
                started_at=started_at,
                completed_at=completed_at,
                input_artifact_paths=artifacts[1:3],
                intermediate_artifact_paths=artifacts[3:8],
                output_artifact_paths=artifacts[8:],
            )
            store.write_json("99-run-complete.json", completed)
            publish_json(self.root / "state" / "signal-state.json", updated_state)
            publish_json(self.root / "state" / "development-docket.json", updated_docket)
            publish_json(history_path, updated_history)
            publish_json(self.root / "public" / "signal-state.json", public)
            return run
        except Exception as exc:
            usage = getattr(self.client, "usage_records", None)
            usage_path = store.path / "98-private-usage.json"
            if usage and not usage_path.exists():
                store.write_json(
                    "98-private-usage.json", _usage_payload(active_id, usage)
                )
            store.write_json(
                "99-run-failed.json",
                AgentRun(
                    run_id=active_id,
                    agent_name="live-autonomous-intelligence",
                    program_id="SGL-001",
                    status=RunStatus.FAILED,
                    started_at=started_at,
                    completed_at=self.now_factory(),
                    intermediate_artifact_paths=artifacts[1:],
                    error=f"{type(exc).__name__}: {exc}",
                ),
            )
            raise

    def _generate_chair(
        self, chair_input: str
    ) -> tuple[LiveChairRecommendation, bool, list[str]]:
        try:
            return (
                self.client.generate(
                    instructions=LIVE_CHAIR_INSTRUCTIONS,
                    input_text=chair_input,
                    output_type=LiveChairRecommendation,
                ),
                False,
                [],
            )
        except (StructuredOutputError, ValidationError) as first_error:
            conflicts = _semantic_conflicts(first_error)
            repair = getattr(self.client, "repair", None)
            try:
                if repair is None:
                    raise StructuredOutputError("model client does not support structured repair")
                return (
                    repair(
                        instructions=(
                            LIVE_CHAIR_REPAIR_INSTRUCTIONS
                            + "\nValidation conflicts:\n- "
                            + "\n- ".join(conflicts)
                        ),
                        input_text=chair_input,
                        output_type=LiveChairRecommendation,
                    ),
                    True,
                    conflicts,
                )
            except (StructuredOutputError, ValidationError) as retry_error:
                raise StructuredOutputError(
                    "Chair structured output failed after one repair attempt",
                    conflicts=[*conflicts, *_semantic_conflicts(retry_error)],
                ) from retry_error

    def _build_staged_public(self, state, docket, history):
        with tempfile.TemporaryDirectory(dir=self.root) as raw:
            staged = Path(raw)
            (staged / "state").mkdir()
            for name, value in (
                ("signal-state.json", state),
                ("development-docket.json", docket),
                ("live-runs.json", history),
            ):
                publish_json(staged / "state" / name, value)
            for name in ("asset-development.json", "clinical-network.json"):
                (staged / "state" / name).symlink_to(self.root / "state" / name)
            (staged / "runs").symlink_to(self.root / "runs")
            return build_current_public_state(staged, generated_at=self.now_factory())

    @staticmethod
    def _validate_docket(docket: DevelopmentDocket, state: SignalState) -> None:
        if docket.program_id != state.program.program_id:
            raise ValueError("docket and state belong to different programs")
        evidence = {item.evidence_id for item in state.evidence}
        risks = {item.risk_id for item in state.risks}
        hypotheses = {state.hypothesis.hypothesis_id}
        for matter in docket.matters:
            if set(matter.linked_evidence_ids) - evidence:
                raise ValueError(f"matter {matter.matter_id} references unknown evidence")
            if set(matter.linked_risk_ids) - risks:
                raise ValueError(f"matter {matter.matter_id} references unknown risks")
            if set(matter.linked_hypothesis_ids) - hypotheses:
                raise ValueError(f"matter {matter.matter_id} references unknown hypotheses")

    @staticmethod
    def _validate_evidence_refs(ids: list[str], state: SignalState) -> None:
        if set(ids) - {item.evidence_id for item in state.evidence}:
            raise ValueError("live output references unknown evidence")

    @classmethod
    def _validate_analysis(cls, analysis, matter, reviewers, state) -> None:
        if analysis.matter_id != matter.matter_id:
            raise ValueError("analysis references a different matter")
        allowed = set(reviewers) - {ReviewerRole.VERIFIER, ReviewerRole.ADVERSARY, ReviewerRole.CHAIR}
        if {item.reviewer_role for item in analysis.reviewer_conclusions} - allowed:
            raise ValueError("analysis contains a conclusion from an unconvened reviewer")
        for item in analysis.reviewer_conclusions:
            cls._validate_evidence_refs(item.evidence_ids, state)
        cls._validate_evidence_refs(analysis.strongest_supporting_evidence_ids, state)
        cls._validate_evidence_refs(analysis.strongest_contradictory_evidence_ids, state)


def _matter_as_selected(matter: DevelopmentMatter):
    """Adapter for reusing the established synthesis reference validator."""
    from signalai.schemas import AgendaItem, AgendaItemType, AgendaPriority, SelectedTask

    return SelectedTask(
        item=AgendaItem(
            agenda_item_id=matter.matter_id,
            type=AgendaItemType.UNRESOLVED_SCIENTIFIC_QUESTION,
            question=matter.question,
            priority=AgendaPriority.HIGH,
            rationale=matter.why_it_matters,
            created_at=matter.selected_at or _now(),
        ),
        selection_reason="Live matter adapter",
    )
