"""Render an absolute one-shot timer from the actual stage-6 online_since."""
import argparse
from datetime import timedelta, timezone
from pathlib import Path

from daily_report import timestamp


def render(online_since):
    due = timestamp(online_since) + timedelta(hours=2)
    if due.microsecond:
        due = (due + timedelta(seconds=1)).replace(microsecond=0)
    text = Path(__file__).with_name("incident-stage8-check.timer.in").read_text(encoding="utf-8")
    return text.replace("@DUE_UTC@", due.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online-since", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    text = render(args.online_since)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(text)
    print("prepared_not_installed")


if __name__ == "__main__":
    main()
