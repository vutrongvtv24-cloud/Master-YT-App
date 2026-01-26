# youtube_research_tool/config.py

# --- Configuration and Constants ---
APP_NAME = "YouTubeResearchTool"
ORGANIZATION_NAME = "MyCompany" # Or your actual organization name
CONFIG_API_KEY = "youtube_api_key"

# Mapping for region and language codes
YOUTUBE_REGION_LANGUAGE_MAP = {
    "Việt Nam": {
        "region_code": "VN",
        "languages": ["vi", "en"],  # Tiếng Việt, tiếng Anh
        "name": "Việt Nam"
    },
    "Hoa Kỳ (US)": {
        "region_code": "US",
        "languages": ["en", "es", "fr", "zh"],  # Tiếng Anh, Tây Ban Nha, Pháp, Trung Quốc
        "name": "Hoa Kỳ (US)"
    },
    "Canada (CA)": {
        "region_code": "CA",
        "languages": ["en", "fr"],  # Tiếng Anh, Pháp
        "name": "Canada (CA)"
    },
    "Đức (DE)": {
        "region_code": "DE",
        "languages": ["de", "en"],  # Tiếng Đức, Anh
        "name": "Đức (DE)"
    },
    "Pháp (FR)": {
        "region_code": "FR",
        "languages": ["fr", "en", "es"],  # Tiếng Pháp, Anh, Tây Ban Nha
        "name": "Pháp (FR)"
    },
    "Anh (GB)": {
        "region_code": "GB",
        "languages": ["en", "fr"],  # Tiếng Anh, Pháp
        "name": "Anh (GB)"
    },
    "Singapore (SG)": {
        "region_code": "SG",
        "languages": ["en", "zh", "ms"],  # Tiếng Anh, Trung Quốc, Mã Lai
        "name": "Singapore (SG)"
    },
    "Indonesia (ID)": {
        "region_code": "ID",
        "languages": ["id", "en"],  # Tiếng Indonesia, Anh
        "name": "Indonesia (ID)"
    },
    "Malaysia (MY)": {
        "region_code": "MY",
        "languages": ["ms", "en", "zh"],  # Tiếng Mã Lai, Anh, Trung Quốc
        "name": "Malaysia (MY)"
    },
    "Nhật Bản (JP)": {
        "region_code": "JP",
        "languages": ["ja", "en"],  # Tiếng Nhật, Anh
        "name": "Nhật Bản (JP)"
    },
    "Hàn Quốc (KR)": {
        "region_code": "KR",
        "languages": ["ko", "en"],  # Tiếng Hàn, Anh
        "name": "Hàn Quốc (KR)"
    },
    "Ấn Độ (IN)": {
        "region_code": "IN",
        "languages": ["hi", "en", "ta", "te"],  # Tiếng Hindi, Anh, Tamil, Telugu
        "name": "Ấn Độ (IN)"
    },
    "Brazil (BR)": {
        "region_code": "BR",
        "languages": ["pt", "en"],  # Tiếng Bồ Đào Nha, Anh
        "name": "Brazil (BR)"
    },
    "Úc (AU)": {
        "region_code": "AU",
        "languages": ["en"],  # Tiếng Anh
        "name": "Úc (AU)"
    },
    "Thái Lan (TH)": {
        "region_code": "TH",
        "languages": ["th", "en"],  # Tiếng Thái, Anh
        "name": "Thái Lan (TH)"
    },
    "Philippines (PH)": {
        "region_code": "PH",
        "languages": ["tl", "en"],  # Tiếng Tagalog, Anh
        "name": "Philippines (PH)"
    }
}

# Video duration options for keyword research tab
# ===== BẮT ĐẦU THAY ĐỔI =====
VIDEO_DURATION_OPTIONS = {
    "Bất kỳ": None,
    "Dưới 1 phút": "under_60s",
    "Trên 1 phút": "over_60s",
    "Trên 4 phút": "over_4m",
    "Trên 30 phút": "over_30m",
    "Trên 60 phút": "over_60m",
    "Trên 120 phút": "over_120m"
}
# ===== KẾT THÚC THAY ĐỔI =====

# Upload date options for keyword research tab
# Note: timedelta will be handled in the tab logic or main_app
UPLOAD_DATE_OPTIONS_DESC = {
    "Bất kỳ": None,
    "Trong 1 giờ qua": "PT1H", # ISO 8601 duration for 1 hour
    "Trong 24 giờ qua": "P1D", # ISO 8601 duration for 1 day
    "Trong 7 ngày qua": "P7D",
    "Trong 30 ngày qua": "P30D",
    "Trong 90 ngày qua": "P90D",
    "Trong 365 ngày qua": "P365D"
}

ORDER_OPTIONS_MAP = {
    "Mức độ liên quan": "relevance",
    "Ngày": "date",
    "Số lượt xem": "viewCount"
}

VIDEO_DEFINITION_OPTIONS_MAP = {
    "Bất kỳ": None,
    "Chuẩn (SD)": "standard",
    "Cao (HD)": "high"
}