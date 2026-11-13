import os
import json
import sqlite3
import threading
from datetime import datetime
from flask import Flask, send_file
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo
)

# Hisobot kutubxonalari
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# ================= SOZLAMALAR =================
BOT_TOKEN = "8636730483:AAFCHNjwvmaLZuRk3fd3sOIbN2QMYd-h_4g"
ADMIN_PAROL = "kimyo2026"
ADMIN_LICHKA = "@onlyibrohimov"
KANAL_USER = "@kimyo_sertifkat_uchun"
KARTA_RAQAM = "9860 3501 4209 7954"
KARTA_EGASI = "Azizbek Ibrohimov"

RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://e-kimyo-kurs-bot.onrender.com")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

user_states = {}
user_data = {}

# ================= MA'LUMOTLAR BAZASI =================
def init_db():
    with sqlite3.connect("database.db") as conn:
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
                raw_correct INTEGER,
                rash_score REAL,
                written_score REAL DEFAULT 0,
                percent REAL,
                daraja TEXT,
                checked_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS sample_lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                file_id TEXT,
                file_type TEXT,
                added_at TEXT
            )
        """)
        conn.commit()

def db_add_user(user_id, full_name, username):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO users (user_id, full_name, username, joined_at) VALUES (?, ?, ?, ?)",
            (user_id, full_name, username or "", datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        conn.commit()

def db_is_admin(user_id):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return bool(row and row[0] == 1)

def db_set_admin(user_id):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))
        conn.commit()

def db_get_admins():
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE is_admin = 1")
        return [r[0] for r in c.fetchall()]

# ================= MENYULAR =================
def main_menu(user_id):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    titr_solve_btn = KeyboardButton(
        text="📊 Elektron Titr (40 talik MS)",
        web_app=WebAppInfo(url=f"{RENDER_URL}/titr?mode=solve")
    )
    kb.add(titr_solve_btn)
    kb.add(
        KeyboardButton("🎬 Namuna darslar"),
        KeyboardButton("🏆 Umumiy Reyting"),
        KeyboardButton("👤 Shaxsiy kabinet"),
        KeyboardButton("✍️ Kursga yozilish"),
        KeyboardButton("📞 Admin bilan aloqa")
    )
    if db_is_admin(user_id):
        kb.add(KeyboardButton("⚙️ Admin Panel"))
    return kb

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    titr_create_btn = KeyboardButton(
        text="➕ Titr orqali Test Yaratish (40 ta)",
        web_app=WebAppInfo(url=f"{RENDER_URL}/titr?mode=create")
    )
    kb.add(titr_create_btn)
    kb.add(
        KeyboardButton("🎬 Namuna dars qoʻshish"),
        KeyboardButton("📑 Vazifa nazorati (Qilgan/Qilmagan)"),
        KeyboardButton("📊 Elektron Jadval (Excel/Word/PDF)"),
        KeyboardButton("📋 Testlar roʻyxati"),
        KeyboardButton("🗑 Testni oʻchirish"),
        KeyboardButton("📢 Hammaga xabar"),
        KeyboardButton("🔙 Asosiy menyu")
    )
    return kb

def cancel_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("❌ Bekor qilish"))
    return kb

# ================= BUYRUQLAR =================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.from_user.id
    user_states.pop(uid, None)
    db_add_user(uid, message.from_user.full_name, message.from_user.username)
    
    text = (
        f"Assalomu alaykum, <b>{message.from_user.full_name}</b>! 👋\n\n"
        f"🧪 <b>A+ Kimyo | Online Maktabi</b> platformasiga xush kelibsiz!\n\n"
        f"🔹 <b>📊 Elektron Titr:</b> 40 talik Milliy Sertifikat testini topshirish\n"
        f"🔹 <b>🎬 Namuna darslar:</b> Bepul video darslar va qoʻllanmalar\n"
        f"🔹 <b>🏆 Reyting:</b> Oʻquvchilarning umumiy natijalari\n\n"
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
        bot.send_message(uid, "✅ <b>Admin huquqi faollashtirildi!</b>", reply_markup=admin_menu())
    elif db_is_admin(uid):
        bot.send_message(uid, "⚙️ <b>Admin Panel:</b>", reply_markup=admin_menu())
    else:
        bot.send_message(uid, "🔒 Parolni kiriting: <code>/admin kimyo2026</code>")

@bot.message_handler(func=lambda m: m.text in ["❌ Bekor qilish", "🔙 Asosiy menyu"])
def cancel_action(message):
    uid = message.from_user.id
    user_states.pop(uid, None)
    bot.send_message(uid, "🏠 Asosiy menyu:", reply_markup=main_menu(uid))

@bot.message_handler(func=lambda m: m.text == "⚙️ Admin Panel")
def open_admin(message):
    uid = message.from_user.id
    if db_is_admin(uid):
        bot.send_message(uid, "⚙️ <b>Admin Panel:</b>", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📞 Admin bilan aloqa")
def contact_admin(message):
    text = (
        f"👨‍🏫 <b>Muallif va kurs rahbari:</b> Azizbek Ibrohimov\n\n"
        f"💬 <b>Shaxsiy lichka:</b> {ADMIN_LICHKA}\n"
        f"📢 <b>Rasmiy Telegram kanal:</b> {KANAL_USER}\n\n"
        f"Savollaringiz boʻlsa, toʻgʻridan-toʻgʻri {ADMIN_LICHKA} ga yozishingiz mumkin!"
    )
    bot.send_message(message.chat.id, text)

# ================= SHAXSIY KABINET (YANGI IDEYA) =================
@bot.message_handler(func=lambda m: m.text == "👤 Shaxsiy kabinet")
def user_profile(message):
    uid = message.from_user.id
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name, phone, joined_at FROM users WHERE user_id = ?", (uid,))
        u = c.fetchone()
        c.execute("SELECT COUNT(*), COALESCE(AVG(rash_score), 0), COALESCE(MAX(rash_score), 0) FROM results WHERE user_id = ?", (uid,))
        stats = c.fetchone()

    text = (
        f"👤 <b>SHAXSIY KABINET</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📛 <b>Ism:</b> {u[0] if u else message.from_user.full_name}\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"📞 <b>Tel:</b> {u[1] if u and u[1] else 'Kiritilmagan'}\n"
        f"📅 <b>Aʼzo boʻlgan sana:</b> {u[2] if u else '-'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Ishlangan testlar:</b> {stats[0]} ta\n"
        f"📈 <b>Oʻrtacha ball:</b> {round(stats[1], 1)} ball\n"
        f"🏆 <b>Eng yuqori natija:</b> {round(stats[2], 1)} ball"
    )
    bot.send_message(uid, text)

# ================= NAMUNA DARSLAR (O'QUVCHILAR UCHUN) =================
@bot.message_handler(func=lambda m: m.text == "🎬 Namuna darslar")
def show_sample_lessons(message):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT id, title FROM sample_lessons ORDER BY id DESC LIMIT 20")
        rows = c.fetchall()

    if not rows:
        return bot.send_message(
            message.chat.id,
            f"🎬 Hozircha botga namuna darslar yuklanmagan.\nBarcha darslarni kanalimizda koʻrishingiz mumkin: {KANAL_USER}"
        )

    kb = InlineKeyboardMarkup(row_width=1)
    for r in rows:
        kb.add(InlineKeyboardButton(f"▶️ {r[1]}", callback_data=f"lesson_{r[0]}"))
    
    bot.send_message(message.chat.id, "🎬 <b>Koʻrish yoki yuklab olish uchun namuna darsni tanlang:</b>", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("lesson_"))
def send_sample_lesson(call):
    lid = int(call.data.split("_")[1])
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT title, description, file_id, file_type FROM sample_lessons WHERE id = ?", (lid,))
        row = c.fetchone()

    if not row:
        return bot.answer_callback_query(call.id, "Dars topilmadi!", show_alert=True)

    title, desc, file_id, ftype = row
    caption = f"🎬 <b>{title}</b>\n\n{desc}\n\n👨‍🏫 {ADMIN_LICHKA} | 📢 {KANAL_USER}"
    
    if ftype == "video":
        bot.send_video(call.message.chat.id, file_id, caption=caption)
    elif ftype == "document":
        bot.send_document(call.message.chat.id, file_id, caption=caption)
    elif ftype == "photo":
        bot.send_photo(call.message.chat.id, file_id, caption=caption)
    bot.answer_callback_query(call.id)

# ================= ADMIN: NAMUNA DARS QO'SHISH =================
@bot.message_handler(func=lambda m: m.text == "🎬 Namuna dars qoʻshish")
def adm_add_lesson_1(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    user_states[uid] = "les_title"
    bot.send_message(uid, "🎬 <b>Namuna dars nomini kiriting</b> (masalan: <i>1-dars: Atom tuzilishi</i>):", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "les_title")
def adm_add_lesson_2(message):
    uid = message.from_user.id
    user_data[uid] = {"title": message.text}
    user_states[uid] = "les_desc"
    bot.send_message(uid, "📝 <b>Dars haqida qisqacha izoh yozing</b> (yoki <code>-</code> belgisini yuboring):")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "les_desc")
def adm_add_lesson_3(message):
    uid = message.from_user.id
    user_data[uid]["desc"] = "" if message.text == "-" else message.text
    user_states[uid] = "les_file"
    bot.send_message(uid, "📎 Endi <b>Video dars, PDF fayl yoki Rasmni</b> yuboring:")

@bot.message_handler(content_types=['video', 'document', 'photo'], func=lambda m: user_states.get(m.from_user.id) == "les_file")
def adm_save_lesson(message):
    uid = message.from_user.id
    info = user_data[uid]
    
    if message.video:
        fid, ftype = message.video.file_id, "video"
    elif message.document:
        fid, ftype = message.document.file_id, "document"
    else:
        fid, ftype = message.photo[-1].file_id, "photo"

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO sample_lessons (title, description, file_id, file_type, added_at) VALUES (?, ?, ?, ?, ?)",
            (info["title"], info["desc"], fid, ftype, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        conn.commit()

    user_states.pop(uid, None)
    bot.send_message(uid, f"✅ <b>«{info['title']}»</b> namuna darslar boʻlimiga qoʻshildi!", reply_markup=admin_menu())

# ================= WEB APP (40 TALIK TITR) QABUL QILISH =================
@bot.message_handler(content_types=['web_app_data'])
def handle_webapp_data(message):
    uid = message.from_user.id
    payload = json.loads(message.web_app_data.data)
    
    mode = payload.get("mode")
    meta = payload.get("meta")
    answers = payload.get("answers")  # 40 talik massiv

    # 1. ADMIN TEST YARATGANDA
    if mode == "create":
        if not db_is_admin(uid):
            return bot.send_message(uid, "⚠️ Siz admin emassiz!")
        
        stored_keys = json.dumps(answers)
        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO tests (title, answers, created_at) VALUES (?, ?, ?)",
                (meta, stored_keys, datetime.now().strftime("%Y-%m-%d %H:%M"))
            )
            code = c.lastrowid
            conn.commit()

        bot.send_message(
            uid,
            f"✅ <b>Yangi 40 talik MS Testi yaratildi!</b>\n\n"
            f"🔢 <b>Test kodi:</b> <code>{code}</code>\n"
            f"📘 <b>Mavzu:</b> {meta}\n\n"
            f"Oʻquvchilar endi <b>«📊 Elektron Titr»</b> orqali <code>{code}</code> kodi bilan javob yuborishlari mumkin!",
            reply_markup=admin_menu()
        )

    # 2. O'QUVCHI TEST TOPSHIRGANDA
    elif mode == "solve":
        if not meta.isdigit():
            return bot.send_message(uid, "⚠️ Test kodi faqat raqam boʻlishi kerak!", reply_markup=main_menu(uid))
        
        code = int(meta)
        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute("SELECT title, answers FROM tests WHERE test_code = ?", (code,))
            row = c.fetchone()

        if not row:
            return bot.send_message(uid, f"❌ <code>{code}</code>-kodli test topilmadi!", reply_markup=main_menu(uid))

        title = row[0]
        correct_keys = json.loads(row[1])

        raw_correct = 0
        rash_score = 0.0
        details = []

        for i in range(40):
            u = str(answers[i]).strip().lower()
            k = str(correct_keys[i]).strip().lower()
            q_num = i + 1

            # 40 talik ball taqsimoti (1-32: 1.5, 33-35: 2.2, 36-40: 4.08 -> Jami 75 ball)
            if q_num <= 32:
                weight = 1.5
            elif q_num <= 35:
                weight = 2.2
            else:
                weight = 4.08

            if u != "" and u == k:
                raw_correct += 1
                rash_score += weight
                details.append(f"{q_num}.✅")
            else:
                details.append(f"{q_num}.❌")

        rash_score = round(rash_score, 2)
        percent = round((rash_score / 75.0) * 100, 1)

        if rash_score >= 70: daraja = "🏆 A+ daraja"
        elif rash_score >= 65: daraja = "🥇 A daraja"
        elif rash_score >= 60: daraja = "🥈 B+ daraja"
        elif rash_score >= 55: daraja = "🥈 B daraja"
        elif rash_score >= 50: daraja = "🥉 C+ daraja"
        elif rash_score >= 46: daraja = "🥉 C daraja"
        else: daraja = "📚 Sertifikat baliga yetmadi"

        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM results WHERE user_id = ? AND test_code = ?", (uid, code))
            if not c.fetchone():
                c.execute(
                    "INSERT INTO results (user_id, full_name, test_code, raw_correct, rash_score, percent, daraja, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (uid, message.from_user.full_name, code, raw_correct, rash_score, percent, daraja, datetime.now().strftime("%Y-%m-%d %H:%M"))
                )
                conn.commit()

        res_text = (
            f"📊 <b>TEST NATIJANGIZ (40 TALIK)</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Oʻquvchi:</b> {message.from_user.full_name}\n"
            f"🔢 <b>Test kodi:</b> <code>{code}</code> ({title})\n"
            f"✅ <b>Toʻgʻri javoblar:</b> {raw_correct} / 40 ta\n"
            f"📈 <b>Test bali:</b> <b>{rash_score} ball</b> ({percent}%)\n"
            f"🎖 <b>Daraja:</b> <b>{daraja}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n" + " | ".join(details)
        )
        bot.send_message(uid, res_text)

        # O'quvchidan yozma ishni rasm holatda yuborishni so'raymiz!
        user_data[uid] = {"test_code": code, "title": title, "score": rash_score}
        user_states[uid] = "wait_written_photo"
        
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("⏭ Yozma ish yoʻq (Oʻtkazib yuborish)"))
        bot.send_message(
            uid,
            "📸 <b>Endi yozma ish (yechimlaringiz) rasmini shu yerga tashlang!</b>\n"
            "Ustoz Azizbek Ibrohimov yechimingizni koʻrib tekshiradilar:",
            reply_markup=kb
        )

# ================= YOZMA ISH RASMINI QABUL QILISH VA ADMINGA YUBORISH =================
@bot.message_handler(func=lambda m: m.text == "⏭ Yozma ish yoʻq (Oʻtkazib yuborish)")
def skip_written_photo(message):
    uid = message.from_user.id
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Test yakunlandi! Asosiy menyu:", reply_markup=main_menu(uid))

@bot.message_handler(content_types=['photo'], func=lambda m: user_states.get(m.from_user.id) == "wait_written_photo")
def receive_written_photo(message):
    uid = message.from_user.id
    info = user_data.get(uid, {})
    photo_id = message.photo[-1].file_id

    caption = (
        f"📝 <b>YANGI YOZMA ISH KELDI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Oʻquvchi:</b> {message.from_user.full_name}\n"
        f"🔗 <b>Username:</b> @{message.from_user.username or 'yoq'}\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"🔢 <b>Test kodi:</b> <code>{info.get('test_code')}</code> ({info.get('title')})\n"
        f"📈 <b>Test bali:</b> {info.get('score')} ball"
    )

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✍️ Yozma ish uchun ball qoʻshish", callback_data=f"addw_{uid}_{info.get('test_code')}"))

    for adm in db_get_admins():
        try:
            bot.send_photo(adm, photo_id, caption=caption, reply_markup=kb)
        except Exception:
            pass

    user_states.pop(uid, None)
    bot.send_message(
        uid,
        "✅ <b>Yozma ish rasmi qabul qilindi va ustozga yuborildi!</b>",
        reply_markup=main_menu(uid)
    )

# Admin yozma ishga qo'shimcha ball berishi (Yangi ideya)
@bot.callback_query_handler(func=lambda call: call.data.startswith("addw_"))
def ask_written_bonus(call):
    _, target_uid, t_code = call.data.split("_")
    adm_id = call.from_user.id
    user_data[adm_id] = {"target_uid": int(target_uid), "t_code": int(t_code)}
    user_states[adm_id] = "adm_give_w_score"
    bot.send_message(adm_id, f"✍️ Oʻquvchi (ID: <code>{target_uid}</code>) ning yozma ishi uchun necha ball qoʻshasiz? (Raqam yozing, masalan: <code>5</code>):")
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "adm_give_w_score")
def save_written_bonus(message):
    adm_id = message.from_user.id
    try:
        bonus = float(message.text.replace(",", "."))
    except ValueError:
        return bot.send_message(adm_id, "⚠️ Iltimos, faqat raqam kiriting (masalan: 4.5):")

    info = user_data[adm_id]
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE results SET written_score = ?, rash_score = rash_score + ? WHERE user_id = ? AND test_code = ?",
            (bonus, bonus, info["target_uid"], info["t_code"])
        )
        conn.commit()

    user_states.pop(adm_id, None)
    bot.send_message(adm_id, f"✅ Yozma ish uchun <b>+{bonus} ball</b> qoʻshildi!", reply_markup=admin_menu())
    try:
        bot.send_message(info["target_uid"], f"🎉 <b>Ustoz yozma ishingizni tekshirdi va +{bonus} ball qoʻshdi!</b>")
    except Exception:
        pass

# ================= REYTING VA HISOBOTLAR =================
@bot.message_handler(func=lambda m: m.text == "🏆 Umumiy Reyting")
def show_global_rating(message):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name, rash_score, raw_correct, daraja FROM results ORDER BY rash_score DESC LIMIT 20")
        rows = c.fetchall()

    if not rows:
        return bot.send_message(message.chat.id, "📭 Hali hech kim test topshirmagan.")

    medals = ["🥇", "🥈", "🥉"]
    text = "🏆 <b>A+ KIMYO | TOP-20 REYTING</b>\n━━━━━━━━━━━━━━━━━━\n"
    for idx, r in enumerate(rows, 1):
        m = medals[idx - 1] if idx <= 3 else f"<b>{idx}.</b>"
        text += f"{m} {r[0]} — <b>{round(r[1], 2)} ball</b> ({r[2]}/40) | {r[3]}\n"
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "📑 Vazifa nazorati (Qilgan/Qilmagan)")
def ask_check_test_code(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    user_states[uid] = "check_hw_code"
    bot.send_message(uid, "🔢 Qaysi test boʻyicha vazifa qilgan va qilmaganlarni koʻrmoqchisiz? <b>Test kodini</b> kiriting:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "check_hw_code")
def show_hw_status(message):
    uid = message.from_user.id
    if not message.text.isdigit(): return bot.send_message(uid, "⚠️ Raqam kiriting!")
    code = int(message.text)

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT title FROM tests WHERE test_code = ?", (code,))
        t = c.fetchone()
        if not t: return bot.send_message(uid, "❌ Test topilmadi!")

        c.execute("SELECT user_id, full_name, rash_score, raw_correct FROM results WHERE test_code = ? ORDER BY rash_score DESC", (code,))
        done_rows = c.fetchall()
        done_ids = {r[0] for r in done_rows}

        c.execute("SELECT user_id, full_name, phone FROM users WHERE is_admin = 0")
        all_users = c.fetchall()

    user_states.pop(uid, None)
    not_done = [u for u in all_users if u[0] not in done_ids]

    text = f"📑 <b>VAZIFA NAZORATI: Test #{code} ({t[0]})</b>\n━━━━━━━━━━━━━━━━━━\n"
    text += f"✅ <b>Vazifani bajarganlar ({len(done_rows)} ta):</b>\n"
    for r in done_rows:
        text += f"  • {r[1]} — <b>{round(r[2], 2)} ball</b> ({r[3]}/40)\n"

    text += f"\n❌ <b>Vazifa qilmaganlar ({len(not_done)} ta):</b>\n"
    for u in not_done:
        text += f"  • {u[1]} (Tel: {u[2] or 'yoʻq'})\n"

    bot.send_message(uid, text, reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📊 Elektron Jadval (Excel/Word/PDF)")
def export_menu(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return

    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("📊 Excel (.xlsx)", callback_data="exp_excel"),
        InlineKeyboardButton("📄 Word (.docx)", callback_data="exp_word"),
        InlineKeyboardButton("📑 PDF (.pdf)", callback_data="exp_pdf")
    )
    bot.send_message(uid, "📥 <b>Oʻquvchilar hisobotini qaysi formatda yuklab olasiz?</b>", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("exp_"))
def handle_export(call):
    uid = call.from_user.id
    if not db_is_admin(uid): return
    fmt = call.data.split("_")[1]

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("""
            SELECT u.full_name, u.phone, COALESCE(r.test_code, 0),
                   COALESCE(r.raw_correct, 0), COALESCE(r.rash_score, 0),
                   COALESCE(r.daraja, 'Vazifa qilinmagan'), COALESCE(r.checked_at, '-')
            FROM users u
            LEFT JOIN results r ON u.user_id = r.user_id
            WHERE u.is_admin = 0
            ORDER BY r.rash_score DESC
        """)
        rows = c.fetchall()

    if fmt == "excel":
        filename = "A_Plus_Kimyo_Hisobot.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Reyting va Vazifalar"
        ws.append(["№", "O'quvchi F.I.Sh.", "Telefon", "Test Kodi", "To'g'ri Javob", "Umumiy Ball", "Holati", "Vaqti"])
        for idx, r in enumerate(rows, 1):
            holat = "Bajarilgan (" + r[5] + ")" if r[2] != 0 else "❌ Qilinmagan"
            ws.append([idx, r[0], r[1], r[2] or "-", f"{r[3]}/40" if r[2] else "-", round(r[4], 2), holat, r[6]])
        wb.save(filename)
        with open(filename, "rb") as f:
            bot.send_document(uid, f, caption="📊 <b>Excel elektron jadval</b>")

    elif fmt == "word":
        filename = "A_Plus_Kimyo_Hisobot.docx"
        doc = Document()
        doc.add_heading("A+ KIMYO | O'QUVCHILAR REYTINGI", 0)
        table = doc.add_table(rows=1, cols=5)
        table.style = 'Table Grid'
        hdr = table.rows[0].cells
        hdr[0].text = "№"
        hdr[1].text = "F.I.Sh."
        hdr[2].text = "To'g'ri"
        hdr[3].text = "Ball"
        hdr[4].text = "Holati"
        for idx, r in enumerate(rows, 1):
            rc = table.add_row().cells
            rc[0].text = str(idx)
            rc[1].text = str(r[0])
            rc[2].text = f"{r[3]}/40" if r[2] else "-"
            rc[3].text = str(round(r[4], 2))
            rc[4].text = "Bajarilgan" if r[2] != 0 else "Qilinmagan"
        doc.save(filename)
        with open(filename, "rb") as f:
            bot.send_document(uid, f, caption="📄 <b>Word hujjat</b>")

    elif fmt == "pdf":
        filename = "A_Plus_Kimyo_Hisobot.pdf"
        c_pdf = canvas.Canvas(filename, pagesize=letter)
        c_pdf.drawString(50, 750, "A+ KIMYO | O'QUVCHILAR REYTINGI")
        y = 720
        for idx, r in enumerate(rows[:32], 1):
            status = "Bajarilgan" if r[2] != 0 else "Qilinmagan"
            c_pdf.drawString(50, y, f"{idx}. {r[0]} | Ball: {round(r[4], 2)} | {status}")
            y -= 20
        c_pdf.save()
        with open(filename, "rb") as f:
            bot.send_document(uid, f, caption="📑 <b>PDF fayl</b>")

    bot.answer_callback_query(call.id, "Tayyor!")

# ================= KURSGA YOZILISH =================
@bot.message_handler(func=lambda m: m.text == "✍️ Kursga yozilish")
def reg_1(message):
    uid = message.from_user.id
    user_states[uid] = "reg_name"
    bot.send_message(uid, "✍️ Ism va familiyangizni kiriting:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "reg_name")
def reg_2(message):
    uid = message.from_user.id
    user_data[uid] = {"ism": message.text}
    user_states[uid] = "reg_phone"
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True), KeyboardButton("❌ Bekor qilish"))
    bot.send_message(uid, "📱 Telefon raqamingizni yuboring:", reply_markup=kb)

@bot.message_handler(content_types=['contact', 'text'], func=lambda m: user_states.get(m.from_user.id) == "reg_phone")
def reg_3(message):
    uid = message.from_user.id
    if message.text == "❌ Bekor qilish": return cancel_action(message)
    phone = message.contact.phone_number if message.contact else message.text
    user_data[uid]["phone"] = phone
    user_states[uid] = "reg_receipt"

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET full_name = ?, phone = ? WHERE user_id = ?", (user_data[uid]["ism"], phone, uid))
        conn.commit()

    pay_text = (
        f"💳 <b>Toʻlov rekvizitlari:</b>\n"
        f"🔹 <b>Karta:</b> <code>9860350142097954</code> ({KARTA_EGASI})\n\n"
        f"📸 Toʻlovni qilib, <b>chek rasmini</b> shu yerga tashlang:"
    )
    bot.send_message(uid, pay_text, reply_markup=cancel_kb())

@bot.message_handler(content_types=['photo'], func=lambda m: user_states.get(m.from_user.id) == "reg_receipt")
def reg_done(message):
    uid = message.from_user.id
    info = user_data.get(uid, {})
    photo = message.photo[-1].file_id
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"pay_ok_{uid}"), InlineKeyboardButton("❌ Rad etish", callback_data=f"pay_no_{uid}"))
    caption = f"🆕 <b>YANGI TOʻLOV CHEKI</b>\n👤 Ism: {info.get('ism')}\n📞 Tel: {info.get('phone')}\n🆔 ID: <code>{uid}</code>"
    for adm in db_get_admins():
        try: bot.send_photo(adm, photo, caption=caption, reply_markup=kb)
        except Exception: pass
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Chek yuborildi! Tasdiqlangach xabar keladi.", reply_markup=main_menu(uid))

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def pay_decision(call):
    _, act, target = call.data.split("_")
    target = int(target)
    if act == "ok":
        bot.send_message(target, "🎉 <b>Tabriklaymiz! Toʻlovingiz tasdiqlandi!</b>")
        bot.edit_message_caption(caption=call.message.caption + "\n\n✅ <b>TASDIQLANDI</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
    else:
        bot.send_message(target, "❌ <b>Toʻlov cheki tasdiqlanmadi.</b>")
        bot.edit_message_caption(caption=call.message.caption + "\n\n❌ <b>RAD ETILDI</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
    bot.answer_callback_query(call.id)

# Admin ro'yxat / o'chirish / rassilka
@bot.message_handler(func=lambda m: m.text == "📋 Testlar roʻyxati")
def list_tests(message):
    if not db_is_admin(message.from_user.id): return
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT test_code, title, created_at FROM tests ORDER BY test_code DESC LIMIT 15")
        rows = c.fetchall()
    if not rows: return bot.send_message(message.chat.id, "📭 Testlar yoʻq.")
    bot.send_message(message.chat.id, "📋 <b>Testlar:</b>\n" + "\n".join([f"🔹 Kod: <code>{r[0]}</code> — {r[1]}" for r in rows]))

@bot.message_handler(func=lambda m: m.text == "🗑 Testni oʻchirish")
def del_test(message):
    if not db_is_admin(message.from_user.id): return
    user_states[message.from_user.id] = "del_t"
    bot.send_message(message.chat.id, "🗑 Oʻchiriladigan test kodini yuboring:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "del_t")
def del_test_do(message):
    uid = message.from_user.id
    if not message.text.isdigit(): return bot.send_message(uid, "Faqat raqam!")
    code = int(message.text)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("DELETE FROM tests WHERE test_code = ?", (code,))
        conn.commit()
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Oʻchirildi!", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📢 Hammaga xabar")
def broadcast(message):
    if not db_is_admin(message.from_user.id): return
    user_states[message.from_user.id] = "broad"
    bot.send_message(message.chat.id, "📢 Hammaga yuboriladigan xabarni kiriting:", reply_markup=cancel_kb())

@bot.message_handler(content_types=['text', 'photo', 'video', 'document'], func=lambda m: user_states.get(m.from_user.id) == "broad")
def broadcast_send(message):
    uid = message.from_user.id
    if message.text == "❌ Bekor qilish": return cancel_action(message)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        users = [r[0] for r in c.fetchall()]
    user_states.pop(uid, None)
    sent = 0
    for u in users:
        try: bot.copy_message(u, message.chat.id, message.message_id); sent += 1
        except Exception: pass
    bot.send_message(uid, f"✅ {sent} ta oʻquvchiga yuborildi!", reply_markup=admin_menu())

# ================= FLASK SERVER =================
@app.route("/")
def index():
    return "A+ Kimyo Bot 24/7 ishlamoqda!"

@app.route("/titr")
def serve_titr():
    return send_file("titr.html")

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web, daemon=True).start()
    bot.remove_webhook()
    print("Bot ishga tushdi...")
    bot.infinity_polling(none_stop=True, interval=0, timeout=20)
    
