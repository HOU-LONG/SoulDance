import sys
from pathlib import Path

from modelscope import snapshot_download
from huggingface_hub import snapshot_download as hf_snapshot_download

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import get_settings


def main() -> None:
    settings = get_settings()
    model_id = settings.rerank_model_id
    target_dir = Path(settings.rerank_model_dir)

    if target_dir.exists() and any(target_dir.iterdir()):
        print(f"Reranker model already exists: {target_dir}")
        return

    target_dir.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Try ModelScope first
        path = snapshot_download(model_id, local_dir=str(target_dir))
        print(f"Reranker model downloaded from ModelScope to: {path}")
    except Exception:
        # Fallback to HuggingFace
        print(f"ModelScope download failed, falling back to HuggingFace")
        path = hf_snapshot_download(model_id, local_dir=str(target_dir))
        print(f"Reranker model downloaded from HuggingFace to: {path}")


if __name__ == "__main__":
    main()
