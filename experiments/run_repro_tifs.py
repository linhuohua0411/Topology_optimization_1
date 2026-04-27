#!/usr/bin/env python3
"""
One-click reproduction entry for TIFS experiments.

Usage:
  python experiments/run_repro_tifs.py --eth
  python experiments/run_repro_tifs.py --dual
  python experiments/run_repro_tifs.py --all
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


def run_cmd(cmd, cwd):
    t0 = time.time()
    print(f"\n[RUN] {' '.join(cmd)}")
    ret = subprocess.run(cmd, cwd=cwd)
    dt = time.time() - t0
    print(f"[DONE] exit={ret.returncode} elapsed={dt:.1f}s")
    return ret.returncode


def main():
    parser = argparse.ArgumentParser(description="Run TIFS reproduction experiments.")
    parser.add_argument("--eth", action="store_true", help="Run ETH real-network experiment only.")
    parser.add_argument("--dual", action="store_true", help="Run ETH+DOT dual-network experiment.")
    parser.add_argument("--all", action="store_true", help="Run both ETH and dual experiments.")
    args = parser.parse_args()

    if not (args.eth or args.dual or args.all):
        parser.error("Specify one of --eth, --dual, --all.")

    root = Path(__file__).resolve().parent.parent
    py = sys.executable
    exit_code = 0

    if args.eth or args.all:
        exit_code = run_cmd([py, "experiments/run_eth_real_experiments.py"], root)
        if exit_code != 0:
            sys.exit(exit_code)

    if args.dual or args.all:
        exit_code = run_cmd([py, "experiments/run_real_dual_network_experiments.py"], root)
        if exit_code != 0:
            sys.exit(exit_code)

    print("\nAll requested runs finished.")


if __name__ == "__main__":
    main()
