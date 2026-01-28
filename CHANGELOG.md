# Changelog

Tất cả các thay đổi quan trọng của dự án Master-YT-App sẽ được ghi lại ở đây.

---

## [2026-01-28] - Tối

### Added ✨
- **Tính năng xuất bình luận ra TXT** (Tab 4)
  - Nút "Xuất ra TXT (chỉ nội dung)" bên cạnh nút CSV
  - Chỉ xuất nội dung bình luận thuần túy, không có metadata (tác giả, like, reply)
  - Mỗi bình luận cách nhau 2 dòng trống để dễ đọc
  - Hữu ích cho phân tích văn bản, training AI, hoặc đọc nhanh

### Technical Details
- File: `ui_tabs/tab_downloader.py`
- Method mới: `_export_comments_to_txt()`
- Encoding: UTF-8 (hỗ trợ tiếng Việt)

---

## [2026-01-28] - Chiều

### Changed 🔧
- **Triển khai hệ thống logging tập trung**
  - Tạo file `logging_config.py` với auto log rotation theo ngày
  - Logs được lưu tại: `~/YouTubeResearchTool/logs/app_YYYYMMDD.log`
  - Thay thế tất cả `print()` bằng `logging` trong toàn bộ codebase

### Fixed 🐛
- **Sửa tất cả bare exception handlers**
  - `utils.py`: 4 chỗ (format_datetime_iso, format_date_dd_mm_yyyy, format_int_with_separator, convert_iso_duration)
  - `db_cache.py`: 2 chỗ (clear_cache_key, clear_all_cache)
  - `main_app.py`: 1 chỗ (JSON parsing)
  - Giờ đây tất cả lỗi đều được log ra, không còn "nuốt" lỗi

### Documentation 📝
- Hoàn thành full code audit
- Tạo báo cáo: `docs/reports/audit_28-01-2026.md`
- Tạo báo cáo fix: `docs/reports/fix_all_report_28-01-2026.md`
- Findings: 5 critical, 8 warnings, 6 suggestions → **Tất cả đã được sửa**

---

## Phiên bản trước

Xem git history để biết các thay đổi trước ngày 2026-01-28.
