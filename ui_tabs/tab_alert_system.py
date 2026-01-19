
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QGroupBox, QSpinBox, QSystemTrayIcon, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtGui import QIcon
from datetime import datetime
from youtube_service import YouTubeService, APIKeyManager

class AlertSystemTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.settings = self.main_window.settings
        self.timer = QTimer()
        self.timer.timeout.connect(self._check_for_new_videos)
        
        self.monitored_channels = {} # {channel_id: last_video_id}
        self._load_monitored_data()
        
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 1. Config
        # Config group
        config_group = QGroupBox("Cấu hình Theo dõi")
        config_layout = QVBoxLayout()
        
        self.txt_channel_ids = QTextEdit()
        self.txt_channel_ids.setPlaceholderText("Nhập ID Kênh cần theo dõi (mỗi dòng 1 ID, ví dụ: UCxxxxx)...")
        # Load saved channels
        saved_channels = self.settings.value("ALERT_CHANNELS", [])
        if saved_channels:
            self.txt_channel_ids.setText("\n".join(saved_channels))
            
        config_layout.addWidget(QLabel("Danh sách ID Kênh:"))
        config_layout.addWidget(self.txt_channel_ids)
        
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("Tần suất kiểm tra (phút):"))
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(5, 1440) # 5m to 24h
        self.spin_interval.setValue(int(self.settings.value("ALERT_INTERVAL", 60)))
        interval_layout.addWidget(self.spin_interval)
        interval_layout.addStretch()
        config_layout.addLayout(interval_layout)
        
        self.chk_enable = QCheckBox("Kích hoạt chạy ngầm")
        self.chk_enable.setChecked(bool(int(self.settings.value("ALERT_ENABLE", 0))))
        self.chk_enable.toggled.connect(self._toggle_monitoring)
        config_layout.addWidget(self.chk_enable)

        btn_save = QPushButton("Lưu Cấu hình")
        btn_save.clicked.connect(self._save_config)
        config_layout.addWidget(btn_save)
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        # 2. Status Log
        layout.addWidget(QLabel("Nhật ký Theo dõi:"))
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        layout.addWidget(self.txt_log)
        
        if self.chk_enable.isChecked():
            self._start_timer()

    def _load_monitored_data(self):
        # Load last known video dict
        data = self.settings.value("ALERT_DATA", {})
        if isinstance(data, dict):
            self.monitored_channels = data

    def _save_config(self):
        channels_text = self.txt_channel_ids.toPlainText().strip()
        channels = [line.strip() for line in channels_text.split('\n') if line.strip()]
        
        self.settings.setValue("ALERT_CHANNELS", channels)
        self.settings.setValue("ALERT_INTERVAL", self.spin_interval.value())
        self.settings.setValue("ALERT_ENABLE", 1 if self.chk_enable.isChecked() else 0)
        
        self.log(f"Đã lưu cấu hình. Theo dõi {len(channels)} kênh.")
        
        if self.chk_enable.isChecked():
            self._start_timer()
        else:
            self.timer.stop()

    def _toggle_monitoring(self, checked):
        if checked:
            self._start_timer()
        else:
            self.timer.stop()
            self.log("Đã dừng theo dõi tự động.")

    def _start_timer(self):
        interval_ms = self.spin_interval.value() * 60 * 1000
        self.timer.start(interval_ms)
        self.log(f"Đã kích hoạt theo dõi tự động. Chu kỳ: {self.spin_interval.value()} phút.")
        # Check immediately once
        # QTimer.singleShot(1000, self._check_for_new_videos) 

    def _check_for_new_videos(self):
        channels_text = self.txt_channel_ids.toPlainText().strip()
        channel_ids = [line.strip() for line in channels_text.split('\n') if line.strip()]
        
        if not channel_ids: return
        if not self.main_window.api_key:
            self.log("Lỗi: Không tìm thấy API Key để chạy theo dõi.")
            return

        self.log(f"Đang kiểm tra {len(channel_ids)} kênh lúc {datetime.now().strftime('%H:%M:%S')}...")
        
        try:
            # Init Service Wrapper manually here
            key_list = self.main_window.api_key.split('\n')
            key_manager = APIKeyManager(key_list)
            service = YouTubeService(key_manager)
            
            # Fetch channel details to get Uploads playlist ID
            # Note: Tối ưu hơn thì nên lưu Upload Playlist ID vào settings để ko phải query lại channel
            # Ở đây làm đơn giản query lại
            
            response = service.get_channel_details(channel_ids)
            
            new_videos_found = []
            
            for item in response.get('items', []):
                c_id = item['id']
                c_title = item['snippet']['title']
                uploads_playlist = item['contentDetails']['relatedPlaylists']['uploads']
                
                # Get latest video from uploads
                pl_response = service.get_playlist_items(uploads_playlist, max_results=1)
                if pl_response.get('items'):
                    latest_vid = pl_response['items'][0]
                    vid_id = latest_vid['contentDetails']['videoId']
                    vid_title = latest_vid['snippet']['title']
                    
                    last_known = self.monitored_channels.get(c_id)
                    
                    if last_known and last_known != vid_id:
                        # New video detected!
                        new_videos_found.append(f"Kênh {c_title} vừa đăng: {vid_title}")
                    
                    # Update state
                    self.monitored_channels[c_id] = vid_id
            
            # Save state
            self.settings.setValue("ALERT_DATA", self.monitored_channels)
            
            if new_videos_found:
                msg = "\n".join(new_videos_found)
                self.log("PHÁT HIỆN VIDEO MỚI:\n" + msg)
                self.main_window.tray_icon.showMessage(
                    "Theo dõi YouTube",
                    f"Có {len(new_videos_found)} video mới từ đối thủ!",
                    QSystemTrayIcon.MessageIcon.Information,
                    5000
                )
            else:
                self.log("Không có video mới.")
                
        except Exception as e:
            self.log(f"Lỗi khi kiểm tra: {str(e)}")

    def log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.txt_log.append(f"[{timestamp}] {msg}")
