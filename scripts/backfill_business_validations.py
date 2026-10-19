#!/usr/bin/env python3
"""Compatibility entrypoint for the business-quality repair workflow.

The command remains read-only unless ``--apply`` is supplied. New automation
should call ``scripts/repair_business_quality.py`` directly.
"""

from repair_business_quality import main


if __name__ == "__main__":
    raise SystemExit(main())
