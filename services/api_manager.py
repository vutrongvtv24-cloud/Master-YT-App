from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import threading
import logging

logger = logging.getLogger(__name__)

class APIKeyManager:
    _instance = None
    _lock = threading.Lock()
    _api_keys = []
    _current_key_index = 0

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(APIKeyManager, cls).__new__(cls)
        return cls._instance

    @classmethod
    def set_api_keys(cls, api_key_string):
        """Sets the list of API keys from a newline-separated string."""
        with cls._lock:
            if not api_key_string:
                cls._api_keys = []
            else:
                cls._api_keys = [key.strip() for key in api_key_string.splitlines() if key.strip()]
            cls._current_key_index = 0

    @classmethod
    def get_current_key(cls):
        """Returns the current API key."""
        with cls._lock:
            if not cls._api_keys:
                return None
            return cls._api_keys[cls._current_key_index]

    @classmethod
    def rotate_key(cls):
        """Rotates to the next API key. Returns True if successful, False if all keys exhausted (wrapped around)."""
        with cls._lock:
            if not cls._api_keys:
                return False
            
            cls._current_key_index = (cls._current_key_index + 1) % len(cls._api_keys)
            # Nếu quay về 0, tức là đã thử hết keys. 
            # Tuy nhiên, trong ngữ cảnh này, chúng ta chỉ cần trả về key mới để thử.
            # Logic "hết keys" nên được xử lý bởi người gọi nếu cần đếm số lần rotate.
            return True

    @classmethod
    def get_service(cls):
        """Builds and returns a YouTube service using the current key. Rotates if necessary (manual retry needed)."""
        key = cls.get_current_key()
        if not key:
            raise ValueError("No API keys configured.")
        return build('youtube', 'v3', developerKey=key)

class YouTubeService:
    """Wrapper class to handle API calls with automatic key rotation."""
    
    def __init__(self):
        self.manager = APIKeyManager()

    def search_videos(self, **kwargs):
        """Executes a search().list() call with automatic error handling and key rotation."""
        return self._execute_with_rotation(
            lambda service: service.search().list(**kwargs)
        )
    
    def get_video_details(self, **kwargs):
        """Executes a videos().list() call."""
        return self._execute_with_rotation(
            lambda service: service.videos().list(**kwargs)
        )
        
    def get_channel_details(self, **kwargs):
        """Executes a channels().list() call."""
        return self._execute_with_rotation(
            lambda service: service.channels().list(**kwargs)
        )

    def get_playlist_items(self, **kwargs):
        """Executes a playlistItems().list() call."""
        return self._execute_with_rotation(
            lambda service: service.playlistItems().list(**kwargs)
        )
    
    def get_comment_threads(self, **kwargs):
        """Executes a commentThreads().list() call."""
        return self._execute_with_rotation(
            lambda service: service.commentThreads().list(**kwargs)
        )

    def _execute_with_rotation(self, api_call_lambda):
        """
        Helper method to execute an API call.
        If a quota error (403) occurs, it rotates the key and retries.
        """
        # Thử tối đa số lần bằng số lượng keys
        max_retries = len(self.manager._api_keys) if self.manager._api_keys else 1
        
        for attempt in range(max_retries):
            try:
                service = self.manager.get_service()
                request = api_call_lambda(service)
                response = request.execute()
                return response
            except HttpError as e:
                if e.resp.status == 403:
                    error_content = e.content.decode('utf-8')
                    if "quotaExceeded" in error_content or "dailyLimitExceeded" in error_content:
                        logger.info(f"Key {self.manager.get_current_key()[:10]}... hết hạn mức. Đang đổi key...")
                        if not self.manager.rotate_key():
                            # Nếu chỉ có 1 key hoặc rotate thất bại
                            raise e 
                    else:
                        raise e # Lỗi 403 khác (vd: cấm truy cập)
                else:
                    raise e # Lỗi khác (400, 404, 500...)
            except Exception as e:
                raise e
        
        raise Exception("Đã thử tất cả API Keys nhưng đều thất bại (Hết quota).")
