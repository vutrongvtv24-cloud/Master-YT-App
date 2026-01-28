"""
Logging configuration for YouTube Research Tool.
Tạo log files tự động trong thư mục user để dễ debug.
"""
import logging
import os
from datetime import datetime

def setup_logging():
    """
    Thiết lập logging system cho toàn bộ ứng dụng.
    Log files sẽ được lưu tại: ~/YouTubeResearchTool/logs/
    """
    # Tạo thư mục logs trong thư mục user
    log_dir = os.path.join(os.path.expanduser("~"), "YouTubeResearchTool", "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # Tên file log theo ngày
    log_file = os.path.join(log_dir, f"app_{datetime.now().strftime('%Y%m%d')}.log")
    
    # Cấu hình logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            # Ghi vào file
            logging.FileHandler(log_file, encoding='utf-8'),
            # Vẫn hiện console khi dev (có thể tắt khi release)
            logging.StreamHandler()
        ]
    )
    
    # Log thông tin khởi động
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("YouTube Research Tool - Logging System Initialized")
    logger.info(f"Log file: {log_file}")
    logger.info("=" * 60)
    
    return log_file

def get_logger(name):
    """
    Lấy logger cho module cụ thể.
    
    Args:
        name: Tên module (thường dùng __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)
