import os
import sqlite3
import threading
from datetime import datetime
from flask import Flask
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ================= SOZLAMALAR =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8636730483:AAGl0wHYP-ZBqaEA64EKUkzSlo1G3DDmkcI")
ADMIN_PAROL = "kimyo2026"  # Botda /admin kimyo2026 deb yozsangiz admin bo'lasiz
KANAL_USER = "@kimyo_sertifkat_uchun"
KARTA_RAQAM = "8600 0000 0000 0000"
KARTA_EGASI = "Azizbek Ibrohimov"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

user_states = {}
user_data = {}

# ================= MA'LUMOTLAR BAZASI =================
def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            phone TEXT DEFAULT '',
            is_admin INTEGER DEFAULT 0,
            joined_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tests (
            test_code INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            answers TEXT,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            full_name TEXT,
            test_code INTEGER,
            score INTEGER,
            total INTEGER,
            percent REAL,
            checked_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            file_id TEXT,
            file_type TEXT,
            added_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_setting(key, default=""):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def db_add_user(user_id, full_name, username):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, full_name, username, joined_at) VALUES (?, ?, ?, ?)",
        (user_id, full_name, username or "", datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()
    conn.close()

def db_is_admin(user_id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row and row[0] == 1)

def db_set_admin(user_id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def db_get_admins():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE is_admin = 1")
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows

# ================= TUGMALAR =================
def main_menu(user_id):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("📝 Test tekshirish"),
        KeyboardButton("🏆 Test reytingi"),
        KeyboardButton("✍️ Kursga yozilish"),
        KeyboardButton("📚 Bepul darsliklar"),
        KeyboardButton("ℹ️ Kurslar haqida"),
        KeyboardButton("📞 Admin bilan aloqa")
    )
    if db_is_admin(user_id):
        kb.add(KeyboardButton("⚙️ Admin Panel"))
    return kb

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("➕ Yangi test yaratish"),
        KeyboardButton("📋 Testlar roʻyxati"),
        KeyboardButton("🗑 Testni oʻchirish"),
        KeyboardButton("📥 Darslik (PDF/Video) qoʻshish"),
        KeyboardButton("💳 Karta raqamni oʻzgartirish"),
        KeyboardButton("📊 Statistika"),
        KeyboardButton("📢 Hammaga xabar (Rassilka)"),
        KeyboardButton("🔙 Asosiy menyu")
    )
    return kb

def cancel_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("❌ Bekor qilish"))
    return kb

# ================= /START VA /ADMIN =================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.from_user.id
    user_states.pop(uid, None)
    db_add_user(uid, message.from_user.full_name, message.from_user.username)
    
    text = (
        f"Assalomu alaykum, <b>{message.from_user.full_name}</b>! 👋\n\n"
        f"🧪 <b>A+ Kimyo | Online Maktabi</b>ning rasmiy botiga xush kelibsiz!\n\n"
        f"🔹 Diagnostik va Milliy sertifikat testlarini tekshiring\n"
        f"🔹 Bepul PDF qoʻllanmalar va video-darslarni oling\n"
        f"🔹 Maxsus onlayn kurslarimizga roʻyxatdan oʻting\n\n"
        f"👇 Quyidagi menyudan kerakli boʻlimni tanlang:"
    )
    bot.send_message(uid, text, reply_markup=main_menu(uid))

@bot.message_handler(commands=['admin'])
def admin_cmd(message):
    uid = message.from_user.id
    db_add_user(uid, message.from_user.full_name, message.from_user.username)
    parts = message.text.split()
    if len(parts) > 1 and parts[1] == ADMIN_PAROL:
        db_set_admin(uid)
        bot.send_message(uid, "✅ <b>Tabriklaymiz! Sizga Admin huquqi berildi.</b>", reply_markup=admin_menu())
    elif db_is_admin(uid):
        bot.send_message(uid, "⚙️ <b>Admin Panelga xush kelibsiz:</b>", reply_markup=admin_menu())
    else:
        bot.send_message(uid, "🔒 Admin boʻlish uchun parolni yozing:\n<code>/admin kimyo2026</code>")

@bot.message_handler(func=lambda m: m.text in ["❌ Bekor qilish", "🔙 Asosiy menyu"])
def cancel_action(message):
    uid = message.from_user.id
    user_states.pop(uid, None)
    bot.send_message(uid, "🏠 Asosiy menyu:", reply_markup=main_menu(uid))

@bot.message_handler(func=lambda m: m.text == "⚙️ Admin Panel")
def open_admin(message):
    uid = message.from_user.id
    if db_is_admin(uid):
        user_states.pop(uid, None)
        bot.send_message(uid, "⚙️ <b>Admin Panel:</b>", reply_markup=admin_menu())

# ================= MA'LUMOTLAR =================
@bot.message_handler(func=lambda m: m.text == "ℹ️ Kurslar haqida")
def about_courses(message):
    text = (
        "🧪 <b>A+ KIMYO | ONLINE MAKTABI KURSLARI</b>\n\n"
        "1️⃣ <b>Noldan Kimyo (Fundamental baza):</b>\n"
        "• Kimyoni 0 dan boshlovchilar uchun maxsus tizimli darslar\n"
        "• Har bir mavzu boʻyicha video-yechim va testlar\n\n"
        "2️⃣ <b>Milliy Sertifikat va Attestatsiya guruhi:</b>\n"
        "• Yuqori ball (A+, A, B) olish uchun intensiv tayyorlov\n"
        "• Oʻqituvchilar va abituriyentlar uchun maxsus baza\n"
        "• Har hafta diagnostik testlar va jonli tahlillar\n\n"
        f"📢 <b>Rasmiy kanalimiz:</b> {KANAL_USER}\n"
        "✍️ Roʻyxatdan oʻtish uchun <b>«✍️ Kursga yozilish»</b> tugmasini bosing!"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "📞 Admin bilan aloqa")
def contact_admin(message):
    text = (
        "👨‍🏫 <b>Muallif va kurs rahbari:</b> Azizbek Ibrohimov\n\n"
        f"📢 <b>Telegram kanal:</b> {KANAL_USER}\n"
        "💬 Kurslar boʻyicha savollaringiz boʻlsa, kanalimiz orqali bogʻlanishingiz mumkin."
    )
    bot.send_message(message.chat.id, text)

# ================= BEPUL DARSLIKLAR =================
@bot.message_handler(func=lambda m: m.text == "📚 Bepul darsliklar")
def show_materials(message):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT id, title FROM materials ORDER BY id DESC LIMIT 20")
    rows = c.fetchall()
    conn.close()

    if not rows:
        return bot.send_message(
            message.chat.id,
            f"📂 Hozircha botga darsliklar yuklanmagan.\nBarcha yangi PDF va video darslarni kanalimizdan topishingiz mumkin: {KANAL_USER}"
        )

    kb = InlineKeyboardMarkup(row_width=1)
    for r in rows:
        kb.add(InlineKeyboardButton(f"📥 {r[1]}", callback_data=f"mat_{r[0]}"))
    
    bot.send_message(message.chat.id, "📚 <b>Yuklab olish uchun kerakli darslik ustiga bosing:</b>", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mat_"))
def send_material(call):
    mat_id = int(call.data.split("_")[1])
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT title, file_id, file_type FROM materials WHERE id = ?", (mat_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return bot.answer_callback_query(call.id, "Fayl topilmadi!", show_alert=True)

    title, file_id, file_type = row
    caption = f"📘 <b>{title}</b>\n\n📢 {KANAL_USER}"
    if file_type == "document":
        bot.send_document(call.message.chat.id, file_id, caption=caption)
    elif file_type == "video":
        bot.send_video(call.message.chat.id, file_id, caption=caption)
    elif file_type == "photo":
        bot.send_photo(call.message.chat.id, file_id, caption=caption)
    bot.answer_callback_query(call.id)

# ================= TEST TEKSHIRISH =================
@bot.message_handler(func=lambda m: m.text == "📝 Test tekshirish")
def ask_test_code(message):
    uid = message.from_user.id
    user_states[uid] = "wait_test_input"
    text = (
        "📝 <b>Testni tekshirish uchun:</b>\n\n"
        "1️⃣ Yoki <b>Test kodini</b> yuboring (masalan: <code>1</code>)\n"
        "2️⃣ Yoki <b>Kod*javoblar</b> koʻrinishida birdan yuboring (masalan: <code>1*abcdabcd...</code>)"
    )
    bot.send_message(uid, text, reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "wait_test_input")
def process_test_input(message):
    uid = message.from_user.id
    txt = message.text.strip()

    if "*" in txt:
        parts = txt.split("*", 1)
        if not parts[0].isdigit():
            return bot.send_message(uid, "⚠️ Test kodi raqam boʻlishi kerak! Masalan: <code>1*abcd</code>")
        test_code = int(parts[0])
        user_ans = parts[1].strip().lower()
        evaluate_test(message, test_code, user_ans)
    else:
        if not txt.isdigit():
            return bot.send_message(uid, "⚠️ Iltimos, test kodini raqam bilan kiriting!")
        test_code = int(txt)
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("SELECT title, answers FROM tests WHERE test_code = ?", (test_code,))
        row = c.fetchone()
        conn.close()

        if not row:
            return bot.send_message(uid, "❌ Bunday kodli test topilmadi! Kodni tekshirib qayta yozing:")

        user_data[uid] = {"test_code": test_code}
        user_states[uid] = "wait_test_answers"
        bot.send_message(
            uid,
            f"📘 <b>Test:</b> {row[0]}\n"
            f"❓ <b>Savollar soni:</b> {len(row[1])} ta\n\n"
            f"✍️ Javoblaringizni ketma-ket harflar bilan yuboring (masalan: <code>abcdabcd...</code>):"
        )

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "wait_test_answers")
def process_test_answers(message):
    uid = message.from_user.id
    test_code = user_data[uid]["test_code"]
    user_ans = message.text.strip().lower()
    evaluate_test(message, test_code, user_ans)

def evaluate_test(message, test_code, user_ans):
    uid = message.from_user.id
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT title, answers FROM tests WHERE test_code = ?", (test_code,))
    row = c.fetchone()

    if not row:
        conn.close()
        return bot.send_message(uid, "❌ Bunday kodli test topilmadi!")

    title, correct_ans = row[0], row[1].lower()
    if len(user_ans) != len(correct_ans):
        conn.close()
        return bot.send_message(
            uid,
            f"⚠️ <b>Javoblar soni mos kelmadi!</b>\n"
            f"Testda <b>{len(correct_ans)} ta</b> savol bor, siz esa <b>{len(user_ans)} ta</b> belgi yubordingiz."
        )

    score = 0
    details = []
    for i, (u, k) in enumerate(zip(user_ans, correct_ans), start=1):
        if u == k:
            score += 1
            details.append(f"{i}. ✅")
        else:
            details.append(f"{i}. ❌ ({u.upper()})")

    total = len(correct_ans)
    percent = round((score / total) * 100, 1)

    c.execute("SELECT id FROM results WHERE user_id = ? AND test_code = ?", (uid, test_code))
    existing = c.fetchone()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not existing:
        c.execute(
            "INSERT INTO results (user_id, full_name, test_code, score, total, percent, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, message.from_user.full_name, test_code, score, total, percent, now_str)
        )
        conn.commit()
    conn.close()

    user_states.pop(uid, None)
    
    if percent >= 86:
        daraja = "🏆 A+ / A daraja (Aʼlo!)"
    elif percent >= 70:
        daraja = "🥈 B+ / B daraja (Yaxshi!)"
    elif percent >= 60:
        daraja = "🥉 C+ / C daraja (Qoniqarli)"
    else:
        daraja = "📚 Yana koʻproq oʻqish kerak!"

    detail_text = " | ".join(details[:40])
    res_msg = (
        f"📊 <b>TEST NATIJANGIZ:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Oʻquvchi:</b> {message.from_user.full_name}\n"
        f"🔢 <b>Test kodi:</b> <code>{test_code}</code>\n"
        f"📘 <b>Mavzu:</b> {title}\n"
        f"✅ <b>Toʻgʻri javoblar:</b> {score} / {total} ta (<b>{percent}%</b>)\n"
        f"🎖 <b>Koʻrsatkich:</b> {daraja}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔍 <b>Tahlil:</b>\n{detail_text}\n\n"
        f"📢 {KANAL_USER}"
    )
    bot.send_message(uid, res_msg, reply_markup=main_menu(uid))

# ================= TEST REYTINGI =================
@bot.message_handler(func=lambda m: m.text == "🏆 Test reytingi")
def ask_rating_code(message):
    uid = message.from_user.id
    user_states[uid] = "wait_rating_code"
    bot.send_message(uid, "🏆 Reytingni koʻrish uchun <b>Test kodini</b> kiriting:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "wait_rating_code")
def show_test_rating(message):
    uid = message.from_user.id
    if not message.text.isdigit():
        return bot.send_message(uid, "⚠️ Test kodini raqamda yozing!")
    
    code = int(message.text)
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT title FROM tests WHERE test_code = ?", (code,))
    t_row = c.fetchone()
    if not t_row:
        conn.close()
        return bot.send_message(uid, "❌ Bunday kodli test topilmadi!")

    c.execute(
        "SELECT full_name, score, total, percent FROM results WHERE test_code = ? ORDER BY score DESC, id ASC LIMIT 25",
        (code,)
    )
    rows = c.fetchall()
    conn.close()
    user_states.pop(uid, None)

    if not rows:
        return bot.send_message(uid, "📭 Bu testni hali hech kim ishlamagan.", reply_markup=main_menu(uid))

    medals = ["🥇", "🥈", "🥉"]
    text = f"🏆 <b>TEST #{code} REYTINGI (TOP-25)</b>\n📘 <b>{t_row[0]}</b>\n━━━━━━━━━━━━━━━━━━\n"
    for idx, r in enumerate(rows, start=1):
        m = medals[idx - 1] if idx <= 3 else f"<b>{idx}.</b>"
        text += f"{m} {r[0]} — <b>{r[1]}/{r[2]}</b> ({r[3]}%)\n"
    
    bot.send_message(uid, text, reply_markup=main_menu(uid))

# ================= KURSGA YOZILISH =================
@bot.message_handler(func=lambda m: m.text == "✍️ Kursga yozilish")
def reg_step1(message):
    uid = message.from_user.id
    user_states[uid] = "reg_name"
    bot.send_message(uid, "✍️ <b>Ism va familiyangizni kiriting:</b>", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "reg_name")
def reg_step2(message):
    uid = message.from_user.id
    user_data[uid] = {"ism": message.text}
    user_states[uid] = "reg_phone"
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True))
    kb.add(KeyboardButton("❌ Bekor qilish"))
    bot.send_message(uid, "📱 <b>Telefon raqamingizni yuboring:</b>", reply_markup=kb)

@bot.message_handler(content_types=['contact', 'text'], func=lambda m: user_states.get(m.from_user.id) == "reg_phone")
def reg_step3(message):
    uid = message.from_user.id
    if message.text == "❌ Bekor qilish":
        return cancel_action(message)
    
    phone = message.contact.phone_number if message.contact else message.text
    user_data[uid]["phone"] = phone
    user_states[uid] = "reg_receipt"

    karta = get_setting("karta", KARTA_RAQAM)
    egasi = get_setting("egasi", KARTA_EGASI)

    text = (
        f"💳 <b>Kurs uchun toʻlov rekvizitlari:</b>\n\n"
        f"Karta: <code>{karta}</code>\n"
        f"Egasi: <b>{egasi}</b>\n\n"
        f"📸 Toʻlovni amalga oshirgach, <b>toʻlov cheki rasmini</b> shu yerga yuboring:"
    )
    bot.send_message(uid, text, reply_markup=cancel_kb())

@bot.message_handler(content_types=['photo'], func=lambda m: user_states.get(m.from_user.id) == "reg_receipt")
def reg_finish(message):
    uid = message.from_user.id
    info = user_data.get(uid, {})
    photo_id = message.photo[-1].file_id
    admins = db_get_admins()

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"pay_ok_{uid}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"pay_no_{uid}")
    )

    caption = (
        f"🆕 <b>YANGI KURS ARIZASI (TOʻLOV CHEKI)</b>\n\n"
        f"👤 <b>Oʻquvchi:</b> {info.get('ism')}\n"
        f"📞 <b>Tel:</b> {info.get('phone')}\n"
        f"🔗 <b>Username:</b> @{message.from_user.username or 'yoq'}\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>"
    )

    for adm in admins:
        try:
            bot.send_photo(adm, photo_id, caption=caption, reply_markup=kb)
        except Exception:
            pass

    user_states.pop(uid, None)
    bot.send_message(
        uid,
        "✅ <b>Toʻlov cheki qabul qilindi va adminga yuborildi!</b>",
        reply_markup=main_menu(uid)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def handle_payment_decision(call):
    parts = call.data.split("_")
    action, target_uid = parts[1], int(parts[2])

    if action == "ok":
        bot.send_message(target_uid, "🎉 <b>Tabriklaymiz! Toʻlovingiz tasdiqlandi.</b>")
        bot.edit_message_caption(
            caption=call.message.caption + "\n\n✅ <b>TASDIQLANDI</b>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        bot.answer_callback_query(call.id, "Tasdiqlandi!")
    else:
        bot.send_message(target_uid, "❌ <b>Toʻlov cheki tasdiqlanmadi.</b>")
        bot.edit_message_caption(
            caption=call.message.caption + "\n\n❌ <b>RAD ETILDI</b>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        bot.answer_callback_query(call.id, "Rad etildi!")

# ================= ADMIN PANEL =================
@bot.message_handler(func=lambda m: m.text == "➕ Yangi test yaratish")
def adm_new_test(message):
    uid = message.from_user.id
    if not db_is_admin(uid):
        return
    user_states[uid] = "adm_test_title"
    bot.send_message(uid, "📘 <b>Yangi test nomini yozing:</b>", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "adm_test_title")
def adm_new_test_keys(message):
    uid = message.from_user.id
    user_data[uid] = {"title": message.text}
    user_states[uid] = "adm_test_keys"
    bot.send_message(uid, "🔑 <b>Toʻgʻri javoblar kalitini ketma-ket yozing</b> (masalan: <code>abcdabcd...</code>):")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "adm_test_keys")
def adm_save_test(message):
    uid = message.from_user.id
    keys = message.text.strip().lower().replace(" ", "")
    title = user_data[uid]["title"]

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO tests (title, answers, created_at) VALUES (?, ?, ?)",
        (title, keys, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    code = c.lastrowid
    conn.commit()
    conn.close()

    user_states.pop(uid, None)
    bot.send_message(
        uid,
        f"✅ <b>Test bazaga saqlandi!</b>\n🔢 <b>Test kodi:</b> <code>{code}</code>",
        reply_markup=admin_menu()
    )

@bot.message_handler(func=lambda m: m.text == "📋 Testlar roʻyxati")
def adm_list_tests(message):
    uid = message.from_user.id
    if not db_is_admin(uid):
        return
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT test_code, title, length(answers), created_at FROM tests ORDER BY test_code DESC LIMIT 15")
    rows = c.fetchall()
    conn.close()

    if not rows:
        return bot.send_message(uid, "📭 Hozircha testlar yoʻq.")

    text = "📋 <b>Oxirgi testlar:</b>\n\n"
    for r in rows:
        text += f"🔹 Kod: <code>{r[0]}</code> | <b>{r[1]}</b> ({r[2]} ta)\n"
    bot.send_message(uid, text)

@bot.message_handler(func=lambda m: m.text == "🗑 Testni oʻchirish")
def adm_del_test_ask(message):
    uid = message.from_user.id
    if not db_is_admin(uid):
        return
    user_states[uid] = "adm_del_test"
    bot.send_message(uid, "🗑 Oʻchiriladigan <b>Test kodini</b> yozing:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "adm_del_test")
def adm_del_test_confirm(message):
    uid = message.from_user.id
    if not message.text.isdigit():
        return bot.send_message(uid, "⚠️ Faqat raqam yozing!")
    code = int(message.text)
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM tests WHERE test_code = ?", (code,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    user_states.pop(uid, None)
    bot.send_message(uid, f"✅ Test oʻchirildi!" if deleted else "❌ Topilmadi.", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📥 Darslik (PDF/Video) qoʻshish")
def adm_add_mat_start(message):
    uid = message.from_user.id
    if not db_is_admin(uid):
        return
    user_states[uid] = "adm_mat_title"
    bot.send_message(uid, "📘 <b>Darslik nomini yozing:</b>", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "adm_mat_title")
def adm_add_mat_file(message):
    uid = message.from_user.id
    user_data[uid] = {"mat_title": message.text}
    user_states[uid] = "adm_mat_file"
    bot.send_message(uid, "📎 Endi <b>PDF fayl, Video yoki Rasmni</b> yuboring:")

@bot.message_handler(content_types=['document', 'video', 'photo'], func=lambda m: user_states.get(m.from_user.id) == "adm_mat_file")
def adm_save_mat(message):
    uid = message.from_user.id
    title = user_data[uid]["mat_title"]
    
    if message.document:
        file_id, ftype = message.document.file_id, "document"
    elif message.video:
        file_id, ftype = message.video.file_id, "video"
    else:
        file_id, ftype = message.photo[-1].file_id, "photo"

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO materials (title, file_id, file_type, added_at) VALUES (?, ?, ?, ?)",
        (title, file_id, ftype, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()
    conn.close()

    user_states.pop(uid, None)
    bot.send_message(uid, f"✅ <b>«{title}»</b> qoʻshildi!", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "💳 Karta raqamni oʻzgartirish")
def adm_change_card(message):
    uid = message.from_user.id
    if not db_is_admin(uid):
        return
    user_states[uid] = "adm_card"
    bot.send_message(uid, "💳 Karta va egasini yozing (masalan: <code>8600... | Ism F.</code>):", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "adm_card")
def adm_save_card(message):
    uid = message.from_user.id
    if "|" in message.text:
        karta, egasi = [x.strip() for x in message.text.split("|", 1)]
        set_setting("karta", karta)
        set_setting("egasi", egasi)
        user_states.pop(uid, None)
        bot.send_message(uid, f"✅ Karta yangilandi!", reply_markup=admin_menu())
    else:
        bot.send_message(uid, "⚠️ Oʻrtasiga <b>|</b> qoʻyib yozing!")

@bot.message_handler(func=lambda m: m.text == "📊 Statistika")
def adm_stats(message):
    uid = message.from_user.id
    if not db_is_admin(uid):
        return
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    u_cnt = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM tests")
    t_cnt = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM results")
    r_cnt = c.fetchone()[0]
    conn.close()
    bot.send_message(uid, f"📊 Oʻquvchilar: <b>{u_cnt}</b>\nTestlar: <b>{t_cnt}</b>\nIshlanmalar: <b>{r_cnt}</b>")

@bot.message_handler(func=lambda m: m.text == "📢 Hammaga xabar (Rassilka)")
def adm_broadcast_ask(message):
    uid = message.from_user.id
    if not db_is_admin(uid):
        return
    user_states[uid] = "adm_broadcast"
    bot.send_message(uid, "📢 Hammaga yuboriladigan xabarni yuboring:", reply_markup=cancel_kb())

@bot.message_handler(content_types=['text', 'photo', 'video', 'document'], func=lambda m: user_states.get(m.from_user.id) == "adm_broadcast")
def adm_broadcast_send(message):
    uid = message.from_user.id
    if message.text == "❌ Bekor qilish":
        return cancel_action(message)

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [r[0] for r in c.fetchall()]
    conn.close()

    user_states.pop(uid, None)
    bot.send_message(uid, f"⏳ Yuborilmoqda...", reply_markup=admin_menu())

    sent = 0
    for u in users:
        try:
            bot.copy_message(u, message.chat.id, message.message_id)
            sent += 1
        except Exception:
            pass

    bot.send_message(uid, f"✅ {sent} ta oʻquvchiga yetkazildi!")

# ================= WEB SERVER =================
@app.route("/")
def index():
    return "Bot 24/7 ishlamoqda!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web, daemon=True).start()
    bot.remove_webhook()
    print("Bot ishga tushdi...")
    bot.infinity_polling(skip_pending=True)
