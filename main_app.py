import sys
import os
import logging
from datetime import datetime, timezone, timedelta
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QMessageBox,
    QProgressDialog, QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import Qt, QSettings, QUrl, pyqtSlot
from PyQt6.QtGui import QDesktopServices, QClipboard, QIcon, QAction

# Import logging configuration
from logging_config import setup_logging

# Initialize logger for this module
logger = logging.getLogger(__name__)

from config import (
    APP_NAME, ORGANIZATION_NAME, CONFIG_API_KEY,
    YOUTUBE_REGION_LANGUAGE_MAP, UPLOAD_DATE_OPTIONS_DESC
)
from utils import extract_video_id_from_url

from ui_tabs.tab_api_key import ApiKeyTab
from ui_tabs.tab_keyword_research import KeywordResearchTab
from ui_tabs.tab_suggestions import SuggestionsTab
from ui_tabs.tab_channel_research import ChannelResearchTab
# from ui_tabs.tab_channel_search import ChannelSearchTab # << ĐÃ XÓA
from ui_tabs.tab_channel_analyzer import ChannelAnalyzerTab
from ui_tabs.tab_downloader import DownloaderTab


from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)



class YouTubeToolApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Youtube Research Tool V6.4 Premium - Vũ Trọng 0913.318.313")
        self.setGeometry(100, 100, 1280, 800) # Đã tối ưu kích thước cho màn hình laptop
        # self.setWindowState(Qt.WindowState.WindowMaximized) # Tạm tắt auto max để tránh lỗi hiển thị trên màn nhỏ
        
        # Init Tray Icon
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(resource_path("resources/logo.ico")))
        
        tray_menu = QMenu()
        show_action = QAction("Mở ứng dụng", self)
        show_action.triggered.connect(self.show)
        quit_action = QAction("Thoát", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        
        tray_menu.addAction(show_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        # --- Menu Bar ---
        menubar = self.menuBar()
        tools_menu = menubar.addMenu("Công cụ")
        
        update_lib_action = QAction("Cập nhật Core Library (yt-dlp)", self)
        update_lib_action.setStatusTip("Cập nhật thư viện tải video lên phiên bản mới nhất")
        update_lib_action.triggered.connect(self.update_ytdlp_library)
        tools_menu.addAction(update_lib_action)
        
        self.toggle_theme_action = QAction("Chuyển chế độ Sáng/Tối", self)
        self.toggle_theme_action.triggered.connect(self.toggle_theme)
        tools_menu.addAction(self.toggle_theme_action)
        # ----------------

        self.settings = QSettings(ORGANIZATION_NAME, APP_NAME)
        self.current_theme = self.settings.value("theme", "dark") # Default to dark
        self.api_key = self.settings.value(CONFIG_API_KEY, "")
        self.video_categories = {"Bất kỳ": None}
        self.video_categories_loaded_successfully = False

        self.is_operation_running = False
        self.current_active_thread = None
        self.current_thread_name = ""

        self._init_ui_components()
        self._connect_tab_signals()
        self.load_video_categories()
        self.apply_styles()
        self.update_button_states()

        self.statusBar().showMessage("Sẵn sàng")

    def _init_ui_components(self):
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True) # Cho phép cuộn tab nếu quá dài
        self.setCentralWidget(self.tabs)

        self.api_key_tab = ApiKeyTab(self)
        self.tabs.addTab(self.api_key_tab, "1. API Key")

        self.keyword_research_tab = KeywordResearchTab(self)
        self.tabs.addTab(self.keyword_research_tab, "2. Nghiên cứu Từ khóa")

        self.suggestions_tab = SuggestionsTab(self)
        self.tabs.addTab(self.suggestions_tab, "3. Lấy từ khóa gợi ý")

        self.downloader_tab = DownloaderTab(self)
        self.tabs.addTab(self.downloader_tab, "4. Tải Bình luận, Video, Script")

        # Khối code của Tab 5 đã được xóa bỏ hoàn toàn
        # self.channel_search_tab = ChannelSearchTab(self)
        # self.tabs.addTab(self.channel_search_tab, "5. Tìm Kênh theo KW")

        # ✅ Cập nhật số thứ tự cho các tab còn lại
        self.channel_research_tab = ChannelResearchTab(self)
        self.tabs.addTab(self.channel_research_tab, "5. Lấy Video của Kênh")

        self.channel_analyzer_tab = ChannelAnalyzerTab(self)
        self.tabs.addTab(self.channel_analyzer_tab, "6. PT chỉ số Kênh")



        self.progress_dialog = QProgressDialog("Đang xử lý...", "Hủy", 0, 100, self)
        self.progress_dialog.setWindowTitle("Tiến trình")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setAutoClose(True)
        self.progress_dialog.setAutoReset(True)
        self.progress_dialog.canceled.connect(self.cancel_operation)
        self.progress_dialog.close()

    def _connect_tab_signals(self):
        self.api_key_tab.api_key_changed_and_saved.connect(self.load_video_categories)

    def load_video_categories(self):
        self.video_categories_loaded_successfully = False
        if not self.api_key:
            self.video_categories = {"Bất kỳ": None}
            default_message = "Bất kỳ (Cần API Key hợp lệ)"
            if hasattr(self, 'keyword_research_tab'):
                self.keyword_research_tab.update_categories_combobox({default_message: None})
            self.statusBar().showMessage("API Key không có hoặc không hợp lệ để tải danh mục.", 3000)
            return

        self.statusBar().showMessage("Đang tải danh mục video...", 0)
        QApplication.processEvents()

        try:

            from services.api_manager import APIKeyManager
            APIKeyManager.set_api_keys(self.api_key) # Update keys in manager
            try:
                youtube_service = APIKeyManager.get_service()
            except ValueError:
                 self.statusBar().showMessage("Không thể khởi tạo dịch vụ YouTube (Key lỗi).", 3000)
                 return
            if not youtube_service:
                 raise Exception("Không thể khởi tạo dịch vụ YouTube.")
            region_codes_to_try = ['US', 'VN', 'GB'] 
            response = None
            last_error = None

            for region_code in region_codes_to_try:
                if self.current_active_thread and self.current_active_thread.isInterruptionRequested():
                    self.statusBar().showMessage("Hủy tải danh mục.", 2000)
                    return
                try:
                    response = youtube_service.videoCategories().list(
                        part='snippet', regionCode=region_code
                    ).execute()
                    if response and response.get('items'):
                        break
                except HttpError as e:
                    last_error = e
                    if e.resp.status == 403 or e.resp.status == 400:
                        break 
                except Exception as e_gen:
                    last_error = e_gen
                    break

            current_categories = {"Bất kỳ": None}
            if response and response.get('items'):
                for item in response.get('items', []):
                    current_categories[item['snippet']['title']] = item['id']
                self.video_categories = current_categories
                self.video_categories_loaded_successfully = True
                self.statusBar().showMessage("Tải danh mục video thành công.", 3000)
            else:
                self.video_categories = {"Bất kỳ": None}
                error_msg_display = "Lỗi tải DM (Không có mục)"
                if last_error:
                    if isinstance(last_error, HttpError):
                        try:
                            err_content = json.loads(last_error.content.decode('utf-8'))
                            err_reason = err_content.get("error", {}).get("errors", [{}])[0].get("reason", "")
                            if "quota" in err_reason.lower() or "limit" in err_reason.lower():
                                error_msg_display = "Lỗi tải DM (Hết quota)"
                            elif "keyInvalid" in err_reason or "keyNotValid" in err_reason:
                                error_msg_display = "Lỗi tải DM (Key không hợp lệ)"
                            else:
                                error_msg_display = f"Lỗi tải DM (API {last_error.resp.status})"
                        except (json.JSONDecodeError, KeyError, AttributeError) as parse_err:
                            logger.warning(f"Could not parse error details: {parse_err}")
                            error_msg_display = f"Lỗi tải DM (API {last_error.resp.status})"
                    else: error_msg_display = f"Lỗi tải DM ({type(last_error).__name__})"

                self.statusBar().showMessage(error_msg_display, 5000)
                self.video_categories = {error_msg_display: None, **current_categories}

            if hasattr(self, 'keyword_research_tab'):
                self.keyword_research_tab.update_categories_combobox(self.video_categories)

        except Exception as e:
            self.video_categories = {"Bất kỳ": None, "Lỗi tải DM (Chung)": None}
            self.statusBar().showMessage(f"Lỗi nghiêm trọng khi tải danh mục: {str(e)}", 5000)
            if hasattr(self, 'keyword_research_tab'):
                self.keyword_research_tab.update_categories_combobox(self.video_categories)
            import traceback
            traceback.print_exc()

    def worker_started(self, thread_instance, thread_name=""):
        self.is_operation_running = True
        self.current_active_thread = thread_instance
        self.current_thread_name = thread_name
        self.update_button_states()

    @pyqtSlot()
    def on_worker_thread_finished(self):
        thread_was_interrupted = False
        if self.current_active_thread and hasattr(self.current_active_thread, 'isInterruptionRequested'):
            thread_was_interrupted = self.current_active_thread.isInterruptionRequested()
        self.is_operation_running = False
        self.current_active_thread = None
        self.current_thread_name = ""
        self.update_button_states()
        self.hide_progress_dialog()
        status_msg = "Tác vụ đã bị hủy." if thread_was_interrupted else "Hoàn thành tác vụ."
        if self.progress_dialog and not any(err_kw in self.progress_dialog.labelText().lower() for err_kw in ["lỗi", "không tìm thấy", "bị tắt"]):
            self.statusBar().showMessage(status_msg, 3000)
        elif not self.progress_dialog:
            self.statusBar().showMessage(status_msg, 3000)

    def cancel_operation(self):
        if self.current_active_thread and self.current_active_thread.isRunning():
            self.statusBar().showMessage(f"Đang hủy tác vụ: {self.current_thread_name}...", 3000)
            self.current_active_thread.requestInterruption()
            if self.progress_dialog.isVisible():
                self.progress_dialog.setLabelText(f"Đang hủy tác vụ {self.current_thread_name}...")
        else:
            self.statusBar().showMessage("Không có tác vụ nào đang chạy để hủy.", 3000)
            if self.is_operation_running:
                self.is_operation_running = False
                self.update_button_states()
                self.hide_progress_dialog()

    def update_button_states(self):
        enabled = not self.is_operation_running
        if hasattr(self, 'api_key_tab'):
            self.api_key_tab.set_buttons_enabled(enabled)
        if hasattr(self, 'keyword_research_tab'):
            self.keyword_research_tab.set_buttons_enabled(enabled)
        if hasattr(self, 'suggestions_tab'):
            self.suggestions_tab.set_buttons_enabled(enabled)
        if hasattr(self, 'channel_research_tab'):
            self.channel_research_tab.set_buttons_enabled(enabled)
        # ✅ Khối if cho channel_search_tab đã được xóa
        if hasattr(self, 'channel_analyzer_tab'):
            self.channel_analyzer_tab.set_buttons_enabled(enabled)
        if hasattr(self, 'downloader_tab'):
            self.downloader_tab.set_buttons_enabled(enabled)

    def show_progress_dialog(self, message, current_value=0, show_cancel=True):
        self.progress_dialog.setLabelText(message)
        self.progress_dialog.setValue(current_value)
        self.progress_dialog.setCancelButtonText("Hủy" if show_cancel else "")
        self.progress_dialog.setVisible(True)
        QApplication.processEvents()

    def update_progress_dialog(self, value, message):
        if not self.progress_dialog.isVisible() and value < 100:
            if self.current_active_thread and self.current_active_thread.isInterruptionRequested():
                pass
            else:
                self.progress_dialog.show()
        if self.progress_dialog.isVisible():
            if self.current_active_thread and self.current_active_thread.isInterruptionRequested() and \
               "Đang hủy" not in self.progress_dialog.labelText():
                self.progress_dialog.setLabelText(f"Đang hủy tác vụ {self.current_thread_name}...")
            else:
                self.progress_dialog.setLabelText(message)
            self.progress_dialog.setValue(value)
        QApplication.processEvents()

    def hide_progress_dialog(self):
        self.progress_dialog.reset()
        self.progress_dialog.close()

    @pyqtSlot(str)
    def on_api_error_common_slot(self, error_message):
        QMessageBox.critical(self, "Lỗi API hoặc Xử lý", error_message)
        self.statusBar().showMessage(f"Lỗi: {error_message}", 7000)
        if self.progress_dialog.isVisible():
            self.progress_dialog.setLabelText(f"Lỗi: {error_message[:100]}...")

    def open_url_externally(self, url_string):
        if url_string and (url_string.startswith("http://") or url_string.startswith("https://")):
            QDesktopServices.openUrl(QUrl(url_string))
            self.statusBar().showMessage(f"Đã mở URL: {url_string}", 3000)
        elif url_string:
            self.statusBar().showMessage(f"URL không hợp lệ: {url_string}", 3000)

    def copy_text_to_clipboard(self, text):
        if text:
            QApplication.clipboard().setText(text)
            self.statusBar().showMessage(f"Đã sao chép: {text[:50]}...", 3000)

    def update_ytdlp_library(self):
        """Chạy lệnh pip install --upgrade yt-dlp để cập nhật thư viện lõi."""
        if getattr(sys, 'frozen', False):
            QMessageBox.information(
                self, "Thông báo",
                "Bạn đang chạy phiên bản tệp đóng gói (.exe).\n"
                "Không thể cập nhật trực tiếp thư viện bên trong.\n\n"
                "Vui lòng tải phiên bản .exe mới nhất từ nhà phát triển để có bản cập nhật."
            )
            return

        reply = QMessageBox.question(
            self, "Xác nhận cập nhật",
            "Hệ thống sẽ chạy lệnh cập nhật thư viện 'yt-dlp' qua pip.\n"
            "Quá trình này cần kết nối internet và có thể mất vài giây.\n\n"
            "Bạn có muốn tiếp tục?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.statusBar().showMessage("Đang cập nhật yt-dlp...", 0)
            QApplication.processEvents()
            
            import subprocess
            try:
                # Chạy pip install --upgrade yt-dlp
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                self.statusBar().showMessage("Cập nhật thành công!", 5000)
                QMessageBox.information(self, "Thành công", f"Đã cập nhật yt-dlp.\n\nOutput:\n{result.stdout}")
            except subprocess.CalledProcessError as e:
                self.statusBar().showMessage("Cập nhật thất bại.", 5000)
                QMessageBox.critical(self, "Lỗi", f"Cập nhật thất bại.\n\nError:\n{e.stderr}")
            except Exception as e:
                self.statusBar().showMessage("Lỗi không xác định.", 5000)
                QMessageBox.critical(self, "Lỗi", f"Có lỗi xảy ra: {str(e)}")

    def get_active_api_key(self):
        return self.api_key

    def set_operation_running_status(self, is_running, thread_name=""):
        self.is_operation_running = is_running
        if is_running:
            self.current_thread_name = thread_name
        else:
            self.current_thread_name = ""
            self.current_active_thread = None
        self.update_button_states()

    def apply_styles(self):
        style_file = "resources/styles.qss" if self.current_theme == "dark" else "resources/light_theme.qss"
        try:
            with open(resource_path(style_file), "r", encoding='utf-8') as f: # Cần encoding utf-8 để đọc QSS có comment tiếng Việt
                self.setStyleSheet(f.read())
        except Exception as e:
            logger.error(f"Error loading styles ({style_file}): {e}")

    def toggle_theme(self):
        if self.current_theme == "dark":
            self.current_theme = "light"
        else:
            self.current_theme = "dark"
        
        self.settings.setValue("theme", self.current_theme)
        self.apply_styles()
        self.statusBar().showMessage(f"Đã chuyển sang giao diện {self.current_theme.capitalize()}", 3000)

    def closeEvent(self, event):
        if self.is_operation_running and self.current_active_thread:
            tasks_str = self.current_thread_name if self.current_thread_name else "Một tác vụ"
            reply = QMessageBox.warning(
                self, "Cảnh báo - Tác vụ đang chạy",
                f"Tác vụ '{tasks_str}' đang chạy.\nBạn có muốn dừng và thoát không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.statusBar().showMessage("Đang dừng tác vụ và thoát...", 0)
                QApplication.processEvents()
                self.cancel_operation()
                if self.current_active_thread: self.current_active_thread.wait(1000)
                event.accept()
            else:
                event.ignore()
        else:
            reply = QMessageBox.question(
                self, 'Xác nhận thoát', "Bạn có chắc chắn muốn thoát?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                event.accept()
            else:
                event.ignore()

if __name__ == '__main__':
    # Initialize logging system first
    log_file = setup_logging()
    logger.info("Application starting...")
    
    app = QApplication(sys.argv)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setApplicationName(APP_NAME)
    main_window = YouTubeToolApp()
    main_window.show()
    
    logger.info("Main window displayed")
    sys.exit(app.exec())