
import sqlite3
import json
import time
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Create 'data' directory if not exists
if not os.path.exists('data'):
    os.makedirs('data')

DB_PATH = os.path.join('data', 'cache.db')

def init_db():
    """Initialize the SQLite database for caching."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Table for general API responses (search, video details)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS api_cache (
        key TEXT PRIMARY KEY,
        response_json TEXT,
        timestamp REAL,
        expiry REAL
    )
    ''')
    
    # Table for tracking quota usage per key (optional future expansion)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS key_usage (
        api_key TEXT PRIMARY KEY,
        used_quota INTEGER DEFAULT 0,
        last_reset REAL
    )
    ''')
    
    conn.commit()
    conn.close()

def get_cache(key):
    """Retrieve data from cache if it exists and hasn't expired."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT response_json, expiry FROM api_cache WHERE key = ?', (key,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            response_json, expiry = result
            if time.time() < expiry:
                return json.loads(response_json)
            else:
                # Clean up expired entry
                clear_cache_key(key)
                return None
        return None
    except Exception as e:
        logging.error(f"Cache read error: {e}")
        return None

def set_cache(key, data, ttl_seconds=3600):
    """Save data to cache with a Time-To-Live (TTL). Default 1 hour."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        expiry = time.time() + ttl_seconds
        cursor.execute('''
        INSERT OR REPLACE INTO api_cache (key, response_json, timestamp, expiry)
        VALUES (?, ?, ?, ?)
        ''', (key, json.dumps(data), time.time(), expiry))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Cache write error: {e}")

def clear_cache_key(key):
    """Clear a specific cache entry by key."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM api_cache WHERE key = ?', (key,))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        logger.error(f"Failed to clear cache key '{key}': {e}")
    except Exception as e:
        logger.error(f"Unexpected error clearing cache key '{key}': {e}")

def clear_all_cache():
    """Clear all cache entries by removing the database file."""
    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
            init_db()
            logger.info("All cache cleared successfully")
    except OSError as e:
        logger.error(f"Failed to clear cache database: {e}")
    except Exception as e:
        logger.error(f"Unexpected error clearing all cache: {e}")
