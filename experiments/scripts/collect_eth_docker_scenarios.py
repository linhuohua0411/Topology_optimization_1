#!/usr/bin/env python3
"""
Legacy Eth-Docker collector: BASE + LINK + NETEM in one process.

Prefer split entry points (smaller disk bursts between campaigns):
``eth_docker_collect/ed_main_{base,link,netem}/collect.py``.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from eth_docker_collect.collector_core import run_collection

ALL_SCENARIOS = [
    ("ED-MAIN-BASE", "none"),
    ("ED-MAIN-LINK", "link_down"),
    ("ED-MAIN-NETEM", "tc_netem"),
]


def main():
    run_collection(
        ALL_SCENARIOS,
        collector_name="collect_eth_docker_scenarios.py",
        summary_filename="eth_docker_collection_summary.json",
        argv=None,
    )


if __name__ == "__main__":
    main()
