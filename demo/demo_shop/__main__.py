"""python -m demo_shop generate   -> data/demo-shop/*.jsonl
python -m demo_shop summary    -> one line per incident (ground truth)
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from .generator import SEED, build_world, write_all

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m demo_shop")
    ap.add_argument("cmd", choices=["generate", "summary"])
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    if args.cmd == "generate":
        w = write_all(ROOT, args.seed)
        print(
            f"{len(w.incidents)} incidents, {len(w.logs)} log lines, {len(w.metrics)} metric rows, "
            f"{len(w.deploys)} deploys -> data/demo-shop/"
        )
    else:
        w = build_world(args.seed)
        for inc in w.incidents:
            print(
                f"{inc['id']}  {inc['alert_name']:<16} on {inc['alert_service']:<10} "
                f"-> {inc['category']:<18} root={inc['root_service']}"
            )
        print(dict(Counter(i["category"] for i in w.incidents)))


if __name__ == "__main__":
    main()
