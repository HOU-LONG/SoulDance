from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote


def product_image_url(image_path: str | None, base_url: str = "") -> str:
    """生成商品图片 URL。

    当 base_url 为空时返回相对路径（适合 Web 前端同源访问）；
    当 base_url 非空时返回绝对 URL（适合 Android / 跨域访问）。
    """
    if not image_path:
        return ""
    normalized = str(image_path).strip().replace("\\", "/").lstrip("/")
    relative = "/assets/products/" + quote(normalized, safe="/")
    if base_url:
        return base_url.rstrip("/") + relative
    return relative


@lru_cache
def _get_base_url() -> str:
    from .config import get_settings
    return get_settings().server_base_url


def product_image_url_auto(image_path: str | None) -> str:
    """自动根据配置决定返回相对还是绝对 URL。"""
    return product_image_url(image_path, _get_base_url())
