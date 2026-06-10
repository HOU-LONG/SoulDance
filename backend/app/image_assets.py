from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote, urlparse


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
    """???????????????? URL?

    Cloudflare ??????????????????? SERVER_BASE_URL
    ??? http://192.168.x.x:8000??????? Android ??????
    ???????????????????????? URL?
    """
    base_url = _get_base_url()
    if _is_private_base_url(base_url):
        base_url = ""
    return product_image_url(image_path, base_url)


def _is_private_base_url(base_url: str) -> bool:
    if not base_url:
        return False
    host = (urlparse(base_url).hostname or "").lower()
    if host in {"localhost", "127.0.0.1"}:
        return True
    if host.startswith("192.168.") or host.startswith("10."):
        return True
    parts = host.split(".")
    if len(parts) >= 2 and parts[0] == "172":
        try:
            return 16 <= int(parts[1]) <= 31
        except ValueError:
            return False
    return False
