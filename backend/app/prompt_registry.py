from __future__ import annotations

from pathlib import Path


class PromptRegistry:
    """按版本管理 prompt 文件。"""

    def __init__(self, prompts_dir: str | Path, version: str = "v1"):
        self.prompts_dir = Path(prompts_dir)
        self.version = version

    def load(self, name: str) -> str:
        path = self.prompts_dir / self.version / f"{name}.txt"
        if not path.exists():
            path = self.prompts_dir / "v1" / f"{name}.txt"
        if path.exists():
            return path.read_text(encoding="utf-8")
        raise FileNotFoundError(f"prompt not found: {name} (version={self.version})")
