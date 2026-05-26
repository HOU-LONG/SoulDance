import os
from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel, Field


class Settings(BaseModel):
    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])
    dataset_dir: str = "ecommerce_agent_dataset"
    ark_api_key: str | None = None
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3/"
    ark_model: str = "ep-20260514111645-lmgt2"
    embedding_model_dir: str = "model/bge-small-zh-v1.5"
    embedding_model_id: str = "AI-ModelScope/bge-small-zh-v1.5"
    embedding_device: str = "cuda:0"
    use_embedding: bool = True
    request_timeout_seconds: float = 45.0

    @property
    def dataset_path(self) -> Path:
        path = Path(self.dataset_dir)
        if path.is_absolute():
            return path
        return self.project_root / path

    @property
    def embedding_path(self) -> Path:
        path = Path(self.embedding_model_dir)
        if path.is_absolute():
            return path
        return self.project_root / path


@lru_cache
def get_settings() -> Settings:
    return Settings(
        dataset_dir=os.getenv("DATASET_DIR", "ecommerce_agent_dataset"),
        ark_api_key=os.getenv("ARK_API_KEY"),
        ark_base_url=os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3/"),
        ark_model=os.getenv("ARK_MODEL", "ep-20260514111645-lmgt2"),
        embedding_model_dir=os.getenv("EMBEDDING_MODEL_DIR", "model/bge-small-zh-v1.5"),
        embedding_model_id=os.getenv("EMBEDDING_MODEL_ID", "AI-ModelScope/bge-small-zh-v1.5"),
        embedding_device=os.getenv("EMBEDDING_DEVICE", "cuda:0"),
        use_embedding=os.getenv("USE_EMBEDDING", "1") not in {"0", "false", "False"},
        request_timeout_seconds=float(os.getenv("ARK_TIMEOUT_SECONDS", "45")),
    )
