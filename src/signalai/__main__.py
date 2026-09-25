"""`python -m signalai` command dispatcher."""

import argparse

from signalai.cli import daily_main, design_lab_main, publish_state_main, should_commit_main, clinic_ingest_main, clinic_batch_main
from signalai.cli import clinic_index_main, clinic_simulation_main, strategy_main, molecular_atlas_discover_main


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m signalai")
    parser.add_argument("command", choices=["daily", "design-lab", "strategy", "publish", "should-commit", "clinic-ingest", "clinic-batch", "clinic-scheduled", "clinic-discover", "clinic-index", "clinic-enrich", "clinic-import", "clinic-simulate", "molecular-atlas-discover"])
    parser.add_argument("target", nargs="?")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--country")
    parser.add_argument("--region")
    parser.add_argument("--priority", type=int)
    parser.add_argument("--only-new", action="store_true")
    args = parser.parse_args()
    if args.command == "clinic-simulate":
        clinic_simulation_main(args.target)
    elif args.command == "molecular-atlas-discover":
        molecular_atlas_discover_main()
    elif args.command in {"clinic-discover", "clinic-index", "clinic-enrich", "clinic-import"}:
        clinic_index_main(args.command, args.target, limit=args.limit, country=args.country, region=args.region, priority=args.priority, only_new=args.only_new)
    elif args.command == "clinic-ingest":
        parser.error("clinic-ingest requires a URL") if not args.target else clinic_ingest_main(args.target, refresh=args.refresh)
    elif args.command in {"clinic-batch", "clinic-scheduled"}:
        clinic_batch_main(args.target, scheduled=args.command == "clinic-scheduled", refresh=args.refresh)
    else:
        {"daily": daily_main, "design-lab": design_lab_main, "strategy": strategy_main, "publish": publish_state_main, "should-commit": should_commit_main}[args.command]()


if __name__ == "__main__":
    main()
