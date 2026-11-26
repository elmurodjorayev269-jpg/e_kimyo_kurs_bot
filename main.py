import os
import json
import time
import sqlite3
import random
import threading
import requests
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template_string
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ================= SOZLAMALAR =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "SIZNING_YANGI_BOT_TOKENINGIZ")
ADMIN_PAROL = os.environ.get("ADMIN_PAROL", "kimyo2026")
ADMIN_LICHKA = "@onlyibrohimov"
KANAL_USER = "@kimyo_sertifkat_uchun"
KANAL_LINK = "https://t.me/kimyo_sertifkat_uchun"
KARTA_RAQAM = "9860 3501 4209 7954"
KARTA_EGASI = "Azizbek Ibrohimov"

YOPIQ_GURUH_ID = int(os.environ.get("YOPIQ_GURUH_ID", "-1001234567890"))
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://e-kimyo-kurs-bot.onrender.com")

UZ_TZ = timezone(timedelta(hours=5))

def uz_now():
    return datetime.now(UZ_TZ).replace(tzinfo=None)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

user_states = {}
user_data = {}

# ================= BAZA VA XAVFSIZLIK =================
def init_db():
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                phone TEXT DEFAULT '',
                paid_until TEXT,
                is_active INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS written_works (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                full_name TEXT,
                photo_id TEXT,
                score REAL DEFAULT -1,
                checked_at TEXT
            )
        """)
        conn.commit()

def db_check_user(user_id, full_name, username):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT is_active, is_admin FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if not row:
            c.execute(
                "INSERT INTO users (user_id, full_name, username, is_active, is_admin) VALUES (?, ?, ?, 0, 0)",
                (user_id, full_name, username or "")
            )
            conn.commit()
            return False, False
        return bool(row[0] == 1), bool(row[1] == 1)

def db_get_admins():
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE is_admin = 1")
        return [r[0] for r in c.fetchall()]

# ================= MENYULAR =================
def guest_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add(
        KeyboardButton("✍️ Kursga yozilish"),
        KeyboardButton("📞 Admin bilan aloqa")
    )
    return kb

def student_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("📸 Vazifa (Rasm nomi) yuborish"),
        KeyboardButton("👤 Shaxsiy kabinet"),
        KeyboardButton("📞 Admin bilan aloqa")
    )
    return kb

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("👥 O'quvchilarni boshqarish"),
        KeyboardButton("📢 Xabar yuborish"),
        KeyboardButton("🔙 Bosh menyu")
    )
    return kb

def cancel_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("❌ Bekor qilish"))
    return kb

# ================= ASOSIY BUYRUQLAR =================
@bot.message_handler(chat_types=["private"], commands=['start'])
def start_cmd(message):
    uid = message.from_user.id
    user_states.pop(uid, None)
    is_active, is_admin = db_check_user(uid, message.from_user.full_name, message.from_user.username)
    
    if is_admin:
        return bot.send_message(uid, "⚙️ <b>Admin Panel:</b>", reply_markup=admin_menu())
    elif is_active:
        bot.send_message(uid, f"Xush kelibsiz, <b>{message.from_user.full_name}</b>!", reply_markup=student_menu())
    else:
        text = (f"Assalomu alaykum, <b>{message.from_user.full_name}</b>!\n"
                f"🧪 <b>A+ Kimyo</b> platformasiga xush kelibsiz.\n"
                f"Tizimdan to'liq foydalanish uchun kursga ro'yxatdan o'ting:")
        bot.send_message(uid, text, reply_markup=guest_menu())

@bot.message_handler(chat_types=["private"], commands=['admin'])
def admin_cmd(message):
    uid = message.from_user.id
    is_active, is_admin = db_check_user(uid, message.from_user.full_name, message.from_user.username)
    parts = message.text.split()
    if len(parts) > 1 and parts[1] == ADMIN_PAROL:
        with sqlite3.connect("database.db") as conn:
            conn.cursor().execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (uid,))
            conn.commit()
        bot.send_message(uid, "✅ Siz adminga aylandingiz!", reply_markup=admin_menu())
    elif is_admin:
        bot.send_message(uid, "⚙️ <b>Admin Panel:</b>", reply_markup=admin_menu())
    else:
        bot.send_message(uid, "🚫 Ruxsat yo‘q.")

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "🔙 Bosh menyu")
def main_menu_route(message):
    user_states.pop(message.from_user.id, None)
    is_active, is_admin = db_check_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    if is_admin:
        bot.send_message(message.chat.id, "⚙️ Admin Panel:", reply_markup=admin_menu())
    elif is_active:
        bot.send_message(message.chat.id, "🏠 Asosiy menyu:", reply_markup=student_menu())
    else:
        bot.send_message(message.chat.id, "🏠 Asosiy menyu:", reply_markup=guest_menu())

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "")
def cancel_action(message):
    main_menu_route(message)

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📞 Admin bilan aloqa")
def contact_admin(message):
    bot.send_message(message.chat.id, f"👨‍🏫 Murojaat uchun: {ADMIN_LICHKA}")

# ================= TO'LOV JARAYONI =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "✍️ Kursga yozilish")
def reg_1(message):
    user_states[message.from_user.id] = "reg_phone"
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📱 Raqamni yuborish", request_contact=True), KeyboardButton(""))
    bot.send_message(message.chat.id, "📱 Telefon raqamingizni yuboring:", reply_markup=kb)

@bot.message_handler(chat_types=["private"], content_types=['contact', 'text'], func=lambda m: user_states.get(m.from_user.id) == "reg_phone")
def reg_2(message):
    uid = message.from_user.id
    phone = message.contact.phone_number if message.contact else message.text
    user_data[uid] = {"phone": phone}
    user_states[uid] = "reg_receipt"
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, uid))
        conn.commit()
    bot.send_message(uid, f"💳 Karta: <code>{KARTA_RAQAM}</code>\n📸 To'lov chekini rasm ko'rinishida yuboring:", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], content_types=['photo'], func=lambda m: user_states.get(m.from_user.id) == "reg_receipt")
def reg_done(message):
    uid = message.from_user.id
    photo_id = message.photo[-1].file_id
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"pay_ok_{uid}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"pay_no_{uid}")
    )
    caption = f"🆕 <b>YANGI TO'LOV CHEKI</b>\nFoydalanuvchi: {message.from_user.full_name}\nID: <code>{uid}</code>"
    for adm in db_get_admins():
        try:
            bot.send_photo(adm, photo_id, caption=caption, reply_markup=kb)
        except Exception:
            pass
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Chek qabul qilindi. Tez orada admin tasdiqlaydi!", reply_markup=guest_menu())

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def pay_decision(call):
    _, act, target = call.data.split("_")
    target = int(target)
    if act == "ok":
        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET is_active = 1 WHERE user_id = ?", (target,))
            conn.commit()
        bot.send_message(target, "🎉 <b>To'lovingiz tasdiqlandi!</b> Barcha menyular ochildi.", reply_markup=student_menu())
        bot.edit_message_caption("✅ <b>TASDIQLANDI</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
    else:
        bot.send_message(target, "diqlanmadi.")
        bot.edit_message_caption("❌ <b>RAD ETILDI</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
    bot.answer_callback_query(call.id)

# ================= VAZIFA TOPSHIRISH VA BAHOLASH (1-10) =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📸 Vazifa (Rasm nomi) yuborish")
def ask_written_photo(message):
    uid = message.from_user.id
    is_active, _ = db_check_user(uid, message.from_user.full_name, message.from_user.username)
    if not is_active:
        return bot.send_message(uid, "🚫 Ruxsat yo'q.")
    user_states[uid] = "wait_hw_photo"
    bot.send_message(uid, "📸 Yechimlar tushirilgan rasm(lar)ni ustoz tekshiruvi uchun yuboring:", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], content_types=['photo'], func=lambda m: user_states.get(m.from_user.id) == "wait_hw_photo")
def receive_written_photo(message):
    uid = message.from_user.id
    photo_id = message.photo[-1].file_id
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("INSERT INTO written_works (user_id, full_name, photo_id, checked_at) VALUES (?, ?, ?, ?)",
                  (uid, message.from_user.full_name, photo_id, uz_now().strftime("%Y-%m-%d %H:%M")))
        work_id = c.lastrowid
        conn.commit()

    kb = InlineKeyboardMarkup(row_width=5)
    buttons = [InlineKeyboardButton(str(i), callback_data=f"rate_{work_id}_{i}") for i in range(1, 11)]
    kb.add(*buttons)

    caption = f"📝 <b>YANGI VAZIFA KELDI!</b>\nO'quvchi: {message.from_user.full_name}\nID: <code>{uid}</code>\nBaho qo'ying (1-10):"
    for adm in db_get_admins():
        try:
            bot.send_photo(adm, photo_id, caption=caption, reply_markup=kb)
        except Exception:
            pass
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Vazifa ustozga yuborildi!", reply_markup=student_menu())

@bot.callback_query_handler(func=lambda call: call.data.startswith("rate_"))
def rate_work(call):
    _, work_id, score = call.data.split("_")
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE written_works SET score = ? WHERE id = ?", (score, work_id))
        c.execute("SELECT user_id FROM written_works WHERE id = ?", (work_id,))
        student_id = c.fetchone()[0]
        conn.commit()
    bot.edit_message_caption(f"✅ Baholandi: <b>{score} ball</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
    try:
        bot.send_message(student_id, f"🎉 <b>Ustoz vazifangizni tekshirdi!</b>\nBahoyingiz: <b>{score} ball</b>")
    except Exception:
        pass
    bot.answer_callback_query(call.id)

# ================= SHAXSIY KABINET =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "👤 Shaxsiy kabinet")
def profile(message):
    uid = message.from_user.id
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT phone FROM users WHERE user_id = ?", (uid,))
        phone = c.fetchone()[0]
        c.execute("SELECT COUNT(*), AVG(score) FROM written_works WHERE user_id = ? AND score >= 0", (uid,))
        stats = c.fetchone()
    avg_score = round(stats[1], 1) if stats[1] else "Baholanmagan"
    text = (f"👤 <b>SHAXSIY KABINET</b>\n"
            f"F.I.Sh: {message.from_user.full_name}\n"
            f"Tel: {phone}\n\n"
            f"📊 Topshirilgan vazifalar: {stats[0]} ta\n"
            f"📈 O'rtacha ball: {avg_score}")
    bot.send_message(uid, text)

# ================= ADMIN FUNKSIYALARI =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "👥 O'quvchilarni boshqarish")
def admin_users(message):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name, is_active FROM users WHERE is_admin = 0")
        users = c.fetchall()
    text = "👥 <b>O'quvchilar ro'yxati:</b>\n" + "\n".join([f"• {u[0]} ({'Aktiv' if u[1] else 'Kutilmoqda'})" for u in users])
    bot.send_message(message.chat.id, text)

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📢 Xabar yuborish")
def broadcast_ask(message):
    user_states[message.from_user.id] = "broad_text"
    bot.send_message(message.chat.id, "Xabarni kiriting:", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], content_types=['text', 'photo'], func=lambda m: user_states.get(m.from_user.id) == "broad_text")
def broadcast_send(message):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        users = [r[0] for r in c.fetchall()]
    user_states.pop(message.from_user.id, None)
    for u in users:
        try:
            bot.copy_message(u, message.chat.id, message.message_id)
        except Exception:
            pass
    bot.send_message(message.chat.id, "✅ Hammaga yuborildi!", reply_markup=admin_menu())

# ================= FLASK VA BOTNI ISHLATISH =================
@app.route("/")
def index():
    return "Bot ishlamoqda!"

def bot_polling():
    while True:
        try:
            print("Bot polling boshlandi...")
            bot.infinity_polling(none_stop=True, timeout=30)
        except Exception as e:
            print(f"Polling xatosi: {e}. 5 soniyadan so'ng qayta uriniladi...")
            time.sleep(5)

def keep_alive():
    while True:
        try:
            requests.get(RENDER_URL, timeout=10)
        except Exception as e:
            print(f"Ping xatosi: {e}")
        time.sleep(300)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=app.run, args=("0.0.0.0", int(os.environ.get("PORT", 8080))), daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    bot_polling()
