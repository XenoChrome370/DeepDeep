"""DeepDeep entry point.

Examples:
  python main.py --check
  python main.py --download-model       # one-time internet setup
  python main.py                        # offline terminal chat
  python main.py --gui                  # offline Flask web chat
"""

from __future__ import annotations

import argparse
import sys

from brain import DeepDeepBrain
from cli import run_cli
from config import DB_PATH, DOCS_DIR, INDEX_PATH, ensure_directories
from gui import run_gui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepDeep, a private local AI assistant")
    parser.add_argument("--gui", action="store_true", help="start the Flask web interface")
    parser.add_argument("--user", default="local_user", help="name of the local memory profile")
    parser.add_argument("--check", action="store_true", help="check setup without loading the model")
    parser.add_argument("--download-model", action="store_true", help="download the model once")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    ensure_directories()
    print(f"DeepDeep files: {DOCS_DIR.parent}")
    print(f"Memory: {DB_PATH}")
    print(f"Documents: {DOCS_DIR}")

    brain = DeepDeepBrain(DB_PATH, INDEX_PATH)
    if args.check:
        print(f"Device: {brain.device}")
        print(f"Model source: {brain.model_source}")
        print("Runtime dependencies: OK")
        print("Offline policy: model loading will not access the network")
        brain.close()
        return 0

    try:
        if args.download_model:
            print("Downloading the model once; normal runs remain offline afterward…")
            brain.load_model(allow_download=True)
            print("Model downloaded and loaded successfully.")
            brain.close()
            return 0
        if args.gui:
            # The web server starts immediately; gui.py loads the model in its own thread.
            run_gui(brain, args.user)
        else:
            brain.load_model()
            run_cli(brain, args.user)
        return 0
    except KeyboardInterrupt:
        brain.close()
        return 130
    except Exception as exc:
        print(f"\nDeepDeep could not start: {exc}", file=sys.stderr)
        print("\nIf this is the first run, install requirements and run:")
        print("  python main.py --download-model")
        brain.close()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
