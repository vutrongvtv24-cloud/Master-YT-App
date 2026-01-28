import os
import threading
import json
import csv

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QLineEdit,
    QPushButton, QComboBox, QFileDialog as QQtFileDialog, QMessageBox,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QGridLayout, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QIntValidator, QTextCursor

# Import Worker Threads and Constants from separate module
from ui_tabs.download_workers import (
    DownloadMediaThread,
    DownloadCommentsThread,
    DownloadSubtitlesThread,
    AUDIO_FORMATS_DL,
    ACTIVITY_LOG_MAX_LINES
)

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
        # Tạo layout chính cho Tab
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Tạo ScrollArea để chứa toàn bộ nội dung
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        
        # Container widget cho nội dung bên trong ScrollArea
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
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

        # --- Comment Filtering GroupBox ---
        filter_group = QGroupBox("Tùy chọn lọc bình luận")
        filter_layout = QGridLayout(filter_group)
        filter_layout.setColumnStretch(1, 1) # Cho cột 2 giãn ra
        
        # Hàng 0: Checkboxes
        self.chk_enable_filter = QCheckBox("Bật lọc bình luận")
        filter_layout.addWidget(self.chk_enable_filter, 0, 0, 1, 2)
        
        self.chk_exclude_uploader = QCheckBox("Loại bỏ bình luận của chủ kênh")
        self.chk_exclude_uploader.setChecked(True)
        filter_layout.addWidget(self.chk_exclude_uploader, 1, 0, 1, 2)

        # Hàng 2: Số từ tối thiểu 
        lbl_min_words = QLabel("Số từ tối thiểu:")
        filter_layout.addWidget(lbl_min_words, 2, 0)
        self.txt_min_words = QLineEdit("0")
        self.txt_min_words.setValidator(QIntValidator(0, 999))
        self.txt_min_words.setFixedWidth(60)
        filter_layout.addWidget(self.txt_min_words, 2, 1)

        # Hàng 3: Include Keywords
        lbl_include = QLabel("Chứa từ (cách nhau bởi phẩy):")
        filter_layout.addWidget(lbl_include, 3, 0)
        self.txt_include_keywords = QLineEdit()
        self.txt_include_keywords.setPlaceholderText("vd: hay, tuyệt vời,...")
        filter_layout.addWidget(self.txt_include_keywords, 3, 1)

        # Hàng 4: Exclude Keywords
        lbl_exclude = QLabel("Loại bỏ từ (cách nhau bởi phẩy):")
        filter_layout.addWidget(lbl_exclude, 4, 0)
        self.txt_exclude_keywords = QLineEdit()
        self.txt_exclude_keywords.setPlaceholderText("vd: dở, tệ,...")
        filter_layout.addWidget(self.txt_exclude_keywords, 4, 1)

        # Hàng 5: Exclude Authors
        lbl_exclude_auth = QLabel("Loại bỏ tác giả (tên chứa):")
        filter_layout.addWidget(lbl_exclude_auth, 5, 0)
        self.txt_exclude_authors = QLineEdit()
        self.txt_exclude_authors.setPlaceholderText("vd: marketing, casino,...")
        filter_layout.addWidget(self.txt_exclude_authors, 5, 1)
        
        layout.addWidget(filter_group)

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
        
        # Set layout cho content_widget và thêm vào scroll_area
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)

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
        return urls

    def _update_ui_state(self, is_running):
        self.is_downloading_tab6 = is_running
        self.btn_download_media.setEnabled(not is_running)
        self.btn_download_comments.setEnabled(not is_running)
        self.btn_download_subtitles.setEnabled(not is_running)
        self.btn_cancel_download.setEnabled(is_running)
        self.url_text_edit.setEnabled(not is_running)
        self.txt_save_path.setEnabled(not is_running)
        self.btn_choose_dir.setEnabled(not is_running)
        self.combo_format.setEnabled(not is_running)
        self._on_format_change() 
        if is_running:
            self.cancel_event_tab6.clear()
        
    def set_buttons_enabled(self, enabled):
        """Public method to enable/disable buttons from Main Window."""
        # Nếu đang download (is_running=True), thì enabled=False (disable nút).
        # Nếu không download (is_running=False), thì enabled=True (enable nút).
        # Logic của _update_ui_state là: is_running=True -> disable buttons.
        # Nên ta truyền `not enabled` vào _update_ui_state.
        self._update_ui_state(not enabled)

    @pyqtSlot(str)
    def _log_activity(self, message):
         current_text = self.activity_log.toPlainText()
         lines = current_text.split('\n') if current_text else []
         lines.append(message)
         if len(lines) > ACTIVITY_LOG_MAX_LINES:
             lines = lines[-ACTIVITY_LOG_MAX_LINES:]
         self.activity_log.setText('\n'.join(lines))
         self.activity_log.moveCursor(QTextCursor.MoveOperation.End)

    @pyqtSlot(str, str, str)
    def _on_entry_downloaded(self, type_str, title, url):
        self._log_activity(f"[DONE] {type_str}: {title}")

    @pyqtSlot(list)
    def _on_failed_urls(self, failed_list):
        if failed_list:
            self._log_activity(f"Các URL thất bại: {', '.join(failed_list)}")

    @pyqtSlot(str)
    def _on_task_finished(self, msg):
        self._log_activity(f"--- {msg} ---")
        self._update_ui_state(False)
        self.current_download_thread = None
        QMessageBox.information(self.main_window, "Hoàn tất", msg)

    @pyqtSlot(str)
    def _on_error_occurred(self, err_msg):
        self._log_activity(f"[ERROR] {err_msg}")

    # --- Start Handlers ---
    def _start_download_media(self):
        urls = self._get_urls_from_input("media")
        if not urls: return
        
        save_dir = self.txt_save_path.text()
        if not os.path.exists(save_dir):
            try: os.makedirs(save_dir)
            except Exception as e:
                QMessageBox.critical(self, "Lỗi", f"Không thể tạo thư mục lưu: {e}")
                return

        quality = self.combo_quality.currentText()
        fmt = self.combo_format.currentText()
        is_audio = fmt in AUDIO_FORMATS_DL
        
        self._update_ui_state(True)
        self.activity_log.clear()
        self._log_activity(f"Bắt đầu tải {len(urls)} URL (Media)...")

        self.current_download_thread = DownloadMediaThread(
            urls, save_dir, quality, fmt, is_audio, 
            self.cancel_event_tab6, self.downloaded_urls, self
        )
        self.current_download_thread.status_updated.connect(self._log_activity)
        self.current_download_thread.entry_downloaded_signal.connect(self._on_entry_downloaded)
        self.current_download_thread.task_finished_signal.connect(self._on_task_finished)
        self.current_download_thread.error_signal.connect(self._on_error_occurred)
        self.current_download_thread.failed_urls_signal.connect(self._on_failed_urls)
        self.current_download_thread.start()

    def _start_download_comments(self):
        urls = self._get_urls_from_input("comments")
        if not urls: return

        save_dir = self.txt_save_path.text() # Not strictly used but good for consistency
        
        filter_options = {
            'enabled': self.chk_enable_filter.isChecked(),
            'exclude_uploader': self.chk_exclude_uploader.isChecked(),
            'min_words': int(self.txt_min_words.text()) if self.txt_min_words.text().isdigit() else 0,
            'include': self.txt_include_keywords.text(),
            'exclude': self.txt_exclude_keywords.text(),
            'exclude_authors': self.txt_exclude_authors.text()
        }

        self._update_ui_state(True)
        self.activity_log.clear()
        self.comments_table.setRowCount(0)
        self.comments_table.setSortingEnabled(False) 
        self._log_activity(f"Bắt đầu tải bình luận cho {len(urls)} URL...")

        self.current_download_thread = DownloadCommentsThread(
            urls, self.cancel_event_tab6, self.downloaded_urls, filter_options, self
        )
        self.current_download_thread.status_updated.connect(self._log_activity)
        self.current_download_thread.task_finished_signal.connect(self._on_task_finished)
        self.current_download_thread.error_signal.connect(self._on_error_occurred)
        self.current_download_thread.failed_urls_signal.connect(self._on_failed_urls)
        self.current_download_thread.comments_batch_signal.connect(self._on_comments_batch_received)
        self.current_download_thread.start()

    def _start_download_subtitles(self):
        urls = self._get_urls_from_input("subtitles")
        if not urls: return
        
        save_dir = self.txt_save_path.text()
        if not os.path.exists(save_dir):
            try: os.makedirs(save_dir)
            except Exception as e:
                QMessageBox.critical(self.main_window, "Lỗi", f"Không thể tạo thư mục lưu: {e}")
                return

        self._update_ui_state(True)
        self.activity_log.clear()
        self._log_activity(f"Bắt đầu tải phụ đề cho {len(urls)} URL...")

        self.current_download_thread = DownloadSubtitlesThread(
            urls, save_dir, "txt", self.cancel_event_tab6, self.downloaded_urls, self
        )
        self.current_download_thread.status_updated.connect(self._log_activity)
        self.current_download_thread.entry_downloaded_signal.connect(self._on_entry_downloaded)
        self.current_download_thread.task_finished_signal.connect(self._on_task_finished)
        self.current_download_thread.error_signal.connect(self._on_error_occurred)
        self.current_download_thread.failed_urls_signal.connect(self._on_failed_urls)
        self.current_download_thread.start()

    def _request_cancel_tab6(self):
        if self.is_downloading_tab6:
            action = QMessageBox.question(self.main_window, "Xác nhận", "Bạn có chắc muốn hủy tác vụ đang chạy?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if action == QMessageBox.StandardButton.Yes:
                self._log_activity("Đang gửi yêu cầu hủy...")
                self.cancel_event_tab6.set()
                if self.current_download_thread:
                    self.current_download_thread.requestInterruption()
                self.btn_cancel_download.setEnabled(False) # Prevent multiple clicks

    @pyqtSlot(list)
    def _on_comments_batch_received(self, comments_list):
        self.comments_table.setSortingEnabled(False)
        current_row = self.comments_table.rowCount()
        for com in comments_list:
            self.comments_table.insertRow(current_row)
            
            author_item = QTableWidgetItem(com.get('author', 'N/A'))
            text_item = QTableWidgetItem(com.get('text', ''))
            likes_item = QTableWidgetItem()
            likes_item.setData(Qt.ItemDataRole.DisplayRole, com.get('like_count', 0))
            replies_item = QTableWidgetItem()
            replies_item.setData(Qt.ItemDataRole.DisplayRole, com.get('reply_count', 0))
            
            self.comments_table.setItem(current_row, 0, author_item)
            self.comments_table.setItem(current_row, 1, text_item)
            self.comments_table.setItem(current_row, 2, likes_item)
            self.comments_table.setItem(current_row, 3, replies_item)
            current_row += 1
            
        self.comments_table.setSortingEnabled(True)
        # Enable Export button if we have data
        if self.comments_table.rowCount() > 0:
            self.btn_export_comments.setEnabled(True)

    def _export_comments_to_csv(self):
        if self.comments_table.rowCount() == 0:
            return

        file_path, _ = QQtFileDialog.getSaveFileName(self, "Lưu file CSV", "", "CSV Files (*.csv)")
        if not file_path:
            return

        try:
            with open(file_path, mode='w', newline='', encoding='utf-8-sig') as file:
                writer = csv.writer(file)
                headers = [self.comments_table.horizontalHeaderItem(i).text() for i in range(self.comments_table.columnCount())]
                writer.writerow(headers)

                for row in range(self.comments_table.rowCount()):
                    row_data = []
                    for col in range(self.comments_table.columnCount()):
                        item = self.comments_table.item(row, col)
                        row_data.append(item.text() if item else "")
                    writer.writerow(row_data)
            
            QMessageBox.information(self.main_window, "Thành công", f"Đã xuất {self.comments_table.rowCount()} bình luận ra file CSV.")
        except Exception as e:
            QMessageBox.critical(self.main_window, "Lỗi", f"Không thể lưu file: {e}")