import os

# جلب المتغيرات من البيئة
TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME")
ADMINS = list(map(int, os.environ.get("ADMINS", "").split(',')))

# التحقق من وجود المتغيرات
if not all([TOKEN, CHANNEL_ID, CHANNEL_USERNAME]):
    raise ValueError("❌ تأكد من تعيين جميع المتغيرات في Railway")
