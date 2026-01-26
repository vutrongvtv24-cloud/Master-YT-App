import os
import threading
import time
import csv
import re
import traceback
import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QLineEdit,
    QPushButton, QComboBox, QProgressBar, QFileDialog as QQtFileDialog, QMessageBox,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QApplication,
    QSizePolicy, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QMetaObject, pyqtSlot
from PyQt6.QtGui import QGuiApplication, QIntValidator, QTextCursor

import yt_dlp

# --- Constants ---
AUDIO_FORMATS_DL = ["mp3", "m4a", "wav"]
BATCH_SIZE = 5
MAX_PLAYLIST_ENTRIES = 50
ACTIVITY_LOG_MAX_LINES = 100 # Giới hạn số dòng trong log

# --- Custom Exception for Cancellation ---
class CancelledErrorDL(Exception):
    """Custom exception for download cancellation specific to this tab."""
    pass

# --- Utility Function ---
def sanitize_filename_local(filename_str):
    if not isinstance(filename_str, str):
        filename_str = str(filename_str)
    
    invalid_os_chars = r'<>:"/\\|?*'
    control_chars_map = {
        '\n': '_', '\r': '_', '\t': '_',
    }
    
    sanitized = filename_str
    for char, replacement in control_chars_map.items():
        sanitized = sanitized.replace(char, replacement)

    for char in invalid_os_chars:
        sanitized = sanitized.replace(char, '_')
    
    return sanitized[:200].strip('_ ')

# --- Utility Function to Format View Count ---
def format_view_count(view_count):
    if not view_count:
        return "0k"
    if view_count < 1000000:
        return f"{round(view_count / 1000)}k"
    else:
        millions = view_count / 1000000
        return f"{millions:.2f}m".replace(".", ",")

# --- Worker Thread for Downloading Media ---
class DownloadMediaThread(QThread):
    status_updated = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str, str)
    entry_downloaded_signal = pyqtSignal(str, str, str)
    task_finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    failed_urls_signal = pyqtSignal(list)

    def __init__(self, urls, save_dir, quality, media_format, is_audio_only, cancel_event_ref, downloaded_urls, parent=None):
        super().__init__(parent)
        self.urls = urls
        self.save_dir = save_dir
        self.quality = quality
        self.media_format = media_format
        self.is_audio_only = is_audio_only
        self.cancel_event = cancel_event_ref
        self.downloaded_urls = downloaded_urls
        self._is_interruption_requested_qthread = False
        self.failed_urls = []

    def requestInterruption(self):
        self._is_interruption_requested_qthread = True
        self.cancel_event.set()
        super().requestInterruption()

    def isInterruptionGlobalRequested(self):
        if super().isInterruptionRequested() or self._is_interruption_requested_qthread:
            self.cancel_event.set()
            return True
        return self.cancel_event.is_set()

    def run(self):
        total_urls = len(self.urls)
        download_errors = []
        processed_url_count = 0

        for batch_start in range(0, total_urls, BATCH_SIZE):
            batch_urls = self.urls[batch_start:batch_start + BATCH_SIZE]
            
            for index, url_item in enumerate(batch_urls, batch_start):
                current_url_num = index + 1
                processed_url_count = current_url_num

                if self.isInterruptionGlobalRequested():
                    download_errors.append(f"Quá trình tải bị hủy trước URL {current_url_num}")
                    break
                
                self.status_updated.emit(f"({current_url_num}/{total_urls}) Chuẩn bị URL: {url_item[:70]}...")

                def qt_progress_hook(d):
                    if self.isInterruptionGlobalRequested():
                        raise CancelledErrorDL("Hủy bỏ từ progress hook.")

                    if d['status'] == 'downloading':
                        total_bytes_str = d.get('_total_bytes_str', 'N/A').replace('iB', 'B')
                        downloaded_bytes_str = d.get('_downloaded_bytes_str', 'N/A').replace('iB', 'B')
                        speed_str = d.get('_speed_str', 'N/A').replace('iB', 'B')
                        eta_str = d.get('_eta_str', 'N/A')
                        
                        status_msg = (f"Đang tải... {downloaded_bytes_str} / {total_bytes_str} "
                                      f"@ {speed_str} (ETA: {eta_str})")
                        self.status_updated.emit(status_msg)

                    elif d['status'] == 'finished':
                        self.status_updated.emit(f"Tải xong file: {os.path.basename(d.get('filename', '...'))}")
                    elif d['status'] == 'error':
                        self.status_updated.emit(f"Lỗi khi tải file: {os.path.basename(d.get('filename', '...'))}")

                try:
                    ydl_opts = {
                        'progress_hooks': [qt_progress_hook],
                        'noplaylist': False,
                        'ignoreerrors': True,
                        'quiet': True,
                        'no_warnings': True,
                        'nocheckcertificate': True,
                        'continuedl': True,
                        'fragment_retries': 10,
                        'retry_sleep_functions': {'http': lambda n: min(n * 1, 30), 'fragment': lambda n: min(n * 1, 30)},
                        'restrictfilenames': False,
                        'playlistend': MAX_PLAYLIST_ENTRIES,
                    }

                    if self.is_audio_only:
                        ydl_opts['format'] = 'bestaudio/best'
                        ydl_opts['postprocessors'] = [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': self.media_format,
                            'preferredquality': '192',
                        }]
                    else:
                        ydl_opts['merge_output_format'] = self.media_format
                        quality_val_str = self.quality[:-1] if self.quality.endswith('p') else self.quality
                        if self.quality and self.quality != "best":
                            ydl_opts['format'] = f'bestvideo[height<={quality_val_str}]+bestaudio/best[height<={quality_val_str}]'
                        else:
                            ydl_opts['format'] = 'bestvideo+bestaudio/best'
                    
                    info_ydl_opts = ydl_opts.copy()
                    info_ydl_opts['extract_flat'] = 'in_playlist'
                    
                    with yt_dlp.YoutubeDL(info_ydl_opts) as ydl_info_fetcher:
                        self.status_updated.emit(f"({current_url_num}/{total_urls}) Đang lấy thông tin URL: {url_item[:70]}...")
                        info = ydl_info_fetcher.extract_info(url_item, download=False)

                    if self.isInterruptionGlobalRequested(): raise CancelledErrorDL(f"Hủy bỏ URL {current_url_num} sau khi lấy info")

                    actual_dl_opts = ydl_opts.copy() 
                    actual_dl_opts['extract_flat'] = False 
                    actual_dl_opts['noplaylist'] = True   
                    
                    # SỬA LỖI: Thêm `if info` để tránh lỗi khi không lấy được dữ liệu
                    if info and 'entries' in info and info['entries']: 
                        playlist_entries = info['entries']
                        total_in_playlist = len(playlist_entries)
                        pl_title = sanitize_filename_local(info.get('title', f'Playlist_{current_url_num}'))
                        self.status_updated.emit(f"Playlist '{pl_title}' ({total_in_playlist} video). Bắt đầu xử lý...")

                        for i, entry in enumerate(playlist_entries):
                            if self.isInterruptionGlobalRequested(): raise CancelledErrorDL("Hủy bỏ trong playlist.")
                            if entry is None:
                                self.status_updated.emit(f"Playlist '{pl_title}': Bỏ qua video {i+1}/{total_in_playlist} (lỗi info)")
                                continue

                            entry_url = entry.get('webpage_url') or entry.get('url')
                            if not entry_url:
                                self.status_updated.emit(f"Playlist '{pl_title}': Bỏ qua video {i+1}/{total_in_playlist} (không có URL)")
                                continue
                                
                            entry_title_orig = entry.get('title', f'Video_{i+1}_thuoc_{pl_title}')
                            entry_title_sanitized = sanitize_filename_local(entry_title_orig)
                            view_count = format_view_count(entry.get('view_count', 0))
                            self.status_updated.emit(f"Playlist '{pl_title}': Video {i+1}/{total_in_playlist}: {entry_title_sanitized[:50]}...")
                            
                            current_item_opts = actual_dl_opts.copy()
                            if self.is_audio_only:
                                 current_item_opts['outtmpl'] = os.path.join(self.save_dir, f'{entry_title_sanitized}_{view_count}.{self.media_format}')
                            else:
                                 current_item_opts['outtmpl'] = os.path.join(self.save_dir, f'{entry_title_sanitized}_{view_count}.%(ext)s')

                            try:
                                with yt_dlp.YoutubeDL(current_item_opts) as ydl_item:
                                    ydl_item.download([entry_url])
                                self.entry_downloaded_signal.emit("Video/Audio" if not self.is_audio_only else "Audio", entry_title_orig, entry_url)
                                self.downloaded_urls.add((url_item, "media"))
                            except yt_dlp.utils.DownloadError as pl_item_de:
                                err = f"Lỗi tải '{entry_title_sanitized[:30]}' (Playlist): {str(pl_item_de)[:100]}"
                                download_errors.append(err); self.error_signal.emit(err)
                                self.failed_urls.append(url_item)
                            except CancelledErrorDL: raise
                            except Exception as pl_item_ex:
                                err = f"Lỗi khác với '{entry_title_sanitized[:30]}' (Playlist): {type(pl_item_ex).__name__} - {str(pl_item_ex)[:100]}"
                                download_errors.append(err); self.error_signal.emit(err)
                                self.failed_urls.append(url_item)
                            if self.isInterruptionGlobalRequested(): break
                            self.msleep(10)
                    elif info: 
                        single_title_orig = info.get('title', f'Video_{current_url_num}')
                        single_title_sanitized = sanitize_filename_local(single_title_orig)
                        view_count = format_view_count(info.get('view_count', 0))
                        single_url_to_download = info.get('webpage_url', url_item)
                        self.status_updated.emit(f"({current_url_num}/{total_urls}) Đang tải: {single_title_sanitized[:60]}...")
                        
                        current_item_opts = actual_dl_opts.copy()
                        if self.is_audio_only:
                             current_item_opts['outtmpl'] = os.path.join(self.save_dir, f'{single_title_sanitized}_{view_count}.{self.media_format}')
                        else:
                             current_item_opts['outtmpl'] = os.path.join(self.save_dir, f'{single_title_sanitized}_{view_count}.%(ext)s')

                        try:
                            with yt_dlp.YoutubeDL(current_item_opts) as ydl_item:
                                ydl_item.download([single_url_to_download])
                            self.entry_downloaded_signal.emit("Video/Audio" if not self.is_audio_only else "Audio", single_title_orig, single_url_to_download)
                            self.downloaded_urls.add((url_item, "media"))
                        except yt_dlp.utils.DownloadError as de:
                            err = f"Lỗi DownloadError (chung) URL {current_url_num}: {str(de)[:150]}"
                            download_errors.append(err); self.error_signal.emit(err)
                            self.failed_urls.append(url_item)
                        except Exception as e:
                            err = f"Lỗi không xác định (chung) URL {current_url_num}: {type(e).__name__} - {str(e)[:150]}"
                            download_errors.append(err); self.error_signal.emit(err)
                            self.failed_urls.append(url_item)
                    else:
                        err = f"Không thể lấy thông tin cho URL: {url_item}"
                        download_errors.append(err); self.error_signal.emit(err)
                        self.failed_urls.append(url_item)

                except CancelledErrorDL as ce:
                     download_errors.append(str(ce)); break
                except Exception as e:
                     err = f"Lỗi không xác định (chung) URL {current_url_num}: {type(e).__name__} - {str(e)[:150]}"
                     download_errors.append(err); self.error_signal.emit(err)
                     self.failed_urls.append(url_item)
                     self.status_updated.emit(f"Lỗi URL {current_url_num}, chuyển tiếp...")

                self.msleep(10)

            if self.isInterruptionGlobalRequested():
                break
            self.msleep(100)

        if self.failed_urls:
            self.failed_urls_signal.emit(self.failed_urls)

        final_msg = ""
        if self.isInterruptionGlobalRequested() and processed_url_count > 0 and total_urls > 0:
             final_msg = f"Đã hủy. Xử lý {processed_url_count - 1 if processed_url_count <= total_urls else total_urls - 1}/{total_urls} URL."
        elif download_errors:
             final_msg = f"Hoàn tất {processed_url_count}/{total_urls} URL với {len(download_errors)} lỗi."
        else:
             final_msg = f"Hoàn tất tải xuống tất cả {total_urls} URL!"
        self.task_finished_signal.emit(final_msg)

# --- Worker Thread for Downloading Comments ---
class DownloadCommentsThread(QThread):
    status_updated = pyqtSignal(str)
    comments_batch_signal = pyqtSignal(list)
    task_finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    failed_urls_signal = pyqtSignal(list)

    def __init__(self, urls, cancel_event_ref, downloaded_urls, filter_options, parent=None):
        super().__init__(parent)
        self.urls = urls
        self.cancel_event = cancel_event_ref
        self.downloaded_urls = downloaded_urls
        self.filter_options = filter_options
        self._is_interruption_requested_qthread = False
        self.failed_urls = []
        self.total_comments_fetched = 0
        self.total_comments_passed_filter = 0

    def requestInterruption(self):
        self._is_interruption_requested_qthread = True
        self.cancel_event.set()
        super().requestInterruption()

    def isInterruptionGlobalRequested(self):
        if super().isInterruptionRequested() or self._is_interruption_requested_qthread:
            self.cancel_event.set(); return True
        return self.cancel_event.is_set()

    def _filter_comments_dynamically(self, comments):
        if not self.filter_options.get('enabled', False):
            count = len(comments)
            self.total_comments_fetched += count
            self.total_comments_passed_filter += count
            return comments

        min_words = self.filter_options.get('min_words', 0)
        include_keywords = [k.strip().lower() for k in self.filter_options.get('include', '').split(',') if k.strip()]
        exclude_keywords = [k.strip().lower() for k in self.filter_options.get('exclude', '').split(',') if k.strip()]
        exclude_authors_keywords = [a.strip().lower() for a in self.filter_options.get('exclude_authors', '').split(',') if a.strip()]
        exclude_uploader = self.filter_options.get('exclude_uploader', False)
        
        filtered_comments = []
        self.total_comments_fetched += len(comments)

        for comment in comments:
            if exclude_uploader and comment.get('author_is_uploader', False):
                continue
            
            author_lower = comment.get('author', '').lower()
            if exclude_authors_keywords and any(author_keyword in author_lower for author_keyword in exclude_authors_keywords):
                continue

            text = comment.get('text', '').strip()
            text_lower = text.lower()
            
            if len(text.split()) < min_words:
                continue
            
            if exclude_keywords and any(re.search(r'\b' + re.escape(keyword) + r'\b', text_lower) for keyword in exclude_keywords):
                continue
            
            if include_keywords and not any(re.search(r'\b' + re.escape(keyword) + r'\b', text_lower) for keyword in include_keywords):
                continue
            
            filtered_comments.append(comment)
        
        self.total_comments_passed_filter += len(filtered_comments)
        return filtered_comments

    def run(self):
        total_urls = len(self.urls)
        errors = []
        processed_url_count = 0

        for batch_start in range(0, total_urls, BATCH_SIZE):
            batch_urls = self.urls[batch_start:batch_start + BATCH_SIZE]
            
            for index, url_item in enumerate(batch_urls, batch_start):
                current_url_num = index + 1
                processed_url_count = current_url_num

                if self.isInterruptionGlobalRequested():
                    errors.append(f"Hủy tải bình luận trước URL {current_url_num}"); break

                self.status_updated.emit(f"({current_url_num}/{total_urls}) Lấy bình luận: {url_item[:70]}...")

                try:
                    ydl_opts = {
                        'extract_flat': 'in_playlist',
                        'noplaylist': False,
                        'ignoreerrors': True,
                        'getcomments': True,
                        'force_generic_extractor': False,
                        'quiet': False,
                        'no_warnings': True,
                        'nocheckcertificate': True,
                        'playlistend': MAX_PLAYLIST_ENTRIES,
                    }

                    class YtDlpLogger:
                        def debug(self, msg):
                            if 'Downloading comment' in msg:
                                self.status_updated.emit(msg.strip())
                        def info(self, msg): pass
                        def warning(self, msg): pass
                        def error(self, msg): self.error_signal.emit(msg.strip())
                    
                    logger = YtDlpLogger()
                    logger.status_updated = self.status_updated
                    logger.error_signal = self.error_signal
                    ydl_opts['logger'] = logger

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url_item, download=False, process=True)
                        if self.isInterruptionGlobalRequested(): raise CancelledErrorDL("Hủy bỏ")

                        def process_single_video_comments(video_info_dict):
                            if video_info_dict is None: return
                            video_title_sanitized = sanitize_filename_local(video_info_dict.get('title', 'Video_khong_ten'))
                            comments_data = video_info_dict.get('comments')

                            if comments_data:
                                filtered_comments = self._filter_comments_dynamically(comments_data)
                                if filtered_comments:
                                    self.comments_batch_signal.emit(filtered_comments)
                                    self.downloaded_urls.add((url_item, "comments"))
                                else:
                                    self.status_updated.emit(f"Không có bình luận nào thỏa mãn điều kiện lọc cho '{video_title_sanitized[:50]}'")
                            else:
                                self.status_updated.emit(f"Không có bình luận hoặc không thể lấy cho '{video_title_sanitized[:50]}'")
                        
                        # SỬA LỖI: Thêm `if info` để tránh lỗi khi không lấy được dữ liệu
                        if info and 'entries' in info and info['entries']:
                            pl_title = sanitize_filename_local(info.get('title', f'Playlist_{current_url_num}'))
                            self.status_updated.emit(f"Playlist '{pl_title}': Xử lý bình luận cho từng video...")
                            for i, entry in enumerate(info['entries']):
                                if self.isInterruptionGlobalRequested(): raise CancelledErrorDL("Hủy trong playlist comments")
                                if entry is None: continue
                                process_single_video_comments(entry)
                                self.msleep(10)
                        elif info:
                            process_single_video_comments(info)
                        else:
                            err = f"Không thể lấy thông tin (bình luận) cho URL: {url_item}"
                            errors.append(err); self.error_signal.emit(err)
                            self.failed_urls.append(url_item)

                except CancelledErrorDL as ce: errors.append(str(ce)); break
                except yt_dlp.utils.DownloadError as de:
                    err = f"Lỗi yt-dlp (comments) URL {current_url_num}: {str(de)[:150]}"
                    errors.append(err); self.error_signal.emit(err)
                    self.failed_urls.append(url_item)
                except Exception as e:
                    err = f"Lỗi không xác định (comments) URL {current_url_num}: {type(e).__name__} - {str(e)[:150]}"
                    errors.append(err); self.error_signal.emit(err); traceback.print_exc()
                    self.failed_urls.append(url_item)

                self.msleep(10)

            if self.isInterruptionGlobalRequested():
                break
            self.msleep(100)

        if self.failed_urls:
            self.failed_urls_signal.emit(self.failed_urls)

        summary = (f"Tổng cộng: Lấy được {self.total_comments_fetched} bình luận, "
                   f"{self.total_comments_passed_filter} bình luận thỏa mãn điều kiện lọc. ")

        final_msg = ""
        if self.isInterruptionGlobalRequested() and processed_url_count > 0:
            final_msg = summary + f"Đã hủy tải bình luận. Xử lý {processed_url_count-1}/{total_urls} URL."
        elif errors:
            final_msg = summary + f"Hoàn tất tải bình luận {processed_url_count}/{total_urls} URL với {len(errors)} lỗi."
        else:
            final_msg = summary + f"Hoàn tất tải bình luận cho tất cả {total_urls} URL!"
        self.task_finished_signal.emit(final_msg)
        
# --- Worker Thread for Downloading Subtitles ---
class DownloadSubtitlesThread(QThread):
    status_updated = pyqtSignal(str)
    entry_downloaded_signal = pyqtSignal(str, str, str)
    task_finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    failed_urls_signal = pyqtSignal(list)

    def __init__(self, urls, save_dir, target_format, cancel_event_ref, downloaded_urls, parent=None):
        super().__init__(parent)
        self.urls = urls
        self.save_dir = save_dir
        self.target_format = target_format
        self.cancel_event = cancel_event_ref
        self.downloaded_urls = downloaded_urls
        self._is_interruption_requested_qthread = False
        self.failed_urls = []

    def requestInterruption(self):
        self._is_interruption_requested_qthread = True
        self.cancel_event.set()
        super().requestInterruption()

    def isInterruptionGlobalRequested(self):
        if super().isInterruptionRequested() or self._is_interruption_requested_qthread:
            self.cancel_event.set(); return True
        return self.cancel_event.is_set()

    def _convert_subtitle_to_txt(self, subtitle_filepath, txt_filepath):
        try:
            with open(subtitle_filepath, 'r', encoding='utf-8') as infile:
                raw_content = infile.read()

            processed_content = re.sub(r'^(WEBVTT[^\n]*\n+)([^\n]*Kind:[^\n]*\n)?([^\n]*Language:[^\n]*\n)?\n*', '', raw_content, flags=re.MULTILINE)
            if not processed_content.strip() and raw_content.startswith("WEBVTT"):
                 processed_content = re.sub(r'^WEBVTT[^\n]*\n*', '', raw_content, flags=re.MULTILINE)
            processed_content = re.sub(r'^\s*\d*\s*\n?\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}.*\n', '', processed_content, flags=re.MULTILINE)
            processed_content = re.sub(r'^\s*\d+\s*\n', '', processed_content, flags=re.MULTILINE)
            processed_content = re.sub(r'<[^>]*>', '', processed_content)

            lines = [line.strip() for line in processed_content.split('\n')]
            final_lines = []
            previous_distinct_line = object()
            for current_line_text in lines:
                if not current_line_text: continue
                if re.fullmatch(r'\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}.*', current_line_text): continue
                if re.fullmatch(r'\d+', current_line_text) and len(final_lines) > 0 and not final_lines[-1]: continue

                if current_line_text != previous_distinct_line:
                    final_lines.append(current_line_text)
                    previous_distinct_line = current_line_text
            content = '\n'.join(final_lines)

            with open(txt_filepath, 'w', encoding='utf-8') as outfile:
                outfile.write(content)
            self.status_updated.emit(f"Đã chuyển đổi phụ đề: {os.path.basename(txt_filepath)}")
            return True
        except FileNotFoundError:
            self.error_signal.emit(f"Lỗi: Không tìm thấy file phụ đề {os.path.basename(subtitle_filepath)} để chuyển đổi.")
            return False
        except Exception as e:
            self.error_signal.emit(f"Lỗi khi chuyển đổi {os.path.basename(subtitle_filepath)} sang TXT: {e}")
            traceback.print_exc()
            return False

    def run(self):
        total_urls = len(self.urls)
        errors = []
        processed_url_count = 0
        yt_dlp_sub_formats = 'vtt/srt/best'

        for batch_start in range(0, total_urls, BATCH_SIZE):
            batch_urls = self.urls[batch_start:batch_start + BATCH_SIZE]
            
            for index, url_item in enumerate(batch_urls, batch_start):
                current_url_num = index + 1
                processed_url_count = current_url_num

                if self.isInterruptionGlobalRequested():
                    errors.append(f"Hủy tải phụ đề trước URL {current_url_num}"); break
                
                self.status_updated.emit(f"({current_url_num}/{total_urls}) Tải phụ đề (cho .txt): {url_item[:70]}...")

                try:
                    base_outtmpl = os.path.join(self.save_dir, sanitize_filename_local('%(title)s') + ' [%(id)s]')
                    ydl_opts = {
                        'writesubtitles': True,
                        'writeautomaticsub': True,
                        'subtitlesformat': yt_dlp_sub_formats,
                        'subtitleslangs': ['vi', 'en'],
                        'skip_download': True,
                        'outtmpl': base_outtmpl,
                        'extract_flat': 'in_playlist',
                        'noplaylist': False,
                        'ignoreerrors': True,
                        'quiet': True,
                        'no_warnings': True,
                        'nocheckcertificate': True,
                        'restrictfilenames': False,
                        'playlistend': MAX_PLAYLIST_ENTRIES,
                    }

                    info_ydl_opts = ydl_opts.copy()
                    info_ydl_opts['writesubtitles'] = False 
                    info_ydl_opts['writeautomaticsub'] = False
                    
                    with yt_dlp.YoutubeDL(info_ydl_opts) as ydl_info_fetcher:
                        info = ydl_info_fetcher.extract_info(url_item, download=False, process=False)

                    if self.isInterruptionGlobalRequested(): raise CancelledErrorDL("Hủy bỏ sau khi lấy info phụ đề")

                    sub_dl_opts = ydl_opts.copy()
                    sub_dl_opts['extract_flat'] = False
                    sub_dl_opts['noplaylist'] = True

                    def find_and_convert_subs_for_video_item(video_info_dict, original_url_hist):
                        if not video_info_dict: return # Thêm kiểm tra phòng vệ
                        video_title_orig = video_info_dict.get('title', 'Video_khong_ten')
                        video_title_sanitized = sanitize_filename_local(video_title_orig)
                        video_id = video_info_dict.get('id')
                        view_count = format_view_count(video_info_dict.get('view_count', 0))

                        if not video_id:
                            msg = f"Không có Video ID cho '{video_title_orig}', bỏ qua tải phụ đề."
                            errors.append(msg); self.status_updated.emit(msg)
                            self.failed_urls.append(url_item)
                            return

                        current_item_sub_dl_opts = sub_dl_opts.copy()
                        current_item_sub_dl_opts['outtmpl'] = os.path.join(self.save_dir, f'{video_title_sanitized} [%(id)s]')

                        try:
                            with yt_dlp.YoutubeDL(current_item_sub_dl_opts) as ydl_item_subs:
                                ydl_item_subs.extract_info(video_info_dict.get('webpage_url') or original_url_hist, download=True)
                        except Exception as e_dl_sub:
                            errors.append(f"Lỗi khi yt-dlp tải phụ đề cho '{video_title_sanitized}': {type(e_dl_sub).__name__} - {e_dl_sub}")
                            self.failed_urls.append(url_item)
                            return

                        if self.isInterruptionGlobalRequested(): raise CancelledErrorDL("Hủy trong khi tìm/chuyển đổi phụ đề")

                        found_any_sub_for_conversion = False
                        for fname_candidate in os.listdir(self.save_dir):
                            if video_id in fname_candidate and \
                               (fname_candidate.lower().endswith('.vtt') or fname_candidate.lower().endswith('.srt')):
                                sub_file_path = os.path.join(self.save_dir, fname_candidate)
                                if os.path.isfile(sub_file_path):
                                    lang_match = re.search(r'\.([a-zA-Z]{2}(?:-[a-zA-Z]{2,3})?)\.(vtt|srt)$', fname_candidate, re.IGNORECASE)
                                    lang_suffix_for_txt = f"_{lang_match.group(1)}" if lang_match else "_sub"
                                    txt_filename = f"{video_title_sanitized}_{view_count}_script{lang_suffix_for_txt}.txt"
                                    txt_output_file_path = os.path.join(self.save_dir, txt_filename)
                                    self.status_updated.emit(f"Đang chuyển đổi '{fname_candidate}' sang .txt")
                                    if self._convert_subtitle_to_txt(sub_file_path, txt_output_file_path):
                                        found_any_sub_for_conversion = True
                                        self.entry_downloaded_signal.emit(f"Phụ đề .txt ({lang_suffix_for_txt.strip('_')})", video_title_orig, original_url_hist)
                                        self.downloaded_urls.add((url_item, "subtitles"))
                                    try: os.remove(sub_file_path)
                                    except OSError as e_rem: self.status_updated.emit(f"Không thể xóa file tạm '{sub_file_path}': {e_rem}")
                        if not found_any_sub_for_conversion:
                            self.status_updated.emit(f"Không tìm/chuyển đổi được phụ đề .txt nào cho '{video_title_sanitized[:50]}'")
                    
                    # SỬA LỖI: Thêm `if info` để tránh lỗi khi không lấy được dữ liệu
                    if info and 'entries' in info and info['entries']:
                        pl_title = sanitize_filename_local(info.get('title', f'Playlist_{current_url_num}'))
                        self.status_updated.emit(f"Playlist '{pl_title}': Xử lý phụ đề cho từng video...")
                        for i, entry in enumerate(info['entries']):
                            if self.isInterruptionGlobalRequested(): raise CancelledErrorDL("Hủy trong playlist subs")
                            if entry is None: continue
                            entry_webpage_url = entry.get('webpage_url') or entry.get('url')
                            current_entry_info = entry
                            if not entry.get('id') and entry_webpage_url:
                                 try:
                                    self.status_updated.emit(f"Fetch lại info chi tiết cho mục playlist: {entry.get('title', '...')[:30]}")
                                    temp_info_opts = {'quiet':True, 'no_warnings':True, 'extract_flat': False, 'noplaylist': True, 'skip_download':True}
                                    with yt_dlp.YoutubeDL(temp_info_opts) as ydl_entry_info_fetch:
                                        current_entry_info = ydl_entry_info_fetch.extract_info(entry_webpage_url, download=False)
                                 except Exception as e_refetch_pl_entry:
                                     errors.append(f"Lỗi fetch ID cho mục playlist '{entry.get('title', 'N/A')}': {e_refetch_pl_entry}")
                                     self.failed_urls.append(url_item)
                                     continue
                            find_and_convert_subs_for_video_item(current_entry_info, entry_webpage_url)
                            self.msleep(10)
                    elif info:
                        find_and_convert_subs_for_video_item(info, url_item)
                    else:
                        errors.append(f"Không lấy được thông tin/ID cho URL (phụ đề): {url_item}")
                        self.failed_urls.append(url_item)

                except CancelledErrorDL as ce: errors.append(str(ce)); break
                except yt_dlp.utils.DownloadError as de:
                    err = f"Lỗi yt-dlp (phụ đề chung) URL {current_url_num}: {str(de)[:150]}"
                    errors.append(err); self.error_signal.emit(err)
                    self.failed_urls.append(url_item)
                except Exception as e:
                    err = f"Lỗi không xác định (phụ đề chung) URL {current_url_num}: {type(e).__name__} - {str(e)[:150]}"
                    errors.append(err); self.error_signal.emit(err); traceback.print_exc()
                    self.failed_urls.append(url_item)

                self.msleep(10)

            if self.isInterruptionGlobalRequested():
                break
            self.msleep(100)

        if self.failed_urls:
            self.failed_urls_signal.emit(self.failed_urls)

        final_msg = ""
        if self.isInterruptionGlobalRequested() and processed_url_count > 0:
            final_msg = f"Đã hủy tải phụ đề. Xử lý {processed_url_count-1}/{total_urls} URL."
        elif errors:
            final_msg = f"Hoàn tất tải phụ đề {processed_url_count}/{total_urls} URL với {len(errors)} lỗi."
        else:
            final_msg = f"Hoàn tất tải và chuyển đổi phụ đề cho {total_urls} URL!"
        self.task_finished_signal.emit(final_msg)

class DownloaderTab(QWidget):
    def __init__(self, main_window_ref):
        super().__init__()
        self.main_window = main_window_ref
        self.is_downloading_tab6 = False
        self.cancel_event_tab6 = threading.Event()
        self.current_download_thread = None
        self.downloaded_urls = set()

        self._setup_ui()
        self._connect_signals()
        self._on_format_change()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # --- URL Input ---
        url_group = QGroupBox("YouTube URL(s) (mỗi URL một dòng) hoặc URL Playlist")
        url_layout = QVBoxLayout(url_group)
        self.url_text_edit = QTextEdit()
        self.url_text_edit.setPlaceholderText("Dán các URL vào đây...")
        self.url_text_edit.setFixedHeight(100)
        url_layout.addWidget(self.url_text_edit)
        layout.addWidget(url_group)

        # --- Download Options ---
        options_main_layout = QHBoxLayout()
        quality_group = QGroupBox("Chất lượng Video")
        quality_v_layout = QVBoxLayout(quality_group)
        self.combo_quality = QComboBox()
        self.combo_quality.addItems(["best", "1440p", "1080p", "720p", "480p", "360p"])
        quality_v_layout.addWidget(self.combo_quality)
        options_main_layout.addWidget(quality_group)

        format_group = QGroupBox("Định dạng")
        format_v_layout = QVBoxLayout(format_group)
        self.combo_format = QComboBox()
        self.combo_format.addItems(["mp4", "mkv"] + AUDIO_FORMATS_DL)
        format_v_layout.addWidget(self.combo_format)
        options_main_layout.addWidget(format_group)
        layout.addLayout(options_main_layout)

        # --- Save Path ---
        save_path_group = QGroupBox("Thư mục lưu")
        save_path_layout = QHBoxLayout(save_path_group)
        self.txt_save_path = QLineEdit(os.path.expanduser("~/Downloads"))
        save_path_layout.addWidget(self.txt_save_path, 1)
        self.btn_choose_dir = QPushButton("Chọn...")
        save_path_layout.addWidget(self.btn_choose_dir)
        layout.addWidget(save_path_group)

        # --- Action Buttons ---
        action_buttons_layout = QHBoxLayout()
        self.btn_download_media = QPushButton("Tải Video/Audio")
        action_buttons_layout.addWidget(self.btn_download_media)
        self.btn_download_comments = QPushButton("Tải Bình luận")
        action_buttons_layout.addWidget(self.btn_download_comments)
        self.btn_download_subtitles = QPushButton("Tải Phụ đề (.txt)")
        action_buttons_layout.addWidget(self.btn_download_subtitles)
        layout.addLayout(action_buttons_layout)

        # --- SỬA LỖI GIAO DIỆN: Comment Filtering GroupBox ---
        filter_group = QGroupBox("Tùy chọn lọc bình luận")
        filter_layout = QVBoxLayout(filter_group)
        
        # Hàng 1: Checkbox bật/tắt bộ lọc
        self.chk_enable_filter = QCheckBox("Bật lọc bình luận")
        filter_layout.addWidget(self.chk_enable_filter)

        # Hàng 2: Bố cục ngang cho "Số từ tối thiểu" để nhãn và ô nhập liệu đi cùng nhau
        min_words_layout = QHBoxLayout()
        min_words_label = QLabel("Số từ tối thiểu:")
        self.txt_min_words = QLineEdit("0")
        self.txt_min_words.setValidator(QIntValidator(0, 999))
        self.txt_min_words.setFixedWidth(50)
        min_words_layout.addWidget(min_words_label)
        min_words_layout.addWidget(self.txt_min_words)
        min_words_layout.addStretch() # Đẩy các phần tử về bên trái
        filter_layout.addLayout(min_words_layout)

        # Hàng 3: Checkbox "Loại bỏ bình luận của chủ kênh" nằm trên một hàng riêng
        self.chk_exclude_uploader = QCheckBox("Loại bỏ bình luận của chủ kênh")
        self.chk_exclude_uploader.setChecked(True)
        filter_layout.addWidget(self.chk_exclude_uploader)
        
        # Các tùy chọn còn lại giữ nguyên
        include_label = QLabel("Bình luận chứa từ (phân tách bằng dấu phẩy):")
        self.txt_include_keywords = QLineEdit()
        self.txt_include_keywords.setPlaceholderText("vd: hay, tuyệt vời,... (khớp toàn bộ từ)")
        filter_layout.addWidget(include_label)
        filter_layout.addWidget(self.txt_include_keywords)

        exclude_label = QLabel("Loại bỏ bình luận chứa từ (phân tách bằng dấu phẩy):")
        self.txt_exclude_keywords = QLineEdit()
        self.txt_exclude_keywords.setPlaceholderText("vd: dở, tệ,... (khớp toàn bộ từ)")
        filter_layout.addWidget(exclude_label)
        filter_layout.addWidget(self.txt_exclude_keywords)

        exclude_authors_label = QLabel("Loại bỏ bình luận có tên tác giả chứa từ (phân tách bằng dấu phẩy):")
        self.txt_exclude_authors = QLineEdit()
        self.txt_exclude_authors.setPlaceholderText("vd: marketing, casino, review,... (khớp một phần tên)")
        filter_layout.addWidget(exclude_authors_label)
        filter_layout.addWidget(self.txt_exclude_authors)
        
        layout.addWidget(filter_group)
        # --- KẾT THÚC PHẦN SỬA LỖI ---

        # --- Progress and Status ---
        self.btn_cancel_download = QPushButton("Hủy Tải")
        self.btn_cancel_download.setEnabled(False)
        layout.addWidget(self.btn_cancel_download, 0, Qt.AlignmentFlag.AlignRight)

        # --- Activity Log ---
        activity_log_group = QGroupBox("Activity Log")
        log_layout = QVBoxLayout(activity_log_group)
        self.activity_log = QTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setFixedHeight(80)
        log_layout.addWidget(self.activity_log)
        layout.addWidget(activity_log_group)

        # --- Comments Result Group ---
        comment_results_group = QGroupBox("Kết quả bình luận đã lọc")
        comment_results_layout = QVBoxLayout(comment_results_group)
        self.comments_table = QTableWidget()
        self.comments_table.setColumnCount(4)
        self.comments_table.setHorizontalHeaderLabels(["Tác giả", "Nội dung bình luận", "Lượt thích", "Số phản hồi"])
        self.comments_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.comments_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.comments_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.comments_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        comment_results_layout.addWidget(self.comments_table)

        self.btn_export_comments = QPushButton("Xuất kết quả ra CSV")
        self.btn_export_comments.setEnabled(False)
        comment_results_layout.addWidget(self.btn_export_comments, 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(comment_results_group)
        
        layout.addStretch()

    def _connect_signals(self):
        self.combo_format.currentTextChanged.connect(self._on_format_change)
        self.btn_choose_dir.clicked.connect(self._choose_directory)
        self.btn_download_media.clicked.connect(self._start_download_media)
        self.btn_download_comments.clicked.connect(self._start_download_comments)
        self.btn_download_subtitles.clicked.connect(self._start_download_subtitles)
        self.btn_cancel_download.clicked.connect(self._request_cancel_tab6)
        self.btn_export_comments.clicked.connect(self._export_comments_to_csv)

    def _on_format_change(self, _=None):
        selected_format = self.combo_format.currentText()
        is_audio = selected_format in AUDIO_FORMATS_DL
        self.combo_quality.setEnabled(not is_audio and not self.is_downloading_tab6)
        if is_audio:
            if self.combo_quality.count() > 0: self.combo_quality.setCurrentIndex(0)
        else:
            if not self.combo_quality.currentText() or self.combo_quality.currentText() == "":
                self.combo_quality.setCurrentText("best")

    def _choose_directory(self):
        current_path = self.txt_save_path.text()
        if not current_path or not os.path.isdir(current_path):
            current_path = os.path.expanduser("~/Downloads")
        directory = QQtFileDialog.getExistingDirectory(self, "Chọn thư mục lưu trữ", current_path)
        if directory: self.txt_save_path.setText(directory)

    def _get_urls_from_input(self, task_type):
        url_content = self.url_text_edit.toPlainText().strip()
        if not url_content:
            QMessageBox.warning(self.main_window, "Thiếu URL", "Vui lòng nhập ít nhất một URL YouTube.")
            return None
        urls = [line.strip() for line in url_content.splitlines() if line.strip() and (line.strip().startswith("http://") or line.strip().startswith("https://"))]
        urls = list(dict.fromkeys(urls))
        
        def extract_video_id_from_url(url):
            patterns = [
                r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})',
                r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([a-zA-Z0-9_-]{11})',
                r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
                r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/v\/([a-zA-Z0-9_-]{11})'
            ]
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    return match.group(1)
            return None

        invalid_urls = []
        valid_urls = []
        for url in urls:
            if 'playlist?list=' in url or extract_video_id_from_url(url):
                valid_urls.append(url)
            else:
                invalid_urls.append(url)

        if not valid_urls:
            QMessageBox.warning(self.main_window, "URL không hợp lệ", "Không tìm thấy URL hợp lệ nào (video hoặc playlist).")
            return None
        
        if invalid_urls:
            error_message = "Các URL sau không hợp lệ và sẽ bị bỏ qua:\n" + "\n".join(invalid_urls)
            QMessageBox.warning(self.main_window, "URL không hợp lệ", error_message)

        new_urls = valid_urls

        if len(new_urls) > 20:
            reply = QMessageBox.question(self.main_window, "Danh sách URL lớn",
                                         f"Bạn đã nhập {len(new_urls)} URL hợp lệ. Xử lý nhiều URL có thể gây chậm. Tiếp tục?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                return None
        return new_urls

    def _request_cancel_tab6(self):
        if self.is_downloading_tab6 and self.current_download_thread and self.current_download_thread.isRunning():
            reply = QMessageBox.question(self.main_window, "Xác nhận hủy",
                                         "Bạn có chắc chắn muốn hủy quá trình tải xuống hiện tại?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self._add_to_activity_log("Đang yêu cầu hủy...")
                self.current_download_thread.requestInterruption()
        else:
            self._add_to_activity_log("Không có tác vụ tải nào đang chạy để hủy.")

    def _start_generic_download_task(self, task_type):
        urls = self._get_urls_from_input(task_type)
        if not urls: return

        if self.is_downloading_tab6:
            QMessageBox.warning(self.main_window, "Đang xử lý", "Một quá trình tải ở tab này đang chạy.")
            return

        self.is_downloading_tab6 = True
        self.cancel_event_tab6.clear()
        self.activity_log.clear()
        self.main_window.update_button_states() # Disable controls on this tab only

        save_dir = self.txt_save_path.text()
        if not os.path.isdir(save_dir):
            try: os.makedirs(save_dir, exist_ok=True)
            except OSError as e:
                QMessageBox.critical(self.main_window, "Lỗi Thư mục", f"Không thể tạo thư mục lưu: {save_dir}\n{e}")
                self.is_downloading_tab6 = False; self.main_window.update_button_states()
                return

        thread_class, thread_args, thread_display_name = None, [urls], ""

        if task_type == "media":
            quality = self.combo_quality.currentText()
            media_format = self.combo_format.currentText()
            is_audio = media_format in AUDIO_FORMATS_DL
            
            thread_class = DownloadMediaThread
            thread_args.extend([save_dir, quality, media_format, is_audio, self.cancel_event_tab6, self.downloaded_urls])
            thread_display_name = "Tải Video/Audio"
        elif task_type == "comments":
            self.comments_table.setRowCount(0)
            self.btn_export_comments.setEnabled(False)
            filter_options = {
                'enabled': self.chk_enable_filter.isChecked(),
                'min_words': int(self.txt_min_words.text()) if self.txt_min_words.text().isdigit() else 0,
                'include': self.txt_include_keywords.text(),
                'exclude': self.txt_exclude_keywords.text(),
                'exclude_uploader': self.chk_exclude_uploader.isChecked(),
                'exclude_authors': self.txt_exclude_authors.text(),
            }
            thread_class = DownloadCommentsThread
            thread_args.extend([self.cancel_event_tab6, self.downloaded_urls, filter_options])
            thread_display_name = "Tải Bình luận"
        elif task_type == "subtitles":
            thread_class = DownloadSubtitlesThread
            thread_args.extend([save_dir, "txt", self.cancel_event_tab6, self.downloaded_urls])
            thread_display_name = "Tải Phụ đề .txt"
        else:
            self.is_downloading_tab6 = False
            self.main_window.update_button_states()
            return

        self.current_download_thread = thread_class(*thread_args, parent=self)
        self._add_to_activity_log(f"Chuẩn bị {thread_display_name} cho {len(urls)} URL...")

        self.current_download_thread.status_updated.connect(self._add_to_activity_log)
        self.current_download_thread.task_finished_signal.connect(self._on_task_finished_slot)
        self.current_download_thread.error_signal.connect(self._on_task_error_slot)
        self.current_download_thread.failed_urls_signal.connect(self._show_failed_urls)
        
        if isinstance(self.current_download_thread, DownloadCommentsThread):
             self.current_download_thread.comments_batch_signal.connect(self._add_comments_to_table)

        # Remove main_window.on_worker_thread_finished connection because we don't want to affect global state
        self.current_download_thread.finished.connect(self._reset_tab_download_state_slot)

        # Removed main_window.worker_started to prevent global UI lock
        self.current_download_thread.start()

    def _start_download_media(self): self._start_generic_download_task("media")
    def _start_download_comments(self): self._start_generic_download_task("comments")
    def _start_download_subtitles(self): self._start_generic_download_task("subtitles")

    @pyqtSlot()
    def _reset_tab_download_state_slot(self):
        if self.sender() is self.current_download_thread:
            self.is_downloading_tab6 = False
            self.current_download_thread = None
        self.main_window.update_button_states()

    @pyqtSlot(str)
    def _add_to_activity_log(self, message):
        if not self.isHidden():
            self.activity_log.append(message)
            if self.activity_log.document().blockCount() > ACTIVITY_LOG_MAX_LINES:
                cursor = self.activity_log.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.Start)
                cursor.select(QTextCursor.SelectionType.LineUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()
            self.activity_log.verticalScrollBar().setValue(self.activity_log.verticalScrollBar().maximum())

    @pyqtSlot(list)
    def _add_comments_to_table(self, comments_batch):
        self.comments_table.setSortingEnabled(False)
        for comment in comments_batch:
            row_pos = self.comments_table.rowCount()
            self.comments_table.insertRow(row_pos)
            self.comments_table.setItem(row_pos, 0, QTableWidgetItem(comment.get('author', 'N/A')))
            self.comments_table.setItem(row_pos, 1, QTableWidgetItem(comment.get('text', '')))
            self.comments_table.setItem(row_pos, 2, QTableWidgetItem(str(comment.get('like_count', 0))))
            self.comments_table.setItem(row_pos, 3, QTableWidgetItem(str(comment.get('reply_count', 0))))
        self.comments_table.setSortingEnabled(True)
        if self.comments_table.rowCount() > 0:
            self.btn_export_comments.setEnabled(True)

    def _export_comments_to_csv(self):
        if self.comments_table.rowCount() == 0:
            QMessageBox.information(self, "Không có dữ liệu", "Không có bình luận nào trong bảng để xuất.")
            return

        save_dir = self.txt_save_path.text()
        default_filename = os.path.join(save_dir, "filtered_comments.csv")
        filepath, _ = QQtFileDialog.getSaveFileName(self, "Lưu file CSV", default_filename, "CSV Files (*.csv)")

        if not filepath:
            return

        try:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                headers = [self.comments_table.horizontalHeaderItem(i).text() for i in range(self.comments_table.columnCount())]
                writer.writerow(headers)
                
                for row in range(self.comments_table.rowCount()):
                    row_data = [self.comments_table.item(row, col).text() for col in range(self.comments_table.columnCount())]
                    writer.writerow(row_data)
            
            QMessageBox.information(self, "Thành công", f"Đã xuất thành công {self.comments_table.rowCount()} bình luận ra file:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể lưu file.\nLỗi: {e}")

    @pyqtSlot(str)
    def _on_task_finished_slot(self, final_message):
        if not self.isHidden():
            self._add_to_activity_log(f"--- {final_message} ---")
            if "Hoàn tất" in final_message and "lỗi" not in final_message.lower() and "hủy" not in final_message.lower():
                QMessageBox.information(self.main_window, "Thành công", final_message)
            elif "hủy" in final_message.lower():
                QMessageBox.warning(self.main_window, "Đã hủy", final_message)
            elif "lỗi" in final_message.lower() or "không thể" in final_message.lower():
                 QMessageBox.warning(self.main_window, "Hoàn tất với lỗi", final_message + "\nHãy kiểm tra log và console để biết thêm chi tiết.")

    @pyqtSlot(list)
    def _show_failed_urls(self, failed_urls):
        if not self.isHidden() and failed_urls:
            failed_urls_text = "\n".join(failed_urls)
            msg_box = QMessageBox(self.main_window)
            msg_box.setWindowTitle("URL không tải được")
            msg_box.setText("Danh sách URL không thể tải xuống (có thể chọn và copy nội dung dưới đây):")
            msg_box.setDetailedText(failed_urls_text)
            # SỬA LỖI: Bỏ nút Copy để tránh lỗi `AttributeError` trên một số phiên bản PyQt6
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()

    @pyqtSlot(str)
    def _on_task_error_slot(self, error_message):
        if not self.isHidden():
            self._add_to_activity_log(f"LỖI: {error_message}")
            self.main_window.statusBar().showMessage(f"Lỗi tải item: {error_message[:100]}...", 7000)
            print(f"ERROR_PER_ITEM (DownloaderTab): {error_message}")

    def set_buttons_enabled(self, global_app_busy):
        can_start_new_in_tab = not global_app_busy and not self.is_downloading_tab6

        self.btn_download_media.setEnabled(can_start_new_in_tab)
        self.btn_download_comments.setEnabled(can_start_new_in_tab)
        self.btn_download_subtitles.setEnabled(can_start_new_in_tab)

        self.btn_cancel_download.setEnabled(self.is_downloading_tab6)
        
        has_comment_data = self.comments_table.rowCount() > 0
        self.btn_export_comments.setEnabled(has_comment_data and not self.is_downloading_tab6)

        controls_should_be_active = not (global_app_busy or self.is_downloading_tab6)
        self.url_text_edit.setReadOnly(not controls_should_be_active)
        is_audio = self.combo_format.currentText() in AUDIO_FORMATS_DL
        self.combo_quality.setEnabled(controls_should_be_active and not is_audio)
        self.combo_format.setEnabled(controls_should_be_active)
        self.txt_save_path.setReadOnly(not controls_should_be_active)
        self.btn_choose_dir.setEnabled(controls_should_be_active)
        
        self.chk_enable_filter.setEnabled(controls_should_be_active)
        self.txt_min_words.setReadOnly(not controls_should_be_active)
        self.txt_include_keywords.setReadOnly(not controls_should_be_active)
        self.txt_exclude_keywords.setReadOnly(not controls_should_be_active)
        self.chk_exclude_uploader.setEnabled(controls_should_be_active)
        self.txt_exclude_authors.setReadOnly(not controls_should_be_active)