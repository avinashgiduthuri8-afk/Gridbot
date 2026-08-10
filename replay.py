#!/usr/bin/env python3
"""Entry point for the replay & stress-testing framework.

    python replay.py --symbols BTCINR ETHINR SOLINR --scenario bull --speed 100x
    python replay.py --symbols BTCINR --data-dir ./historical --from 2025-01-01 --to 2025-06-30

Run `python replay.py --help` for the full option list.
"""
import sys

from replay.cli import main

if __name__ == "__main__":
    sys.exit(main())
