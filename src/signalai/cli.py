"""Command-line entry points for SignalAI development runs and migrations."""

import json
from os import environ
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signalai.client import OpenAIResponsesClient
from signalai.clinic_intelligence import ClinicIngestor, DeterministicClinicExtractionClient
from signalai.clinic_index import ClinicIndexer, enrich_selected, import_clinic_profiles, import_seeds, load_seeds
from signalai.schemas.clinic_intelligence import ClinicIntelligenceDataset
from signalai.daily import DailyRunOrchestrator
from signalai.live import LiveRunOrchestrator
from signalai.material_change import repository_has_material_change
from signalai.legacy_migration import migrate_legacy_workspace, write_migration_outputs
from signalai.orchestrator import MilestoneOneOrchestrator
from signalai.publisher import publish_current_public_state
from signalai.clinic_simulation import advance_simulation
from signalai.design_lab import DesignLabOrchestrator
from signalai.product_strategy import ProductStrategyOrchestrator
from signalai.molecular_atlas import run_discovery
from signalai.schemas import (
    DevelopmentAgenda,
    SignalState,
    TherapeuticAssetWorkspace,
)


def main() -> None:
    root = Path.cwd()
    state = MilestoneOneOrchestrator(
        client=OpenAIResponsesClient.from_env(),
        evidence_path=root / "evidence" / "fixtures" / "sgl-001.json",
        runs_root=root / "runs",
        public_state_path=root / "public" / "signal-state.json",
        workspace_path=root / "state" / "asset-development.json",
        clinical_network_path=root / "state" / "clinical-network.json",
    ).run()
    print(f"Completed {state.run_id}")


def agenda_daily_main() -> None:
    root = Path.cwd()
    state, _ = DailyRunOrchestrator(
        client=OpenAIResponsesClient.from_env(),
        state_path=root / "state" / "signal-state.json",
        agenda_path=root / "state" / "development-agenda.json",
        runs_root=root / "runs",
        public_state_path=root / "public" / "signal-state.json",
        workspace_path=root / "state" / "asset-development.json",
        clinical_network_path=root / "state" / "clinical-network.json",
    ).run()
    print(f"Completed daily run {state.run_id}")


def daily_main() -> None:
    root = Path.cwd()
    run = LiveRunOrchestrator(client=OpenAIResponsesClient.from_env(), root=root).run()
    print(f"Completed live run {run.run_id}")


def design_lab_main() -> None:
    root = Path.cwd()
    if not environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY must be set for a Design Lab run")
    client = OpenAIResponsesClient(
        model=environ.get("OPENAI_DESIGN_MODEL") or environ.get("OPENAI_MODEL", ""),
        reasoning_effort=environ.get("OPENAI_DESIGN_REASONING_EFFORT", "low"),
        chair_reasoning_effort=environ.get("OPENAI_DESIGN_CHAIR_REASONING_EFFORT", "medium"),
        max_output_tokens=int(environ.get("OPENAI_DESIGN_MAX_OUTPUT_TOKENS", "5000")),
        chair_max_output_tokens=int(environ.get("OPENAI_DESIGN_CHAIR_MAX_OUTPUT_TOKENS", "2500")),
        chair_retry_max_output_tokens=int(environ.get("OPENAI_DESIGN_RETRY_MAX_OUTPUT_TOKENS", "6000")),
    )
    hypothesis = DesignLabOrchestrator(client=client, root=root).run()
    print(f"Completed design run {hypothesis.run_id}")


def strategy_main() -> None:
    root = Path.cwd()
    client = OpenAIResponsesClient(
        model=environ.get("OPENAI_STRATEGY_MODEL") or environ.get("OPENAI_MODEL", ""),
        reasoning_effort=environ.get("OPENAI_STRATEGY_REASONING_EFFORT", "low"),
        max_output_tokens=int(environ.get("OPENAI_STRATEGY_MAX_OUTPUT_TOKENS", "3000")),
        chair_max_output_tokens=int(environ.get("OPENAI_STRATEGY_CHAIR_MAX_OUTPUT_TOKENS", "2500")),
        chair_retry_max_output_tokens=int(environ.get("OPENAI_STRATEGY_RETRY_MAX_OUTPUT_TOKENS", "4000")),
    ) if environ.get("OPENAI_API_KEY") else None
    orchestrator = ProductStrategyOrchestrator(client=client, root=root)
    orchestrator.run()
    print(f"Completed strategy assessment {orchestrator.last_run_id}")


def should_commit_main() -> None:
    raise SystemExit(0 if repository_has_material_change(Path.cwd()) else 1)


def migrate_legacy_main() -> None:
    root = Path.cwd()
    legacy_root = Path(
        environ.get("SIGNALAI_LEGACY_ROOT", "/Users/raziel/Desktop/signalAgent")
    )
    workspace_path = root / "state" / "asset-development.json"
    workspace, report = migrate_legacy_workspace(
        cargo_path=legacy_root / "artifacts" / "data" / "mirna-cargo.json",
        formulation_path=legacy_root / "artifacts" / "data" / "formulation.json",
        jurisdictions_path=legacy_root / "state" / "jurisdictions.json",
        seed_workspace=TherapeuticAssetWorkspace.model_validate_json(
            workspace_path.read_text(encoding="utf-8")
        ),
        scientific_state=SignalState.model_validate_json(
            (root / "state" / "signal-state.json").read_text(encoding="utf-8")
        ),
        agenda=DevelopmentAgenda.model_validate_json(
            (root / "state" / "development-agenda.json").read_text(encoding="utf-8")
        ),
    )
    report_path = root / "reports" / "legacy-import-report.json"
    write_migration_outputs(
        workspace=workspace,
        report=report,
        workspace_path=workspace_path,
        report_path=report_path,
    )
    publish_current_public_state(root)
    print(f"Imported legacy data; report: {report_path}")


def publish_state_main() -> None:
    root = Path.cwd()
    state = publish_current_public_state(root)
    print(f"Published complete public state at {state.generated_at.isoformat()}")


def molecular_atlas_discover_main() -> None:
    root = Path.cwd()
    workspace = run_discovery(
        root,
        limit_per_query=int(environ.get("SIGNALAI_ATLAS_RESULTS_PER_QUERY", "5")),
    )
    publish_current_public_state(root)
    print(
        f"Molecular Atlas discovery completed: {len(workspace.sources)} candidate records; "
        "all require human review"
    )


def clinic_simulation_main(target: str | None = None) -> None:
    root = Path.cwd()
    simulated_date = datetime.fromisoformat(target).date() if target else None
    state = advance_simulation(root, simulated_date=simulated_date)
    publish_current_public_state(root)
    latest = state.days[-1]
    print(
        f"Completed synthetic clinic day {latest.protocol_day}: "
        f"{latest.determination.determination_type.value}"
    )


def _clinic_ingestor() -> ClinicIngestor:
    client = (
        OpenAIResponsesClient(
            model=environ.get("OPENAI_CLINIC_MODEL", "gpt-5-mini"),
            reasoning_effort=environ.get("OPENAI_CLINIC_REASONING_EFFORT", "low"),
            max_output_tokens=int(environ.get("OPENAI_CLINIC_MAX_OUTPUT_TOKENS", "2500")),
        )
        if environ.get("OPENAI_API_KEY") else DeterministicClinicExtractionClient()
    )
    return ClinicIngestor(
        root=Path.cwd(),
        client=client,
        max_pages=int(environ.get("SIGNALAI_CLINIC_MAX_PAGES", "5")),
        max_clinics=int(environ.get("SIGNALAI_CLINIC_MAX_BATCH", "10")),
    )


def clinic_ingest_main(url: str, *, refresh: bool = False) -> None:
    profile, _, changed = _clinic_ingestor().ingest(url, refresh=refresh)
    if changed:
        publish_current_public_state(Path.cwd())
    print(f"Clinic {profile.clinic_id}: {profile.profile_state.value if changed else 'unchanged'}")


def clinic_batch_main(path: str | None, *, scheduled: bool = False, refresh: bool = False) -> None:
    root = Path.cwd()
    if scheduled and path is None:
        path = str(root / "data" / "clinics" / "queue.txt")
    if not path:
        raise ValueError("clinic-batch requires a path to a URL list")
    source = Path(path)
    if not source.exists() and not scheduled:
        raise FileNotFoundError(source)
    if source.exists() and source.suffix == ".json":
        urls = [str(seed.url) for seed in load_seeds(source) if seed.enabled]
    else:
        urls = [line.strip() for line in source.read_text().splitlines() if line.strip() and not line.startswith("#")] if source.exists() else []
    limit = int(environ.get("SIGNALAI_CLINIC_MAX_BATCH", "6"))
    if scheduled:
        dataset_path = root / "data" / "clinics" / "clinics.json"
        dataset = ClinicIntelligenceDataset.model_validate_json(dataset_path.read_text()) if dataset_path.exists() else ClinicIntelligenceDataset()
        stale_before = datetime.now(timezone.utc) - timedelta(days=int(environ.get("SIGNALAI_CLINIC_STALE_DAYS", "30")))
        stale = sorted((item for item in dataset.profiles if item.last_checked_at < stale_before), key=lambda item: item.last_checked_at)
        urls = list(dict.fromkeys([*urls[:limit], *(str(item.website) for item in stale)]))[:limit]
        refresh = True
    if not urls:
        print("No clinic URLs scheduled; nothing to ingest")
        return
    ingestor = _clinic_ingestor()
    results = ingestor.batch(urls, refresh=refresh)
    for item in ingestor.batch_report:
        print(json.dumps(item, sort_keys=True))
    if any(changed for _, _, changed in results):
        publish_current_public_state(root)
    print(f"Clinic batch: {len(results)} processed, {sum(changed for _, _, changed in results)} changed")


def clinic_index_main(command, target=None, *, limit=None, country=None, region=None, priority=None, only_new=False):
    root = Path.cwd()
    path = Path(target) if target else root / "data/clinic-seeds.json"
    if command in {"clinic-import", "clinic-enrich"} and path.resolve() != (root / "data/clinic-seeds.json").resolve():
        raise ValueError(f"{command} uses only the canonical data/clinic-seeds.json")
    if command == "clinic-import":
        counts = import_clinic_profiles(root, path)
        print(json.dumps(counts, sort_keys=True))
        if counts["imported"] or counts["merged"]:
            publish_current_public_state(root)
        return
    if command == "clinic-discover":
        if not target:
            raise ValueError("clinic-discover requires a supplied directory JSON or URL-list file")
        print(f"Imported {import_seeds(root, path, limit=1000 if limit is None else limit, country=country, region=region, priority=priority)} new seeds")
        return
    seeds = load_seeds(path)
    if command == "clinic-index":
        report = ClinicIndexer(root=root).index(seeds, limit=25 if limit is None else limit, country=country, region=region, priority=priority, only_new=only_new)
        for item in report:
            print(json.dumps(item, sort_keys=True))
        changed = any(item["status"] == "indexed" for item in report)
    else:
        ingestor = _clinic_ingestor()
        results = enrich_selected(ingestor, seeds, limit=10 if limit is None else limit, country=country, region=region, priority=priority, only_new=only_new)
        for record in ingestor.batch_report:
            print(json.dumps(record, sort_keys=True))
        changed = any(item[2] for item in results)
        print(f"Enriched {sum(item[2] for item in results)} clinics")
    if changed:
        publish_current_public_state(root)


if __name__ == "__main__":
    main()
