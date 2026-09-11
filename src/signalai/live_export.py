"""Sanitize canonical live-run history for public consumption."""

from signalai.schemas.live import DevelopmentDocket, LiveRun, LiveRunHistory, MatterStatus
from signalai.schemas.public_live import (
    LiveIntelligenceStatus,
    PublicCurrentMatter,
    PublicLiveIntelligence,
    PublicLiveRun,
)
from signalai.schemas.public_product import (
    AccessTier,
    IntelligenceFeedType,
    IntelligenceImportance,
    PublicIntelligenceFeedItem,
)


def export_live_intelligence(
    docket: DevelopmentDocket,
    history: LiveRunHistory,
) -> PublicLiveIntelligence:
    latest = history.runs[-1] if history.runs else None
    open_matters = [item for item in docket.matters if item.status is MatterStatus.OPEN]
    current = open_matters[0] if open_matters else (latest.selected_matter if latest else None)
    return PublicLiveIntelligence(
        status=LiveIntelligenceStatus.ACTIVE if current is not None else LiveIntelligenceStatus.IDLE,
        currentMatter=PublicCurrentMatter.from_internal(current) if current else None,
        latestRun=PublicLiveRun.from_internal(latest) if latest else None,
        recentRuns=[PublicLiveRun.from_internal(item) for item in reversed(history.runs[-10:])],
    )


def live_run_feed_item(run: LiveRun) -> PublicIntelligenceFeedItem:
    kind = IntelligenceFeedType.NO_MATERIAL_CHANGE
    if run.state_changed:
        kind = IntelligenceFeedType.PROGRAM_STATE_CHANGE
    headline = (
        f"{run.selected_matter.title}: state updated"
        if run.state_changed
        else f"{run.selected_matter.title}: no material change"
    )
    return PublicIntelligenceFeedItem(
        itemId=f"feed-live-{run.run_id}",
        type=kind,
        title=headline,
        summary=run.what_changed,
        domain=run.selected_matter.domain.value,
        programId=run.program_id,
        importance=(
            IntelligenceImportance.HIGH
            if run.selected_matter.advancement_value.value in {"critical", "high"}
            else IntelligenceImportance.MODERATE
        ),
        accessTier=AccessTier.PUBLIC,
        createdAt=run.completed_at,
        linkedArtifactIds=run.artifact_ids,
        linkedReviewIds=[run.run_id],
        reasonEvidence=list(
            dict.fromkeys(
                run.strongest_supporting_evidence_ids
                + run.strongest_contradictory_evidence_ids
            )
        ),
        determination=run.chair_determination,
        nextAction=run.next_action,
        runId=run.run_id,
    )


def merge_live_feed(
    existing: list[PublicIntelligenceFeedItem], history: LiveRunHistory
) -> list[PublicIntelligenceFeedItem]:
    combined = {item.item_id: item for item in existing}
    for run in history.runs:
        item = live_run_feed_item(run)
        combined[item.item_id] = item
    return sorted(combined.values(), key=lambda item: (item.created_at, item.item_id), reverse=True)
