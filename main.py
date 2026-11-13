import os
import json
import random
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

# Hisobot va Sertifikat kutubxonalari
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw, ImageFont

# ================= SOZLAMALAR =================
BOT_TOKEN = "8636730483:AAFCHNjwvmaLZuRk3fd3sOIbN2QMYd-h_4g"
ADMIN_PAROL = "kimyo2026"
ADMIN_LICHKA = "@onlyibrohimov"
KANAL_USER = "@kimyo_sertifkat_uchun"
KANAL_LINK = "https://t.me/kimyo_sertifkat_uchun"
KARTA_RAQAM = "9860 3501 4209 7954"
KARTA_EGASI = "Azizbek Ibrohimov"

RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://e-kimyo-kurs-bot.onrender.com")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

user_states = {}
user_data = {}

# ================= KIMYOVIY VIKTORINA VA LUG'AT BAZASI =================
QUIZ_QUESTIONS = [
    {"q": "Sulfat kislotaning molekulyar formulasi qaysi?", "opts": ["H2SO4", "H2SO3", "H2S", "HNO3"], "ans": "H2SO4"},
    {"q": "Kaliy permanganatning formulasi qaysi?", "opts": ["KMnO4", "K2MnO4", "MnO2", "KClO3"], "ans": "KMnO4"},
    {"q": "Oltinning kimyoviy belgisi nima?", "opts": ["Au", "Ag", "Fe", "Cu"], "ans": "Au"},
    {"q": "Avogadro doimiysi nechaga teng?", "opts": ["6.02×10²³", "22.4", "8.31", "1.6×10⁻¹⁹"], "ans": "6.02×10²³"},
    {"q": "Eng yengil gaz qaysi?", "opts": ["Vodorod (H2)", "Geliy (He)", "Azot (N2)", "Kislorod (O2)"], "ans": "Vodorod (H2)"},
    {"q": "Metanning formulasi qaysi?", "opts": ["CH4", "C2H6", "C2H4", "C2H2"], "ans": "CH4"},
    {"q": "Normal sharoitda 1 mol gaz qancha hajm egallaydi?", "opts": ["22.4 L", "24.0 L", "11.2 L", "44.8 L"], "ans": "22.4 L"},
    {"q": "Osh tuzining kimyoviy nomi nima?", "opts": ["Natriy xlorid", "Kaliy xlorid", "Natriy karbonat", "Kalsiy xlorid"], "ans": "Natriy xlorid"}
]

CHEM_DICT = {
    "kmno4": "🧪 <b>Kaliy permanganat (KMnO₄)</b>\nToʻq binafsha rangli kristall modda, kuchli oksidlovchi.\n• Kislotali muhitda: Mn⁺⁷ → Mn²⁺ (rangsiz eritma)\n• Neytral muhitda: Mn⁺⁷ → MnO₂ (qoʻngʻir choʻkma)\n• Ishqoriy muhitda: Mn⁺⁷ → MnO₄²⁻ (yashil eritma)",
    "h2so4": "🧪 <b>Sulfat kislota (H₂SO₄)</b>\nKuchli ikki negizli mineral kislota. Konsentrlangan H₂SO₄ kuchli oksidlovchi va gigroskopik (suv tortuvchi) xossaga ega.",
    "hno3": "🧪 <b>Nitrat kislota (HNO₃)</b>\nKuchli bir negizli kislota. Har qanday konsentratsiyada kuchli oksidlovchi (odatda H₂ gazi ajralmaydi).",
    "caco3": "🧪 <b>Kalsiy karbonat (CaCO₃)</b>\nTabiatda ohaktosh, marmar va boʻr holida uchraydi. Suvda erimaydi. Qizdirilganda CaO va CO₂ ga parchalanadi.",
    "nh3": "🧪 <b>Ammiak (NH₃)</b>\nOʻtkir hidli, suvda juda yaxshi eriydigan gaz. Suvdagi eritmasi kuchsiz asos (NH₄OH) xossasini namoyon qiladi.",
    "naoh": "🧪 <b>Natriy gidroksid (NaOH)</b>\nOʻyuvchi natriy — kuchli ishqor, suvda yaxshi eriydi, havodan namlik va CO₂ ni yutadi."
}

# ================= MAJBURIY OBUNA =================
def check_subscription(user_id):
    if db_is_admin(user_id):
        return True
    try:
        member = bot.get_chat_member(KANAL_USER, user_id)
        return member.status in ['creator', 'administrator', 'member']
    except Exception:
        return True

def ask_to_subscribe(chat_id):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📢 Kanalga obuna boʻlish (A+ Kimyo)", url=KANAL_LINK),
        InlineKeyboardButton("✅ Obuna boʻldim (Tekshirish)", callback_data="check_sub")
    )
    bot.send_message(
        chat_id,
        f"⚠️ <b>Botdan foydalanish uchun rasmiy kanalimizga obuna boʻling!</b>\n\n📢 Kanal: {KANAL_USER}",
        reply_markup=kb
    )

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
                group_name TEXT DEFAULT 'Umumiy guruh',
                bonus_points INTEGER DEFAULT 0,
                referred_by INTEGER DEFAULT 0,
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

def db_add_user(user_id, full_name, username, ref_id=0):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        exists = c.fetchone()
        if not exists:
            c.execute(
                "INSERT INTO users (user_id, full_name, username, referred_by, joined_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, full_name, username or "", ref_id, datetime.now().strftime("%Y-%m-%d %H:%M"))
            )
            if ref_id and ref_id != user_id:
                c.execute("UPDATE users SET bonus_points = bonus_points + 10 WHERE user_id = ?", (ref_id,))
                try:
                    bot.send_message(ref_id, f"🎉 <b>Yangi referal!</b> Doʻstingiz <b>{full_name}</b> botga qoʻshildi va sizga <b>+10 bonus ball</b> berildi!")
                except Exception:
                    pass
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

# ================= AVTOMATIK SERTIFIKAT GENERATORI =================
def generate_certificate_image(full_name, test_title, score, level):
    filename = f"cert_{random.randint(1000,9999)}.png"
    W, H = 1000, 700
    img = Image.new("RGB", (W, H), color=(18, 28, 45))
    draw = ImageDraw.Draw(img)

    # Oltin ramka
    draw.rectangle([25, 25, W - 25, H - 25], outline=(212, 175, 55), width=8)
    draw.rectangle([40, 40, W - 40, H - 40], outline=(106, 179, 243), width=2)

    font_lg = ImageFont.load_default()
    
    # Matnlarni markazga joylash (Pillow default shrift o'lchami bilan)
    draw.text((340, 80), "A+ KIMYO | ONLINE MAKTABI", fill=(212, 175, 55))
    draw.text((390, 140), "MAXSUS SERTIFIKAT", fill=(255, 255, 255))
    draw.text((330, 210), "Ushbu sertifikat egasi:", fill=(180, 195, 210))
    
    # O'quvchi ismi
    draw.text((320, 260), full_name.upper(), fill=(106, 179, 243))
    
    draw.text((280, 330), f"Sinov nomi: {test_title}", fill=(255, 255, 255))
    draw.text((320, 380), f"To'plagan natijasi: {score} ball", fill=(46, 204, 113))
    draw.text((320, 430), f"Darajasi: {level}", fill=(241, 196, 15))

    draw.text((120, 560), f"Sana: {datetime.now().strftime('%d.%m.%Y')}", fill=(180, 195, 210))
    draw.text((620, 560), "Kurs rahbari: Azizbek Ibrohimov", fill=(212, 175, 55))
    draw.text((380, 620), "Telegram: @kimyo_sertifkat_uchun", fill=(140, 155, 175))

    img.save(filename)
    return filename

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
        KeyboardButton("🎮 Kimyo Viktorina"),
        KeyboardButton("📖 Moddalar lugʻati"),
        KeyboardButton("👤 Shaxsiy kabinet"),
        KeyboardButton("🔗 Doʻstlarni taklif qilish"),
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
        KeyboardButton("👥 Guruhlarni boshqarish (CRM)"),
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

# ================= OBUNA CALLBACK =================
@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def verify_sub_callback(call):
    uid = call.from_user.id
    if check_subscription(uid):
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception: pass
        bot.send_message(uid, "✅ <b>Obuna tasdiqlandi!</b> Xush kelibsiz!", reply_markup=main_menu(uid))
    else:
        bot.answer_callback_query(call.id, "❌ Siz hali kanalga obuna boʻlmadingiz!", show_alert=True)

# ================= /START VA ASOSIY BUYRUQLAR =================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.from_user.id
    user_states.pop(uid, None)
    
    # Referal ID ni tekshirish (/start 123456)
    parts = message.text.split()
    ref_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    db_add_user(uid, message.from_user.full_name, message.from_user.username, ref_id)

    if not check_subscription(uid):
        return ask_to_subscribe(uid)
    
    text = (
        f"Assalomu alaykum, <b>{message.from_user.full_name}</b>! 👋\n\n"
        f"🧪 <b>A+ Kimyo | Online Maktabi</b> platformasiga xush kelibsiz!\n\n"
        f"🔹 <b>📊 Elektron Titr:</b> 40 talik MS testini topshirish va Sertifikat olish\n"
        f"🔹 <b>🎬 Namuna darslar:</b> Bepul video darslar va qoʻllanmalar\n"
        f"🔹 <b>🎮 Kimyo Viktorina:</b> Tezkor savol-javob oʻyini\n"
        f"🔹 <b>📖 Moddalar lugʻati:</b> Kimyoviy moddalar haqida maʼlumot\n\n"
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
    if db_is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⚙️ <b>Admin Panel:</b>", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📞 Admin bilan aloqa")
def contact_admin(message):
    if not check_subscription(message.from_user.id): return ask_to_subscribe(message.chat.id)
    bot.send_message(
        message.chat.id,
        f"👨‍🏫 <b>Muallif va kurs rahbari:</b> Azizbek Ibrohimov\n"
        f"💬 <b>Shaxsiy lichka:</b> {ADMIN_LICHKA}\n"
        f"📢 <b>Kanalimiz:</b> {KANAL_USER}"
    )

# ================= SHAXSIY KABINET VA REFERAL =================
@bot.message_handler(func=lambda m: m.text == "👤 Shaxsiy kabinet")
def user_profile(message):
    uid = message.from_user.id
    if not check_subscription(uid): return ask_to_subscribe(uid)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name, phone, group_name, bonus_points, joined_at FROM users WHERE user_id = ?", (uid,))
        u = c.fetchone()
        c.execute("SELECT COUNT(*), COALESCE(AVG(rash_score), 0), COALESCE(MAX(rash_score), 0) FROM results WHERE user_id = ?", (uid,))
        stats = c.fetchone()

    text = (
        f"👤 <b>SHAXSIY KABINET</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📛 <b>Ism:</b> {u[0]}\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"👥 <b>Guruh:</b> {u[2]}\n"
        f"📞 <b>Tel:</b> {u[1] or 'Kiritilmagan'}\n"
        f"💎 <b>Bonus ballar:</b> <b>{u[3]} ball</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Ishlangan testlar:</b> {stats[0]} ta\n"
        f"📈 <b>Oʻrtacha ball:</b> {round(stats[1], 1)} ball\n"
        f"🏆 <b>Rekord natija:</b> {round(stats[2], 1)} ball"
    )
    bot.send_message(uid, text)

@bot.message_handler(func=lambda m: m.text == "🔗 Doʻstlarni taklif qilish")
def referral_link(message):
    uid = message.from_user.id
    if not check_subscription(uid): return ask_to_subscribe(uid)
    bot_info = bot.get_me()
    ref_url = f"https://t.me/{bot_info.username}?start={uid}"
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (uid,))
        count = c.fetchone()[0]

    text = (
        f"🔗 <b>DOʻSTLARNI TAKLIF QILING VA BALL YIGʻING!</b>\n\n"
        f"Har bir taklif qilingan doʻstingiz uchun sizga <b>+10 bonus ball</b> beriladi.\n\n"
        f"👥 <b>Siz taklif qilganlar:</b> {count} kishi\n"
        f"📎 <b>Sizning shaxsiy havolangiz:</b>\n<code>{ref_url}</code>"
    )
    bot.send_message(uid, text)

# ================= KIMYOVIY VIKTORINA (O'YIN) =================
@bot.message_handler(func=lambda m: m.text == "🎮 Kimyo Viktorina")
def start_quiz(message):
    uid = message.from_user.id
    if not check_subscription(uid): return ask_to_subscribe(uid)
    q_obj = random.choice(QUIZ_QUESTIONS)
    opts = q_obj["opts"].copy()
    random.shuffle(opts)
    
    user_data[uid] = {"quiz_ans": q_obj["ans"]}
    kb = InlineKeyboardMarkup(row_width=2)
    btns = [InlineKeyboardButton(o, callback_data=f"quiz_{o}") for o in opts]
    kb.add(*btns)
    bot.send_message(uid, f"🎮 <b>TEZKOR KIMYO VIKTORINASI:</b>\n\n❓ {q_obj['q']}", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("quiz_"))
def check_quiz(call):
    uid = call.from_user.id
    chosen = call.data.split("_", 1)[1]
    correct = user_data.get(uid, {}).get("quiz_ans")

    if not correct:
        return bot.answer_callback_query(call.id, "Savol eskirgan!")

    if chosen == correct:
        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET bonus_points = bonus_points + 2 WHERE user_id = ?", (uid,))
            conn.commit()
        bot.edit_message_text(
            f"✅ <b>Toʻgʻri topdingiz!</b> ({correct})\n💎 Sizga <b>+2 bonus ball</b> qoʻshildi!",
            call.message.chat.id, call.message.message_id
        )
    else:
        bot.edit_message_text(
            f"❌ <b>Xato!</b> Siz tanladingiz: {chosen}\n✅ Toʻgʻri javob: <b>{correct}</b>",
            call.message.chat.id, call.message.message_id
        )
    user_data.pop(uid, None)
    bot.answer_callback_query(call.id)

# ================= MODDALAR LUG'ATI =================
@bot.message_handler(func=lambda m: m.text == "📖 Moddalar lugʻati")
def ask_dict_word(message):
    uid = message.from_user.id
    if not check_subscription(uid): return ask_to_subscribe(uid)
    user_states[uid] = "wait_chem_word"
    bot.send_message(
        uid,
        "📖 <b>Kimyoviy modda formulasini yozing</b> (masalan: <code>KMnO4</code>, <code>H2SO4</code>, <code>HNO3</code>, <code>CaCO3</code>, <code>NH3</code>, <code>NaOH</code>):",
        reply_markup=cancel_kb()
    )

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "wait_chem_word")
def search_chem_dict(message):
    uid = message.from_user.id
    query = message.text.strip().lower()
    res = CHEM_DICT.get(query)
    if res:
        bot.send_message(uid, res)
    else:
        bot.send_message(uid, "🔍 Bu modda bazaga endi kiritilmoqda. Boshqa formula yozib koʻring (masalan: <code>KMnO4</code>).")

# ================= NAMUNA DARSLAR =================
@bot.message_handler(func=lambda m: m.text == "🎬 Namuna darslar")
def show_sample_lessons(message):
    if not check_subscription(message.from_user.id): return ask_to_subscribe(message.chat.id)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT id, title FROM sample_lessons ORDER BY id DESC LIMIT 20")
        rows = c.fetchall()

    if not rows:
        return bot.send_message(message.chat.id, f"🎬 Hozircha namuna darslar yuklanmagan. Kanal: {KANAL_USER}")

    kb = InlineKeyboardMarkup(row_width=1)
    for r in rows:
        kb.add(InlineKeyboardButton(f"▶️ {r[1]}", callback_data=f"lesson_{r[0]}"))
    bot.send_message(message.chat.id, "🎬 <b>Namuna darsni tanlang:</b>", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("lesson_"))
def send_sample_lesson(call):
    lid = int(call.data.split("_")[1])
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT title, description, file_id, file_type FROM sample_lessons WHERE id = ?", (lid,))
        row = c.fetchone()
    if not row: return bot.answer_callback_query(call.id, "Topilmadi!")

    title, desc, file_id, ftype = row
    caption = f"🎬 <b>{title}</b>\n\n{desc}\n\n👨‍🏫 {ADMIN_LICHKA} | 📢 {KANAL_USER}"
    if ftype == "video": bot.send_video(call.message.chat.id, file_id, caption=caption)
    elif ftype == "document": bot.send_document(call.message.chat.id, file_id, caption=caption)
    elif ftype == "photo": bot.send_photo(call.message.chat.id, file_id, caption=caption)
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.text == "🎬 Namuna dars qoʻshish")
def adm_add_lesson_1(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    user_states[uid] = "les_title"
    bot.send_message(uid, "🎬 <b>Namuna dars nomini kiriting:</b>", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "les_title")
def adm_add_lesson_2(message):
    uid = message.from_user.id
    user_data[uid] = {"title": message.text}
    user_states[uid] = "les_desc"
    bot.send_message(uid, "📝 <b>Izoh yozing</b> (yoki <code>-</code> yuboring):")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "les_desc")
def adm_add_lesson_3(message):
    uid = message.from_user.id
    user_data[uid]["desc"] = "" if message.text == "-" else message.text
    user_states[uid] = "les_file"
    bot.send_message(uid, "📎 Endi <b>Video, PDF yoki Rasmni</b> yuboring:")

@bot.message_handler(content_types=['video', 'document', 'photo'], func=lambda m: user_states.get(m.from_user.id) == "les_file")
def adm_save_lesson(message):
    uid = message.from_user.id
    info = user_data[uid]
    if message.video: fid, ftype = message.video.file_id, "video"
    elif message.document: fid, ftype = message.document.file_id, "document"
    else: fid, ftype = message.photo[-1].file_id, "photo"

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("INSERT INTO sample_lessons (title, description, file_id, file_type, added_at) VALUES (?, ?, ?, ?, ?)",
                  (info["title"], info["desc"], fid, ftype, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
    user_states.pop(uid, None)
    bot.send_message(uid, f"✅ <b>«{info['title']}»</b> qoʻshildi!", reply_markup=admin_menu())

# ================= WEB APP (40 TALIK TITR) + AVTO-SERTIFIKAT =================
@bot.message_handler(content_types=['web_app_data'])
def handle_webapp_data(message):
    uid = message.from_user.id
    if not check_subscription(uid): return ask_to_subscribe(uid)

    payload = json.loads(message.web_app_data.data)
    mode, meta, answers = payload.get("mode"), payload.get("meta"), payload.get("answers")

    if mode == "create":
        if not db_is_admin(uid): return
        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute("INSERT INTO tests (title, answers, created_at) VALUES (?, ?, ?)",
                      (meta, json.dumps(answers), datetime.now().strftime("%Y-%m-%d %H:%M")))
            code = c.lastrowid
            conn.commit()
        bot.send_message(uid, f"✅ <b>Yangi 40 talik Test yaratildi!</b>\n🔢 Kod: <code>{code}</code>\n📘 Mavzu: {meta}", reply_markup=admin_menu())

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

        title, correct_keys = row[0], json.loads(row[1])
        raw_correct, rash_score, details = 0, 0.0, []

        for i in range(40):
            u = str(answers[i]).strip().lower()
            k = str(correct_keys[i]).strip().lower()
            q_num = i + 1
            weight = 1.5 if q_num <= 32 else (2.2 if q_num <= 35 else 4.08)
            if u != "" and u == k:
                raw_correct += 1
                rash_score += weight
                details.append(f"{q_num}.✅")
            else:
                details.append(f"{q_num}.❌")

        rash_score = round(rash_score, 2)
        percent = round((rash_score / 75.0) * 100, 1)

        if rash_score >= 70: daraja = "A+ daraja"
        elif rash_score >= 65: daraja = "A daraja"
        elif rash_score >= 60: daraja = "B+ daraja"
        elif rash_score >= 55: daraja = "B daraja"
        elif rash_score >= 50: daraja = "C+ daraja"
        elif rash_score >= 46: daraja = "C daraja"
        else: daraja = "Sertifikat baliga yetmadi"

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
            f"📈 <b>Ball:</b> <b>{rash_score} ball</b> ({percent}%)\n"
            f"🎖 <b>Daraja:</b> <b>{daraja}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n" + " | ".join(details)
        )
        bot.send_message(uid, res_text)

        # Agar 46 balldan yuqori olsa AVTOMATIK SERTIFIKAT yuboramiz!
        if rash_score >= 46:
            try:
                cert_file = generate_certificate_image(message.from_user.full_name, title, rash_score, daraja)
                with open(cert_file, "rb") as cf:
                    bot.send_photo(uid, cf, caption=f"🎓 <b>Tabriklaymiz! Siz {daraja} sertifikatini qoʻlga kiritdingiz!</b>\n📢 {KANAL_USER}")
                os.remove(cert_file)
            except Exception:
                pass

        # Yozma ishni rasm holatda yuborishni so'raymiz
        user_data[uid] = {"test_code": code, "title": title, "score": rash_score}
        user_states[uid] = "wait_written_photo"
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("⏭ Yozma ish yoʻq (Oʻtkazib yuborish)"))
        bot.send_message(uid, "📸 <b>Endi yozma ish (yechimlar) rasmini shu yerga tashlang:</b>", reply_markup=kb)

# ================= YOZMA ISH RASMINI QABUL QILISH =================
@bot.message_handler(func=lambda m: m.text == "⏭ Yozma ish yoʻq (Oʻtkazib yuborish)")
def skip_written_photo(message):
    user_states.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "✅ Test yakunlandi!", reply_markup=main_menu(message.from_user.id))

@bot.message_handler(content_types=['photo'], func=lambda m: user_states.get(m.from_user.id) == "wait_written_photo")
def receive_written_photo(message):
    uid = message.from_user.id
    info = user_data.get(uid, {})
    photo_id = message.photo[-1].file_id
    caption = (
        f"📝 <b>YANGI YOZMA ISH KELDI!</b>\n"
        f"👤 Oʻquvchi: {message.from_user.full_name} (@{message.from_user.username or 'yoq'})\n"
        f"🆔 ID: <code>{uid}</code> | Test: #{info.get('test_code')}\n"
        f"📈 Joriy bali: {info.get('score')} ball"
    )
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✍️ Yozma ish uchun ball qoʻshish", callback_data=f"addw_{uid}_{info.get('test_code')}"))
    for adm in db_get_admins():
        try: bot.send_photo(adm, photo_id, caption=caption, reply_markup=kb)
        except Exception: pass
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ <b>Yozma ish rasmi ustozga yuborildi!</b>", reply_markup=main_menu(uid))

@bot.callback_query_handler(func=lambda call: call.data.startswith("addw_"))
def ask_written_bonus(call):
    _, target_uid, t_code = call.data.split("_")
    adm_id = call.from_user.id
    user_data[adm_id] = {"target_uid": int(target_uid), "t_code": int(t_code)}
    user_states[adm_id] = "adm_give_w_score"
    bot.send_message(adm_id, f"✍️ Oʻquvchi (ID: <code>{target_uid}</code>) yozma ishi uchun necha ball qoʻshasiz?")
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "adm_give_w_score")
def save_written_bonus(message):
    adm_id = message.from_user.id
    try: bonus = float(message.text.replace(",", "."))
    except ValueError: return bot.send_message(adm_id, "⚠️ Faqat raqam kiriting:")
    info = user_data[adm_id]
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE results SET written_score = ?, rash_score = rash_score + ? WHERE user_id = ? AND test_code = ?",
                  (bonus, bonus, info["target_uid"], info["t_code"]))
        conn.commit()
    user_states.pop(adm_id, None)
    bot.send_message(adm_id, f"✅ Yozma ish uchun <b>+{bonus} ball</b> qoʻshildi!", reply_markup=admin_menu())
    try: bot.send_message(info["target_uid"], f"🎉 <b>Ustoz yozma ishingizni tekshirdi va +{bonus} ball qoʻshdi!</b>")
    except Exception: pass

# ================= CRM: GURUHLARNI BOSHQARISH =================
@bot.message_handler(func=lambda m: m.text == "👥 Guruhlarni boshqarish (CRM)")
def crm_groups_menu(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    user_states[uid] = "crm_set_user"
    bot.send_message(
        uid,
        "👥 <b>Oʻquvchini guruhga biriktirish:</b>\nOʻquvchining Telegram <b>ID raqamini</b> yuboring (yoki bekor qiling):",
        reply_markup=cancel_kb()
    )

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "crm_set_user")
def crm_choose_group(message):
    uid = message.from_user.id
    if not message.text.isdigit(): return bot.send_message(uid, "⚠️ ID raqam kiriting:")
    target_id = int(message.text)
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🧪 Milliy Sertifikat guruhi", callback_data=f"grp_{target_id}_Milliy Sertifikat"),
        InlineKeyboardButton("👨‍🏫 Attestatsiya (Ustozlar)", callback_data=f"grp_{target_id}_Attestatsiya"),
        InlineKeyboardButton("📚 Noldan boshlovchilar", callback_data=f"grp_{target_id}_Noldan Kimyo")
    )
    user_states.pop(uid, None)
    bot.send_message(uid, f"Oʻquvchi (ID: <code>{target_id}</code>) uchun guruhni tanlang:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("grp_"))
def crm_save_group(call):
    _, tid, gname = call.data.split("_", 2)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET group_name = ? WHERE user_id = ?", (gname, int(tid)))
        conn.commit()
    bot.send_message(call.message.chat.id, f"✅ Oʻquvchi <b>«{gname}»</b> guruhiga biriktirildi!", reply_markup=admin_menu())
    bot.answer_callback_query(call.id)

# ================= REYTING, VAZIFA NAZORATI VA EXCEL/WORD/PDF =================
@bot.message_handler(func=lambda m: m.text == "🏆 Umumiy Reyting")
def show_global_rating(message):
    if not check_subscription(message.from_user.id): return ask_to_subscribe(message.chat.id)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name, rash_score, raw_correct, daraja FROM results ORDER BY rash_score DESC LIMIT 20")
        rows = c.fetchall()
    if not rows: return bot.send_message(message.chat.id, "📭 Hali natijalar yoʻq.")
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
    bot.send_message(uid, "🔢 <b>Test kodini</b> kiriting:", reply_markup=cancel_kb())

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
        c.execute("SELECT user_id, full_name, phone, group_name FROM users WHERE is_admin = 0")
        all_users = c.fetchall()

    user_states.pop(uid, None)
    not_done = [u for u in all_users if u[0] not in done_ids]

    text = f"📑 <b>VAZIFA NAZORATI: Test #{code} ({t[0]})</b>\n━━━━━━━━━━━━━━━━━━\n"
    text += f"✅ <b>Vazifani bajarganlar ({len(done_rows)} ta):</b>\n"
    for r in done_rows:
        text += f"  • {r[1]} — <b>{round(r[2], 2)} ball</b> ({r[3]}/40)\n"
    text += f"\n❌ <b>Vazifa qilmaganlar ({len(not_done)} ta):</b>\n"
    for u in not_done:
        text += f"  • {u[1]} [{u[3]}] (Tel: {u[2] or 'yoʻq'})\n"
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
    bot.send_message(uid, "📥 <b>Hisobot formatini tanlang:</b>", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("exp_"))
def handle_export(call):
    uid = call.from_user.id
    if not db_is_admin(uid): return
    fmt = call.data.split("_")[1]
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("""
            SELECT u.full_name, u.group_name, u.phone, COALESCE(r.test_code, 0),
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
        ws.append(["№", "F.I.Sh.", "Guruh", "Telefon", "Test Kodi", "To'g'ri", "Umumiy Ball", "Holati", "Vaqti"])
        for idx, r in enumerate(rows, 1):
            holat = "Bajarilgan (" + r[6] + ")" if r[3] != 0 else "❌ Qilinmagan"
            ws.append([idx, r[0], r[1], r[2], r[3] or "-", f"{r[4]}/40" if r[3] else "-", round(r[5], 2), holat, r[7]])
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
        hdr[0].text, hdr[1].text, hdr[2].text, hdr[3].text, hdr[4].text = "№", "F.I.Sh.", "Guruh", "Ball", "Holati"
        for idx, r in enumerate(rows, 1):
            rc = table.add_row().cells
            rc[0].text, rc[1].text, rc[2].text, rc[3].text, rc[4].text = str(idx), str(r[0]), str(r[1]), str(round(r[5], 2)), ("Bajarilgan" if r[3] != 0 else "Qilinmagan")
        doc.save(filename)
        with open(filename, "rb") as f:
            bot.send_document(uid, f, caption="📄 <b>Word hujjat</b>")

    elif fmt == "pdf":
        filename = "A_Plus_Kimyo_Hisobot.pdf"
        c_pdf = canvas.Canvas(filename, pagesize=letter)
        c_pdf.drawString(50, 750, "A+ KIMYO | O'QUVCHILAR REYTINGI")
        y = 720
        for idx, r in enumerate(rows[:32], 1):
            status = "Bajarilgan" if r[3] != 0 else "Qilinmagan"
            c_pdf.drawString(50, y, f"{idx}. {r[0]} [{r[1]}] | Ball: {round(r[5], 2)} | {status}")
            y -= 20
        c_pdf.save()
        with open(filename, "rb") as f:
            bot.send_document(uid, f, caption="📑 <b>PDF fayl</b>")
    bot.answer_callback_query(call.id, "Tayyor!")

# ================= KURSGA YOZILISH =================
@bot.message_handler(func=lambda m: m.text == "✍️ Kursga yozilish")
def reg_1(message):
    uid = message.from_user.id
    if not check_subscription(uid): return ask_to_subscribe(uid)
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
    bot.send_message(uid, f"💳 <b>Karta:</b> <code>9860350142097954</code> ({KARTA_EGASI})\n\n📸 Toʻlov chekini yuboring:", reply_markup=cancel_kb())

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
    bot.send_message(uid, "✅ Chek yuborildi!", reply_markup=main_menu(uid))

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

# Admin boshqa funksiyalari
@bot.message_handler(func=lambda m: m.text == "📋 Testlar roʻyxati")
def list_tests(message):
    if not db_is_admin(message.from_user.id): return
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT test_code, title FROM tests ORDER BY test_code DESC LIMIT 15")
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
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("DELETE FROM tests WHERE test_code = ?", (int(message.text),))
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
    print("A+ Kimyo Super Bot ishga tushdi...")
    bot.infinity_polling(none_stop=True, interval=0, timeout=20)
