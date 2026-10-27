"""Helper for loading and managing Douyin account cookies."""
import os
import re
import logging
from pathlib import Path
from http.cookiejar import MozillaCookieJar
from config import COOKIE_FILE, DOUYIN_COOKIE

logger = logging.getLogger(__name__)

def parse_cookie_string(cookie_str: str) -> dict:
    """Parse cookie string (e.g. 'name=value; name2=value2') into dictionary."""
    cookies = {}
    if not cookie_str:
        return cookies
    cookie_str = cookie_str.lstrip('\ufeff').strip()
    for item in cookie_str.split(';'):
        item = item.strip()
        if '=' in item:
            name, val = item.split('=', 1)
            clean_name = name.strip().lstrip('\ufeff')
            cookies[clean_name] = val.strip()
    return cookies

def load_cookies_from_file(file_path: Path) -> dict:
    """Load cookies from cookies.txt (supports both Netscape format and raw key=value format)."""
    if not file_path.exists():
        return {}
    
    try:
        content = file_path.read_text(encoding='utf-8').strip()
        if not content:
            return {}
        
        # Check if Netscape format (starts with # Netscape or contains tabs)
        if '\t' in content or content.startswith('# Netscape'):
            cookies = {}
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('\t')
                if len(parts) >= 7:
                    name = parts[5].strip()
                    val = parts[6].strip()
                    cookies[name] = val
            return cookies
        else:
            # Raw string format
            return parse_cookie_string(content)
    except Exception as e:
        logger.warning(f"Không thể đọc file cookie {file_path}: {e}")
        return {}

def get_douyin_cookies() -> dict:
    """Get active Douyin cookies from cookies.txt, config, or environment variable."""
    # 1. From env var
    env_cookie = os.environ.get("DOUYIN_COOKIE", "").strip()
    if env_cookie:
        return parse_cookie_string(env_cookie)
    
    # 2. From config string
    if DOUYIN_COOKIE and DOUYIN_COOKIE.strip():
        return parse_cookie_string(DOUYIN_COOKIE.strip())
    
    # 3. From COOKIE_FILE
    if COOKIE_FILE.exists():
        cookies = load_cookies_from_file(COOKIE_FILE)
        if cookies:
            return cookies
            
    return {}

def get_cookie_header_string() -> str:
    """Return raw Cookie header string for HTTP requests."""
    cookies = get_douyin_cookies()
    if not cookies:
        return ""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())

def has_user_cookie() -> bool:
    """Check if valid user cookie is loaded."""
    cookies = get_douyin_cookies()
    return bool(cookies and len(cookies) > 0)
