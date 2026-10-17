"""Compatibility entrypoint; importable implementation lives in acps_mcp_bridge."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acps_mcp_bridge.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
