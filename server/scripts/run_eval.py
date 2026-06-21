from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

server_dir = Path(__file__).resolve().parent.parent
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

from backend.app.eval.runner import load_scenarios, run_scenarios
from backend.app.main import create_app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenarios",
        default="../data/eval/shopguide_core_scenarios.json",
    )
    args = parser.parse_args()
    app = create_app(use_fake_llm=True, use_fake_retriever=False)
    report = run_scenarios(app, load_scenarios(Path(args.scenarios)))
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
