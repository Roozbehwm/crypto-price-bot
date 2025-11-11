# ربات قیمت ارز (Crypto Price Bot)

ربات تلگرام برای استعلام قیمت لحظه‌ای + هشدار قیمت + مدیریت ارزها

---

## ویژگی‌ها
- قیمت هر ۱۵ دقیقه (قابل تنظیم)
- هشدار قیمت (بیشتر/کمتر از X دلار)
- جستجوی پیشرفته
- حداکثر ۲۰ ارز
- داده‌ها دائمی (Upstash Redis)
- ۲۴ ساعته (Render + Webhook)

---

## دیپلوی (Deploy)

### 1. Fork این ریپو
### 2. در Render.com:
- **New Web Service**
- **Runtime**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python bot.py`

### 3. Environment Variables (در Render → Environment)
```env
TOKEN=your_bot_token_here
UPSTASH_REDIS_URL=your_upstash_redis_url_here
