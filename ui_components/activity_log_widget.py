# ui_components/activity_log_widget.py

"""
ActivityLogWidget - Reusable activity log component for all tabs.
Displays status messages, errors, and overall activity in real-time.
"""

import logging
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QHBoxLayout, QPushButton, QLabel
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor, QColor

logger = logging.getLogger(__name__)

# Max lines in the log to prevent memory issues
ACTIVITY_LOG_MAX_LINES = 200


class ActivityLogWidget(QWidget):
    """A reusable widget for displaying activity logs with color-coded messages."""
    
    def __init__(self, parent=None, title="Activity Log"):
        super().__init__(parent)
        self.max_lines = ACTIVITY_LOG_MAX_LINES
        self.title = title
        self._setup_ui()
        self._apply_styles()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 0)
        layout.setSpacing(5)
        
        # Header with title and clear button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)
        
        self.title_label = QLabel(f"📋 {self.title}")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        self.clear_button = QPushButton("🗑️ Xóa Log")
        self.clear_button.setFixedWidth(100)
        self.clear_button.clicked.connect(self.clear_log)
        header_layout.addWidget(self.clear_button)
        
        layout.addLayout(header_layout)
        
        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFixedHeight(120)
        self.log_text.setPlaceholderText("Các hoạt động và lỗi sẽ hiển thị ở đây...")
        layout.addWidget(self.log_text)
    
    def _apply_styles(self):
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                padding: 5px;
            }
        """)
        self.clear_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #3c3c3c;
            }
        """)
    
    def _get_timestamp(self):
        """Return current timestamp in HH:MM:SS format."""
        return datetime.now().strftime("%H:%M:%S")
    
    def _trim_log(self):
        """Remove old lines if exceeding max_lines."""
        document = self.log_text.document()
        if document.blockCount() > self.max_lines:
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            # Remove first 50 lines when limit is exceeded
            for _ in range(50):
                cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
    
    def _append_html(self, html):
        """Append HTML content and scroll to bottom."""
        self.log_text.append(html)
        self._trim_log()
        # Scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def log_info(self, message: str):
        """Log an info message (default color)."""
        timestamp = self._get_timestamp()
        html = f'<span style="color:#808080">[{timestamp}]</span> <span style="color:#d4d4d4">{message}</span>'
        self._append_html(html)
        logger.debug(f"[ActivityLog] {message}")
    
    def log_success(self, message: str):
        """Log a success message (green color)."""
        timestamp = self._get_timestamp()
        html = f'<span style="color:#808080">[{timestamp}]</span> <span style="color:#4ec9b0">✅ {message}</span>'
        self._append_html(html)
        logger.info(f"[ActivityLog] SUCCESS: {message}")
    
    def log_warning(self, message: str):
        """Log a warning message (yellow color)."""
        timestamp = self._get_timestamp()
        html = f'<span style="color:#808080">[{timestamp}]</span> <span style="color:#dcdcaa">⚠️ {message}</span>'
        self._append_html(html)
        logger.warning(f"[ActivityLog] WARNING: {message}")
    
    def log_error(self, message: str):
        """Log an error message (red color)."""
        timestamp = self._get_timestamp()
        html = f'<span style="color:#808080">[{timestamp}]</span> <span style="color:#f14c4c">❌ {message}</span>'
        self._append_html(html)
        logger.error(f"[ActivityLog] ERROR: {message}")
    
    def log_progress(self, message: str):
        """Log a progress message (blue color)."""
        timestamp = self._get_timestamp()
        html = f'<span style="color:#808080">[{timestamp}]</span> <span style="color:#569cd6">🔄 {message}</span>'
        self._append_html(html)
    
    def clear_log(self):
        """Clear all log content."""
        self.log_text.clear()
        self.log_info("Log đã được xóa.")
    
    def set_title(self, title: str):
        """Update the log title."""
        self.title = title
        self.title_label.setText(f"📋 {self.title}")
