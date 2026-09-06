import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from signalai.legacy_migration import migrate_legacy_workspace
from signalai.schemas import DevelopmentAgenda, SignalState, TherapeuticAssetWorkspace
from signalai.workspace_export import export_workspace, validate_workspace_references


ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = Path("/Users/raziel/Desktop/signalAgent")
CARGO_PATH = LEGACY_ROOT / "artifacts" / "data" / "mirna-cargo.json"
FORMULATION_PATH = LEGACY_ROOT / "artifacts" / "data" / "formulation.json"
JURISDICTIONS_PATH = LEGACY_ROOT / "state" / "jurisdictions.json"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _migrate(cargo_path: Path = CARGO_PATH):
    return migrate_legacy_workspace(
        cargo_path=cargo_path,
        formulation_path=FORMULATION_PATH,
        jurisdictions_path=JURISDICTIONS_PATH,
        seed_workspace=TherapeuticAssetWorkspace.model_validate_json(
            (ROOT / "state" / "asset-development.json").read_text()
        ),
        scientific_state=SignalState.model_validate_json(
            (ROOT / "state" / "signal-state.json").read_text()
        ),
        agenda=DevelopmentAgenda.model_validate_json(
            (ROOT / "state" / "development-agenda.json").read_text()
        ),
        generated_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )


def test_exact_legacy_sources_are_readable_and_unchanged_by_migration() -> None:
    paths = (CARGO_PATH, FORMULATION_PATH, JURISDICTIONS_PATH)
    before = {path: _hash(path) for path in paths}

    workspace, report = _migrate()

    assert {path: _hash(path) for path in paths} == before
    assert [source.source_file for source in report.sources] == [str(path) for path in paths]
    assert len(workspace.cargo.candidates) == 27
    assert len(workspace.formulation.candidates) == 6
    assert len(workspace.formulation.excipients) == 15
    assert len(workspace.formulation.presentations) == 3
    assert len(workspace.jurisdictions.jurisdictions) == 12


def test_migration_maps_all_discovered_fields_and_preserves_source_paths() -> None:
    workspace, report = _migrate()

    assert all(not source.unmapped_fields for source in report.sources)
    mirna = next(item for item in workspace.cargo.candidates if item.name == "miR-133b")
    assert mirna.biological_targets == ["RhoA", "CTGF"]
    assert mirna.source_citation
    assert mirna.legacy_source_file == str(CARGO_PATH)
    insulin = next(
        item for item in workspace.formulation.candidates if item.name == "Intranasal insulin"
    )
    assert insulin.legacy_scores == {
        "mechanism_score": 5,
        "evidence_score": 5,
        "manufacturability_score": 5,
        "regulatory_score": 5,
    }
    assert insulin.legacy_source_file == str(FORMULATION_PATH)
    assert all(
        item.verification_status.value == "legacy_import_unverified"
        for item in workspace.jurisdictions.jurisdictions
    )
    assert all(item.source_document_ids for item in workspace.jurisdictions.jurisdictions)


def test_migration_reports_unknown_fields_instead_of_dropping_them(tmp_path: Path) -> None:
    rows = json.loads(CARGO_PATH.read_text())
    rows[0]["future_field"] = "must be reported"
    modified = tmp_path / "cargo.json"
    modified.write_text(json.dumps(rows), encoding="utf-8")

    _, report = _migrate(modified)

    assert report.sources[0].unmapped_fields == ["future_field"]


def test_migrated_workspace_cross_references_and_public_export_validate() -> None:
    workspace, _ = _migrate()
    state = SignalState.model_validate_json((ROOT / "state" / "signal-state.json").read_text())
    agenda = DevelopmentAgenda.model_validate_json(
        (ROOT / "state" / "development-agenda.json").read_text()
    )

    validate_workspace_references(workspace, state, agenda)
    cargo, formulation, jurisdictions = export_workspace(workspace)
    assert len(cargo.candidates) == 27
    assert len(formulation.excipients) == 15
    assert len(formulation.presentations) == 3
    assert len(jurisdictions.jurisdictions) == 12
