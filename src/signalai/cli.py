"""Command-line entry points for SignalAI development runs and migrations."""

from os import environ
from pathlib import Path

from signalai.client import OpenAIResponsesClient
from signalai.clinical_network_export import export_clinical_network
from signalai.daily import DailyRunOrchestrator
from signalai.legacy_migration import migrate_legacy_workspace, write_migration_outputs
from signalai.orchestrator import MilestoneOneOrchestrator
from signalai.product_export import export_product_layer
from signalai.schemas import (
    ClinicalNetworkState,
    DevelopmentAgenda,
    PublicSignalState,
    SignalState,
    TherapeuticAssetWorkspace,
)
from signalai.storage import publish_json
from signalai.workspace_export import export_workspace


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


def daily_main() -> None:
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
    public_path = root / "public" / "signal-state.json"
    public = PublicSignalState.model_validate_json(public_path.read_text(encoding="utf-8"))
    cargo, formulation, jurisdictions = export_workspace(workspace)
    scientific_state = SignalState.model_validate_json(
        (root / "state" / "signal-state.json").read_text(encoding="utf-8")
    )
    clinical_state = ClinicalNetworkState.model_validate_json(
        (root / "state" / "clinical-network.json").read_text(encoding="utf-8")
    )
    public_network = export_clinical_network(
        clinical_state,
        scientific_state,
        workspace,
        what_changed_recently=public.changes[0].summary if public.changes else None,
    )
    product, feed = export_product_layer(
        scientific_state,
        workspace,
        clinical_state,
        public_network,
        changes=public.changes,
        latest_run=public.latest_run,
    )
    publish_json(
        public_path,
        public.model_copy(
            update={
                "cargo": cargo,
                "formulation": formulation,
                "jurisdictions": jurisdictions,
                "clinical_network": public_network,
                "product": product,
                "intelligence_feed": feed,
            }
        ),
    )
    print(f"Imported legacy data; report: {report_path}")


if __name__ == "__main__":
    main()
