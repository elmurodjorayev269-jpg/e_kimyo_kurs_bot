import os
import json
import sqlite3
import random
import threading
from datetime import datetime
from flask import Flask, send_file, render_template_string
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo
)

# Hisobot va Sertifikat kutubxonalari
import openpyxl
from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw, ImageFont, ImageOps

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

# ================= HTML INTERAKTIV TITR SHABLONI =================
TITR_HTML = """
<!DOCTYPE html>
<html lang="uz">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>A+ Kimyo | Elektron Titr</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background-color: #17212b; color: #ffffff; padding-bottom: 90px; }
        .header { position: sticky; top: 0; background: #242f3d; padding: 12px 15px; z-index: 100; border-bottom: 1px solid #0e1621; display: flex; justify-content: space-between; align-items: center; }
        .header h2 { font-size: 16px; color: #6ab3f3; }
        .cols-header { display: grid; grid-template-columns: 45px repeat(4, 1fr); text-align: center; padding: 8px 10px; background: #1c2733; font-weight: bold; color: #8b9bb4; font-size: 14px; position: sticky; top: 45px; z-index: 99; }
        .q-row { display: grid; grid-template-columns: 45px repeat(4, 1fr); align-items: center; padding: 6px 10px; border-bottom: 1px solid #202b36; }
        .q-num { font-weight: bold; color: #8b9bb4; text-align: center; font-size: 15px; }
        .opt-btn { width: 42px; height: 42px; border-radius: 50%; border: 2px solid #3d4d5d; background: #242f3d; color: #fff; font-weight: bold; font-size: 15px; margin: 0 auto; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: 0.15s; }
        .opt-btn.active { background: #3390ec; border-color: #3390ec; box-shadow: 0 0 10px rgba(51, 144, 236, 0.5); }
        .match-row { padding: 10px 15px; border-bottom: 1px solid #202b36; }
        .match-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 6px; margin-top: 8px; }
        .match-btn { height: 38px; border-radius: 8px; border: 1px solid #3d4d5d; background: #242f3d; color: #fff; font-weight: bold; cursor: pointer; }
        .match-btn.active { background: #3390ec; border-color: #3390ec; }
        .open-row { padding: 12px 15px; border-bottom: 1px solid #202b36; display: flex; align-items: center; gap: 12px; }
        .open-row label { font-weight: bold; color: #8b9bb4; min-width: 75px; }
        .open-row input { flex: 1; padding: 10px 12px; border-radius: 8px; border: 1px solid #3d4d5d; background: #242f3d; color: #fff; font-size: 15px; outline: none; }
        .open-row input:focus { border-color: #3390ec; }
        .section-title { background: #0e1621; padding: 10px 15px; font-size: 13px; color: #6ab3f3; text-transform: uppercase; letter-spacing: 0.5px; font-weight: bold; }
        .footer { position: fixed; bottom: 0; left: 0; right: 0; background: #242f3d; padding: 12px 15px; border-top: 1px solid #0e1621; }
        .submit-btn { width: 100%; padding: 13px; background: #3390ec; color: #fff; border: none; border-radius: 10px; font-size: 16px; font-weight: bold; cursor: pointer; }
        .code-box { padding: 12px 15px; background: #242f3d; margin: 10px; border-radius: 10px; }
        .code-box input { width: 100%; padding: 10px; margin-top: 6px; border-radius: 8px; border: 1px solid #3d4d5d; background: #17212b; color: #fff; font-size: 16px; }
    </style>
</head>
<body>

<div class="header">
    <h2 id="page-title">A+ Kimyo | 40 talik Titr</h2>
    <span id="counter" style="font-size: 13px; color: #8b9bb4;">0 / 40</span>
</div>

<div class="code-box">
    <label id="code-label" style="font-size: 13px; color: #8b9bb4;">Test kodini kiriting:</label>
    <input type="text" id="test-meta" placeholder="6 xonali kod, masalan: 492815">
</div>

<div class="section-title">1–32: Yopiq testlar (A, B, C, D)</div>
<div class="cols-header">
    <div>№</div><div>A</div><div>B</div><div>C</div><div>D</div>
</div>
<div id="closed-questions"></div>

<div class="section-title">33–35: Moslashtirish (A – F)</div>
<div id="matching-questions"></div>

<div class="section-title">36–40: Ochiq savollar (Bitta javob kiriting)</div>
<div id="open-questions"></div>

<div class="footer">
    <button class="submit-btn" onclick="submitTitr()">✅ Javoblarni yuborish</button>
</div>

<script>
    const tg = window.Telegram.WebApp;
    tg.expand();

    const urlParams = new URLSearchParams(window.location.search);
    const mode = urlParams.get('mode') || 'solve';

    if (mode === 'create') {
        document.getElementById('page-title').innerText = "➕ Yangi 40 talik Test Yaratish";
        document.getElementById('code-label').innerText = "Test nomini kiriting:";
        document.getElementById('test-meta').placeholder = "Masalan: Milliy Sertifikat #1";
    }

    const answers = new Array(40).fill("");

    function updateCounter() {
        const filled = answers.filter(x => x !== "").length;
        document.getElementById('counter').innerText = `${filled} / 40`;
    }

    // 1-32
    const closedDiv = document.getElementById('closed-questions');
    for (let i = 0; i < 32; i++) {
        const row = document.createElement('div');
        row.className = 'q-row';
        row.innerHTML = `<div class="q-num">${i + 1}</div>`;
        ['A', 'B', 'C', 'D'].forEach(opt => {
            const btn = document.createElement('div');
            btn.className = 'opt-btn';
            btn.innerText = opt;
            btn.onclick = () => {
                row.querySelectorAll('.opt-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                answers[i] = opt.toLowerCase();
                updateCounter();
            };
            row.appendChild(btn);
        });
        closedDiv.appendChild(row);
    }

    // 33-35
    const matchDiv = document.getElementById('matching-questions');
    for (let i = 32; i < 35; i++) {
        const row = document.createElement('div');
        row.className = 'match-row';
        row.innerHTML = `<div style="font-weight:bold; color:#8b9bb4;">${i + 1}-savol javobi:</div>`;
        const grid = document.createElement('div');
        grid.className = 'match-grid';
        ['A', 'B', 'C', 'D', 'E', 'F'].forEach(opt => {
            const btn = document.createElement('button');
            btn.className = 'match-btn';
            btn.innerText = opt;
            btn.onclick = () => {
                grid.querySelectorAll('.match-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                answers[i] = opt.toLowerCase();
                updateCounter();
            };
            grid.appendChild(btn);
        });
        row.appendChild(grid);
        matchDiv.appendChild(row);
    }

    // 36-40
    const openDiv = document.getElementById('open-questions');
    for (let i = 35; i < 40; i++) {
        const row = document.createElement('div');
        row.className = 'open-row';
        row.innerHTML = `
            <label>${i + 1}-savol:</label>
            <input type="text" id="q_${i}" placeholder="Javobni yozing..." oninput="updateOpen(${i})">
        `;
        openDiv.appendChild(row);
    }

    function updateOpen(idx) {
        answers[idx] = document.getElementById(`q_${idx}`).value.trim().toLowerCase();
        updateCounter();
    }

    function submitTitr() {
        const meta = document.getElementById('test-meta').value.trim();
        if (!meta) {
            alert(mode === 'create' ? "Test nomini kiriting!" : "Test kodini kiriting!");
            return;
        }
        tg.sendData(JSON.stringify({
            mode: mode,
            meta: meta,
            answers: answers
        }));
    }
</script>
</body>
</html>
"""

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
                test_code INTEGER PRIMARY KEY,
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

# ================= BMBA (DTM) SERTIFIKAT GENERATORI =================
def generate_bmba_certificate(full_name, score, percent, level, photo_path):
    cert_path = f"bmba_cert_{random.randint(1000, 9999)}.png"
    W, H = 842, 1191  # A4 o'lchamlari 96 DPI uchun
    
    # Oq qog'oz foni
    img = Image.new("RGB", (W, H), color="white")
    draw = ImageDraw.Draw(img)
    
    # Milliy va professional chegaralar (Skrinshotdagidek)
    draw.rectangle([15, 15, W - 15, H - 15], outline="#1a1a1a", width=3)
    draw.line([30, 195, W - 30, 195], fill="#0a0a0a", width=2)
    
    # Gerb virtual o'rni
    draw.ellipse([386, 35, 456, 105], outline="#1b5e20", width=3)
    draw.ellipse([391, 40, 451, 100], fill="#0d47a1")
    
    font_normal = ImageFont.load_default()
    
    # Yuqori idoralar (Markazlashtirilgan)
    draw.text((150, 120), "O'ZBEKISTON RESPUBLIKASI OLIY TA'LIM, FAN VA INNOVATSIYALAR VAZIRLIGI", fill="black")
    draw.text((195, 138), "HUZURIDAGI BILIM VA MALAKALARNI BAHOLASH AGENTLIGI", fill="black")
    
    # To'g'risida sertifikat
    draw.text((220, 210), "UMUMTA'LIM FANINI BILISH DARAJASI TO'G'RISIDA", fill="black")
    draw.text((360, 230), "SERTIFIKAT", fill="black")
    
    # Random Sertifikat raqami (UZ26 + 6 xonali)
    cert_num = f"UZ26 {random.randint(100000, 999999)}"
    draw.text((50, 280), "Sertifikat raqami:")
    draw.text((180, 280), cert_num)
    draw.line([30, 310, W - 30, 310], fill="#cccccc", width=1)
    
    # Shaxsiy Ma'lumotlar sathlari
    user_code = str(random.randint(1000000, 9999999))
    draw.text((50, 330), "Talabgoringiz shaxsiy kodi:")
    draw.text((260, 330), user_code)
    
    name_parts = full_name.split()
    f_name = name_parts[0].upper() if len(name_parts) > 0 else "FOZILOV"
    i_name = name_parts[1].upper() if len(name_parts) > 1 else "SHOXRUX"
    o_name = (name_parts[2].upper() + " O'G'LI") if len(name_parts) > 2 else "SHAVKAT O'G'LI"
    
    draw.text((50, 365), "Familiyasi:")
    draw.text((200, 365), f_name)
    
    draw.text((50, 395), "Ismi:")
    draw.text((200, 395), i_name)
    
    draw.text((50, 425), "Otasining ismi:")
    draw.text((200, 425), o_name)
    
    draw.line([30, 460, W - 30, 460], fill="#cccccc", width=1)
    
    # O'quvchi rasmini o'ng tomonga kesib, chiroyli joylashtirish
    try:
        user_img = Image.open(photo_path)
        user_img = ImageOps.fit(user_img, (130, 160)) 
        img.paste(user_img, (650, 330))
        draw.rectangle([650, 330, 780, 490], outline="#cccccc", width=1)
    except Exception:
        draw.rectangle([650, 330, 780, 490], outline="red", width=1)
        draw.text((670, 400), "Rasmda xato", fill="red")

    # Ball va Daraja
    draw.text((50, 480), "Umumta'lim fani:")
    draw.text((380, 480), "Kimyo (O'zbekiston)")
    
    draw.text((50, 510), "Umumiy to'plagan ball (Rash shkalasi):")
    draw.text((380, 510), f"{score}")
    
    draw.text((50, 540), "Umumiy ballga nisbatan foiz ko'rsatkichi:")
    draw.text((380, 540), f"{percent} %")
    
    draw.text((50, 570), "Sertifikat darajasi:")
    draw.text((380, 570), level)
    
    draw.line([30, 610, W - 30, 610], fill="#cccccc", width=1)
    
    # Natijalar tarkibi
    t_test = round(score * 0.72, 2)
    t_yozma = round(score * 0.28, 2)
    draw.text((50, 630), "Test sinovi natijasi:")
    draw.text((650, 630), f"{t_test}")
    
    draw.text((50, 660), "Yozma ish natijasi:")
    draw.text((650, 660), f"{t_yozma}")
    
    # Muddati (Amal qilish)
    s_sana = datetime.now().strftime("%d.%m.%Y")
    m_sana = (datetime.now().replace(year=datetime.now().year + 3)).strftime("%d.%m.%Y")
    
    draw.line([30, 850, W - 30, 850], fill="#0a0a0a", width=1)
    draw.text((50, 880), f"Berilgan sanasi: {s_sana}")
    draw.text((450, 880), f"Amal qilish muddati: {m_sana}")
    
    # Direktor va QR kod virtual o'rni
    draw.rectangle([340, 920, 440, 1020], fill="black")
    draw.rectangle([350, 930, 430, 1010], fill="white")
    draw.rectangle([375, 955, 405, 985], fill="black")
    
    draw.text((200, 960), "Direktor")
    draw.text((500, 960), "M.KARIMOV")
    
    img.save(cert_path)
    return cert_path

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

# ================= KIMYOVIY VIKTORINA =================
@bot.message_handler(func=lambda m: m.text == "🎮 Kimyo Viktorina")
def start_quiz(message):
    uid = message.from_user.id
    if not check_subscription(uid): return ask_to_subscribe(uid)
    
    q_obj = random.choice([
        {"q": "Sulfat kislotaning molekulyar formulasi qaysi?", "opts": ["H2SO4", "H2SO3", "H2S", "HNO3"], "ans": "H2SO4"},
        {"q": "Kaliy permanganatning formulasi qaysi?", "opts": ["KMnO4", "K2MnO4", "MnO2", "KClO3"], "ans": "KMnO4"},
        {"q": "Oltinning kimyoviy belgisi nima?", "opts": ["Au", "Ag", "Fe", "Cu"], "ans": "Au"},
        {"q": "Avogadro doimiysi nechaga teng?", "opts": ["6.02×10²³", "22.4", "8.31", "1.6×10⁻¹⁹"], "ans": "6.02×10²³"},
        {"q": "Eng yengil gaz qaysi?", "opts": ["Vodorod (H2)", "Geliy (He)", "Azot (N2)", "Kislorod (O2)"], "ans": "Vodorod (H2)"},
        {"q": "Metanning formulasi qaysi?", "opts": ["CH4", "C2H6", "C2H4", "C2H2"], "ans": "CH4"}
    ])
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
            f"❌ <b>Xato!</b>\n✅ Toʻgʻri javob: <b>{correct}</b>",
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
        "📖 <b>Kimyoviy modda formulasini yozing</b> (masalan: <code>KMnO4</code>, <code>H2SO4</code>, <code>HNO3</code>):",
        reply_markup=cancel_kb()
    )

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "wait_chem_word")
def search_chem_dict(message):
    uid = message.from_user.id
    query = message.text.strip().lower()
    
    CHEM_DICT = {
        "kmno4": "🧪 <b>Kaliy permanganat (KMnO₄)</b>\nToʻq binafsha rangli kristall modda, kuchli oksidlovchi.\n• Kislotali muhitda: Mn⁺⁷ → Mn²⁺ (rangsiz eritma)",
        "h2so4": "🧪 <b>Sulfat kislota (H₂SO₄)</b>\nKuchli ikki negizli mineral kislota.",
        "hno3": "🧪 <b>Nitrat kislota (HNO₃)</b>\nKuchli bir negizli kislota."
    }
    
    res = CHEM_DICT.get(query)
    if res:
        bot.send_message(uid, res)
    else:
        bot.send_message(uid, "🔍 Bu modda bazada topilmadi. Boshqa formula yozib koʻring (masalan: <code>KMnO4</code>).")

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

# ================= WEB APP (40 TALIK TITR) MA'LUMOTINI QABUL QILISH =================
@bot.message_handler(content_types=['web_app_data'])
def handle_webapp_data(message):
    uid = message.from_user.id
    if not check_subscription(uid): return ask_to_subscribe(uid)

    payload = json.loads(message.web_app_data.data)
    mode, meta, answers = payload.get("mode"), payload.get("meta"), payload.get("answers")

    # Admin yangi test kodi yaratganda (HAR SAFAR RANDOM 6 XONALI KOD BERILADI)
    if mode == "create":
        if not db_is_admin(uid): return
        
        # Takrorlanmas 6 xonali random kod generatsiyasi
        while True:
            code = random.randint(100000, 999999)
            with sqlite3.connect("database.db") as conn:
                c = conn.cursor()
                c.execute("SELECT test_code FROM tests WHERE test_code = ?", (code,))
                if not c.fetchone():
                    break
                    
        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute("INSERT INTO tests (test_code, title, answers, created_at) VALUES (?, ?, ?, ?)",
                      (code, meta, json.dumps(answers), datetime.now().strftime("%Y-%m-%d %H:%M")))
            conn.commit()
            
        bot.send_message(
            uid, 
            f"✅ <b>Yangi 40 talik Milliy Test muvaffaqiyatli yaratildi!</b>\n\n"
            f"🔢 <b>Maxsus Test kodi:</b> <code>{code}</code>\n"
            f"📘 Mavzu: <b>{meta}</b>\n\n"
            f"Oʻquvchilar ushbu random kodni kiritib testni topshirishadi.", 
            reply_markup=admin_menu()
        )

    # O'quvchi testni yechib tugatganda
    elif mode == "solve":
        if not meta.isdigit():
            return bot.send_message(uid, "⚠️ Test kodi faqat raqam boʻlishi kerak!", reply_markup=main_menu(uid))
        code = int(meta)
        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute("SELECT title, answers FROM tests WHERE test_code = ?", (code,))
            row = c.fetchone()
        if not row:
            return bot.send_message(uid, f"❌ Bunday kodli test topilmadi! Qaytadan tekshirib ko'ring.", reply_markup=main_menu(uid))

        title, correct_keys = row[0], json.loads(row[1])
        raw_correct, rash_score, details = 0, 0.0, []

        for i in range(40):
            u = str(answers[i]).strip().lower()
            k = str(correct_keys[i]).strip().lower()
            q_num = i + 1
            
            # To'g'ri Rash ball taqsimoti
            weight = 1.5 if q_num <= 32 else (2.2 if q_num <= 35 else 4.08)
            
            if u != "" and u == k:
                raw_correct += 1
                rash_score += weight
                details.append(f"{q_num}.✅")
            else:
                details.append(f"{q_num}.❌")

        rash_score = round(rash_score, 1)
        percent = round((rash_score / 75.0) * 100, 1)

        # Qat'iy va rasmiy BMBA daraja shkalasi
        if rash_score >= 70.0: daraja = "A+ daraja (A'lo)"
        elif rash_score >= 65.0: daraja = "A daraja (A'lo)"
        elif rash_score >= 60.0: daraja = "B+ daraja (Yaxshi)"
        elif rash_score >= 55.0: daraja = "B daraja (Yaxshi)"
        elif rash_score >= 50.0: daraja = "C+ daraja (Qoniqarli)"
        elif rash_score >= 46.0: daraja = "C daraja (Qoniqarli)"
        else: daraja = "Sertifikat darajasiga yetmadi"

        # Bazaga natijani yozish
        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute("INSERT INTO results (user_id, full_name, test_code, raw_correct, rash_score, percent, daraja, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (uid, message.from_user.full_name, code, raw_correct, rash_score, percent, daraja, datetime.now().strftime("%Y-%m-%d %H:%M")))
            conn.commit()

        # O'quvchi ma'lumotlarini keyingi rasm so'rashda ishlatish uchun saqlash
        user_data[uid] = {
            "test_code": code,
            "title": title,
            "score": rash_score,
            "percent": percent,
            "daraja": daraja,
            "raw_correct": raw_correct,
            "details": details
        }
        
        # Agar 46 balldan yuqori olgan bo'lsa darhol rasm yuklashni so'rab, sertifikatga bog'laymiz
        if rash_score >= 46.0:
            user_states[uid] = "wait_user_photo"
            bot.send_message(
                uid,
                f"📊 <b>NATIJANGIZ (40 TALIK):</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 Oʻquvchi: <b>{message.from_user.full_name}</b>\n"
                f"🔢 Test kodi: <code>{code}</code> ({title})\n"
                f"✅ Toʻgʻri: {raw_correct} / 40 ta\n"
                f"📈 Rash ball: <b>{rash_score} ball</b> ({percent}%)\n"
                f"🎖 Daraja: <b>{daraja}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n" + " | ".join(details) + "\n\n"
                f"📸 <b>Siz sertifikat darajasini qo'lga kiritdingiz!</b>\n\n"
                f"Milliy shablondagi rasmiy sertifikatingizni yuklab olish uchun iltimos shaxsiy **3x4 yoki yuzingiz aniq tushgan oddiy rasmingizni** rasm (photo) ko'rinishida shu yerga yuboring!"
            )
        else:
            # 46 dan past ball olgan bo'lsa
            res_text = (
                f"📊 <b>Sertifikat olish uchun ball yetarli emas (Minimal: 46 ball).</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 Oʻquvchi: {message.from_user.full_name}\n"
                f"📈 Rash ballingiz: <b>{rash_score} ball</b> ({percent}%)\n"
                f"🎖 Holat: {daraja}\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"Ko'proq o'qib, boshqa test kodlari orqali qayta urinib ko'ring!"
            )
            bot.send_message(uid, res_text, reply_markup=main_menu(uid))

# ================= RASH MODULI BO'YICHA RASMLI SERTIFIKAT TAYYORLASH =================
@bot.message_handler(content_types=['photo'], func=lambda m: user_states.get(m.from_user.id) == "wait_user_photo")
def receive_user_photo_cert(message):
    uid = message.from_user.id
    info = user_data.get(uid, {})
    
    # Rasmni vaqtincha saqlab olish
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    temp_photo_path = f"temp_user_{uid}.jpg"
    with open(temp_photo_path, "wb") as new_file:
        new_file.write(downloaded_file)
        
    bot.send_message(uid, "⏳ <b>Milliy Sertifikatingiz tayyorlanmoqda, iltimos biron soniya kuting...</b>")
    
    # Rasm bilan BMBA sertifikatini generatsiya qilish (Pillow ishlatilgan)
    try:
        cert_file = generate_bmba_certificate(
            message.from_user.full_name, 
            info["score"], 
            info["percent"], 
            info["daraja"], 
            temp_photo_path
        )
        
        with open(cert_file, "rb") as cf:
            bot.send_photo(
                uid, 
                cf, 
                caption=f"🎓 <b>Tiriklik darsi muvaffaqiyatli yakunlandi! Milliy darajadagi {info['daraja']} Sertifikatingiz tayyorlandi!</b>\n\n📢 {KANAL_USER}",
                reply_markup=main_menu(uid)
            )
        os.remove(cert_file)
    except Exception as e:
        bot.send_message(uid, f"❌ Sertifikat tayyorlashda xatolik bo'ldi. Hisobot adminga yuborildi.")
        
    if os.path.exists(temp_photo_path):
        os.remove(temp_photo_path)
        
    user_states[uid] = "wait_written_photo"
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("⏭ Yozma ish yoʻq (Oʻtkazib yuborish)"))
    bot.send_message(uid, "📸 <b>Endi esa yozma ish (yechimlar) rasmini shu yerga yuklang (ustoz tekshiruvi uchun):</b>", reply_markup=kb)

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
        f"👤 Oʻquvchi: {message.from_user.full_name}\n"
        f"🆔 ID: <code>{uid}</code> | Test: #{info.get('test_code')}\n"
        f"📈 Joriy ball: {info.get('score')} ball"
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
    bot.send_message(adm_id, f"✍️ Oʻquvchi (ID: {target_uid}) yozma ishi uchun necha ball qoʻshasiz?")
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

# ================= CRM VA GURUHLAR =================
@bot.message_handler(func=lambda m: m.text == "👥 Guruhlarni boshqarish (CRM)")
def crm_groups_menu(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    user_states[uid] = "crm_set_user"
    bot.send_message(
        uid,
        "👥 <b>Oʻquvchini guruhga biriktirish:</b>\nOʻquvchining Telegram <b>ID raqamini</b> yuboring:",
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

# ================= REYTING VA VAZIFALAR =================
@bot.message_handler(func=lambda m: m.text == "🏆 Umumiy Reyting")
def show_global_rating(message):
    if not check_subscription(message.from_user.id): return ask_to_subscribe(message.chat.id)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name, rash_score, raw_correct, daraja FROM results ORDER BY rash_score DESC LIMIT 20")
        rows = c.fetchall()
    if not rows: return bot.send_message(message.chat.id, "📭 Hali natijalar yoʻq.")
    medals = ["🥇", "🥈", "🥉"]
    text = "🏆 <b>A+ KIMYO | TOP-20 REYTING:</b>\n━━━━━━━━━━━━━━━━━━\n"
    for idx, r in enumerate(rows, 1):
        m = medals[idx - 1] if idx <= 3 else f"<b>{idx}.</b>"
        text += f"{m} {r[0]} — <b>{round(r[1], 1)} ball</b> ({r[2]}/40) | {r[3]}\n"
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "📑 Vazifa nazorati (Qilgan/Qilmagan)")
def ask_check_test_code(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    user_states[uid] = "check_hw_code"
    bot.send_message(uid, "🔢 6 xonali maxsus test kodini kiriting:", reply_markup=cancel_kb())

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
        text += f"  • {r[1]} — <b>{round(r[2], 1)} ball</b>\n"
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
        ws.title = "Reyting"
        ws.append(["№", "F.I.Sh.", "Guruh", "Telefon", "Test Kodi", "To'g'ri", "Umumiy Ball", "Holati", "Vaqti"])
        for idx, r in enumerate(rows, 1):
            holat = "Bajarilgan (" + r[6] + ")" if r[3] != 0 else "❌ Qilinmagan"
            ws.append([idx, r[0], r[1], r[2], r[3] or "-", f"{r[4]}/40" if r[3] else "-", round(r[5], 1), holat, r[7]])
        wb.save(filename)
        with open(filename, "rb") as f:
            bot.send_document(uid, f, caption="📊 Excel elektron jadval")

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
            rc[0].text, rc[1].text, rc[2].text, rc[3].text, rc[4].text = str(idx), str(r[0]), str(r[1]), str(round(r[5], 1)), ("Bajarilgan" if r[3] != 0 else "Qilinmagan")
        doc.save(filename)
        with open(filename, "rb") as f:
            bot.send_document(uid, f, caption="📄 Word hujjat")

    elif fmt == "pdf":
        filename = "A_Plus_Kimyo_Hisobot.pdf"
        c_pdf = canvas.Canvas(filename, pagesize=letter)
        c_pdf.drawString(50, 750, "A+ KIMYO | O'QUVCHILAR REYTINGI")
        y = 720
        for idx, r in enumerate(rows[:32], 1):
            status = "Bajarilgan" if r[3] != 0 else "Qilinmagan"
            c_pdf.drawString(50, y, f"{idx}. {r[0]} [{r[1]}] | Ball: {round(r[5], 1)} | {status}")
            y -= 20
        c_pdf.save()
        with open(filename, "rb") as f:
            bot.send_document(uid, f, caption="📑 PDF fayl")
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
        c.execute("SELECT test_code, title FROM tests ORDER BY created_at DESC LIMIT 15")
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

# ================= FLASK WEB SERVER VA INTERAKTIV TITR =================
@app.route("/")
def index():
    return "A+ Kimyo Bot 24/7 ishlamoqda!"

@app.route("/titr")
def serve_titr():
    return render_template_string(TITR_HTML)

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web, daemon=True).start()
    bot.remove_webhook()
    print("A+ Kimyo Super Bot ishga tushdi...")
    bot.infinity_polling(none_stop=True, interval=0, timeout=20)
