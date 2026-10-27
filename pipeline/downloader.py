"""Video downloader with yt-dlp + local file support."""
import logging
import shutil
from pathlib import Path
import yt_dlp

import re
import requests
from config import CACHE_DIR, COOKIE_FILE
from utils.cache import get_cache_dir, is_cached, get_cache_key
from utils.cookie_helper import get_douyin_cookies, get_cookie_header_string, has_user_cookie

logger = logging.getLogger(__name__)

def extract_douyin_id(url: str) -> str | None:
    """Trích xuất ID video từ mọi định dạng link Douyin."""
    # Match modal_id=...
    m = re.search(r'modal_id=(\d+)', url)
    if m:
        return m.group(1)
    # Match /video/...
    m = re.search(r'/video/(\d+)', url)
    if m:
        return m.group(1)
    # Match short link redirect
    if 'v.douyin.com' in url:
        try:
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, allow_redirects=True, timeout=10)
            m = re.search(r'/video/(\d+)', r.url)
            if m:
                return m.group(1)
        except Exception:
            pass
    if url.isdigit():
        return url
    return None

def _get_guest_ttwid(session: requests.Session, headers: dict) -> str | None:
    """Lấy guest session ttwid mới nhất từ ByteDance."""
    data = {
        'region': 'cn', 'aid': 1768, 'needFid': '0',
        'service': 'www.ixigua.com',
        'migrate_info': {'ticket': '', 'source': 'node'},
        'cbUrlProtocol': 'https', 'union': True
    }
    try:
        r = session.post('https://ttwid.bytedance.com/ttwid/union/register/', json=data, headers=headers, timeout=10)
        return r.cookies.get('ttwid') or session.cookies.get('ttwid')
    except Exception as e:
        logger.warning(f"Lỗi lấy ttwid: {e}")
        return None

def download_douyin_direct(url_or_id: str, output_path: Path) -> Path:
    """Tải trực tiếp video Douyin không logo qua CDN API (hỗ trợ cookie tài khoản và tự động fallback guest ttwid)."""
    video_id = extract_douyin_id(url_or_id)
    if not video_id:
        raise ValueError(f"Không thể trích xuất ID video Douyin từ: {url_or_id}")
        
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Referer': 'https://www.douyin.com/',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    # Danh sách các endpoints chi tiết video của Douyin
    api_endpoints = [
        f'https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}&aid=6383&device_platform=webapp',
        f'https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}&aid=1128&version_name=23.5.0&device_platform=android&os_version=23333'
    ]
    
    aweme_detail = None
    
    # 1. Thử với Cookie tài khoản người dùng trước nếu có
    user_cookies = get_douyin_cookies()
    if user_cookies:
        logger.info(f"Đang thử tải với {len(user_cookies)} cookies tài khoản Douyin...")
        for k, v in user_cookies.items():
            session.cookies.set(k, v, domain='.douyin.com')
        headers['Cookie'] = get_cookie_header_string()
        
        for ep in api_endpoints:
            try:
                r = session.get(ep, headers=headers, timeout=10)
                if r.status_code == 200 and 'aweme_detail' in r.text:
                    res = r.json()
                    if res.get('aweme_detail'):
                        aweme_detail = res['aweme_detail']
                        break
            except Exception:
                pass
                
    # 2. Nếu cookie tài khoản bị hết hạn (403) hoặc không có cookie -> Tự động lấy guest ttwid mới
    if not aweme_detail:
        logger.info("Chuyển sang chế độ Guest Session (Fresh ttwid)...")
        session = requests.Session()
        headers.pop('Cookie', None)
        ttwid = _get_guest_ttwid(session, headers)
        if ttwid:
            session.cookies.set('ttwid', ttwid, domain='.douyin.com')
            headers['Cookie'] = f"ttwid={ttwid}"
            
        for ep in api_endpoints:
            try:
                r = session.get(ep, headers=headers, timeout=10)
                if r.status_code == 200 and 'aweme_detail' in r.text:
                    res = r.json()
                    if res.get('aweme_detail'):
                        aweme_detail = res['aweme_detail']
                        break
            except Exception as e:
                logger.warning(f"Lỗi truy vấn endpoint {ep}: {e}")
                
    if not aweme_detail:
        raise RuntimeError(f"Không thể lấy thông tin chi tiết video {video_id} từ Douyin API.")
        
    video_info = aweme_detail.get('video', {})
    
    # Ưu tiên lấy luồng video có Bitrate và độ phân giải cao nhất (1080p HD)
    play_urls = []
    bit_rate_list = video_info.get('bit_rate', [])
    if bit_rate_list and isinstance(bit_rate_list, list):
        sorted_rates = sorted(bit_rate_list, key=lambda x: x.get('bit_rate', 0) if isinstance(x, dict) else 0, reverse=True)
        for item in sorted_rates:
            if isinstance(item, dict):
                gear = item.get('gear_name', 'HD')
                br = item.get('bit_rate', 0)
                urls = item.get('play_addr', {}).get('url_list', [])
                for u in urls:
                    if u not in play_urls:
                        logger.info(f"Đã chọn luồng video chất lượng cao nhất: {gear} (Bitrate: {br:,} bps)")
                        play_urls.append(u)

    # Fallback vào download_addr, play_addr_h264 và play_addr mặc định
    for addr_key in ['download_addr', 'play_addr_h264', 'play_addr']:
        for u in video_info.get(addr_key, {}).get('url_list', []):
            if u not in play_urls:
                play_urls.append(u)
                
    if not play_urls:
        raise RuntimeError("Không tìm thấy luồng phát video trong phản hồi API!")
        
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    download_success = False
    for i, u in enumerate(play_urls):
        try:
            r = session.get(u, headers=headers, stream=True, timeout=(10, 30))
            if r.status_code == 200:
                content_len = int(r.headers.get('content-length', 0))
                downloaded = 0
                with open(output_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if content_len > 0 and downloaded >= content_len:
                                break
                if output_path.exists() and output_path.stat().st_size > 100 * 1024:
                    download_success = True
                    logger.info(f"✅ Tải thành công luồng Bitrate cao nhất (Kích thước: {output_path.stat().st_size / (1024*1024):.2f} MB)")
                    break
        except Exception as e:
            logger.warning(f"Thử nguồn tải {i+1} lỗi: {e}")
            
    if not download_success:
        raise RuntimeError("Không thể tải video từ các luồng CDN của Douyin.")
        
    # Chuẩn hóa & Validate Metadata đầy đủ (kết hợp ffprobe)
    if aweme_detail and output_path.exists():
        import json
        from utils.ffmpeg import get_video_info
        try:
            vinfo = get_video_info(output_path)
            meta = {
                'title': aweme_detail.get('desc', ''),
                'author': aweme_detail.get('author', {}).get('nickname', ''),
                'tags': [t.get('cha_name', '') for t in aweme_detail.get('text_extra', []) if t.get('cha_name')],
                'duration': vinfo.duration,
                'width': vinfo.width,
                'height': vinfo.height,
                'fps': vinfo.fps,
                'source_url': url_or_id
            }
            meta_file = output_path.parent / "metadata.json"
            meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
            logger.info(f"✅ Đã chuẩn hóa metadata: {vinfo.width}x{vinfo.height}, {vinfo.fps:.1f}fps, {vinfo.duration:.1f}s")
        except Exception as e:
            logger.warning(f"Lỗi trích xuất metadata chi tiết: {e}")
            
    return output_path

def download_video(input_source: str) -> Path:
    """Download video from URL or copy from local file."""
    source_path = Path(input_source)
    
    if source_path.is_file():
        # Handle local file
        valid_extensions = ['.mp4', '.mkv', '.webm', '.mov', '.avi']
        if source_path.suffix.lower() not in valid_extensions:
            raise ValueError(f"Định dạng file không hỗ trợ. Hỗ trợ: {valid_extensions}")
        
        local_cache_dir = CACHE_DIR / 'local'
        local_cache_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = local_cache_dir / source_path.name
        shutil.copy2(source_path, output_path)
        return output_path
        
    if input_source.startswith('http'):
        # Check cache
        if is_cached(input_source, "source.mp4"):
            return get_cache_dir(input_source) / "source.mp4"
            
        cache_dir = get_cache_dir(input_source)
        output_path = cache_dir / "source.mp4"
        
        # Nếu là link Douyin, dùng parser trực tiếp tốc độ cao
        if 'douyin.com' in input_source or extract_douyin_id(input_source):
            try:
                return download_douyin_direct(input_source, output_path)
            except Exception as e:
                logger.warning(f"Direct Douyin parser failed: {e}. Thử fallback qua yt-dlp...")
                
        # Fallback qua yt-dlp
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': str(output_path),
            'no_warnings': True,
            'quiet': True,
            'socket_timeout': 60,
            'retries': 3,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                'Referer': 'https://www.douyin.com/',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            },
        }
        if COOKIE_FILE.exists():
            content = COOKIE_FILE.read_text(encoding='utf-8')
            if '\t' in content or content.startswith('# Netscape'):
                ydl_opts['cookiefile'] = str(COOKIE_FILE)
            else:
                from utils.cookie_helper import get_cookie_header_string
                cookie_str = get_cookie_header_string()
                if cookie_str:
                    ydl_opts['http_headers']['Cookie'] = cookie_str
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([input_source])
        except Exception as e:
            logger.warning(f"yt-dlp failed: {e}. Thử fallback Playwright (trình duyệt thật)...")
            
            # ── Fallback cuối cùng: Playwright (trình duyệt headless thật) ──
            try:
                from playwright_dl import download_douyin_playwright
                success = download_douyin_playwright(input_source, output_path)
                if success and output_path.exists() and output_path.stat().st_size > 100_000:
                    logger.info(f"✅ Tải thành công qua Playwright: {output_path}")
                    return output_path
                else:
                    raise RuntimeError("Playwright download failed hoặc file quá nhỏ")
            except ImportError:
                logger.error("Playwright chưa cài đặt. Chạy: pip install playwright && playwright install chromium")
                raise RuntimeError("Không thể tải video từ URL. Hãy thử tải xuống thủ công và dùng file local.") from e
            except Exception as pw_err:
                logger.error(f"Playwright cũng thất bại: {pw_err}")
                raise RuntimeError("Không thể tải video từ URL. Hãy thử tải xuống thủ công và dùng file local.") from pw_err
            
        if not output_path.exists() or output_path.stat().st_size < 100 * 1024:
            raise RuntimeError("Video tải xuống không hợp lệ hoặc quá nhỏ.")
            
        return output_path
        
    raise ValueError("Input phải là URL hoặc đường dẫn file video")

def validate_video(path: Path) -> bool:
    """Validate if file exists and has size > 100KB."""
    if not path.exists():
        return False
    if path.stat().st_size < 100 * 1024:
        return False
    return True

def get_video_metadata(video_path: Path) -> dict:
    """Lấy thông tin tiêu đề/tác giả đã lưu trong cache."""
    import json
    meta_file = video_path.parent / "metadata.json"
    if meta_file.exists():
        try:
            return json.loads(meta_file.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"title": "", "author": "", "tags": []}
