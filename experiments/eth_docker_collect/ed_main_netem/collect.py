#!/usr/bin/env python3
"""ED-MAIN-NETEM only (tc_netem). Use ``--restart-sim-before-netem`` by default in resume helper."""
import os
import sys

_EXP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _EXP)
from eth_docker_collect.collector_core import run_collection

COLLECTOR = "experiments/eth_docker_collect/ed_main_netem/collect.py"


def main():
    run_collection(
        [("ED-MAIN-NETEM", "tc_netem")],
        collector_name=COLLECTOR,
        summary_filename="eth_docker_collection_summary_ED-MAIN-NETEM.json",
        argv=None,
    )


if __name__ == "__main__":
    main()
