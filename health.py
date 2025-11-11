# health.py
from flask import Flask
import os
import redis
import logging

# --- لاگ ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- اتصال به Redis (دقیقاً مثل bot.py) ---
UPSTASH_REDIS_URL = os.environ["UPSTASH_REDIS_URL"]

if not UPSTASH_REDIS_URL.startswith("rediss://"):
    logger.error("UPSTASH_REDIS_URL باید با rediss:// شروع بشه!")
    raise ValueError("Invalid Redis URL scheme")

try:
    r = redis.from_url(
        UPSTASH_REDIS_URL,
        decode_responses=True,
        ssl_cert_reqs=None  # برای Upstash حیاتیه
    )
    # تست اتصال
    r.ping()
    logger.info("health.py: Redis متصل شد!")
except Exception as e:
    logger.error(f"health.py: خطا در اتصال به Redis: {e}")
    r = None  # اگر وصل نشد، بعداً خطا می‌دیم

# --- مسیر health با چک Redis ---
@app.route('/health', methods=['GET'])
def health_check():
    if r is None:
        return 'Redis: Not Connected', 500
    try:
        r.ping()  # دوباره تست کن
        return 'OK', 200
    except Exception as e:
        return f'Redis Down: {str(e)}', 500

# --- برای Render (اجباری) ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
