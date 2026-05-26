from pathlib import Path

from modelscope import snapshot_download


MODEL_ID = "AI-ModelScope/bge-small-zh-v1.5"
TARGET = Path("model/bge-small-zh-v1.5")


def main() -> None:
    if TARGET.exists() and any(TARGET.iterdir()):
        print(f"Embedding model already exists: {TARGET}")
        return
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    path = snapshot_download(MODEL_ID, local_dir=str(TARGET))
    print(f"Embedding model downloaded to: {path}")


if __name__ == "__main__":
    main()
