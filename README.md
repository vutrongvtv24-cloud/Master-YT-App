# Master-YT-App

**YouTube Research Tool** - Công cụ nghiên cứu YouTube chuyên nghiệp với giao diện PyQt6

![Version](https://img.shields.io/badge/version-6.4-blue)
![Python](https://img.shields.io/badge/python-3.x-green)
![License](https://img.shields.io/badge/license-MIT-orange)

---

## 🎯 Tính năng chính

### 1️⃣ **API Key Management** (Tab 1)
- Quản lý nhiều YouTube API keys
- Test validity tự động
- Auto-rotation khi hết quota

### 2️⃣ **Keyword Research** (Tab 2)
- Tìm kiếm video theo từ khóa
- Filters: Duration, Date, Category, Region
- Export kết quả ra Excel/CSV

### 3️⃣ **Keyword Suggestions** (Tab 3)
- Lấy gợi ý từ khóa từ YouTube autocomplete
- Hữu ích cho SEO và content planning

### 4️⃣ **Video/Comment Downloader** (Tab 4)
- Tải video/audio với nhiều chất lượng
- Tải bình luận với bộ lọc thông minh:
  - Loại bỏ bình luận của chủ kênh
  - Lọc theo số từ tối thiểu
  - Lọc theo từ khóa (include/exclude)
  - Loại bỏ tác giả spam
- **Xuất bình luận:**
  - **CSV** (đầy đủ): Tác giả, Nội dung, Like, Reply
  - **TXT** (chỉ nội dung): Thuần văn bản, dễ phân tích
- Tải phụ đề (subtitles) tự động

### 5️⃣ **Channel Video Fetcher** (Tab 5)
- Lấy tất cả video của kênh
- Filters: Views, Comments, Duration
- Phân tích xu hướng nội dung

### 6️⃣ **Channel Analyzer** (Tab 6)
- Phân tích metrics kênh: Subscribers, Videos, Views
- Xem ngày tạo kênh
- So sánh nhiều kênh cùng lúc

---

## 🚀 Cài đặt

### Yêu cầu hệ thống
- Python 3.8 trở lên
- Windows 10/11 (hoặc Linux/macOS với PyQt6)

### Cài đặt dependencies

```bash
pip install -r requirements.txt
```

### Chạy ứng dụng

```bash
python main_app.py
```

---

## 📦 Dependencies chính

```
PyQt6                      # UI Framework
google-api-python-client   # YouTube Data API v3
yt-dlp                     # Video/Audio/Subtitle downloader
pandas                     # Data manipulation
openpyxl                   # Excel export
isodate                    # ISO 8601 duration parsing
```

---

## 🔑 Cấu hình YouTube API Key

1. Truy cập [Google Cloud Console](https://console.cloud.google.com/)
2. Tạo project mới hoặc chọn project có sẵn
3. Enable **YouTube Data API v3**
4. Tạo API Key (Credentials → Create Credentials → API Key)
5. Dán API Key vào **Tab 1** của ứng dụng

> **Lưu ý:** Mỗi API key có quota 10,000 units/ngày. Bạn có thể thêm nhiều keys để tăng quota.

---

## 📊 Logging & Debugging

Ứng dụng sử dụng hệ thống logging tập trung:

- **Log location:** `~/YouTubeResearchTool/logs/app_YYYYMMDD.log`
- **Log format:** `timestamp - module - level - message`
- **Auto rotation:** Mỗi ngày tạo file log mới

Khi gặp lỗi, kiểm tra log file để biết chi tiết.

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Frontend** | PyQt6 + QSS |
| **Backend** | Python 3.x |
| **Database** | SQLite (API cache) |
| **APIs** | YouTube Data API v3 |
| **Downloader** | yt-dlp |
| **Logging** | Python logging module |

---

## 📁 Cấu trúc dự án

```
Master-YT-App/
├── main_app.py              # Main window
├── ui_tabs/                 # Feature tabs
│   ├── tab_api_key.py
│   ├── tab_keyword_research.py
│   ├── tab_suggestions.py
│   ├── tab_downloader.py
│   ├── tab_channel_research.py
│   └── tab_channel_analyzer.py
├── services/                # API management
│   └── api_manager.py
├── utils.py                 # Utility functions
├── config.py                # Configuration
├── db_cache.py              # SQLite caching
├── logging_config.py        # Logging setup
├── requirements.txt         # Dependencies
└── docs/                    # Documentation
    ├── architecture/
    ├── reports/
    └── specs/
```

---

## 🐛 Troubleshooting

### Lỗi "quotaExceeded"
- API key đã hết quota hôm nay
- Thêm API key khác vào Tab 1
- Hoặc đợi đến 00:00 PST (quota reset)

### Lỗi "Invalid API Key"
- Kiểm tra API key đã enable YouTube Data API v3 chưa
- Kiểm tra API key có bị restrict không

### Video không tải được
- Kiểm tra URL có hợp lệ không
- Một số video bị giới hạn vùng hoặc riêng tư
- Xem log file để biết chi tiết lỗi

---

## 📝 Changelog

Xem [CHANGELOG.md](CHANGELOG.md) để biết lịch sử thay đổi.

---

## 📄 License

MIT License - Xem file LICENSE để biết chi tiết.

---

## 🤝 Contributing

Mọi đóng góp đều được chào đón! Vui lòng:
1. Fork repo
2. Tạo branch mới (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Mở Pull Request

---

## 📧 Contact

- **GitHub:** [vutrongvtv24-cloud](https://github.com/vutrongvtv24-cloud)
- **Repository:** [Master-YT-App](https://github.com/vutrongvtv24-cloud/Master-YT-App)

---

**Made with ❤️ using Python & PyQt6**
