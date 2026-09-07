"""Minimal end-to-end therapeutic development run."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from signalai.agents.prompts import (
    CRITIC_INSTRUCTIONS,
    HYPOTHESIS_INSTRUCTIONS,
    RESEARCH_INSTRUCTIONS,
    SYNTHESIS_INSTRUCTIONS,
)
from signalai.client import ModelClient
from signalai.clinical_network_export import export_clinical_network
from signalai.product_export import export_product_layer
from signalai.schemas import (
    AgentRun,
    ApprovalStatus,
    ClaimSet,
    CritiqueResult,
    DecisionProposal,
    Evidence,
    EvidenceConfidence,
    HypothesisProposal,
    ProgramStatus,
    PublicSignalState,
    RunStatus,
    SignalState,
    TherapeuticProgram,
    TherapeuticAssetWorkspace,
    ClinicalNetworkState,
)
from signalai.storage import RunStore, new_run_id, publish_json
from signalai.workspace_export import export_workspace


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> str:
    value = TypeAdapter(Any).dump_python(value, mode="json")
    return json.dumps(value, indent=2, sort_keys=True)


def load_evidence(path: Path) -> list[Evidence]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return TypeAdapter(list[Evidence]).validate_python(raw)


class MilestoneOneOrchestrator:
    def __init__(
        self,
        *,
        client: ModelClient,
        evidence_path: Path,
        runs_root: Path,
        public_state_path: Path,
        workspace_path: Path | None = None,
        clinical_network_path: Path | None = None,
    ) -> None:
        self.client = client
        self.evidence_path = evidence_path
        self.runs_root = runs_root
        self.public_state_path = public_state_path
        self.workspace_path = workspace_path
        self.clinical_network_path = clinical_network_path

    def run(self, *, run_id: str | None = None) -> SignalState:
        active_run_id = run_id or new_run_id()
        started_at = _utc_now()
        store = RunStore(self.runs_root, active_run_id)
        artifact_paths: list[str] = []

        initial_run = AgentRun(
            run_id=active_run_id,
            agent_name="milestone-one-orchestrator",
            program_id="SGL-001",
            status=RunStatus.RUNNING,
            started_at=started_at,
        )
        artifact_paths.append(str(store.write_json("00-run-start.json", initial_run)))

        try:
            evidence = load_evidence(self.evidence_path)
            artifact_paths.append(str(store.write_json("01-evidence.json", evidence)))

            claims_result = self.client.generate(
                instructions=RESEARCH_INSTRUCTIONS,
                input_text=_json(evidence),
                output_type=ClaimSet,
            )
            self._validate_claims(claims_result, evidence)
            artifact_paths.append(str(store.write_json("02-claims.json", claims_result)))

            hypothesis_result = self.client.generate(
                instructions=HYPOTHESIS_INSTRUCTIONS,
                input_text=_json(claims_result),
                output_type=HypothesisProposal,
            )
            self._validate_hypothesis(hypothesis_result, claims_result, evidence)
            artifact_paths.append(
                str(store.write_json("03-hypothesis.json", hypothesis_result))
            )

            critic_input = {
                "evidence": [item.model_dump(mode="json") for item in evidence],
                "claims": claims_result.model_dump(mode="json"),
                "hypothesis": hypothesis_result.model_dump(mode="json"),
            }
            critique_result = self.client.generate(
                instructions=CRITIC_INSTRUCTIONS,
                input_text=_json(critic_input),
                output_type=CritiqueResult,
            )
            self._validate_critique(critique_result, hypothesis_result, evidence)
            artifact_paths.append(str(store.write_json("04-critique.json", critique_result)))

            synthesis_input = {**critic_input, "critique": critique_result.model_dump(mode="json")}
            decision_result = self.client.generate(
                instructions=SYNTHESIS_INSTRUCTIONS,
                input_text=_json(synthesis_input),
                output_type=DecisionProposal,
            )
            self._validate_decision(
                decision_result,
                claims_result,
                critique_result,
                evidence,
            )
            artifact_paths.append(str(store.write_json("05-decision.json", decision_result)))

            now = _utc_now()
            program = TherapeuticProgram(
                program_id="SGL-001",
                name="SGL-001 development program",
                asset_name="SGL-001",
                modality="extracellular-vesicle/exosome therapeutic",
                route_of_administration="intranasal",
                indication=None,
                development_focus="Neuroregeneration and cognitive function",
                lead_indication="Not yet selected",
                status=ProgramStatus.PRECLINICAL,
                current_formulation_hypothesis=(
                    "Intranasal mesenchymal-stromal-cell-derived small-EV preparation "
                    "with defined identity, purity, dose, and a mechanism-relevant "
                    "potency assay; therapeutic cargo remains to be selected."
                ),
                evidence_confidence=EvidenceConfidence.MODERATE,
                largest_unresolved_risk=(
                    "Intranasal CNS exposure observed in rodents may not translate to "
                    "larger species or humans."
                ),
                next_proposed_action=(
                    "Run a formulation-controlled biodistribution and pharmacology "
                    "study with label controls, quantitative tissue exposure, and "
                    "predefined acceptance criteria, then select a cognition/aging "
                    "model aligned with the program intent."
                ),
                claim_ids=[claim.claim_id for claim in claims_result.claims],
                hypothesis_ids=[hypothesis_result.hypothesis.hypothesis_id],
                risk_ids=[risk.risk_id for risk in critique_result.risks],
                decision_ids=[decision_result.decision.decision_id],
                created_at=started_at,
                updated_at=now,
            )
            state = SignalState(
                schema_version="2.0",
                run_id=active_run_id,
                generated_at=now,
                program=program,
                evidence=evidence,
                claims=claims_result.claims,
                hypothesis=hypothesis_result.hypothesis,
                critique=critique_result.critique,
                risks=critique_result.risks,
                decision=decision_result.decision,
            )
            artifact_paths.append(str(store.write_json("06-signal-state.json", state)))
            workspace = (
                TherapeuticAssetWorkspace.model_validate_json(
                    self.workspace_path.read_text(encoding="utf-8")
                )
                if self.workspace_path is not None
                else None
            )
            clinical_state = (
                ClinicalNetworkState.model_validate_json(
                    self.clinical_network_path.read_text(encoding="utf-8")
                )
                if self.clinical_network_path is not None
                else None
            )
            public_domains = (
                export_workspace(workspace) if workspace is not None else (None, None, None)
            )
            public_network = (
                export_clinical_network(clinical_state, state, workspace)
                if clinical_state is not None and workspace is not None
                else None
            )
            public_state = PublicSignalState.from_internal(
                state,
                cargo=public_domains[0],
                formulation=public_domains[1],
                jurisdictions=public_domains[2],
                clinical_network=public_network,
            )
            if clinical_state is not None and workspace is not None and public_network is not None:
                product, feed = export_product_layer(
                    state,
                    workspace,
                    clinical_state,
                    public_network,
                    changes=public_state.changes,
                    latest_run=None,
                )
                public_state = public_state.model_copy(
                    update={"product": product, "intelligence_feed": feed}
                )
            artifact_paths.append(
                str(store.write_json("07-public-signal-state.json", public_state))
            )
            publish_json(self.public_state_path, public_state)

            completed_run = AgentRun(
                run_id=active_run_id,
                agent_name="milestone-one-orchestrator",
                program_id="SGL-001",
                status=RunStatus.SUCCEEDED,
                started_at=started_at,
                completed_at=_utc_now(),
                intermediate_artifact_paths=artifact_paths[1:-2],
                output_artifact_paths=[artifact_paths[-1], str(self.public_state_path)],
            )
            store.write_json("99-run-complete.json", completed_run)
            return state
        except Exception as exc:
            failed_run = AgentRun(
                run_id=active_run_id,
                agent_name="milestone-one-orchestrator",
                program_id="SGL-001",
                status=RunStatus.FAILED,
                started_at=started_at,
                completed_at=_utc_now(),
                intermediate_artifact_paths=artifact_paths[1:],
                error=f"{type(exc).__name__}: {exc}",
            )
            store.write_json("99-run-failed.json", failed_run)
            raise

    @staticmethod
    def _validate_claims(result: ClaimSet, evidence: list[Evidence]) -> None:
        evidence_ids = {item.evidence_id for item in evidence}
        claim_ids: set[str] = set()
        for claim in result.claims:
            if claim.program_id != "SGL-001":
                raise ValueError("all claims must belong to SGL-001")
            if claim.claim_id in claim_ids:
                raise ValueError(f"duplicate claim_id: {claim.claim_id}")
            claim_ids.add(claim.claim_id)
            unknown = set(claim.evidence_ids) - evidence_ids
            if unknown:
                raise ValueError(f"claim cites unknown evidence IDs: {sorted(unknown)}")

    @staticmethod
    def _validate_hypothesis(
        result: HypothesisProposal,
        claims: ClaimSet,
        evidence: list[Evidence],
    ) -> None:
        hypothesis = result.hypothesis
        if hypothesis.program_id != "SGL-001":
            raise ValueError("hypothesis must belong to SGL-001")
        known_claims = {claim.claim_id for claim in claims.claims}
        referenced = set(hypothesis.supporting_claim_ids + hypothesis.contradicting_claim_ids)
        if referenced - known_claims:
            raise ValueError("hypothesis references unknown claim IDs")
        known_evidence = {item.evidence_id for item in evidence}
        if set(hypothesis.evidence_ids) - known_evidence:
            raise ValueError("hypothesis references unknown evidence IDs")

    @staticmethod
    def _validate_critique(
        result: CritiqueResult,
        hypothesis: HypothesisProposal,
        evidence: list[Evidence],
    ) -> None:
        if result.critique.hypothesis_id != hypothesis.hypothesis.hypothesis_id:
            raise ValueError("critique must reference the proposed hypothesis")
        known_evidence = {item.evidence_id for item in evidence}
        if set(result.critique.evidence_ids) - known_evidence:
            raise ValueError("critique references unknown evidence IDs")
        risk_ids: set[str] = set()
        for risk in result.risks:
            if risk.program_id != "SGL-001":
                raise ValueError("all risks must belong to SGL-001")
            if risk.risk_id in risk_ids:
                raise ValueError(f"duplicate risk_id: {risk.risk_id}")
            risk_ids.add(risk.risk_id)
            if set(risk.evidence_ids) - known_evidence:
                raise ValueError("risk references unknown evidence IDs")

    @staticmethod
    def _validate_decision(
        result: DecisionProposal,
        claims: ClaimSet,
        critique: CritiqueResult,
        evidence: list[Evidence],
    ) -> None:
        decision = result.decision
        if decision.program_id != "SGL-001":
            raise ValueError("decision must belong to SGL-001")
        if not decision.requires_human_approval or decision.approval_status != ApprovalStatus.PENDING:
            raise ValueError("decision proposal must be pending human approval")
        known_claims = {claim.claim_id for claim in claims.claims}
        if set(decision.supporting_claim_ids) - known_claims:
            raise ValueError("decision references unknown claim IDs")
        known_evidence = {item.evidence_id for item in evidence}
        if set(decision.evidence_ids) - known_evidence:
            raise ValueError("decision references unknown evidence IDs")
        known_risks = {risk.risk_id for risk in critique.risks}
        if set(decision.risk_ids) - known_risks:
            raise ValueError("decision references unknown risk IDs")
