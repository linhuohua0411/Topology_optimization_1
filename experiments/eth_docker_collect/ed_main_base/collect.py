#!/usr/bin/env python3
"""ED-MAIN-BASE only (no link/netem). Log: results/raw/eth_docker_collection_ED-MAIN-BASE.log (optional)."""
import os
import sys

_EXP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _EXP)
from eth_docker_collect.collector_core import run_collection

COLLECTOR = "experiments/eth_docker_collect/ed_main_base/collect.py"


def main():
    run_collection(
        [("ED-MAIN-BASE", "none")],
        collector_name=COLLECTOR,
        summary_filename="eth_docker_collection_summary_ED-MAIN-BASE.json",
        argv=None,
    )


if __name__ == "__main__":
    main()
