import google.generativeai as genai
import logging
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

class AIService(QObject):
    """
    Service layer for interacting with Google Gemini API via Native SDK.
    Supports Custom Endpoint (Antigravity Proxy).
    """
    analysis_complete = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, api_key, base_url="", model_name=""):
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url.strip()
        self.model_name = model_name.strip() or "gemini-3-pro-high"
        self.model = None

        if self.api_key:
            try:
                # Nếu có base_url thì dùng custom endpoint với transport='rest'
                if self.base_url:
                    # Clean URL: genai usually expects 'http://ip:port' without /v1/chat...
                    # User provided 'http://127.0.0.1:8045/v1' or just 'http://127.0.0.1:8045'
                    # According to snippet explanation: 'http://127.0.0.1:8045' is recommended.
                    # But the user snippet has 'http://127.0.0.1:8045' in options.
                    # Let's try to keep it clean.
                     
                    endpoint = self.base_url
                    # Nếu user nhập thừa /v1, có thể cần xử lý, nhưng snippet mẫu user đưa không có /v1
                    # Tuy nhiên, nếu user nhập 'http://127.0.0.1:8045', ta để nguyên.
                    
                    genai.configure(
                        api_key=self.api_key,
                        transport='rest',
                        client_options={'api_endpoint': endpoint}
                    )
                else:
                    # Default Google API
                    genai.configure(api_key=self.api_key)
                
                self.model = genai.GenerativeModel(self.model_name)
            except Exception as e:
                logger.error(f"Error configuring Gemini: {e}")

    def analyze_comments(self, comments_list, context="", custom_instruction=None):
        """
        Gửi danh sách comment lên AI để phân tích.
        """
        if not self.api_key:
            return "Vui lòng nhập API Key."

        if not comments_list:
             if not custom_instruction:
                return "Không có nội dung bình luận để phân tích."
            
        if not self.model:
            return "Lỗi: Chưa khởi tạo được AI Model. Kiểm tra Key/Base URL."

        # Chuẩn bị dữ liệu
        comments_text = "\n- ".join(comments_list[:500]) if comments_list else "(Không có dữ liệu comment)"

        if custom_instruction:
            # Custom Chat Mode
            prompt = f"""
            Dữ liệu ngữ cảnh (Comments của Video "{context}"):
            ---
            {comments_text}
            ---
            
            Yêu cầu của người dùng:
            {custom_instruction}
            
            Hãy trả lời ngắn gọn, tập trung vào dữ liệu trên.
            """
        else:
            # Default Analysis Mode
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
