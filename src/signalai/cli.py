"""Command-line entry point for the local Milestone 1 run."""

from pathlib import Path

from signalai.client import OpenAIResponsesClient
from signalai.orchestrator import MilestoneOneOrchestrator


def main() -> None:
    root = Path.cwd()
    state = MilestoneOneOrchestrator(
        client=OpenAIResponsesClient.from_env(),
        evidence_path=root / "evidence" / "fixtures" / "sgl-001.json",
        runs_root=root / "runs",
        public_state_path=root / "public" / "signal-state.json",
    ).run()
    print(f"Completed {state.run_id}")


if __name__ == "__main__":
    main()
