
import re
import yt_dlp
import isodate
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def extract_video_id_from_url(url):
    """
    Trích xuất Video ID từ URL YouTube (hỗ trợ nhiều định dạng).
    Trả về None nếu không tìm thấy.
    """
    if not url:
        return None
    
    # Các pattern phổ biến
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"(?:youtu\.be\/)([0-9A-Za-z_-]{11})",
        r"(?:shorts\/)([0-9A-Za-z_-]{11})",
        r"^([0-9A-Za-z_-]{11})$"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
            
    return None

def extract_channel_id_yt_dlp(url, status_bar_func=None, process_events_func=None):
    """
    Sử dụng yt-dlp để lấy Channel ID từ URL (handle, custom URL, channel URL, ...).
    Returns: (channel_id, error_message)
    """
    if not url:
        return None, "Url trống"
        
    # Nếu input đã giống channel ID (UC...)
    if re.match(r"^UC[a-zA-Z0-9_-]{22}$", url):
        return url, None

    if status_bar_func:
        status_bar_func(f"Đang phân giải URL kênh: {url} ...")
    if process_events_func:
        process_events_func()

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'playlistend': 1, # Chỉ cần thông tin kênh
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # yt-dlp hỗ trợ tốt việc lấy info từ url kênh
            info = ydl.extract_info(url, download=False)
            
            # Kiểm tra các trường chứa channel id
            c_id = info.get('channel_id')
            if c_id:
                return c_id, None
            
            # Fallback nếu api trả về uploader_id (thường là channel id)
            u_id = info.get('uploader_id')
            if u_id and u_id.startswith('UC'):
                return u_id, None
                
            return None, "Không tìm thấy Channel ID trong thông tin trả về."
            
    except Exception as e:
        return None, str(e)

def format_datetime_iso(iso_str):
    """
    Chuyển đổi chuỗi ISO 8601 (2023-01-01T12:00:00Z) sang format dễ đọc hơn: DD/MM/YYYY HH:MM:SS
    """
    if not iso_str: 
        return ""
    try:
        # Xử lý trường hợp có 'Z' ở cuối
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    except (ValueError, AttributeError) as e:
        logger.debug(f"Could not parse datetime '{iso_str}': {e}")
        return iso_str

def format_date_dd_mm_yyyy(iso_str):
    """
    Chuyển đổi ISO 8601 sang DD-MM-YYYY (Dùng cho Channel Analyzer)
    """
    if not iso_str: return "N/A"
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.strftime("%d-%m-%Y")
    except (ValueError, AttributeError) as e:
        logger.debug(f"Could not parse date '{iso_str}': {e}")
        return iso_str

def format_int_with_separator(value):
    """
    Format số nguyên với dấu phân cách hàng nghìn (dấu chấm hoặc phẩy tùy locale, ở đây dùng phẩy làm chuẩn quốc tế hoặc chấm cho VN).
    """
    if value is None:
        return "0"
    try:
        val = int(value)
        return f"{val:,}"
    except (ValueError, TypeError) as e:
        logger.debug(f"Could not format number '{value}': {e}")
        return str(value)

# Alias cho hàm này vì tab_channel_analyzer gọi tên khác
format_number = format_int_with_separator

def convert_iso_duration(iso_duration):
    """
    Chuyển đổi ISO 8601 duration (PT1H2M30S) sang chuỗi HH:MM:SS hoặc MM:SS
    """
    if not iso_duration:
        return "00:00"
    
    try:
        dur = isodate.parse_duration(iso_duration)
        total_seconds = int(dur.total_seconds())
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    except (ValueError, AttributeError, isodate.ISO8601Error) as e:
        logger.debug(f"Could not parse duration '{iso_duration}': {e}")
        return iso_duration
