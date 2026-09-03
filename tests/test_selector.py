from datetime import datetime, timezone

import pytest

from signalai.schemas import (
    AgendaItem,
    AgendaItemType,
    AgendaPriority,
    AgendaStatus,
    DevelopmentAgenda,
)
from signalai.selector import NoOpenAgendaItemsError, select_highest_value_task


NOW = datetime(2026, 9, 3, tzinfo=timezone.utc)


def _item(
    item_id: str,
    item_type: AgendaItemType,
    priority: AgendaPriority,
    status: AgendaStatus = AgendaStatus.OPEN,
) -> AgendaItem:
    return AgendaItem(
        agenda_item_id=item_id,
        type=item_type,
        question=f"Evaluate {item_id}",
        priority=priority,
        rationale="Therapeutic-development test fixture.",
        status=status,
        created_at=NOW,
    )


def test_program_threatening_risk_precedes_novel_refinement() -> None:
    agenda = DevelopmentAgenda(
        program_id="SGL-001",
        updated_at=NOW,
        items=[
            _item(
                "novel-hypothesis",
                AgendaItemType.ACTIVE_HYPOTHESIS,
                AgendaPriority.CRITICAL,
            ),
            _item(
                "delivery-risk",
                AgendaItemType.OPEN_TRANSLATIONAL_RISK,
                AgendaPriority.HIGH,
            ),
        ],
    )

    selected = select_highest_value_task(agenda)

    assert selected.item.agenda_item_id == "delivery-risk"


def test_selector_ignores_resolved_items() -> None:
    resolved = AgendaItem(
        agenda_item_id="resolved-risk",
        type=AgendaItemType.OPEN_TRANSLATIONAL_RISK,
        question="Evaluate resolved risk",
        priority=AgendaPriority.CRITICAL,
        rationale="Therapeutic-development test fixture.",
        status=AgendaStatus.RESOLVED,
        created_at=NOW,
        resolution="Closed by evidence.",
    )
    agenda = DevelopmentAgenda(program_id="SGL-001", updated_at=NOW, items=[resolved])

    with pytest.raises(NoOpenAgendaItemsError):
        select_highest_value_task(agenda)
