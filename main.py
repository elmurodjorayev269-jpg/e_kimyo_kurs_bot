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
BOT_TOKEN = "8636730483:AAFCHNjwvmaLZuRk3fd3sOIbN2QMYd-h_4g"
ADMIN_PAROL = "kimyo2026"
KANAL_USER = "@kimyo_sertifkat_uchun"
KARTA_RAQAM = "9860 3501 4209 7954"
KARTA_EGASI = "Azizbek Ibrohimov"

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
                test_type TEXT DEFAULT 'oddiy',
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
                score REAL,
                total INTEGER,
                percent REAL,
                daraja TEXT,
                checked_at TEXT
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
    kb.add(
        KeyboardButton("📊 Rash modul (43 talik)"),
        KeyboardButton("📝 Oddiy test tekshirish"),
        KeyboardButton("🏆 Test reytingi"),
        KeyboardButton("✍️ Kursga yozilish"),
        KeyboardButton("ℹ️ Kurslar haqida"),
        KeyboardButton("📞 Admin bilan aloqa")
    )
    if db_is_admin(user_id):
        kb.add(KeyboardButton("⚙️ Admin Panel"))
    return kb

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("➕ Rash test qoʻshish (43 ta)"),
        KeyboardButton("➕ Oddiy test qoʻshish"),
        KeyboardButton("📋 Testlar roʻyxati"),
        KeyboardButton("🗑 Testni oʻchirish"),
        KeyboardButton("📊 Statistika"),
        KeyboardButton("📢 Hammaga xabar"),
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
        f"🧪 <b>A+ Kimyo | Online Maktabi</b> rasmiy botiga xush kelibsiz!\n\n"
        f"🔹 <b>📊 Rash modul (43 talik):</b> Milliy sertifikat testlarini tekshirish\n"
        f"🔹 <b>📝 Oddiy test:</b> Mavzulashtirilgan testlarni tekshirish\n"
        f"🔹 <b>✍️ Kursga yozilish:</b> Onlayn darslarga toʻlov va roʻyxatdan oʻtish\n\n"
        f"👇 Kerakli boʻlimni tanlang:"
    )
    bot.send_message(uid, text, reply_markup=main_menu(uid))

@bot.message_handler(commands=['admin'])
def admin_cmd(message):
    uid = message.from_user.id
    db_add_user(uid, message.from_user.full_name, message.from_user.username)
    parts = message.text.split()
    if len(parts) > 1 and parts[1] == ADMIN_PAROL:
        db_set_admin(uid)
        bot.send_message(uid, "✅ <b>Sizga Admin huquqi berildi!</b>", reply_markup=admin_menu())
    elif db_is_admin(uid):
        bot.send_message(uid, "⚙️ <b>Admin Panel:</b>", reply_markup=admin_menu())
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

@bot.message_handler(func=lambda m: m.text == "ℹ️ Kurslar haqida")
def about_courses(message):
    text = (
        "🧪 <b>A+ KIMYO | ONLINE MAKTABI</b>\n\n"
        "✅ Noldan boshlovchilar uchun fundamental kurs\n"
        "✅ Milliy Sertifikat va Attestatsiyaga intensiv tayyorlov\n"
        "✅ Haftalik 43 talik Rash diagnostik testlari va video tahlillar\n\n"
        f"👨‍🏫 <b>Muallif:</b> Azizbek Ibrohimov\n"
        f"📢 <b>Kanalimiz:</b> {KANAL_USER}"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "📞 Admin bilan aloqa")
def contact_admin(message):
    bot.send_message(
        message.chat.id,
        f"👨‍🏫 <b>Muallif:</b> Azizbek Ibrohimov\n📢 <b>Kanal:</b> {KANAL_USER}\n\n"
        f"Kursga qoʻshilish uchun <b>«✍️ Kursga yozilish»</b> tugmasidan foydalaning."
    )

# ================= 1. RASH MODUL (43 TALIK) =================
@bot.message_handler(func=lambda m: m.text == "📊 Rash modul (43 talik)")
def rash_menu_open(message):
    uid = message.from_user.id
    user_states[uid] = "wait_rash_code"
    text = (
        "📊 <b>RASH MODULI (43 TALIK MILLIY SERTIFIKAT TESTI)</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Bu boʻlimda 43 ta savoldan iborat Milliy sertifikat testlari tekshiriladi va Rash shkalasi boʻyicha darajangiz hisoblanadi.\n\n"
        "🔢 <b>Test kodini kiriting:</b>"
    )
    bot.send_message(uid, text, reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "wait_rash_code")
def rash_get_code(message):
    uid = message.from_user.id
    if not message.text.isdigit():
        return bot.send_message(uid, "⚠️ Iltimos, test kodini raqam bilan kiriting!")
    code = int(message.text)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT title, answers, test_type FROM tests WHERE test_code = ?", (code,))
        row = c.fetchone()

    if not row or row[2] != "rash":
        return bot.send_message(uid, "❌ Bunday kodli 43 talik Rash testi topilmadi!")

    keys_list = row[1].split("|")
    user_data[uid] = {"test_code": code, "title": row[0], "keys": keys_list}
    user_states[uid] = "wait_rash_answers"

    namuna = (
        f"📘 <b>Test:</b> {row[0]}\n"
        "❓ <b>Savollar:</b> 43 ta (Rash moduli)\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✍️ <b>Javoblaringizni 43 ta savol uchun vergul (,) yoki probel bilan ajratib yuboring</b>\n\n"
        "💡 <b>Namuna:</b> <code>a,b,c,d,a,b...</code>"
    )
    bot.send_message(uid, namuna)

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "wait_rash_answers")
def rash_evaluate(message):
    uid = message.from_user.id
    raw = message.text.strip().lower()
    data = user_data[uid]
    correct_keys = data["keys"]
    total_q = len(correct_keys)

    if "," in raw:
        user_ans = [x.strip() for x in raw.split(",") if x.strip()]
    elif " " in raw:
        user_ans = [x.strip() for x in raw.split() if x.strip()]
    else:
        user_ans = list(raw)

    if len(user_ans) != total_q:
        return bot.send_message(uid, f"⚠️ Javoblar soni 43 ta boʻlishi kerak! Siz {len(user_ans)} ta yubordingiz.")

    raw_correct = 0
    rash_score = 0.0
    details = []

    for i in range(total_q):
        u = user_ans[i]
        k = correct_keys[i].lower()
        q_num = i + 1

        if q_num <= 32: weight = 1.5
        elif q_num <= 35: weight = 2.2
        else: weight = 2.55

        if u == k:
            raw_correct += 1
            rash_score += weight
            details.append(f"{q_num}.✅")
        else:
            details.append(f"{q_num}.❌")

    rash_score = round(rash_score, 2)
    percent = round((rash_score / 75.0) * 100, 1)

    if rash_score >= 70: daraja = "🏆 A+ daraja (Maksimal imtiyoz!)"
    elif rash_score >= 65: daraja = "🥇 A daraja (100% imtiyoz!)"
    elif rash_score >= 60: daraja = "🥈 B+ daraja"
    elif rash_score >= 55: daraja = "🥈 B daraja (Sertifikat!)"
    elif rash_score >= 50: daraja = "🥉 C+ daraja"
    elif rash_score >= 46: daraja = "🥉 C daraja"
    else: daraja = "📚 Sertifikat baliga yetmadi"

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM results WHERE user_id = ? AND test_code = ?", (uid, data["test_code"]))
        if not c.fetchone():
            c.execute(
                "INSERT INTO results (user_id, full_name, test_code, score, total, percent, daraja, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (uid, message.from_user.full_name, data["test_code"], rash_score, total_q, percent, daraja, datetime.now().strftime("%Y-%m-%d %H:%M"))
            )
            conn.commit()

    user_states.pop(uid, None)
    res_text = (
        f"📊 <b>RASH MODULI NATIJASI (43 TALIK)</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Talabgor:</b> {message.from_user.full_name}\n"
        f"🔢 <b>Test kodi:</b> <code>{data['test_code']}</code>\n"
        f"📘 <b>Mavzu:</b> {data['title']}\n"
        f"✅ <b>Toʻgʻri javoblar:</b> {raw_correct} / 43 ta\n"
        f"📈 <b>Rash bali:</b> <b>{rash_score} ball</b> ({percent}%)\n"
        f"🎖 <b>Daraja:</b> <b>{daraja}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔍 <b>Tahlil:</b>\n" + " | ".join(details) + f"\n\n📢 {KANAL_USER}"
    )
    bot.send_message(uid, res_text, reply_markup=main_menu(uid))

# ================= 2. ODDIY TEST =================
@bot.message_handler(func=lambda m: m.text == "📝 Oddiy test tekshirish")
def ask_test_code(message):
    uid = message.from_user.id
    user_states[uid] = "wait_test_input"
    bot.send_message(uid, "📝 Oddiy test kodini kiriting (masalan: <code>1</code>):", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "wait_test_input")
def process_test_input(message):
    uid = message.from_user.id
    txt = message.text.strip()
    if "*" in txt:
        parts = txt.split("*", 1)
        if not parts[0].isdigit(): return bot.send_message(uid, "⚠️ Kod raqam boʻlishi kerak!")
        evaluate_simple_test(message, int(parts[0]), parts[1].strip().lower())
    else:
        if not txt.isdigit(): return bot.send_message(uid, "⚠️ Kodni raqamda kiriting!")
        test_code = int(txt)
        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute("SELECT title, answers, test_type FROM tests WHERE test_code = ?", (test_code,))
            row = c.fetchone()
        if not row: return bot.send_message(uid, "❌ Test topilmadi!")
        if row[2] == "rash": return bot.send_message(uid, "⚠️ Bu 43 talik Rash testi! «📊 Rash modul» boʻlimidan tekshiring.")
        user_data[uid] = {"test_code": test_code}
        user_states[uid] = "wait_test_answers"
        bot.send_message(uid, f"📘 Test: <b>{row[0]}</b> ({len(row[1])} ta savol)\nJavoblarni yuboring:")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "wait_test_answers")
def process_test_answers(message):
    uid = message.from_user.id
    test_code = user_data[uid]["test_code"]
    evaluate_simple_test(message, test_code, message.text.strip().lower())

def evaluate_simple_test(message, test_code, user_ans):
    uid = message.from_user.id
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT title, answers FROM tests WHERE test_code = ?", (test_code,))
        row = c.fetchone()
    if not row: return bot.send_message(uid, "❌ Test topilmadi!")
    title, correct_ans = row[0], row[1].lower()
    if len(user_ans) != len(correct_ans):
        return bot.send_message(uid, f"⚠️ Savollar soni mos emas! Testda {len(correct_ans)} ta savol bor.")
    
    score = 0
    details = []
    for i, (u, k) in enumerate(zip(user_ans, correct_ans), start=1):
        if u == k: score += 1; details.append(f"{i}.✅")
        else: details.append(f"{i}.❌({u.upper()})")

    total = len(correct_ans)
    percent = round((score / total) * 100, 1)

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM results WHERE user_id = ? AND test_code = ?", (uid, test_code))
        if not c.fetchone():
            c.execute(
                "INSERT INTO results (user_id, full_name, test_code, score, total, percent, daraja, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (uid, message.from_user.full_name, test_code, score, total, percent, f"{percent}%", datetime.now().strftime("%Y-%m-%d %H:%M"))
            )
            conn.commit()

    user_states.pop(uid, None)
    bot.send_message(uid, f"📊 <b>Natija:</b> {score}/{total} ({percent}%)\n📘 {title}\n\n" + " | ".join(details), reply_markup=main_menu(uid))

# ================= REYTING =================
@bot.message_handler(func=lambda m: m.text == "🏆 Test reytingi")
def ask_rating_code(message):
    uid = message.from_user.id
    user_states[uid] = "wait_rating_code"
    bot.send_message(uid, "🏆 Reyting uchun test kodini kiriting:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "wait_rating_code")
def show_test_rating(message):
    uid = message.from_user.id
    if not message.text.isdigit(): return bot.send_message(uid, "⚠️ Faqat raqam!")
    code = int(message.text)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT title, test_type FROM tests WHERE test_code = ?", (code,))
        t_row = c.fetchone()
        if not t_row: return bot.send_message(uid, "❌ Test topilmadi!")
        c.execute("SELECT full_name, score, total, daraja FROM results WHERE test_code = ? ORDER BY score DESC LIMIT 25", (code,))
        rows = c.fetchall()
    user_states.pop(uid, None)
    if not rows: return bot.send_message(uid, "📭 Hali natijalar yoʻq.", reply_markup=main_menu(uid))
    
    text = f"🏆 <b>TEST #{code} REYTINGI (TOP-25)</b>\n📘 <b>{t_row[0]}</b>\n━━━━━━━━━━━━━━━━━━\n"
    for idx, r in enumerate(rows, start=1):
        m = ["🥇", "🥈", "🥉"][idx-1] if idx <= 3 else f"<b>{idx}.</b>"
        if t_row[1] == "rash": text += f"{m} {r[0]} — <b>{r[1]} ball</b> ({r[3]})\n"
        else: text += f"{m} {r[0]} — <b>{int(r[1])}/{r[2]}</b> ({r[3]})\n"
    bot.send_message(uid, text, reply_markup=main_menu(uid))

# ================= KURSGA YOZILISH VA CHEK =================
@bot.message_handler(func=lambda m: m.text == "✍️ Kursga yozilish")
def reg_step1(message):
    uid = message.from_user.id
    user_states[uid] = "reg_name"
    bot.send_message(uid, "✍️ Ism va familiyangizni kiriting:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "reg_name")
def reg_step2(message):
    uid = message.from_user.id
    user_data[uid] = {"ism": message.text}
    user_states[uid] = "reg_phone"
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True), KeyboardButton("❌ Bekor qilish"))
    bot.send_message(uid, "📱 Telefon raqamingizni yuboring:", reply_markup=kb)

@bot.message_handler(content_types=['contact', 'text'], func=lambda m: user_states.get(m.from_user.id) == "reg_phone")
def reg_step3(message):
    uid = message.from_user.id
    if message.text == "❌ Bekor qilish": return cancel_action(message)
    phone = message.contact.phone_number if message.contact else message.text
    user_data[uid]["phone"] = phone
    user_states[uid] = "reg_receipt"

    pay_text = (
        f"💳 <b>Toʻlov rekvizitlari:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔹 <b>Karta:</b> <code>9860350142097954</code>\n"
        f"🔹 <b>Egasi:</b> <b>{KARTA_EGASI}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📸 Toʻlovni qilib, <b>chek rasmini</b> shu yerga yuboring. Ustoz Azizbek Ibrohimov oʻzlari tasdiqlaydilar:"
    )
    bot.send_message(uid, pay_text, reply_markup=cancel_kb())

@bot.message_handler(content_types=['photo'], func=lambda m: user_states.get(m.from_user.id) == "reg_receipt")
def reg_finish(message):
    uid = message.from_user.id
    info = user_data.get(uid, {})
    photo_id = message.photo[-1].file_id
    admins = db_get_admins()

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"pay_ok_{uid}"), InlineKeyboardButton("❌ Rad etish", callback_data=f"pay_no_{uid}"))
    caption = f"🆕 <b>YANGI TOʻLOV CHEKI!</b>\n\n👤 Ism: {info.get('ism')}\n📞 Tel: {info.get('phone')}\n🆔 ID: <code>{uid}</code>"
    for adm in admins:
        try: bot.send_photo(adm, photo_id, caption=caption, reply_markup=kb)
        except Exception: pass

    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Chek adminga yuborildi! Tasdiqlangach sizga xabar keladi.", reply_markup=main_menu(uid))

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def handle_payment_decision(call):
    parts = call.data.split("_")
    action, target_uid = parts[1], int(parts[2])
    if action == "ok":
        bot.send_message(target_uid, "🎉 <b>Tabriklaymiz! Toʻlovingiz ustoz Azizbek Ibrohimov tomonidan tasdiqlandi!</b>")
        bot.edit_message_caption(caption=call.message.caption + "\n\n✅ <b>TASDIQLANDI</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.answer_callback_query(call.id, "Tasdiqlandi!")
    else:
        bot.send_message(target_uid, "❌ <b>Toʻlov cheki tasdiqlanmadi.</b>")
        bot.edit_message_caption(caption=call.message.caption + "\n\n❌ <b>RAD ETILDI</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.answer_callback_query(call.id, "Rad etildi!")

# ================= ADMIN PANEL =================
@bot.message_handler(func=lambda m: m.text == "➕ Rash test qoʻshish (43 ta)")
def adm_new_rash_test(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    user_states[uid] = "adm_rash_title"
    bot.send_message(uid, "📊 43 talik Rash testi nomini yozing:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "adm_rash_title")
def adm_new_rash_keys(message):
    uid = message.from_user.id
    user_data[uid] = {"title": message.text}
    user_states[uid] = "adm_rash_keys"
    bot.send_message(uid, "🔑 43 ta javob kalitini vergul yoki ketma-ket yuboring:")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "adm_rash_keys")
def adm_save_rash_test(message):
    uid = message.from_user.id
    raw = message.text.strip().lower()
    keys = [x.strip() for x in raw.split(",")] if "," in raw else list(raw)
    if len(keys) != 43: return bot.send_message(uid, f"⚠️ 43 ta boʻlishi shart! Siz {len(keys)} ta kiritdingiz.")
    title = user_data[uid]["title"]
    stored_keys = "|".join(keys)

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("INSERT INTO tests (test_type, title, answers, created_at) VALUES (?, ?, ?, ?)", ("rash", title, stored_keys, datetime.now().strftime("%Y-%m-%d %H:%M")))
        code = c.lastrowid
        conn.commit()
    user_states.pop(uid, None)
    bot.send_message(uid, f"✅ 43 talik Rash testi saqlandi!\n🔢 Kod: <code>{code}</code>", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "➕ Oddiy test qoʻshish")
def adm_new_test(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    user_states[uid] = "adm_test_title"
    bot.send_message(uid, "📘 Oddiy test nomini yozing:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "adm_test_title")
def adm_new_test_keys(message):
    uid = message.from_user.id
    user_data[uid] = {"title": message.text}
    user_states[uid] = "adm_test_keys"
    bot.send_message(uid, "🔑 Javoblar kalitini ketma-ket yozing:")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "adm_test_keys")
def adm_save_test(message):
    uid = message.from_user.id
    keys = message.text.strip().lower().replace(" ", "")
    title = user_data[uid]["title"]
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("INSERT INTO tests (test_type, title, answers, created_at) VALUES (?, ?, ?, ?)", ("oddiy", title, keys, datetime.now().strftime("%Y-%m-%d %H:%M")))
        code = c.lastrowid
        conn.commit()
    user_states.pop(uid, None)
    bot.send_message(uid, f"✅ Oddiy test qoʻshildi!\n🔢 Kod: <code>{code}</code>", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📋 Testlar roʻyxati")
def adm_list_tests(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT test_code, test_type, title FROM tests ORDER BY test_code DESC LIMIT 15")
        rows = c.fetchall()
    if not rows: return bot.send_message(uid, "📭 Testlar yoʻq.")
    bot.send_message(uid, "📋 <b>Testlar:</b>\n" + "\n".join([f"🔹 Kod: <code>{r[0]}</code> [{r[1].upper()}] — {r[2]}" for r in rows]))

@bot.message_handler(func=lambda m: m.text == "🗑 Testni oʻchirish")
def adm_del_test_ask(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    user_states[uid] = "adm_del_test"
    bot.send_message(uid, "🗑 Test kodini yozing:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "adm_del_test")
def adm_del_test_confirm(message):
    uid = message.from_user.id
    if not message.text.isdigit(): return bot.send_message(uid, "⚠️ Faqat raqam!")
    code = int(message.text)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("DELETE FROM tests WHERE test_code = ?", (code,))
        conn.commit()
        deleted = c.rowcount
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Oʻchirildi!" if deleted else "❌ Topilmadi.", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📊 Statistika")
def adm_stats(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        u = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM tests")
        t = c.fetchone()[0]
    bot.send_message(uid, f"📊 Oʻquvchilar: {u}\nTestlar: {t}")

@bot.message_handler(func=lambda m: m.text == "📢 Hammaga xabar")
def adm_broadcast_ask(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    user_states[uid] = "adm_broadcast"
    bot.send_message(uid, "📢 Hammaga yuboriladigan xabarni yuboring:", reply_markup=cancel_kb())

@bot.message_handler(content_types=['text', 'photo', 'video', 'document'], func=lambda m: user_states.get(m.from_user.id) == "adm_broadcast")
def adm_broadcast_send(message):
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
    bot.send_message(uid, f"✅ Xabar {sent} ta oʻquvchiga yetkazildi!", reply_markup=admin_menu())

# ================= WEB SERVER =================
@app.route("/")
def index():
    return "Bot 24/7 ishlamoqda!"

def run_web():
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web, daemon=True).start()
    bot.remove_webhook()
    print("Bot ishga tushdi...")
    bot.infinity_polling(skip_pending=True)
