
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QGroupBox, QFileDialog, QMessageBox, 
    QProgressBar, QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from ai_service import AIService
import pandas as pd

class AIAnalysisWorker(QThread):
    finished = pyqtSignal(str)
    
    def __init__(self, ai_service, comments, context):
        super().__init__()
        self.ai_service = ai_service
        self.comments = comments
        self.context = context

    def run(self):
        result = self.ai_service.analyze_comments(self.comments, self.context)
        self.finished.emit(result)

class AIAnalysisTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.ai_service = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 1. Cấu hình
        config_group = QGroupBox("Cấu hình AI (Gemini)")
        config_layout = QHBoxLayout()
        
        self.txt_gemini_key = QLineEdit()
        self.txt_gemini_key.setPlaceholderText("Nhập Google Gemini API Key (Bắt đầu bằng AIza...)")
        self.txt_gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        
        # Load key if saved (Optional: add to settings later)
        saved_key = self.main_window.settings.value("GEMINI_API_KEY", "")
        self.txt_gemini_key.setText(saved_key)

        btn_save_key = QPushButton("Lưu Key")
        btn_save_key.clicked.connect(self._save_gemini_key)
        
        config_layout.addWidget(QLabel("API Key:"))
        config_layout.addWidget(self.txt_gemini_key)
        config_layout.addWidget(btn_save_key)
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # 2. Input Dữ liệu
        input_group = QGroupBox("Dữ liệu đầu vào")
        input_layout = QVBoxLayout()
        
        btn_layout = QHBoxLayout()
        self.btn_load_excel = QPushButton("Chọn File Excel Comment")
        self.btn_load_excel.clicked.connect(self._load_excel_file)
        self.lbl_file_info = QLabel("Chưa chọn file nào")
        
        btn_layout.addWidget(self.btn_load_excel)
        btn_layout.addWidget(self.lbl_file_info)
        btn_layout.addStretch()
        input_layout.addLayout(btn_layout)

        self.txt_context = QLineEdit()
        self.txt_context.setPlaceholderText("Nhập ngữ cảnh/chủ đề video (VD: Review iPhone 16) để AI hiểu rõ hơn...")
        input_layout.addWidget(QLabel("Chủ đề/Ngữ cảnh:"))
        input_layout.addWidget(self.txt_context)
        
        self.lbl_preview_count = QLabel("Số lượng comment đã load: 0")
        input_layout.addWidget(self.lbl_preview_count)

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # 3. Action & Result
        action_layout = QHBoxLayout()
        self.btn_analyze = QPushButton("🚀 Bắt đầu Phân tích AI")
        self.btn_analyze.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 8px;")
        self.btn_analyze.clicked.connect(self._start_analysis)
        self.btn_analyze.setEnabled(False)
        action_layout.addWidget(self.btn_analyze)
        layout.addLayout(action_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0) # Indeterminate
        layout.addWidget(self.progress_bar)

        self.txt_result = QTextEdit()
        self.txt_result.setPlaceholderText("Kết quả phân tích từ AI sẽ hiện ở đây...")
        self.txt_result.setReadOnly(True)
        self.txt_result.setStyleSheet("font-size: 14px; line-height: 1.5;")
        layout.addWidget(QLabel("Kết quả Phân tích:"))
        layout.addWidget(self.txt_result, 1)

        self.loaded_comments = []

    def _save_gemini_key(self):
        key = self.txt_gemini_key.text().strip()
        if key:
            self.main_window.settings.setValue("GEMINI_API_KEY", key)
            QMessageBox.information(self, "Thành công", "Đã lưu Gemini API Key!")
            self.ai_service = AIService(key)
        else:
            QMessageBox.warning(self, "Lỗi", "Key không được để trống.")

    def _load_excel_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn File Excel", "", "Excel Files (*.xlsx)")
        if not file_path:
            return

        try:
            df = pd.read_excel(file_path)
            # Find comment column
            possible_cols = ['Comment', 'comment', 'Nội dung', 'Content', 'Text', 'text']
            target_col = None
            for col in df.columns:
                if col in possible_cols:
                    target_col = col
                    break
            
            if not target_col:
                # Fallback: take the column with longest avg string length usually comment
                target_col = df.columns[-1] # Simple heuristic
            
            self.loaded_comments = df[target_col].dropna().astype(str).tolist()
            self.lbl_file_info.setText(os.path.basename(file_path))
            self.lbl_preview_count.setText(f"Số lượng comment đã load: {len(self.loaded_comments)}")
            
            if self.loaded_comments:
                self.btn_analyze.setEnabled(True)
                
        except Exception as e:
            QMessageBox.critical(self, "Lỗi đọc file", str(e))

    def _start_analysis(self):
        key = self.txt_gemini_key.text().strip()
        if not key:
            QMessageBox.warning(self, "Thiếu Key", "Vui lòng nhập và lưu Gemini API Key trước.")
            return

        # Re-init service just in case
        self.ai_service = AIService(key)
        
        self.progress_bar.setVisible(True)
        self.btn_analyze.setEnabled(False)
        self.txt_result.setText("Đang gửi dữ liệu cho AI phân tích, vui lòng đợi (10-20s)...")
        
        context = self.txt_context.text().strip()
        
        self.worker = AIAnalysisWorker(self.ai_service, self.loaded_comments, context)
        self.worker.finished.connect(self._on_analysis_finished)
        self.worker.start()

    def _on_analysis_finished(self, result):
        self.progress_bar.setVisible(False)
        self.btn_analyze.setEnabled(True)
        self.txt_result.setMarkdown(result)

