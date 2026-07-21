"""Wait for the overnight enrich to finish, then run the mismatched re-link pass.

Run hidden in the background. Polls for the enrich_state_overnight process; once
it exits, launches scripts/relink_mismatched.py to fix wrong-person FDLE links.
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def enrich_running() -> bool:
    try:
        out = subprocess.check_output(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return "enrich_state_overnight" in out
    except Exception:
        return False


def main():
    print("watcher: waiting for overnight enrich to finish...", flush=True)
    while enrich_running():
        time.sleep(60)
    print("watcher: enrich finished; starting relink_mismatched", flush=True)
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "relink_mismatched.py")],
        cwd=str(ROOT),
    )
    print("watcher: relink pass complete", flush=True)


if __name__ == "__main__":
    main()
