"""Start the registered project database under the current Windows token."""
import argparse
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def start(runtime_file):
    config = json.loads(runtime_file.read_text(encoding="utf-8-sig"))
    binary = Path(config["postgres_bin"])
    data = Path(config["pgdata"])
    if binary.resolve() != ROOT / "tools/runtime/pgsql/bin" or data.resolve() != ROOT / "runtime/pgdata":
        raise ValueError("PostgreSQL paths are outside this project's registered runtime")
    ready_args = [str(binary / "pg_isready.exe"), "-h", "127.0.0.1", "-p", str(config["pgport"])]
    if subprocess.run(ready_args, capture_output=True).returncode == 0:
        print("Project PostgreSQL is already accepting connections.")
        return
    with (ROOT / "runtime/postgres.log").open("ab") as log:
        process = subprocess.Popen([str(binary / "postgres.exe"), "-D", str(data), "-p", str(config["pgport"]), "-h", "127.0.0.1"],
                                   stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(60):
        if subprocess.run(ready_args, capture_output=True).returncode == 0:
            print("Project PostgreSQL started under the current token.")
            return
        if process.poll() is not None:
            raise RuntimeError("Project PostgreSQL exited; inspect runtime/postgres.log")
        time.sleep(0.25)
    raise TimeoutError("Project PostgreSQL did not become ready")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    start(parser.parse_args().runtime)
