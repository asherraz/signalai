"""`python -m signalai` command dispatcher."""

import argparse

from signalai.cli import daily_main, publish_state_main, should_commit_main, clinic_ingest_main, clinic_batch_main


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m signalai")
    parser.add_argument("command", choices=["daily", "publish", "should-commit", "clinic-ingest", "clinic-batch", "clinic-scheduled"])
    parser.add_argument("target", nargs="?")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if args.command == "clinic-ingest":
        parser.error("clinic-ingest requires a URL") if not args.target else clinic_ingest_main(args.target, refresh=args.refresh)
    elif args.command in {"clinic-batch", "clinic-scheduled"}:
        clinic_batch_main(args.target, scheduled=args.command == "clinic-scheduled", refresh=args.refresh)
    else:
        {"daily": daily_main, "publish": publish_state_main, "should-commit": should_commit_main}[args.command]()


if __name__ == "__main__":
    main()
