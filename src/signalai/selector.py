"""Deterministic therapeutic-value task selection."""

from __future__ import annotations

from datetime import datetime, timezone

from signalai.schemas import (
    AgendaItem,
    AgendaItemType,
    AgendaPriority,
    AgendaStatus,
    DevelopmentAgenda,
    SelectedTask,
)


_TYPE_ORDER = {
    AgendaItemType.OPEN_TRANSLATIONAL_RISK: 0,
    AgendaItemType.PENDING_DECISION: 1,
    AgendaItemType.JURISDICTION_QUESTION: 2,
    AgendaItemType.UNRESOLVED_SCIENTIFIC_QUESTION: 3,
    AgendaItemType.FORMULATION_QUESTION: 4,
    AgendaItemType.EXPERIMENT_PROPOSAL: 5,
    AgendaItemType.EVIDENCE_GAP: 6,
    AgendaItemType.ACTIVE_HYPOTHESIS: 7,
}

_PRIORITY_ORDER = {
    AgendaPriority.CRITICAL: 0,
    AgendaPriority.HIGH: 1,
    AgendaPriority.MODERATE: 2,
    AgendaPriority.LOW: 3,
}


class NoOpenAgendaItemsError(RuntimeError):
    pass


def _rank(item: AgendaItem) -> tuple[int, int, datetime, datetime, str]:
    never_evaluated = datetime.min.replace(tzinfo=timezone.utc)
    return (
        _TYPE_ORDER[item.type],
        _PRIORITY_ORDER[item.priority],
        item.last_evaluated_at or never_evaluated,
        item.created_at,
        item.agenda_item_id,
    )


def select_highest_value_task(agenda: DevelopmentAgenda) -> SelectedTask:
    eligible = [item for item in agenda.items if item.status == AgendaStatus.OPEN]
    if not eligible:
        raise NoOpenAgendaItemsError("development agenda has no open items")
    selected = min(eligible, key=_rank)
    return SelectedTask(
        item=selected,
        selection_reason=(
            f"Selected {selected.type.value} at {selected.priority.value} priority. "
            "Ranking favors program-threatening translational risks, then blocking "
            "decisions, jurisdiction pathways, evidence contradictions, formulation and delivery questions, "
            "experiment design, evidence gaps, and lower-priority refinement."
        ),
    )
