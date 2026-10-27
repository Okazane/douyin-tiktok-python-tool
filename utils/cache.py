"""Caching utility for Douyin2TikTok."""

import hashlib
import shutil
from pathlib import Path
from config import CACHE_DIR, CACHE_ENABLED

def get_cache_key(url: str) -> str:
    """Tạo SHA256 hash của URL (16 ký tự đầu)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]

def get_cache_dir(url: str) -> Path:
    """Trả về CACHE_DIR / hash. Tạo folder nếu chưa tồn tại."""
    key = get_cache_key(url)
    cache_path = CACHE_DIR / key
    cache_path.mkdir(parents=True, exist_ok=True)
    return cache_path

def is_cached(url: str, filename: str = "source.mp4") -> bool:
    """Kiểm tra file đã được cache chưa và kích thước hợp lệ (>100KB)."""
    if not CACHE_ENABLED:
        return False
    cache_dir = get_cache_dir(url)
    p = cache_dir / filename
    return p.exists() and p.stat().st_size > 100 * 1024

def get_cached_path(url: str, filename: str) -> Path | None:
    """Trả về path nếu có trong cache, ngược lại trả về None."""
    if not CACHE_ENABLED:
        return None
    cache_dir = get_cache_dir(url)
    file_path = cache_dir / filename
    if file_path.exists():
        return file_path
    return None

def save_to_cache(url: str, source_path: Path, filename: str = "source.mp4") -> Path:
    """Copy file vào cache, trả về path mới."""
    cache_dir = get_cache_dir(url)
    target_path = cache_dir / filename
    shutil.copy2(source_path, target_path)
    return target_path
