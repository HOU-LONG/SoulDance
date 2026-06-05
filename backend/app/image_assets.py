from __future__ import annotations

from urllib.parse import quote


def product_image_url(image_path: str | None) -> str:
    if not image_path:
        return ""
    normalized = str(image_path).strip().replace("\\", "/").lstrip("/")
    return "/assets/products/" + quote(normalized, safe="/")
