
import os
import shutil
import re
import yt_dlp
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices, QColor
from datetime import timedelta

class DeepScanWorker(QThread):
    progress_updated = pyqtSignal(int, str) # percent, message
    result_found = pyqtSignal(dict) # data of video found
    finished = pyqtSignal()

    def __init__(self, urls, keyword):
        super().__init__()
        self.urls = urls
        self.keyword = keyword.lower().strip()
        self._is_running = True

    def run(self):
        total = len(self.urls)
        temp_dir = "temp_subs"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        ydl_opts = {
            'skip_download': True,
            'writeautomaticsub': True, # Ưu tiên sub tự động nếu không có sub gốc
            'writesubtitles': True,
            'subtitleslangs': ['vi', 'en'], # Ưu tiên Tiếng Việt, sau đó đến Anh
            'outtmpl': os.path.join(temp_dir, '%(id)s'),
            'quiet': True,
            'no_warnings': True,
        }

        processed = 0
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for url in self.urls:
                if not self._is_running: break
                
                processed += 1
                percent = int((processed / total) * 100)
                self.progress_updated.emit(percent, f"Đang quét video {processed}/{total}: {url}...")

                try:
                    info = ydl.extract_info(url, download=True) # download=True ở đây chỉ tải sub vì skip_download=True
                    video_id = info.get('id')
                    video_title = info.get('title')
                    
                    # Tìm file sub đã tải
                    sub_files = [f for f in os.listdir(temp_dir) if f.startswith(video_id) and f.endswith('.vtt')]
                    
                    found_timestamps = []
                    
                    for sub_file in sub_files:
                        path = os.path.join(temp_dir, sub_file)
                        with open(path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            # Parse VTT đơn giản (lấy timestamp và text)
                            # Regex bắt pattern: 00:00:00.000 --> 00:00:05.000
                            # Và dòng text bên dưới
                            if self.keyword in content.lower():
                                # Nếu tìm thấy, cố gắng trích xuất timecode (đơn giản hoá)
                                lines = content.split('\n')
                                for i, line in enumerate(lines):
                                    if self.keyword in line.lower():
                                        # Tìm ngược lại để lấy timestamp gần nhất
                                        for j in range(i, max(0, i-5), -1):
                                            if '-->' in lines[j]:
                                                found_timestamps.append(lines[j].split(' --> ')[0])
                                                break
                                        # Chỉ lấy 1 lần xuất hiện đầu tiên cho mỗi đoạn để tránh spam
                                        if found_timestamps: break 
                        
                        # Xóa file tạm
                        try: os.remove(path) 
                        except: pass

                    if found_timestamps:
                        # Chỉ lấy timecode đầu tiên tìm thấy
                        first_time = found_timestamps[0] if found_timestamps else "N/A"
                        self.result_found.emit({
                            'title': video_title,
                            'url': url,
                            'timestamp': first_time,
                            'match': 'Có'
                        })

                except Exception as e:
                    # Lỗi tải sub hoặc video không có sub
                    pass
        
        # Cleanup dir
        try: shutil.rmtree(temp_dir)
        except: pass
        
        self.finished.emit()

    def stop(self):
        self._is_running = False

class DeepScanTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._setup_ui()
        self.worker = None

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 1. Input
        input_group = QGroupBox("Cấu hình Quét")
        input_layout = QVBoxLayout()
        
        self.txt_urls = QTextEdit()
        self.txt_urls.setPlaceholderText("Dán danh sách URL video cần quét (mỗi dòng 1 URL)...")
        self.txt_urls.setMinimumHeight(100)
        input_layout.addWidget(QLabel("Danh sách Video:"))
        input_layout.addWidget(self.txt_urls)

        kw_layout = QHBoxLayout()
        self.txt_keyword = QLineEdit()
        self.txt_keyword.setPlaceholderText("Nhập từ khóa cần tìm trong lời thoại (VD: 'khuyến mãi', 'lừa đảo')...")
        kw_layout.addWidget(QLabel("Từ khóa:"))
        kw_layout.addWidget(self.txt_keyword)
        input_layout.addLayout(kw_layout)
        
        self.btn_scan = QPushButton("🔍 Quét Deep Scan")
        self.btn_scan.setStyleSheet("background-color: #8e44ad; color: white; font-weight: bold;")
        self.btn_scan.clicked.connect(self._start_scan)
        input_layout.addWidget(self.btn_scan)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # 2. Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.lbl_status = QLabel("Sẵn sàng")
        layout.addWidget(self.lbl_status)
        layout.addWidget(self.progress_bar)

        # 3. Result Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Tiêu đề Video", "Thời gian xuất hiện", "URL Video (Có Timecode)", "Mở"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

    def _start_scan(self):
        urls = [u.strip() for u in self.txt_urls.toPlainText().split('\n') if u.strip()]
        keyword = self.txt_keyword.text().strip()
        
        if not urls:
            QMessageBox.warning(self, "Thiếu URL", "Vui lòng nhập ít nhất 1 URL video.")
            return
        if not keyword:
            QMessageBox.warning(self, "Thiếu từ khóa", "Vui lòng nhập từ khóa cần tìm.")
            return

        self.btn_scan.setEnabled(False)
        self.table.setRowCount(0)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.worker = DeepScanWorker(urls, keyword)
        self.worker.progress_updated.connect(self._update_progress)
        self.worker.result_found.connect(self._add_result)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _update_progress(self, percent, msg):
        self.progress_bar.setValue(percent)
        self.lbl_status.setText(msg)

    def _add_result(self, data):
        row = self.table.rowCount()
        self.table.setRowCount(row + 1)
        
        self.table.setItem(row, 0, QTableWidgetItem(data['title']))
        self.table.setItem(row, 1, QTableWidgetItem(data['timestamp']))
        
        # Tạo URL có timecode (VD: &t=120s)
        time_str = data['timestamp']
        seconds = 0
        try:
            parts = time_str.split(':')
            if len(parts) == 3:
                seconds = int(parts[0])*3600 + int(parts[1])*60 + int(float(parts[2]))
            elif len(parts) == 2:
                seconds = int(parts[0])*60 + int(float(parts[1]))
        except: pass
        
        url_with_time = f"{data['url']}&t={seconds}s"
        self.table.setItem(row, 2, QTableWidgetItem(url_with_time))
        
        btn_open = QPushButton("Xem ngay")
        btn_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url_with_time)))
        self.table.setCellWidget(row, 3, btn_open)

    def _on_finished(self):
        self.btn_scan.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"Hoàn tất quét. Tìm thấy {self.table.rowCount()} video có chứa từ khóa.")
        QMessageBox.information(self, "Hoàn tất", f"Đã quét xong!\nTìm thấy {self.table.rowCount()} video chứa từ khóa.")
