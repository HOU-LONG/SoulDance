"""Download the configured cross-encoder reranker model.

Usage:
    python scripts/download_reranker_model.py [--model-id ID] [--target DIR]

Reads settings.rerank_model_id and settings.rerank_model_dir from env, then
fetches the model from ModelScope (or HuggingFace mirror) into the target dir.
Idempotent: if the directory already has model files (.bin or .safetensors), this is a noop.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure backend.app is importable from this script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import get_settings

_LOG = logging.getLogger("download_reranker_model")


def _has_model_files(target: Path) -> bool:
    if not target.exists():
        return False
    return any(target.glob("*.bin")) or any(target.glob("*.safetensors"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default=None, help="override RERANK_MODEL_ID")
    parser.add_argument("--target", default=None, help="override RERANK_MODEL_DIR")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    settings = get_settings()
    model_id = args.model_id or settings.rerank_model_id
    target = Path(args.target or settings.rerank_model_dir)
    if not target.is_absolute():
        target = settings.project_root / target

    if _has_model_files(target):
        _LOG.info("reranker model already present at %s, skipping", target)
        return 0

    target.mkdir(parents=True, exist_ok=True)
    _LOG.info("downloading %s -> %s", model_id, target)

    try:
        from modelscope import snapshot_download
        snapshot_download(model_id, cache_dir=str(target.parent), local_dir=str(target))
    except Exception:
        _LOG.exception("ModelScope download failed; trying HuggingFace mirror")
        try:
            from huggingface_hub import snapshot_download as hf_download
            hf_download(repo_id=model_id, local_dir=str(target))
        except Exception:
            _LOG.exception("HuggingFace download also failed")
            return 1

    _LOG.info("download complete: %s", target)
    return 0


if __name__ == "__main__":
    sys.exit(main())