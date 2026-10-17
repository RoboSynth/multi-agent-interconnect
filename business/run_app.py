"""Native process entry point; explicit version/port identify managed processes."""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", choices=["v1", "v2"], required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    os.environ["APP_VERSION"] = args.version
    uvicorn.run("business.order_app.main:app", host="127.0.0.1", port=args.port, log_level="warning")
