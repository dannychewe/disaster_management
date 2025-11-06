# disaster_management/utils/urls.py
from typing import Optional
from urllib.parse import urlparse
from django.conf import settings
from django.http import HttpRequest
from django.core.files.storage import default_storage
from django.templatetags.static import static as dj_static

def _ensure_https(url: str) -> str:
    if not url:
        return url
    if url.startswith("http://"):
        env = getattr(settings, "ENVIRONMENT", "local").lower()
        if env != "local":
            return "https://" + url[len("http://"):]
    return url

def public_base_url() -> str:
    base = (getattr(settings, "PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    if not base:
        env = getattr(settings, "ENVIRONMENT", "local").lower()
        if env != "local":
            raise RuntimeError("PUBLIC_BASE_URL is not configured and no request was provided.")
        return ""
    return _ensure_https(base)

def _is_absolute(u: str) -> bool:
    try:
        p = urlparse(u)
        return p.scheme in ("http", "https")
    except Exception:
        return False

def abs_url(path: str, request: Optional[HttpRequest] = None) -> str:
    if not path:
        base = public_base_url()
        if not base:
            return ""
        return base
    if _is_absolute(path):
        return _ensure_https(path)
    path = "/" + path.lstrip("/")
    if request:
        return _ensure_https(request.build_absolute_uri(path))
    base = public_base_url()
    if not base:
        raise RuntimeError("PUBLIC_BASE_URL is not configured and no request was provided.")
    return f"{base}{path}"

def abs_media_url(name_or_path: str, request: Optional[HttpRequest] = None) -> Optional[str]:
    if not name_or_path:
        return None
    if isinstance(name_or_path, str) and _is_absolute(name_or_path):
        return _ensure_https(name_or_path)
    url = default_storage.url(str(name_or_path).lstrip("/"))
    if _is_absolute(url):
        return _ensure_https(url)
    return abs_url(url, request)

def abs_static_url(path: str, request: Optional[HttpRequest] = None) -> str:
    return abs_url(dj_static(path), request)
