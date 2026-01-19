
import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from PyQt6.QtCore import QObject, pyqtSignal
from db_cache import get_cache, set_cache

class APIKeyManager(QObject):
    """
    Manages multiple API keys with rotation logic.
    """
    key_depleted = pyqtSignal(str) # Signal when a key is exhausted

    def __init__(self, api_keys_list):
        super().__init__()
        # Clean and filter empty keys
        self.api_keys = [k.strip() for k in api_keys_list if k.strip()]
        self.current_index = 0
        self.bad_keys = set()
    
    def get_current_key(self):
        if not self.api_keys:
            return None
        
        # Determine valid key loop
        start_index = self.current_index
        while str(self.current_index) in self.bad_keys:
            self.current_index = (self.current_index + 1) % len(self.api_keys)
            if self.current_index == start_index:
                return None # All keys are bad
        
        return self.api_keys[self.current_index]

    def mark_current_key_as_depleted(self):
        """Mark current key as depleted/invalid and rotate to next."""
        if not self.api_keys:
            return
        
        depleted_key = self.api_keys[self.current_index]
        self.bad_keys.add(str(self.current_index))
        logging.warning(f"API Key marked as depleted: {depleted_key[:5]}...")
        
        # Rotate
        self.current_index = (self.current_index + 1) % len(self.api_keys)
        self.key_depleted.emit(depleted_key)

    def set_keys(self, new_keys_list):
        self.api_keys = [k.strip() for k in new_keys_list if k.strip()]
        self.current_index = 0
        self.bad_keys = set()
        
    def get_service(self):
        """Returns a raw youtube service object using current valid key."""
        key = self.get_current_key()
        if not key: return None
        return build('youtube', 'v3', developerKey=key)

class YouTubeService:
    """
    Service layer handling YouTube API calls with caching and key rotation.
    Decoupled from UI logic.
    """
    def __init__(self, key_manager: APIKeyManager):
        self.key_manager = key_manager

    def _execute_with_retry(self, func, *args, **kwargs):
        """
        Helper to execute an API call with auto key rotation.
        func should be a lambda that takes a 'service' object and returns a request to execute.
        """
        while True:
            current_key = self.key_manager.get_current_key()
            if not current_key:
                raise Exception("Tất cả API Key đều đã hết hạn ngạch hoặc không hợp lệ.")

            try:
                youtube = build('youtube', 'v3', developerKey=current_key)
                request = func(youtube)
                return request.execute()

            except HttpError as e:
                # 403: Quota exceeded, 429: Too many requests
                if e.resp.status in [403, 429]: 
                    logging.warning(f"Key {current_key[:5]}... hit limit ({e.resp.status}). Rotating...")
                    self.key_manager.mark_current_key_as_depleted()
                    continue 
                else:
                    raise e
            except Exception as e:
                raise e

    def search_videos(self, query, **kwargs):
        cache_key = f"search_v2_{query}_{str(kwargs)}"
        cached_data = get_cache(cache_key)
        if cached_data: return cached_data

        def api_call(service):
            return service.search().list(q=query, **kwargs)

        response = self._execute_with_retry(api_call)
        set_cache(cache_key, response, ttl_seconds=86400) # 24h
        return response

    def get_channel_details(self, channel_ids):
        if isinstance(channel_ids, list): ids_str = ",".join(channel_ids)
        else: ids_str = channel_ids
            
        cache_key = f"channel_details_{ids_str}"
        cached_data = get_cache(cache_key)
        if cached_data: return cached_data

        def api_call(service):
            return service.channels().list(
                part="snippet,statistics,contentDetails",
                id=ids_str
            )

        response = self._execute_with_retry(api_call)
        set_cache(cache_key, response, ttl_seconds=172800) # 48h
        return response

    def get_video_details(self, video_ids):
        """Fetch details for a list of video IDs."""
        if isinstance(video_ids, list): ids_str = ",".join(video_ids)
        else: ids_str = video_ids

        cache_key = f"video_details_{ids_str}"
        cached_data = get_cache(cache_key)
        if cached_data: return cached_data

        def api_call(service):
            return service.videos().list(
                part='snippet,statistics,contentDetails',
                id=ids_str
            )
        
        response = self._execute_with_retry(api_call)
        set_cache(cache_key, response, ttl_seconds=172800) # 48h
        return response

    def get_playlist_items(self, playlist_id, page_token=None, max_results=50):
        """Get items from a playlist. Note: Pagination makes caching tricky, so we cache by page."""
        cache_key = f"playlist_items_{playlist_id}_{page_token}_{max_results}"
        cached_data = get_cache(cache_key)
        if cached_data: return cached_data

        def api_call(service):
            return service.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=playlist_id,
                maxResults=max_results,
                pageToken=page_token
            )

        response = self._execute_with_retry(api_call)
        set_cache(cache_key, response, ttl_seconds=3600*6) # 6h
        return response
