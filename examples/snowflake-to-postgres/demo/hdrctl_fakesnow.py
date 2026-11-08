"""Run hdrctl against the local Snowflake emulator instead of a real account.

    python demo/hdrctl_fakesnow.py run .
"""
import os
import sys
from pathlib import Path

import fakesnow

DB = Path(__file__).resolve().parent / "fakesnow-db"
for k in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PRIVATE_KEY_FILE", "SNOWFLAKE_WAREHOUSE"):
    os.environ.setdefault(k, "demo")

with fakesnow.patch(db_path=str(DB)):
    from hydra_etl.cli.hdrctl import main

    sys.argv = ["hdrctl"] + sys.argv[1:]
    sys.exit(main())
