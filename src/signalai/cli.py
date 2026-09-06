"""Command-line entry points for SignalAI development runs."""

from pathlib import Path

from signalai.client import OpenAIResponsesClient
from signalai.daily import DailyRunOrchestrator
from signalai.orchestrator import MilestoneOneOrchestrator


def main() -> None:
    root = Path.cwd()
    state = MilestoneOneOrchestrator(
        client=OpenAIResponsesClient.from_env(),
        evidence_path=root / "evidence" / "fixtures" / "sgl-001.json",
        runs_root=root / "runs",
        public_state_path=root / "public" / "signal-state.json",
        workspace_path=root / "state" / "asset-development.json",
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
    ).run()
    print(f"Completed daily run {state.run_id}")


if __name__ == "__main__":
    main()
