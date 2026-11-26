"""Command line entry point: spec-council review <spec.md> --config agents.toml"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .council import load_council
from .providers import ProviderError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="spec-council",
        description="Multi-agent review of a technical spec. Produces a proposed spec for human review.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    review = sub.add_parser("review", help="Run review rounds on a spec")
    review.add_argument("spec", type=Path, help="Path to the spec (Markdown)")
    review.add_argument("--config", type=Path, required=True, help="Agents config (TOML)")
    review.add_argument("--rounds", type=int, help="Override the number of rounds")
    review.add_argument("--out", type=Path, help="Output folder (default: runs/<timestamp>)")

    args = parser.parse_args(argv)

    if not args.spec.exists():
        print(f"Spec not found: {args.spec}", file=sys.stderr)
        return 2

    out = args.out or Path("runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        council = load_council(args.config, rounds=args.rounds)
        council.run(args.spec.read_text(encoding="utf-8"), out_dir=out)
    except (ProviderError, ValueError, KeyError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"\nDone. Proposed spec: {out / 'proposed_spec.md'}")
    print("Round-by-round reviews are in the round_XX folders. Review before accepting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
