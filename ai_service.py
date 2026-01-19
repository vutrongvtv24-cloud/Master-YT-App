
import google.generativeai as genai
import logging
from PyQt6.QtCore import QObject, pyqtSignal

class AIService(QObject):
    """
    Service layer for interacting with Google Gemini API.
    """
    analysis_complete = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, api_key):
        super().__init__()
        self.api_key = api_key
        if self.api_key:
            genai.configure(api_key=self.api_key)
            # Use Gemini 1.5 Flash for speed and efficiency
            self.model = genai.GenerativeModel('gemini-1.5-flash')

    def analyze_comments(self, comments_list, context=""):
        """
        Gửi danh sách comment lên Gemini để phân tích.
        """
        if not self.api_key:
            return "Vui lòng nhập Gemini API Key."

        if not comments_list:
            return "Không có nội dung bình luận để phân tích."

        # Chuẩn bị dữ liệu (giới hạn token bằng cách nối chuỗi hợp lý)
        # Gemini 1.5 Flash chịu được 1M token, nhưng ta nên gửi vừa phải
        comments_text = "\n- ".join(comments_list[:500]) # Lấy tối đa 500 comment đầu tiên để demo nhanh

        prompt = f"""
        Bạn là một chuyên gia phân tích Insight khách hàng trên YouTube.
        Dưới đây là danh sách các bình luận của khán giả về video chủ đề: "{context}"

        DANH SÁCH BÌNH LUẬN:
        - {comments_text}
        
        YÊU CẦU PHÂN TÍCH:
        1. **Tóm tắt cảm xúc chung (Sentiment):** (Tích cực/Tiêu cực/Trung lập tỉ lệ bao nhiêu%)
        2. **Điểm khán giả thích nhất (Winning Points):** Mọi người khen cái gì?
        3. **Điểm khán giả chê/góp ý (Pain Points):** Mọi người phàn nàn điều gì?
        4. **Ý tưởng video tiếp theo:** Dựa trên yêu cầu của khán giả, hãy gợi ý 3 chủ đề video nên làm.
        
        Hãy trình bày ngắn gọn, gạch đầu dòng rõ ràng bằng Tiếng Việt.
        """

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Lỗi Generative AI: {str(e)}"
