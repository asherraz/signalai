import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from signalai.client import MalformedStructuredOutputError
from signalai.design_lab import (
    DesignLabOrchestrator, initial_design_lab, merge_signature_candidates,
    migrate_design_lab, novelty_conflicts, select_design_gap, validate_evidence_ids,
)
from signalai.design_lab_export import export_design_lab
from signalai.publisher import build_current_public_state
from signalai.schemas.design_lab import (
    CausalChain, CausalEdge, CausalNode, DesignAdversaryReview,
    DesignChairClassification, DesignHypothesis, DesignLabWorkspace,
    DesignProposal, DesignReview, ExperimentProposal, ProductSignatureCandidate,
)
from signalai.storage import publish_json


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc)
RUN_ID = "run-design-test"
EVIDENCE_ID = "ev-misev2023-quality-framework"


def proposal(run_id=RUN_ID, *, theme_id="design-gap-product-identity", sequence=1,
             question="Which measurable composition distinction can discriminate a secretome-retaining-EV product from a small-EV preparation?",
             domain="product_identity", prior_ids=None, angle="composition distinction"):
    hypothesis_id = f"design-hypothesis-{run_id}"
    experiment = ExperimentProposal(
        experiment_id=f"design-experiment-{run_id}",
        question=f"Does the exploratory {angle} separate two proposed product preparations?",
        hypothesis_tested="The proposed distinction is measurable across matched preparations.",
        required_material=["Future matched research preparations; none are represented as existing lots."],
        comparator="Matched preparation using the alternative fractionation concept.",
        control="Assay control appropriate to the selected analytical method.",
        assay=f"Orthogonal exploratory {angle} characterization; method selection remains pending.",
        primary_readout=f"A predeclared qualitative separation in the {angle} profile.",
        secondary_readouts=["Assay feasibility and repeatability observations."],
        success_criterion="The selected profile distinguishes the preparations reproducibly enough to justify follow-up.",
        failure_criterion="The profile does not distinguish the preparations or is not repeatable.",
        falsification_outcome="Failure would weaken the proposed attribute as a product-definition discriminator.",
        dependencies=["Human approval of the research plan", "Future research material"],
        evidence_ids=[EVIDENCE_ID], complexity="moderate", human_approval_state="pending",
    )
    chain = CausalChain(
        nodes=[
            CausalNode(node_id="node-attribute", stage="product_attribute", statement=f"A measurable {angle}."),
            CausalNode(node_id="node-interaction", stage="molecular_interaction", statement=f"A possible {angle}-linked difference in biological interactions; not established."),
        ],
        edges=[CausalEdge(edge_id="edge-attribute-interaction", source_node_id="node-attribute",
            target_node_id="node-interaction", evidence_state="inference", evidence_ids=[EVIDENCE_ID],
            relation_type="inference", model_or_species=None, uncertainty="The relationship is untested in SGL-001.",
            competing_explanation="Non-EV components could explain an observed difference.",
            missing_experiment=f"Matched {angle} and functional comparison.")],
    )
    return DesignProposal(
        title=f"Exploratory {angle} hypothesis",
        design_question=question,
        primary_domain=domain, secondary_domains=["manufacturing", "potency"],
        proposed_product_change_or_attribute=f"Evaluate an evidence-linked orthogonal {angle} as exploratory characterization.",
        biological_rationale="EV and non-EV fractions may contribute differently; this remains an inference.",
        manufacturing_rationale="A measurable distinction could inform an unresolved product-definition choice.",
        causal_chain=chain, expected_measurable_effect="A distinguishable exploratory profile, not a potency or efficacy result.",
        supporting_evidence_ids=[EVIDENCE_ID], contradicting_evidence_ids=[],
        explicit_inferences=["The framework may be useful for SGL-001 product-definition research."],
        assumptions=["Future matched research material can be generated."],
        competing_explanations=["Process variation could drive the profile."],
        manufacturability_assessment="Feasibility remains subject to method and material assessment.",
        measurement_strategy="Use orthogonal exploratory characterization without release acceptance criteria.",
        candidate_quality_attributes=[ProductSignatureCandidate(attribute_id=f"signature-{run_id}",
            name=f"Exploratory {angle} profile", group="non_ev_composition",
            role="exploratory_characterization_candidate", rationale="May help distinguish product concepts.",
            evidence_ids=[EVIDENCE_ID], uncertainty="Not validated for SGL-001.", source_hypothesis_id=hypothesis_id,
            measurement_concept=angle)],
        proposed_potency_relationship="Unknown; the attribute must not be treated as potency without functional linkage.",
        principal_risks=["The profile may reflect process noise."],
        falsification_criteria=["No reproducible distinction between matched preparations."],
        experiment=experiment, dependencies=["Future research material"],
        human_decisions_required=["Approve any experiment before execution."],
        novelty_statement=f"Tests the materially distinct {angle} angle with a dedicated discriminating readout.",
        distinguished_from_hypothesis_ids=prior_ids or [], theme_id=theme_id,
        sequence_within_theme=sequence,
    )


class ScriptedClient:
    def __init__(self, *, run_id=RUN_ID, repair=False, evidence_supported=True, determination="proposed_for_testing"):
        self.run_id = run_id
        self.repair_first = repair
        self.generate_calls = 0
        self.repair_calls = 0
        self.reviews = iter([
            DesignReview(conclusion="Evidence is bounded to the cited framework.", supported=evidence_supported,
                evidence_ids=[EVIDENCE_ID], evidence_gap=None if evidence_supported else "Program-specific evidence is absent."),
            DesignReview(conclusion="Manufacturing feasibility requires future assessment.", supported=True,
                evidence_ids=[EVIDENCE_ID], concerns=["No lots or validated methods exist."]),
            DesignReview(conclusion="The causal link remains inferential but testable.", supported=True,
                evidence_ids=[EVIDENCE_ID], concerns=["Alternative explanations remain."]),
        ])
        self.determination = determination

    def generate(self, *, instructions, input_text, output_type):
        self.generate_calls += 1
        if output_type is DesignProposal:
            if self.repair_first:
                self.repair_first = False
                raise MalformedStructuredOutputError("malformed", conflicts=["experiment: field required"])
            payload = json.loads(input_text)
            theme = payload["selected_gap"]
            sequence = payload["required_sequence_within_theme"]
            prior = [item["hypothesis_id"] for item in payload["prior_hypotheses"] if item.get("theme_id") == theme["gap_id"]]
            angle = f"{theme['title']} sequence {sequence} discriminating comparison"
            return proposal(self.run_id, theme_id=theme["gap_id"], sequence=sequence,
                question=f"Daily question {sequence}: {theme['question']}", domain=theme["domain"],
                prior_ids=prior, angle=angle)
        if output_type is DesignReview:
            return next(self.reviews)
        if output_type is DesignAdversaryReview:
            return DesignAdversaryReview(strongest_objection="The measurement may track process noise rather than meaningful biology.",
                failure_modes=["Confounding by non-EV material"], evidence_ids=[EVIDENCE_ID])
        return DesignChairClassification(determination=self.determination,
            rationale="The bounded proposal may proceed only as a human-approved research test.")

    def repair(self, *, instructions, input_text, output_type):
        self.repair_calls += 1
        payload = json.loads(input_text)
        theme = payload["selected_gap"]
        sequence = payload["required_sequence_within_theme"]
        prior = [item["hypothesis_id"] for item in payload["prior_hypotheses"] if item.get("theme_id") == theme["gap_id"]]
        return proposal(self.run_id, theme_id=theme["gap_id"], sequence=sequence,
            question=f"Daily question {sequence}: {theme['question']}", domain=theme["domain"],
            prior_ids=prior, angle=f"orthogonal perturbation response sequence {sequence}")


def prepare(tmp_path):
    for name in ("state", "runs", "public", "data"):
        source = ROOT / name
        if source.exists():
            shutil.copytree(source, tmp_path / name)
    (tmp_path / "design-runs").mkdir()
    publish_json(tmp_path / "state/design-lab.json", initial_design_lab(NOW))
    return tmp_path


def test_initial_workspace_and_empty_public_projection_are_valid():
    workspace = initial_design_lab(NOW)
    assert workspace.program_id == "SGL-001"
    assert len(workspace.design_gaps) == 13
    assert workspace.reviewed_hypotheses == []
    assert export_design_lab(workspace) is None


def test_design_cycle_is_reviewed_append_only_and_does_not_mutate_canonical_domains(tmp_path):
    root = prepare(tmp_path)
    protected = {name: (root / "state" / name).read_bytes() for name in (
        "signal-state.json", "asset-development.json", "development-docket.json", "live-runs.json")}
    result = DesignLabOrchestrator(client=ScriptedClient(), root=root, now_factory=lambda: NOW).run(run_id=RUN_ID)
    assert result.determination == "proposed_for_testing"
    assert result.minimum_discriminating_experiment.execution_status == "proposed"
    assert result.minimum_discriminating_experiment.human_approval_state == "pending"
    assert protected == {name: (root / "state" / name).read_bytes() for name in protected}
    workspace = DesignLabWorkspace.model_validate_json((root / "state/design-lab.json").read_text())
    assert [x.hypothesis_id for x in workspace.reviewed_hypotheses] == [result.hypothesis_id]
    assert (root / f"design-runs/{RUN_ID}/08-reviewed-hypothesis.json").exists()
    public = json.loads((root / "public/signal-state.json").read_text())
    assert public["designLab"]["latestReviewedHypothesis"]["hypothesisId"] == result.hypothesis_id
    assert "prompt" not in json.dumps(public).casefold()
    assert "api_usage" not in json.dumps(public).casefold()


def test_unknown_evidence_is_rejected_and_prior_state_is_preserved(tmp_path):
    root = prepare(tmp_path)
    before = [(root / path).read_bytes() for path in ("state/design-lab.json", "public/signal-state.json")]
    bad = proposal().model_copy(deep=True)
    bad.supporting_evidence_ids.append("invented-evidence")
    with pytest.raises(ValueError, match="unknown canonical evidence"):
        validate_evidence_ids(bad, {EVIDENCE_ID})
    assert before == [(root / path).read_bytes() for path in ("state/design-lab.json", "public/signal-state.json")]


def test_one_structured_repair_attempt_then_cycle_continues(tmp_path):
    root = prepare(tmp_path)
    client = ScriptedClient(repair=True)
    DesignLabOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(run_id=RUN_ID)
    assert client.repair_calls == 1
    assert client.generate_calls == 6
    assert (root / f"design-runs/{RUN_ID}/private-proposal-validation-error.json").exists()


def test_unsupported_evidence_deterministically_becomes_needs_evidence(tmp_path):
    root = prepare(tmp_path)
    result = DesignLabOrchestrator(client=ScriptedClient(evidence_supported=False), root=root,
        now_factory=lambda: NOW).run(run_id=RUN_ID)
    assert result.determination == "needs_evidence"


def test_autonomous_promotion_and_validated_release_test_are_rejected():
    with pytest.raises(ValidationError, match="cannot promote"):
        DesignChairClassification(determination="promoted_to_experiment", rationale="Not allowed")
    data = proposal().candidate_quality_attributes[0].model_dump(mode="python")
    data["role"] = "validated_release_test"
    with pytest.raises(ValidationError, match="explicit human approval"):
        ProductSignatureCandidate.model_validate(data)


def test_duplicate_hypothesis_and_run_artifacts_are_protected(tmp_path):
    root = prepare(tmp_path)
    orchestrator = DesignLabOrchestrator(client=ScriptedClient(), root=root, now_factory=lambda: NOW)
    result = orchestrator.run(run_id=RUN_ID)
    workspace = DesignLabWorkspace.model_validate_json((root / "state/design-lab.json").read_text())
    gap = workspace.design_gaps[0].model_copy(update={"status": "open"})
    workspace = workspace.model_copy(update={"design_gaps": [gap, *workspace.design_gaps[1:]]})
    publish_json(root / "state/design-lab.json", workspace)
    before = (root / f"design-runs/{RUN_ID}/08-reviewed-hypothesis.json").read_bytes()
    with pytest.raises(FileExistsError):
        DesignLabOrchestrator(client=ScriptedClient(), root=root, now_factory=lambda: NOW).run(run_id=RUN_ID)
    assert (root / f"design-runs/{RUN_ID}/08-reviewed-hypothesis.json").read_bytes() == before
    assert result.hypothesis_id in {x.hypothesis_id for x in workspace.reviewed_hypotheses}


def test_semantically_duplicate_hypothesis_is_not_appended(tmp_path):
    root = prepare(tmp_path)
    first = DesignLabOrchestrator(client=ScriptedClient(), root=root, now_factory=lambda: NOW).run(run_id=RUN_ID)
    duplicate = DesignProposal.model_validate_json(
        (root / f"design-runs/{RUN_ID}/02-design-proposal.json").read_text()
    )
    assert novelty_conflicts(duplicate, [first])


def test_failed_repair_preserves_workspace_and_public_state(tmp_path):
    root = prepare(tmp_path)
    before = [(root / path).read_bytes() for path in ("state/design-lab.json", "public/signal-state.json")]
    class Broken(ScriptedClient):
        def repair(self, **kwargs):
            self.repair_calls += 1
            raise MalformedStructuredOutputError("still malformed")
    client = Broken(repair=True)
    with pytest.raises(MalformedStructuredOutputError):
        DesignLabOrchestrator(client=client, root=root, now_factory=lambda: NOW).run(run_id=RUN_ID)
    assert client.repair_calls == 1
    assert before == [(root / path).read_bytes() for path in ("state/design-lab.json", "public/signal-state.json")]
    assert (root / f"design-runs/{RUN_ID}/99-run-failed.json").exists()


def test_experiment_proposal_cannot_contain_result_fields():
    data = proposal().experiment.model_dump(mode="python")
    data["result"] = "fabricated"
    with pytest.raises(ValidationError, match="Extra inputs"):
        ExperimentProposal.model_validate(data)


def test_daily_workflow_runs_design_lab_between_intelligence_and_simulation():
    workflow = (ROOT / ".github/workflows/daily-signalai.yml").read_text()
    daily = workflow.index("python -m signalai daily")
    design = workflow.index("python -m signalai design-lab")
    simulation = workflow.index("python -m signalai clinic-simulate")
    assert daily < design < simulation
    assert "git add public state runs design-runs simulation-runs" in workflow


def test_continuous_generation_revisits_themes_and_preserves_history(tmp_path):
    root = prepare(tmp_path)
    first_payload = None
    total_runs = 15
    for index in range(total_runs):
        run_id = f"run-continuous-{index:02d}"
        when = datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc) + timedelta(days=index)
        DesignLabOrchestrator(client=ScriptedClient(run_id=run_id), root=root,
            now_factory=lambda value=when: value).run(run_id=run_id)
        workspace = DesignLabWorkspace.model_validate_json((root / "state/design-lab.json").read_text())
        if index == 0:
            first_payload = workspace.reviewed_hypotheses[0].model_dump(mode="json")
    workspace = DesignLabWorkspace.model_validate_json((root / "state/design-lab.json").read_text())
    assert len(workspace.reviewed_hypotheses) == total_runs
    assert len(workspace.recent_runs) == total_runs
    assert workspace.reviewed_hypotheses[0].model_dump(mode="json") == first_payload
    assert sum(theme.times_explored for theme in workspace.design_gaps) == total_runs
    assert all(theme.times_explored >= 1 for theme in workspace.design_gaps)
    assert any(theme.times_explored > 1 for theme in workspace.design_gaps)
    assert all(theme.status == "open" for theme in workspace.design_gaps)
    keys = {(item.title, item.design_question, item.proposed_product_change_or_attribute)
        for item in workspace.reviewed_hypotheses}
    assert len(keys) == total_runs


def test_balanced_selection_rotates_before_revisiting():
    workspace = initial_design_lab(NOW)
    selected = []
    for index in range(len(workspace.design_gaps)):
        theme, _ = select_design_gap(workspace, now=NOW)
        selected.append(theme.gap_id)
        hypothesis_id = f"hypothesis-selection-{index}"
        workspace.design_gaps = [item.model_copy(update={
            "times_explored": 1, "last_explored_at": NOW,
            "latest_hypothesis_id": hypothesis_id, "hypothesis_ids": [hypothesis_id],
        }) if item.gap_id == theme.gap_id else item for item in workspace.design_gaps]
    assert len(set(selected)) == len(workspace.design_gaps)


def test_backward_migration_is_idempotent_and_preserves_existing_hypothesis():
    current = DesignLabWorkspace.model_validate_json((ROOT / "state/design-lab.json").read_text())
    existing = current.reviewed_hypotheses[0]
    legacy = current.model_dump(mode="python")
    legacy["schema_version"] = "1.0"
    legacy["reviewed_hypotheses"][0].pop("novelty_statement")
    legacy["reviewed_hypotheses"][0].pop("distinguished_from_hypothesis_ids")
    legacy["reviewed_hypotheses"][0].pop("theme_id")
    legacy["reviewed_hypotheses"][0].pop("sequence_within_theme")
    legacy["product_signature_candidates"][0].pop("source_hypothesis_ids")
    legacy["product_signature_candidates"][0].pop("measurement_concept")
    legacy["design_gaps"] = legacy["design_gaps"][:6]
    for theme in legacy["design_gaps"]:
        for field in ("times_explored", "last_explored_at", "latest_hypothesis_id",
                      "hypothesis_ids", "open_questions", "priority",
                      "human_priority_override", "mechanistic_relevance"):
            theme.pop(field, None)
    legacy["design_gaps"][0]["status"] = "reviewed"
    migrated = migrate_design_lab(DesignLabWorkspace.model_validate(legacy))
    assert migrate_design_lab(migrated) == migrated
    assert len(migrated.design_gaps) == 13
    theme = next(item for item in migrated.design_gaps if item.gap_id == existing.selected_gap_id)
    assert theme.status == "open" and theme.times_explored == 1
    after = migrated.reviewed_hypotheses[0]
    for field in type(existing).model_fields:
        if field not in {"novelty_statement", "distinguished_from_hypothesis_ids", "theme_id", "sequence_within_theme"}:
            assert getattr(after, field) == getattr(existing, field)


def test_product_signature_candidates_merge_references_without_duplicate_record():
    first = proposal().candidate_quality_attributes[0]
    second = first.model_copy(update={
        "attribute_id": "second-display-id", "source_hypothesis_id": "second-hypothesis",
        "source_hypothesis_ids": ["second-hypothesis"],
        "rationale": "A new rationale that should not duplicate the display record.",
    })
    merged, mapping = merge_signature_candidates([first], [second])
    assert len(merged) == 1
    assert mapping[second.attribute_id] == first.attribute_id
    assert set(merged[0].source_hypothesis_ids) == {first.source_hypothesis_id, "second-hypothesis"}


def test_public_limits_full_history_to_30_and_keeps_canonical_history():
    workspace = DesignLabWorkspace.model_validate_json((ROOT / "state/design-lab.json").read_text())
    source = workspace.reviewed_hypotheses[0]
    hypotheses = [source.model_copy(update={
        "hypothesis_id": f"history-hypothesis-{index}", "run_id": f"history-run-{index}",
        "created_at": datetime(2026, 8, 1, tzinfo=timezone.utc).replace(day=1 + index % 28),
        "sequence_within_theme": index + 1,
    }) for index in range(35)]
    payload = workspace.model_dump(mode="python")
    payload["reviewed_hypotheses"] = hypotheses
    theme = payload["design_gaps"][0]
    theme["times_explored"] = 35
    theme["hypothesis_ids"] = [item.hypothesis_id for item in hypotheses]
    theme["latest_hypothesis_id"] = hypotheses[-1].hypothesis_id
    theme["last_explored_at"] = hypotheses[-1].created_at
    public = export_design_lab(DesignLabWorkspace.model_validate(payload))
    assert len(public.recent_hypotheses) == 30
    assert len(public.older_hypotheses) == 5
    assert public.summary_counts.total_hypotheses == 35
    assert len(hypotheses) == 35
