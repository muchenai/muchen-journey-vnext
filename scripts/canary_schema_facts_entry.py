"""Entrypoint bundled in the API image for the schema-upgrade fact probe."""

from pathlib import Path
import runpy

runpy.run_path(str(Path("/tmp/db_facts.py") if Path("/tmp/db_facts.py").exists() else Path("/app/deploy/production/db_facts.py")), run_name="__main__")
