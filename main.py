import os
import sqlite3
import telebot
from telebot import types
from threading import Thread
from flask import Flask
from dotenv import load_dotenv

# .env faylini o'qish
load_dotenv()

TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN topilmadi! .env fayl yoki Render env variable'ni tekshiring.")

# Sizning kanallaringiz
DATABASE_CHANNEL_ID = -1004318848872
REQUIRED_CHANNEL = "@kinochi_273"

bot = telebot.TeleBot(TOKEN)

# --- HEALTH SERVER (Render uxlab qolmasligi uchun) ---
app = Flask('')


@app.route('/')
@app.route('/health')
def health():
    return "Bot ishlayapti!", 200


def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)


Thread(target=run_health_server, daemon=True).start()


# --- BAZANI YARATISH ---
def init_db():
    conn = sqlite3.connect("movies.db")
    cursor = conn.cursor()
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS movies
                   (
                       code
                       TEXT
                       PRIMARY
                       KEY,
                       file_id
                       TEXT
                   )
                   """)
    conn.commit()
    conn.close()


init_db()


# --- OBUNANI TEKSHIRISH ---
def check_subscription(user_id):
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception as e:
        print(f"Obunani tekshirishda xatolik: {e}")
        return False


# --- YORDAMCHI FUNKSIYA: BAZAGA SAQLASH ---
def save_to_database(message, code, file_id):
    conn = sqlite3.connect("movies.db")
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO movies (code, file_id) VALUES (?, ?)", (code, file_id))
    conn.commit()
    conn.close()
    print(f"✅ {code} - kodli kino bazaga saqlandi!")


# --- 1. KANALDAGI YANGI POSTLARNI SAQLASH ---
@bot.channel_post_handler(content_types=['video', 'document'])
def auto_add_movie(message):
    if message.chat.id == DATABASE_CHANNEL_ID and message.caption:
        code = message.caption.strip()
        file_id = message.video.file_id if message.video else message.document.file_id
        save_to_database(message, code, file_id)


# --- 2. KANALDAGI TAHRIRLANGAN POSTLARNI YANGILASH ---
@bot.edited_channel_post_handler(content_types=['video', 'document'])
def auto_edit_movie(message):
    if message.chat.id == DATABASE_CHANNEL_ID and message.caption:
        code = message.caption.strip()
        file_id = message.video.file_id if message.video else message.document.file_id
        save_to_database(message, code, file_id)


# --- 3. ESKI KINOLARNI FORWARD QILIB SAQLASH ---
@bot.message_handler(content_types=['video', 'document'])
def save_forwarded_movie(message):
    # Agar siz kanaldan forward qilsangiz va tagida matn bo'lsa
    if message.caption:
        code = message.caption.strip()
        file_id = message.video.file_id if message.video else message.document.file_id
        save_to_database(message, code, file_id)
        bot.reply_to(message, f"✅ `{code}` kodi bazaga muvaffaqiyatli saqlandi!", parse_mode="Markdown")


# --- START BUYRUG'I ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id

    if not check_subscription(user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 Kanalga obuna bo'lish", url="https://t.me/kinochi_273"))
        markup.add(types.InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub"))
        bot.send_message(
            message.chat.id,
            "⚠️ **Botdan foydalanish uchun avval kanalimizga obuna bo'ling:**",
            reply_markup=markup, parse_mode="Markdown"
        )
        return

    welcome_text = (
        "🎬 **Kinolar Olami botiga xush kelibsiz!**\n\n"
        "✨ Marhamat, kino kodini yuboring (masalan: `1`, `2`):"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")


# --- OBUNANI TEKSHIRISH (TUGMA BOSILGANDA) ---
@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check_sub(call):
    user_id = call.from_user.id
    if check_subscription(user_id):
        bot.answer_callback_query(call.id, "Rahmat, obuna tasdiqlandi! 🎉")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        bot.send_message(
            call.message.chat.id,
            "✅ **Obunangiz tasdiqlandi!**\n\n✨ Endi kino kodini yuboring:",
            parse_mode="Markdown"
        )
    else:
        bot.answer_callback_query(call.id, "❌ Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)


# --- KINO QIDIRISH (MATNLI XABARLAR UCHUN) ---
@bot.message_handler(func=lambda message: True)
def get_movie(message):
    user_id = message.from_user.id

    if not check_subscription(user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 Kanalga obuna bo'lish", url="https://t.me/kinochi_273"))
        markup.add(types.InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub"))
        bot.reply_to(
            message,
            "⚠️ **Kinoni olish uchun avval kanalimizga obuna bo'ling!**",
            reply_markup=markup, parse_mode="Markdown"
        )
        return

    code = message.text.strip()

    conn = sqlite3.connect("movies.db")
    cursor = conn.cursor()
    cursor.execute("SELECT file_id FROM movies WHERE code = ?", (code,))
    result = cursor.fetchone()
    conn.close()

    if result:
        file_id = result[0]
        text = f"🎬 **Kino kodi:** `{code}`\n\n📥 Bizning kanal: [@kinochi_273](https://t.me/kinochi_273)"

        # Kino turini avtomatik aniqlash (video yoki fayl)
        try:
            bot.send_video(message.chat.id, file_id, caption=text, parse_mode="Markdown")
        except Exception:
            try:
                bot.send_document(message.chat.id, file_id, caption=text, parse_mode="Markdown")
            except Exception as e:
                bot.reply_to(message, f"❌ Faylni yuborishda xatolik yuz berdi.")
    else:
        bot.reply_to(
            message, "❌ **Bunday kodli kino topilmadi.** Kodni tekshirib ko'ring.", parse_mode="Markdown"
        )


# --- BOTNI ISHGA TUSHIRISH ---
print("Bot muvaffaqiyatli ishga tushdi!")
bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)