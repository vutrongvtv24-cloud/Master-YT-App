# youtube_research_tool/ui_tabs/tab_api_key.py

import json
import traceback

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QGroupBox, QTextEdit
)
from PyQt6.QtCore import QThread, pyqtSignal

# Import từ các tệp trong dự án
from config import CONFIG_API_KEY # Để sử dụng key của QSettings

# Các import cần thiết cho ApiKeyTestThread
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class ApiKeyTestThread(QThread):
    test_result = pyqtSignal(bool, str) # boolean for success, string for message

    def __init__(self, api_key, parent=None):
        super().__init__(parent)
        self.api_key = api_key
        self._is_interruption_requested = False

    def run(self):
        if not self.api_key:
            self.test_result.emit(False, "API Key không được để trống.")
            return

        if self.isInterruptionRequested():
            self.test_result.emit(False, "Kiểm tra API Key bị hủy.")
            return

        try:
            youtube_service = build('youtube', 'v3', developerKey=self.api_key)
            # Test with a valid but innocuous video ID to check API key validity and quota
            youtube_service.videos().list(part='id', id='dQw4w9WgXcQ').execute()

            if self.isInterruptionRequested(): return
            self.test_result.emit(True, "API Key hợp lệ và hoạt động!")

        except HttpError as e:
            if self.isInterruptionRequested(): return
            try:
                error_content = json.loads(e.content.decode('utf-8'))
                error_message = error_content.get("error", {}).get("message", "Lỗi không xác định.")
                status_code = e.resp.status

                if status_code == 400 and \
                   ("API key not valid" in error_message or "keyInvalid" in error_message):
                    self.test_result.emit(False, "API Key không hợp lệ. Vui lòng kiểm tra lại.")
                elif status_code == 403:
                    reason = error_content.get("error", {}).get("errors", [{}])[0].get("reason", "")
                    if reason == "dailyLimitExceeded" or reason == "quotaExceeded" or \
                       "Exceeded" in error_message or "quota" in error_message.lower():
                        self.test_result.emit(False, "Lỗi: Hạn ngạch API đã bị vượt quá.")
                    else:
                        self.test_result.emit(False, f"Lỗi API (403): {error_message}")
                else:
                    self.test_result.emit(False, f"Lỗi khi kiểm tra API Key: {error_message} (Code: {status_code})")
            except json.JSONDecodeError:
                self.test_result.emit(False, f"Lỗi khi phân tích phản hồi lỗi từ API: {e.content.decode('utf-8', errors='ignore')}")
            except Exception as ex_inner:
                self.test_result.emit(False, f"Lỗi không xác định khi xử lý lỗi API: {str(ex_inner)}")
        except Exception as e:
            if self.isInterruptionRequested(): return
            traceback.print_exc()
            self.test_result.emit(False, f"Lỗi không xác định khi kiểm tra API key: {str(e)}. Xem console.")

    def requestInterruption(self):
        self._is_interruption_requested = True
        super().requestInterruption()

    def isInterruptionRequested(self):
        return self._is_interruption_requested or super().isInterruptionRequested()


class ApiKeyTab(QWidget):
    # Signal này có thể được phát ra khi API key được lưu thành công và thay đổi
    # để main_app có thể gọi load_video_categories
    api_key_changed_and_saved = pyqtSignal()

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window  # Tham chiếu đến cửa sổ chính (YouTubeToolApp)
        self.api_key_test_thread = None

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        group_box = QGroupBox("Quản lý API Key")
        group_layout = QVBoxLayout()

        group_layout.addWidget(QLabel("Nhập danh sách API Key (mỗi dòng một Key):"))

        key_input_layout = QHBoxLayout()
        self.txt_api_key = QTextEdit()
        self.txt_api_key.setPlaceholderText("Dán danh sách API Key vào đây, mỗi key một dòng...")
        self.txt_api_key.setMinimumHeight(80)
        # Load API key từ QSettings thông qua main_window
        # Support legacy single key or new multi-key format
        saved_keys = self.main_window.api_key
        self.txt_api_key.setText(saved_keys)

        key_input_layout.addWidget(self.txt_api_key, 1)

        # Removed show/hide button for multiline text edit security simplicity
        # self.btn_show_hide_key = QPushButton("Hiện/Ẩn Key") 
        # ...
        group_layout.addLayout(key_input_layout)

        buttons_layout = QHBoxLayout()
        self.btn_save_key = QPushButton("Lưu Key")
        self.btn_save_key.clicked.connect(self._save_api_key)
        buttons_layout.addWidget(self.btn_save_key)

        self.btn_clear_key = QPushButton("Xóa Key đã lưu")
        self.btn_clear_key.setObjectName("btnDanger") # Để áp dụng style
        self.btn_clear_key.clicked.connect(self._clear_api_key)
        buttons_layout.addWidget(self.btn_clear_key)

        self.btn_test_key = QPushButton("Kiểm tra Key")
        self.btn_test_key.clicked.connect(self._test_api_key)
        buttons_layout.addWidget(self.btn_test_key)
        group_layout.addLayout(buttons_layout)

        self.lbl_api_key_status = QLabel("Trạng thái Key: Chưa kiểm tra (hoặc đã tải từ lần trước).")
        group_layout.addWidget(self.lbl_api_key_status)

        group_layout.addStretch()
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)
        layout.addStretch()



    def _save_api_key(self):
        new_key_text = self.txt_api_key.toPlainText().strip()
        if not new_key_text:
            QMessageBox.warning(self.main_window, "Lưu ý", "Danh sách API Key không được để trống.")
            return

        key_was_changed = (self.main_window.api_key != new_key_text)
        self.main_window.api_key = new_key_text
        self.main_window.settings.setValue(CONFIG_API_KEY, self.main_window.api_key)
        QMessageBox.information(self.main_window, "Thành công", "API Key đã được lưu.")
        self.lbl_api_key_status.setText("Trạng thái Key: Đã lưu (chưa kiểm tra lại với key này).")

        if key_was_changed:
            self.api_key_changed_and_saved.emit() # Thông báo cho main_app

    def _clear_api_key(self):
        reply = QMessageBox.question(self.main_window, "Xác nhận xóa",
                                     "Bạn có chắc chắn muốn xóa API Key đã lưu?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.txt_api_key.clear()
            key_was_present = bool(self.main_window.api_key)
            self.main_window.api_key = ""
            self.main_window.settings.remove(CONFIG_API_KEY)
            QMessageBox.information(self.main_window, "Thông báo", "API Key đã được xóa.")
            self.lbl_api_key_status.setText("Trạng thái Key: Đã xóa.")
            if key_was_present:
                self.api_key_changed_and_saved.emit() # Thông báo cho main_app

    def _test_api_key(self):
        if self.main_window.is_operation_running:
            QMessageBox.warning(self.main_window, "Đang xử lý", "Một tác vụ khác đang chạy. Vui lòng chờ.")
            return

        current_text = self.txt_api_key.toPlainText().strip()
        if not current_text:
            QMessageBox.warning(self.main_window, "Thiếu thông tin", "Vui lòng nhập API Key để kiểm tra.")
            return

        # Chỉ test key đầu tiên để valid
        first_key = current_text.split('\n')[0].strip()

        self.main_window.is_operation_running = True
        self.main_window.update_button_states() # Cập nhật trạng thái các nút trên toàn cục
        self.lbl_api_key_status.setText("Trạng thái Key: Đang kiểm tra...")
        self.main_window.statusBar().showMessage("Đang kiểm tra API Key...")

        # Hủy thread cũ nếu đang chạy (ít khả năng xảy ra ở đây nếu is_operation_running được quản lý đúng)
        if self.api_key_test_thread and self.api_key_test_thread.isRunning():
            self.api_key_test_thread.requestInterruption()
            self.api_key_test_thread.wait() # Chờ thread kết thúc hẳn

        self.api_key_test_thread = ApiKeyTestThread(first_key, self) # self là parent
        self.api_key_test_thread.test_result.connect(self._on_api_key_test_result)
        # Kết nối finished với handler chung trong main_app
        self.api_key_test_thread.finished.connect(self.main_window.on_worker_thread_finished)
        self.api_key_test_thread.start()
        # Kích hoạt progress dialog (nếu cần cho tác vụ test key, thường thì không cần vì nhanh)
        # self.main_window.show_progress_dialog("Đang kiểm tra API Key...", True)

    def _on_api_key_test_result(self, success, message):
        self.lbl_api_key_status.setText(f"Trạng thái Key: {message}")
        self.main_window.statusBar().showMessage(message, 5000)
        # self.main_window.hide_progress_dialog() # Ẩn progress nếu đã hiện

        if success:
            QMessageBox.information(self.main_window, "Kiểm tra API Key", message)
            tested_full_text = self.txt_api_key.toPlainText().strip()
            # Tự động lưu key nếu nó hợp lệ và chưa được lưu hoặc khác với key đã lưu
            if self.main_window.api_key != tested_full_text or not self.main_window.settings.value(CONFIG_API_KEY):
                key_was_changed = (self.main_window.api_key != tested_full_text)
                self.main_window.api_key = tested_full_text
                self.main_window.settings.setValue(CONFIG_API_KEY, self.main_window.api_key)
                self.lbl_api_key_status.setText(f"Trạng thái Key: {message} (Đã tự động lưu)")
                if key_was_changed:
                    self.api_key_changed_and_saved.emit()
            elif self.main_window.api_key == tested_key and not self.main_window.video_categories_loaded_successfully:
                # Key giống nhưng danh mục chưa tải được, thử tải lại
                 self.api_key_changed_and_saved.emit()
        else:
            QMessageBox.warning(self.main_window, "Lỗi Kiểm tra API Key", message)
        # is_operation_running sẽ được reset trong on_worker_thread_finished của main_app

    def set_buttons_enabled(self, enabled):
        """Cho phép main_app cập nhật trạng thái các nút trên tab này."""
        self.btn_save_key.setEnabled(enabled)
        self.btn_clear_key.setEnabled(enabled)
        self.btn_test_key.setEnabled(enabled)
