"""`python -m signalai` command dispatcher."""

import argparse

from signalai.cli import daily_main, publish_state_main, should_commit_main


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m signalai")
    parser.add_argument("command", choices=["daily", "publish", "should-commit"])
    command = parser.parse_args().command
    {"daily": daily_main, "publish": publish_state_main, "should-commit": should_commit_main}[command]()


if __name__ == "__main__":
    main()
