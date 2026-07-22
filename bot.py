import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import yt_dlp
import sqlite3
from config import TOKEN, CHANNEL_ID, CHANNEL_USERNAME, ADMINS

# إعدادات التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# إعدادات Railway
PORT = int(os.environ.get('PORT', 8080))
USE_WEBHOOK = os.environ.get('USE_WEBHOOK', 'False').lower() == 'true'
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', '')

# تهيئة قاعدة البيانات
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, username TEXT, join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def add_user(user_id, username):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"خطأ في إضافة المستخدم: {e}")
        return False

def get_all_users():
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        users = c.fetchall()
        conn.close()
        return [user[0] for user in users]
    except Exception as e:
        logger.error(f"خطأ في جلب المستخدمين: {e}")
        return []

def get_user_count():
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"خطأ في جلب عدد المستخدمين: {e}")
        return 0

# تهيئة قاعدة البيانات عند التشغيل
init_db()

# خيارات تحميل الصوت
ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'ignoreerrors': True,
    'no_check_certificate': True,
}

# دالة التحقق من الاشتراك
async def is_subscribed(user_id, context):
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"خطأ في التحقق من الاشتراك: {e}")
        return False

# زر التحقق من الاشتراك
async def check_subscription(update, context):
    user_id = update.effective_user.id
    username = update.effective_user.username or "مستخدم"
    
    if await is_subscribed(user_id, context):
        # المستخدم مشترك
        add_user(user_id, username)
        await update.message.reply_text(
            "✅ تم التحقق من اشتراكك!\n\n"
            "🎵 أرسل رابط يوتيوب لتحميل الأغنية.\n"
            "📌 مثال: https://youtube.com/watch?v=..."
        )
        return
    
    # زر الاشتراك
    keyboard = [
        [InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")],
        [InlineKeyboardButton("✅ تم الاشتراك", callback_data='check_sub')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⚠️ للاستخدام يجب الاشتراك في القناة أولاً:\n\n"
        f"📢 القناة: {CHANNEL_USERNAME}\n"
        "1️⃣ اضغط على زر الاشتراك\n"
        "2️⃣ اشترك في القناة\n"
        "3️⃣ اضغط على زر 'تم الاشتراك'",
        reply_markup=reply_markup
    )

# التحقق من الزر
async def check_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    username = query.from_user.username or "مستخدم"
    
    if query.data == 'check_sub':
        if await is_subscribed(user_id, context):
            add_user(user_id, username)
            await query.edit_message_text(
                "✅ تم التحقق من اشتراكك!\n\n"
                "🎵 أرسل رابط يوتيوب لتحميل الأغنية."
            )
        else:
            await query.answer(
                "❌ لم تشترك بعد! اشترك في القناة ثم حاول مرة أخرى.",
                show_alert=True
            )

# تحميل ونشر الأغنية
async def download_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "مستخدم"
    
    # التحقق من الاشتراك
    if not await is_subscribed(user_id, context):
        await check_subscription(update, context)
        return
    
    url = update.message.text.strip()
    
    # التحقق من رابط يوتيوب
    if not ('youtube.com' in url or 'youtu.be' in url):
        await update.message.reply_text(
            "❌ هذا ليس رابط يوتيوب صحيح!\n\n"
            "📌 أرسل رابط فيديو يوتيوب مثل:\n"
            "https://youtube.com/watch?v=...\n"
            "أو https://youtu.be/..."
        )
        return
    
    # إرسال رسالة التحميل
    msg = await update.message.reply_text("⏳ جاري تحميل الأغنية...\n🔄 قد يستغرق هذا بضع ثوانٍ")
    
    try:
        # تحميل الصوت
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # تحديد اسم الملف النهائي
            mp3_file = None
            for ext in ['.mp3', '.webm', '.m4a']:
                test_file = filename.replace('.webm', ext).replace('.m4a', ext)
                if os.path.exists(test_file):
                    mp3_file = test_file
                    break
            
            if not mp3_file or not os.path.exists(mp3_file):
                await msg.edit_text("❌ فشل في تحميل الأغنية، حاول مرة أخرى.")
                return
            
            # الحصول على معلومات الأغنية
            title = info.get('title', 'أغنية')
            performer = info.get('uploader', 'مجهول')
            duration = info.get('duration', 0)
            
            # تحويل المدة إلى دقائق وثواني
            minutes = duration // 60
            seconds = duration % 60
            duration_str = f"{minutes}:{seconds:02d}" if minutes > 0 else f"{seconds} ثانية"
            
            # إرسال للقناة
            try:
                with open(mp3_file, 'rb') as audio:
                    await context.bot.send_audio(
                        chat_id=CHANNEL_ID,
                        audio=audio,
                        title=title,
                        performer=performer,
                        duration=duration,
                        caption=f"🎵 {title}\n"
                               f"🎤 {performer}\n"
                               f"⏱️ {duration_str}\n"
                               f"📥 طلب من: @{username}"
                    )
                logger.info(f"تم نشر الأغنية في القناة: {title}")
            except Exception as e:
                logger.error(f"خطأ في النشر للقناة: {e}")
                await msg.edit_text(f"❌ فشل النشر في القناة: {str(e)}")
                # حذف الملف قبل الخروج
                if os.path.exists(mp3_file):
                    os.remove(mp3_file)
                return
            
            # إرسال للمستخدم
            try:
                with open(mp3_file, 'rb') as audio:
                    await update.message.reply_audio(
                        audio=audio,
                        title=title,
                        performer=performer,
                        duration=duration,
                        caption=f"🎵 {title}\n🎤 {performer}\n⏱️ {duration_str}"
                    )
                await msg.edit_text("✅ تم النشر في القناة وإرسال الأغنية بنجاح!")
            except Exception as e:
                logger.error(f"خطأ في إرسال الأغنية للمستخدم: {e}")
                await msg.edit_text(f"⚠️ تم النشر في القناة ولكن فشل الإرسال لك: {str(e)}")
            
            # حذف الملف بعد الإرسال
            try:
                if os.path.exists(mp3_file):
                    os.remove(mp3_file)
                    logger.info(f"تم حذف الملف: {mp3_file}")
            except Exception as e:
                logger.error(f"خطأ في حذف الملف: {e}")
            
    except Exception as e:
        logger.error(f"خطأ في التحميل: {e}")
        await msg.edit_text(f"❌ حدث خطأ أثناء التحميل:\n{str(e)[:200]}")
        
        # تنظيف الملفات المتبقية
        for file in os.listdir('.'):
            if file.endswith(('.mp3', '.webm', '.m4a')):
                try:
                    os.remove(file)
                except:
                    pass

# أمر البث للمشتركين
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in ADMINS:
        await update.message.reply_text("❌ هذا الأمر للمسؤولين فقط!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "📢 استخدم الأمر:\n"
            "/broadcast النص المرسل\n\n"
            "مثال: /broadcast مرحباً جميعاً"
        )
        return
    
    message = ' '.join(context.args)
    users = get_all_users()
    
    if not users:
        await update.message.reply_text("❌ لا يوجد مشتركين للإرسال إليهم!")
        return
    
    # إرسال رسالة البث
    progress_msg = await update.message.reply_text(f"⏳ جاري الإرسال إلى {len(users)} مشترك...")
    sent = 0
    failed = 0
    
    for uid in users:
        try:
            await context.bot.send_message(
                uid,
                f"📢 {message}",
                parse_mode='HTML'
            )
            sent += 1
        except Exception as e:
            failed += 1
            logger.error(f"فشل الإرسال للمستخدم {uid}: {e}")
    
    await progress_msg.edit_text(
        f"✅ تم الإرسال بنجاح!\n"
        f"📨 تم الإرسال: {sent}\n"
        f"❌ فشل الإرسال: {failed}"
    )

# أمر الإحصائيات
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in ADMINS:
        await update.message.reply_text("❌ هذا الأمر للمسؤولين فقط!")
        return
    
    count = get_user_count()
    users = get_all_users()
    
    # جلب معلومات البوت
    bot_info = await context.bot.get_me()
    
    await update.message.reply_text(
        f"📊 <b>إحصائيات البوت</b>\n\n"
        f"🤖 اسم البوت: {bot_info.first_name}\n"
        f"🆔 معرف البوت: @{bot_info.username}\n"
        f"👥 عدد المشتركين: {count}\n"
        f"📌 قناة البوت: {CHANNEL_USERNAME}\n"
        f"👤 عدد المسؤولين: {len(ADMINS)}\n\n"
        f"💡 استخدم /broadcast للإرسال للجميع",
        parse_mode='HTML'
    )

# أمر مساعدة
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 <b>مساعدة بوت الأغاني</b>\n\n"
        "📌 <b>الأوامر المتاحة:</b>\n"
        "/start - بدء البوت والتحقق من الاشتراك\n"
        "/help - عرض هذه المساعدة\n\n"
        "🎯 <b>كيفية الاستخدام:</b>\n"
        "1. اشترك في القناة {}\n"
        "2. أرسل رابط يوتيوب\n"
        "3. استلم الأغنية بصيغة MP3\n\n"
        "📢 <b>أوامر المسؤولين:</b>\n"
        "/broadcast نص - إرسال رسالة للجميع\n"
        "/stats - عرض إحصائيات البوت\n\n"
        "💡 يمكنك إرسال روابط يوتيوب مباشرة دون أوامر.".format(CHANNEL_USERNAME),
        parse_mode='HTML'
    )

# أمر حذف جميع المستخدمين (للمسؤولين فقط)
async def clear_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in ADMINS:
        await update.message.reply_text("❌ هذا الأمر للمسؤولين فقط!")
        return
    
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("DELETE FROM users")
        conn.commit()
        conn.close()
        await update.message.reply_text("🗑️ تم حذف جميع المستخدمين من قاعدة البيانات!")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {str(e)}")

# دالة البدء الرئيسية
def main():
    # إنشاء التطبيق
    app = Application.builder().token(TOKEN).build()
    
    # إضافة معالجات الأوامر
    app.add_handler(CommandHandler("start", check_subscription))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("clearusers", clear_users))
    
    # إضافة معالجات أخرى
    app.add_handler(CallbackQueryHandler(check_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_and_send))
    
    # تشغيل البوت
    logger.info("🚀 بدء تشغيل البوت...")
    
    if USE_WEBHOOK and WEBHOOK_URL:
        # وضع Webhook (لـ Railway مع SSL)
        logger.info(f"🔗 تشغيل بوضع Webhook على المنفذ {PORT}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL,
            secret_token=os.environ.get('WEBHOOK_SECRET', '')
        )
    else:
        # وضع Polling (افتراضي)
        logger.info("🔄 تشغيل بوضع Polling")
        app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
