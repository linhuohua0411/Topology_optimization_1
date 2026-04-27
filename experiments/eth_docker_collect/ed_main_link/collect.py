#!/usr/bin/env python3
"""ED-MAIN-LINK only (link_down). Run after BASE if you need to free disk between campaigns."""
import os
import sys

_EXP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _EXP)
from eth_docker_collect.collector_core import run_collection

COLLECTOR = "experiments/eth_docker_collect/ed_main_link/collect.py"


def main():
    run_collection(
        [("ED-MAIN-LINK", "link_down")],
        collector_name=COLLECTOR,
        summary_filename="eth_docker_collection_summary_ED-MAIN-LINK.json",
        argv=None,
    )


if __name__ == "__main__":
    main()
