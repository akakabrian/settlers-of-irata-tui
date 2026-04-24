"""settlers-of-irata-tui — entry point."""
from __future__ import annotations

import argparse

from settlers_of_irata_tui.app import MuleApp


def main() -> None:
    ap = argparse.ArgumentParser(description="settlers-of-irata-tui")
    ap.add_argument("--seed", type=int, default=1983)
    ap.add_argument("--race", default="mechtron",
                    choices=["mechtron", "flapper", "gollumer", "ugaaite"])
    ap.add_argument("--rounds", type=int, default=12,
                    help="total months to play (1..12)")
    args = ap.parse_args()
    app = MuleApp(seed=args.seed, human_race=args.race, total_rounds=args.rounds)
    app.run()


if __name__ == "__main__":
    main()
