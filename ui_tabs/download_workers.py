import os
import re
import logging
import shutil
import yt_dlp
from datetime import datetime
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

# --- Constants ---
AUDIO_FORMATS_DL = ["mp3", "m4a", "wav"]
BATCH_SIZE = 5
MAX_PLAYLIST_ENTRIES = 50
ACTIVITY_LOG_MAX_LINES = 100 # Giới hạn số dòng trong log


def check_ffmpeg_available():
    """Check if FFmpeg is available in PATH or common locations."""
    if shutil.which('ffmpeg'):
        return True, shutil.which('ffmpeg')
    
    # Check common Windows locations
    common_paths = [
        r'C:\ffmpeg\bin\ffmpeg.exe',
        r'D:\ffmpeg\bin\ffmpeg.exe',
        os.path.expanduser(r'~\ffmpeg\bin\ffmpeg.exe'),
    ]
    for path in common_paths:
        if os.path.isfile(path):
            return True, path
    
    return False, None

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
                        'retries': 10,
                        'file_access_retries': 5,
                        'retry_sleep_functions': {'http': lambda n: min(n * 2, 60), 'fragment': lambda n: min(n * 2, 60)},
                        'restrictfilenames': False,
                        'playlistend': MAX_PLAYLIST_ENTRIES,
                        # --- Anti-Blocking / Bypass 403 Options ---
                        'extractor_args': {
                            'youtube': {
                                'player_client': ['android', 'ios'], # Prefer mobile clients which are less rate-limited
                                'skip': ['dash', 'hls'], # Sometimes helps with 403
                            }
                        },
                        'http_headers': {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                            'Referer': 'https://www.youtube.com/',
                            'Accept-Language': 'en-US,en;q=0.9',
                        },
                        'socket_timeout': 30,
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
                    errors.append(err); self.error_signal.emit(err)
                    logger.exception(f"DownloadCommentsThread error: {err}")
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
            logger.exception(f"Subtitle conversion error: {e}")
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
                        if not video_info_dict: return 
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
                    errors.append(err); self.error_signal.emit(err)
                    logger.exception(f"DownloadSubtitleThread error: {err}")
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
