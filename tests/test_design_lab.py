import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from signalai.client import MalformedStructuredOutputError
from signalai.design_lab import DesignLabOrchestrator, initial_design_lab, validate_evidence_ids
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


def proposal(run_id=RUN_ID):
    hypothesis_id = f"design-hypothesis-{run_id}"
    experiment = ExperimentProposal(
        experiment_id=f"design-experiment-{run_id}",
        question="Does the exploratory composition distinction separate two proposed product preparations?",
        hypothesis_tested="The proposed distinction is measurable across matched preparations.",
        required_material=["Future matched research preparations; none are represented as existing lots."],
        comparator="Matched preparation using the alternative fractionation concept.",
        control="Assay control appropriate to the selected analytical method.",
        assay="Orthogonal exploratory characterization; method selection remains pending.",
        primary_readout="A predeclared qualitative separation in the exploratory characterization profile.",
        secondary_readouts=["Assay feasibility and repeatability observations."],
        success_criterion="The selected profile distinguishes the preparations reproducibly enough to justify follow-up.",
        failure_criterion="The profile does not distinguish the preparations or is not repeatable.",
        falsification_outcome="Failure would weaken the proposed attribute as a product-definition discriminator.",
        dependencies=["Human approval of the research plan", "Future research material"],
        evidence_ids=[EVIDENCE_ID], complexity="moderate", human_approval_state="pending",
    )
    chain = CausalChain(
        nodes=[
            CausalNode(node_id="node-attribute", stage="product_attribute", statement="A measurable composition distinction."),
            CausalNode(node_id="node-interaction", stage="molecular_interaction", statement="A possible difference in biological interactions; not established."),
        ],
        edges=[CausalEdge(edge_id="edge-attribute-interaction", source_node_id="node-attribute",
            target_node_id="node-interaction", evidence_state="inference", evidence_ids=[EVIDENCE_ID],
            relation_type="inference", model_or_species=None, uncertainty="The relationship is untested in SGL-001.",
            competing_explanation="Non-EV components could explain an observed difference.",
            missing_experiment="Matched compositional and functional comparison.")],
    )
    return DesignProposal(
        title="Exploratory EV/non-EV composition discriminator",
        design_question="Which measurable composition distinction can discriminate a secretome-retaining-EV product from a small-EV preparation?",
        primary_domain="product_identity", secondary_domains=["manufacturing", "potency"],
        proposed_product_change_or_attribute="Evaluate an evidence-linked orthogonal composition distinction as exploratory characterization.",
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
            name="Exploratory composition profile", group="non_ev_composition",
            role="exploratory_characterization_candidate", rationale="May help distinguish product concepts.",
            evidence_ids=[EVIDENCE_ID], uncertainty="Not validated for SGL-001.", source_hypothesis_id=hypothesis_id)],
        proposed_potency_relationship="Unknown; the attribute must not be treated as potency without functional linkage.",
        principal_risks=["The profile may reflect process noise."],
        falsification_criteria=["No reproducible distinction between matched preparations."],
        experiment=experiment, dependencies=["Future research material"],
        human_decisions_required=["Approve any experiment before execution."],
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
            return proposal(self.run_id)
        if output_type is DesignReview:
            return next(self.reviews)
        if output_type is DesignAdversaryReview:
            return DesignAdversaryReview(strongest_objection="The measurement may track process noise rather than meaningful biology.",
                failure_modes=["Confounding by non-EV material"], evidence_ids=[EVIDENCE_ID])
        return DesignChairClassification(determination=self.determination,
            rationale="The bounded proposal may proceed only as a human-approved research test.")

    def repair(self, *, instructions, input_text, output_type):
        self.repair_calls += 1
        return proposal(self.run_id)


def prepare(tmp_path):
    for name in ("state", "runs", "public", "data"):
        source = ROOT / name
        if source.exists():
            shutil.copytree(source, tmp_path / name)
    (tmp_path / "design-runs").mkdir()
    return tmp_path


def test_initial_workspace_and_empty_public_projection_are_valid():
    workspace = initial_design_lab(NOW)
    assert workspace.program_id == "SGL-001"
    assert len(workspace.design_gaps) >= 6
    assert workspace.reviewed_hypotheses == []
    assert export_design_lab(workspace) is None
    assert build_current_public_state(ROOT).design_lab is None


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
    DesignLabOrchestrator(client=ScriptedClient(), root=root, now_factory=lambda: NOW).run(run_id=RUN_ID)
    workspace = DesignLabWorkspace.model_validate_json((root / "state/design-lab.json").read_text())
    workspace.design_gaps[0].status = "open"
    publish_json(root / "state/design-lab.json", workspace)
    before = (root / "state/design-lab.json").read_bytes()
    second = "run-design-duplicate"
    with pytest.raises(ValueError, match="duplicate design hypothesis"):
        DesignLabOrchestrator(client=ScriptedClient(run_id=second), root=root, now_factory=lambda: NOW).run(run_id=second)
    assert (root / "state/design-lab.json").read_bytes() == before


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
