"""Run with python -m nanobot.channels.iris.setup --state PATH."""
import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Pair nanobot with one Iris Chat contact.")
    parser.add_argument("--state", required=True)
    args = parser.parse_args()
    state = str(Path(args.state).expanduser().resolve())
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("transport.py")),
        "interactive", "--state", state, "--name", "nanobot"], check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
    print("Iris is paired. Set channels.iris.enabled to true and channels.iris.stateDir to:")
    print(state)


if __name__ == "__main__":
    main()
