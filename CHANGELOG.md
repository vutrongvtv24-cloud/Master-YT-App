# Changelog

## [2026-02-02] - Download Fixes & UX Improvements
### Added
- **Activity Log Component**: Widget hiển thị log màu sắc (Info/Warn/Error) (`ui_components/activity_log_widget.py`).
- **Export TXT**: Xuất bình luận ra file TXT với format `- [content]` và tự động đặt tên file theo tiêu đề video.
- **FFmpeg Check**: Tự động kiểm tra và cảnh báo nếu FFmpeg chưa cài đặt hoặc thiếu trong PATH.

### Fixed
- **YouTube 403 Forbidden**: Cập nhật cấu hình `yt-dlp` giả lập Android/iOS client để bypass chặn bot.
- **Code Quality**: Thay thế toàn bộ `traceback.print_exc()` bằng `logging`, fix lỗi bare exceptions.
- **Import Error**: Sửa lỗi import trong `SearchChannelsThread`.

### Changed
- Refactor `download_workers.py` để hỗ trợ custom options bypass 403.
- Cập nhật UI Tab Downloader để hiển thị nút Export TXT.

---

## [2026-01-28] - Initial Audit & Basic Fixes
### Added
- Audit reports.
- `APIKeyManager` rotation logic.
