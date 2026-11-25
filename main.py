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
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo
)
from group_guard import register_guard

# Hisobot va Sertifikat kutubxonalari
import openpyxl
from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from PIL import Image, ImageOps, ImageDraw

# ================= SOZLAMALAR =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "SIZNING_YANGI_BOT_TOKENINGIZ")
ADMIN_PAROL = os.environ.get("ADMIN_PAROL", "kimyo2026")
ADMIN_LICHKA = "@onlyibrohimov"
KANAL_USER = "@kimyo_sertifkat_uchun"
KANAL_LINK = "https://t.me/kimyo_sertifkat_uchun"
KARTA_RAQAM = "9860 3501 4209 7954"
KARTA_EGASI = "Azizbek Ibrohimov"

# Yopiq o'quvchilar guruhi ID si (Bot ushbu guruhda ADMIN bo'lishi shart!)
YOPIQ_GURUH_ID = int(os.environ.get("YOPIQ_GURUH_ID", "-1001234567890"))

RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://e-kimyo-kurs-bot.onrender.com")

# O'zbekiston vaqt mintaqasi (UTC+5)
UZ_TZ = timezone(timedelta(hours=5))

def uz_now():
    return datetime.now(UZ_TZ).replace(tzinfo=None)

def next_8pm_deadline():
    """Keyingi kechki soat 20:00 (8:00 PM) vaqtini hisoblaydi"""
    now = uz_now()
    target = now.replace(hour=20, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return target

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

# Qorovulni ulash
register_guard(bot)

user_states = {}
user_data = {}

# Jonli dars yo'qlamasi holati
LIVE_ATTENDANCE = {
    "is_open": False,
    "expires_at": None,
    "session_id": None
}

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
        body { background-color: #17212b; color: #ffffff; padding-bottom: 95px; }
        .header { position: sticky; top: 0; background: #242f3d; padding: 12px 15px; z-index: 100; border-bottom: 1px solid #0e1621; display: flex; justify-content: space-between; align-items: center; }
        .header h2 { font-size: 16px; color: #6ab3f3; }
        .cols-header { display: grid; grid-template-columns: 45px repeat(4, 1fr); text-align: center; padding: 8px 10px; background: #1c2733; font-weight: bold; color: #8b9bb4; font-size: 14px; position: sticky; top: 45px; z-index: 99; }
        .q-row { display: grid; grid-template-columns: 45px repeat(4, 1fr); align-items: center; padding: 6px 10px; border-bottom: 1px solid #202b36; }
        .q-num { font-weight: bold; color: #8b9bb4; text-align: center; font-size: 15px; }
        .opt-btn { width: 42px; height: 42px; border-radius: 50%; border: 2px solid #3d4d5d; background: #242f3d; color: #fff; font-weight: bold; font-size: 15px; margin: 0 auto; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: 0.15s; user-select: none; }
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
        .footer { position: fixed; bottom: 0; left: 0; right: 0; background: #242f3d; padding: 12px 15px; border-top: 1px solid #0e1621; z-index: 101; }
        .submit-btn { width: 100%; padding: 13px; background: #3390ec; color: #fff; border: none; border-radius: 10px; font-size: 16px; font-weight: bold; cursor: pointer; }
        .code-box { padding: 12px 15px; background: #242f3d; margin: 10px; border-radius: 10px; border: 1px solid #3390ec; }
        .code-box input { width: 100%; padding: 10px; margin-top: 6px; border-radius: 8px; border: 1px solid #3d4d5d; background: #17212b; color: #fff; font-size: 16px; outline: none; }
    </style>
</head>
<body>

<div class="header">
    <h2 id="page-title">A+ Kimyo | 40 talik Titr</h2>
    <span id="counter" style="font-size: 13px; color: #8b9bb4; font-weight: bold;">0 / 40</span>
</div>

<div class="code-box">
    <label id="code-label" style="font-size: 13px; color: #6ab3f3; font-weight: bold;">Test kodini kiriting:</label>
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
    <button class="submit-btn" id="send-btn" onclick="submitTitr()">✅ Javoblarni yuborish</button>
</div>

<script>
    const tg = window.Telegram.WebApp;
    tg.expand();

    const urlParams = new URLSearchParams(window.location.search);
    const mode = urlParams.get('mode') || 'solve';

    if (mode === 'create') {
        document.getElementById('page-title').innerText = "➕ Yangi Test Yaratish (Titr)";
        document.getElementById('code-label').innerText = "Test nomini kiriting (Kechki 20:00 gacha ochiq bo'ladi):";
        document.getElementById('test-meta').placeholder = "Masalan: Milliy Sertifikat #1";
        document.getElementById('send-btn').innerText = "💾 Test kalitlarini saqlash";
    }

    const answers = new Array(40).fill("");

    function updateCounter() {
        const filled = answers.filter(x => x !== "").length;
        document.getElementById('counter').innerText = `${filled} / 40`;
    }

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
                joined_at TEXT,
                last_active TEXT,
                paid_until TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)
        existing_cols = [row[1] for row in c.execute("PRAGMA table_info(users)").fetchall()]
        now_str = uz_now().strftime("%Y-%m-%d %H:%M")
        trial_str = (uz_now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
        if "last_active" not in existing_cols:
            c.execute(f"ALTER TABLE users ADD COLUMN last_active TEXT DEFAULT '{now_str}'")
        if "paid_until" not in existing_cols:
            c.execute(f"ALTER TABLE users ADD COLUMN paid_until TEXT DEFAULT '{trial_str}'")
        if "is_active" not in existing_cols:
            c.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")

        c.execute("""
            CREATE TABLE IF NOT EXISTS attendance_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                full_name TEXT,
                session_id TEXT,
                checked_at TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS tests (
                test_code INTEGER PRIMARY KEY,
                title TEXT,
                answers TEXT,
                created_at TEXT,
                expires_at TEXT
            )
        """)
        test_cols = [row[1] for row in c.execute("PRAGMA table_info(tests)").fetchall()]
        if "expires_at" not in test_cols:
            default_exp = next_8pm_deadline().strftime("%Y-%m-%d %H:%M")
            c.execute(f"ALTER TABLE tests ADD COLUMN expires_at TEXT DEFAULT '{default_exp}'")

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

def update_user_activity(user_id):
    now_str = uz_now().strftime("%Y-%m-%d %H:%M")
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET last_active = ? WHERE user_id = ?", (now_str, user_id))
        conn.commit()

def db_add_user(user_id, full_name, username, ref_id=0):
    now_str = uz_now().strftime("%Y-%m-%d %H:%M")
    trial_str = (uz_now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        exists = c.fetchone()
        if not exists:
            c.execute(
                """INSERT INTO users 
                   (user_id, full_name, username, referred_by, joined_at, last_active, paid_until, is_active) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
                (user_id, full_name, username or "", ref_id, now_str, now_str, trial_str)
            )
            if ref_id and ref_id != user_id:
                c.execute("UPDATE users SET bonus_points = bonus_points + 10 WHERE user_id = ?", (ref_id,))
                try:
                    bot.send_message(ref_id, f"🎉 <b>Yangi referal!</b> Doʻstingiz <b>{full_name}</b> botga qoʻshildi va sizga <b>+10 bonus ball</b> berildi!")
                except Exception:
                    pass
        else:
            c.execute("UPDATE users SET last_active = ? WHERE user_id = ?", (now_str, user_id))
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

# ================= 30 KUNLIK TO'LOV MUDDATI TUGAGANLARNI CHETLATISH =================
def check_expired_subscriptions(manual_admin_id=None):
    now = uz_now()
    kicked_list = []

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("""
            SELECT user_id, full_name, paid_until, group_name 
            FROM users 
            WHERE is_admin = 0 AND is_active = 1
        """)
        students = c.fetchall()

        for uid, name, paid_until_str, grp in students:
            if not paid_until_str:
                continue
            try:
                paid_until = datetime.strptime(paid_until_str, "%Y-%m-%d %H:%M")
            except ValueError:
                continue

            if now > paid_until:
                try:
                    bot.ban_chat_member(YOPIQ_GURUH_ID, uid)
                except Exception as e:
                    print(f"Guruhdan chetlatishda xato ({uid}): {e}")

                try:
                    bot.send_message(
                        uid,
                        f"⛔ <b>Hurmatli {name}!</b>\n\n"
                        f"Sizning <b>30 kunlik kurs obuna muddatingiz tugadi</b> va shu sababli yopiq guruhdan chetlatildingiz.\n\n"
                        f"🔄 Guruhga qaytish uchun <b>«✍️ Kursga yozilish»</b> tugmasi orqali toʻlov chekini yuboring. "
                        f"Admin tasdiqlashi bilan sizga <b>yangi bir martalik kirish havolasi</b> yuboriladi!"
                    )
                except Exception:
                    pass

                c.execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (uid,))
                kicked_list.append(f"• <b>{name}</b> [{grp}] (Muddati: {paid_until_str})")

        conn.commit()

    if kicked_list:
        report = "🚫 <b>30 KUNLIK TOʻLOV MUDDATI TUGAB CHETLATILGANLAR:</b>\n━━━━━━━━━━━━━━━━━━\n" + "\n".join(kicked_list)
        targets = [manual_admin_id] if manual_admin_id else db_get_admins()
        for adm in targets:
            try:
                bot.send_message(adm, report)
            except Exception:
                pass
    elif manual_admin_id:
        bot.send_message(manual_admin_id, "✅ Hozircha barcha oʻquvchilarning 30 kunlik toʻlov muddati joyida!")

def background_watcher():
    """Har 10 daqiqada serverni uyg'otadi va har 30 daqiqada to'lov muddatini tekshiradi"""
    counter = 0
    while True:
        time.sleep(600)
        counter += 1
        try:
            requests.get(RENDER_URL, timeout=10)
        except Exception as e:
            print(f"Keep-alive ping xatosi: {e}")

        if counter % 3 == 0:
            try:
                check_expired_subscriptions()
            except Exception as e:
                print(f"Watcher xatosi: {e}")

# ================= BMBA (DTM) SERTIFIKAT GENERATORI =================
def generate_bmba_certificate(full_name, score, percent, level, photo_path):
    cert_path = f"bmba_cert_{random.randint(1000, 9999)}.png"
    W, H = 842, 1191

    img = Image.new("RGB", (W, H), color="white")
    draw = ImageDraw.Draw(img)

    draw.rectangle([15, 15, W - 15, H - 15], outline="#1a1a1a", width=3)
    draw.line([30, 195, W - 30, 195], fill="#0a0a0a", width=2)

    draw.ellipse([386, 35, 456, 105], outline="#1b5e20", width=3)
    draw.ellipse([391, 40, 451, 100], fill="#0d47a1")

    draw.text((150, 120), "O'ZBEKISTON RESPUBLIKASI OLIY TA'LIM, FAN VA INNOVATSIYALAR VAZIRLIGI", fill="black")
    draw.text((195, 138), "HUZURIDAGI BILIM VA MALAKALARNI BAHOLASH AGENTLIGI", fill="black")

    draw.text((220, 210), "UMUMTA'LIM FANINI BILISH DARAJASI TO'G'RISIDA", fill="black")
    draw.text((360, 230), "SERTIFIKAT", fill="black")

    cert_num = f"UZ26 {random.randint(100000, 999999)}"
    draw.text((50, 280), "Sertifikat raqami:", fill="black")
    draw.text((180, 280), cert_num, fill="black")
    draw.line([30, 310, W - 30, 310], fill="#cccccc", width=1)

    user_code = str(random.randint(1000000, 9999999))
    draw.text((50, 330), "Talabgoringiz shaxsiy kodi:", fill="black")
    draw.text((260, 330), user_code, fill="black")

    name_parts = full_name.split()
    f_name = name_parts[0].upper() if len(name_parts) > 0 else "FOZILOV"
    i_name = name_parts[1].upper() if len(name_parts) > 1 else "SHOXRUX"
    o_name = (name_parts[2].upper() + " O'G'LI") if len(name_parts) > 2 else "SHAVKAT O'G'LI"

    draw.text((50, 365), "Familiyasi:", fill="black")
    draw.text((200, 365), f_name, fill="black")

    draw.text((50, 395), "Ismi:", fill="black")
    draw.text((200, 395), i_name, fill="black")

    draw.text((50, 425), "Otasining ismi:", fill="black")
    draw.text((200, 425), o_name, fill="black")

    draw.line([30, 460, W - 30, 460], fill="#cccccc", width=1)

    try:
        user_img = Image.open(photo_path)
        user_img = ImageOps.fit(user_img, (130, 160))
        img.paste(user_img, (650, 330))
        draw.rectangle([650, 330, 780, 490], outline="#cccccc", width=1)
    except Exception:
        draw.rectangle([650, 330, 780, 490], outline="red", width=1)
        draw.text((670, 400), "Rasmda xato", fill="red")

    draw.text((50, 480), "Umumta'lim fani:", fill="black")
    draw.text((380, 480), "Kimyo (O'zbekiston)", fill="black")

    draw.text((50, 510), "Umumiy to'plagan ball (Rash shkalasi):", fill="black")
    draw.text((380, 510), f"{score}", fill="black")

    draw.text((50, 540), "Umumiy ballga nisbatan foiz ko'rsatkichi:", fill="black")
    draw.text((380, 540), f"{percent} %", fill="black")

    draw.text((50, 570), "Sertifikat darajasi:", fill="black")
    draw.text((380, 570), level, fill="black")

    draw.line([30, 610, W - 30, 610], fill="#cccccc", width=1)

    t_test = round(score * 0.72, 2)
    t_yozma = round(score * 0.28, 2)
    draw.text((50, 630), "Test sinovi natijasi:", fill="black")
    draw.text((650, 630), f"{t_test}", fill="black")

    draw.text((50, 660), "Yozma ish natijasi:", fill="black")
    draw.text((650, 660), f"{t_yozma}", fill="black")

    s_sana = uz_now().strftime("%d.%m.%Y")
    m_sana = (uz_now().replace(year=uz_now().year + 3)).strftime("%d.%m.%Y")

    draw.line([30, 850, W - 30, 850], fill="#0a0a0a", width=1)
    draw.text((50, 880), f"Berilgan sanasi: {s_sana}", fill="black")
    draw.text((450, 880), f"Amal qilish muddati: {m_sana}", fill="black")

    draw.rectangle([340, 920, 440, 1020], fill="black")
    draw.rectangle([350, 930, 430, 1010], fill="white")
    draw.rectangle([375, 955, 405, 985], fill="black")

    draw.text((200, 960), "Direktor", fill="black")
    draw.text((500, 960), "M.KARIMOV", fill="black")

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
        KeyboardButton("✅ Kunlik yoʻqlama"),
        KeyboardButton("🏆 Umumiy Reyting"),
        KeyboardButton("🎬 Namuna darslar"),
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
        KeyboardButton("⏱ Jonli dars yoʻqlamasini ochish"),
        KeyboardButton("📋 Bugungi yoʻqlama roʻyxati"),
        KeyboardButton("🚫 Muddati tugaganlarni chetlatish"),
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
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        bot.send_message(uid, "✅ <b>Obuna tasdiqlandi!</b> Xush kelibsiz!", reply_markup=main_menu(uid))
    else:
        bot.answer_callback_query(call.id, "❌ Siz hali kanalga obuna boʻlmadingiz!", show_alert=True)

# ================= /START VA ASOSIY BUYRUQLAR =================
@bot.message_handler(chat_types=["private"], commands=['start'])
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
        f"🔹 <b>📊 Elektron Titr:</b> 40 talik vazifa/testni topshirish (Kechki 20:00 gacha ochiq)\n"
        f"🔹 <b>✅ Kunlik yoʻqlama:</b> Jonli dars paytida belgilangan vaqtda davomatdan oʻting\n"
        f"🔹 <b>🎬 Namuna darslar:</b> Bepul video darslar va qoʻllanmalar\n"
        f"🔹 <b>✍️ Kursga yozilish:</b> 30 kunlik yopiq guruhga obuna boʻlish\n\n"
        f"👇 Quyidagi menyudan kerakli boʻlimni tanlang:"
    )
    bot.send_message(uid, text, reply_markup=main_menu(uid))

@bot.message_handler(chat_types=["private"], commands=['admin'])
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
        bot.send_message(uid, "🔒 Parolni kiriting: <code>/admin PAROL</code>")

@bot.message_handler(chat_types=["private"], func=lambda m: m.text in ["❌ Bekor qilish", "🔙 Asosiy menyu"])
def cancel_action(message):
    uid = message.from_user.id
    user_states.pop(uid, None)
    bot.send_message(uid, "🏠 Asosiy menyu:", reply_markup=main_menu(uid))

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "⚙️ Admin Panel")
def open_admin(message):
    if db_is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⚙️ <b>Admin Panel:</b>", reply_markup=admin_menu())

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📞 Admin bilan aloqa")
def contact_admin(message):
    if not check_subscription(message.from_user.id):
        return ask_to_subscribe(message.chat.id)
    bot.send_message(
        message.chat.id,
        f"👨‍🏫 <b>Muallif va kurs rahbari:</b> Azizbek Ibrohimov\n"
        f"💬 <b>Shaxsiy lichka:</b> {ADMIN_LICHKA}\n"
        f"📢 <b>Kanalimiz:</b> {KANAL_USER}"
    )

# ================= JONLI DARS PAYTIDAGI VAQTLI YO'QLAMA =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "⏱ Jonli dars yoʻqlamasini ochish")
def adm_open_attendance_ask(message):
    uid = message.from_user.id
    if not db_is_admin(uid):
        return
    user_states[uid] = "wait_att_minutes"
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    kb.add(
        KeyboardButton("5"), KeyboardButton("10"), KeyboardButton("15"),
        KeyboardButton("20"), KeyboardButton("30"), KeyboardButton("❌ Bekor qilish")
    )
    bot.send_message(
        uid,
        "⏱ <b>Jonli dars yoʻqlamasi necha daqiqa ochiq tursin?</b>\n"
        "Daqiqa sonini tanlang yoki yozing (masalan: <code>10</code>):",
        reply_markup=kb
    )

@bot.message_handler(chat_types=["private"], func=lambda m: user_states.get(m.from_user.id) == "wait_att_minutes")
def adm_open_attendance_start(message):
    uid = message.from_user.id
    if not message.text.isdigit() or int(message.text) <= 0:
        return bot.send_message(uid, "⚠️ Faqat musbat raqam kiriting (masalan: 10):")

    minutes = int(message.text)
    now = uz_now()
    expires = now + timedelta(minutes=minutes)
    session_id = now.strftime("%Y-%m-%d_%H:%M")

    LIVE_ATTENDANCE["is_open"] = True
    LIVE_ATTENDANCE["expires_at"] = expires
    LIVE_ATTENDANCE["session_id"] = session_id
    user_states.pop(uid, None)

    exp_time_str = expires.strftime("%H:%M")
    bot.send_message(
        uid,
        f"✅ <b>Jonli dars yoʻqlamasi ochildi!</b>\n"
        f"⏳ Tugash vaqti: <b>{exp_time_str}</b> ({minutes} daqiqa)\n"
        f"📢 Barcha aktiv oʻquvchilarga xabar yuborilmoqda...",
        reply_markup=admin_menu()
    )

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE is_admin = 0 AND is_active = 1")
        students = [r[0] for r in c.fetchall()]

    alert_text = (
        f"🔴 <b>JONLI DARS BOSHLANDI!</b>\n\n"
        f"⏱ Davomatdan oʻtish uchun <b>{minutes} daqiqa</b> vaqt berildi (soat <b>{exp_time_str}</b> gacha).\n"
        f"👇 Hoziroq pastdagi <b>«✅ Kunlik yoʻqlama»</b> tugmasini bosing!"
    )
    for st_id in students:
        try:
            bot.send_message(st_id, alert_text)
        except Exception:
            pass

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "✅ Kunlik yoʻqlama")
def daily_attendance(message):
    uid = message.from_user.id
    if not check_subscription(uid):
        return ask_to_subscribe(uid)

    now = uz_now()
    if not LIVE_ATTENDANCE["is_open"] or not LIVE_ATTENDANCE["expires_at"] or now > LIVE_ATTENDANCE["expires_at"]:
        LIVE_ATTENDANCE["is_open"] = False
        return bot.send_message(
            uid,
            "⏳ <b>Hozircha yoʻqlama yopiq!</b>\n"
            "Yoʻqlamadan faqat jonli dars paytida ustoz ruxsat bergan daqiqalar ichida oʻtish mumkin."
        )

    session_id = LIVE_ATTENDANCE["session_id"]
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM attendance_logs WHERE user_id = ? AND session_id = ?", (uid, session_id))
        if c.fetchone():
            return bot.send_message(uid, "✅ Siz ushbu jonli dars yoʻqlamasidan oʻtib boʻlgansiz! 👍")

        c.execute("SELECT full_name, bonus_points FROM users WHERE user_id = ?", (uid,))
        u = c.fetchone()
        if not u:
            db_add_user(uid, message.from_user.full_name, message.from_user.username)
            full_name, pts = message.from_user.full_name, 0
        else:
            full_name, pts = u

        new_pts = pts + 5
        c.execute("UPDATE users SET last_active = ?, bonus_points = ? WHERE user_id = ?", (now.strftime("%Y-%m-%d %H:%M"), new_pts, uid))
        c.execute(
            "INSERT INTO attendance_logs (user_id, full_name, session_id, checked_at) VALUES (?, ?, ?, ?)",
            (uid, full_name, session_id, now_str)
        )
        conn.commit()

    rem_sec = int((LIVE_ATTENDANCE["expires_at"] - now).total_seconds())
    rem_min = max(1, rem_sec // 60)

    bot.send_message(
        uid,
        f"✅ <b>Jonli dars yoʻqlamasi qabul qilindi!</b>\n"
        f"🕒 Vaqt: <b>{now.strftime('%H:%M:%S')}</b> (Yopilishiga ~{rem_min} daq qoldi)\n"
        f"💎 Sizga <b>+5 bonus ball</b> berildi. Jami: <b>{new_pts} ball</b>"
    )

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📋 Bugungi yoʻqlama roʻyxati")
def admin_daily_list(message):
    uid = message.from_user.id
    if not db_is_admin(uid):
        return

    session_id = LIVE_ATTENDANCE.get("session_id")
    if not session_id:
        return bot.send_message(uid, "📭 Hali birorta ham jonli dars yoʻqlamasi ochilmagan.")

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, full_name, checked_at FROM attendance_logs WHERE session_id = ? ORDER BY id ASC", (session_id,))
        present = c.fetchall()
        present_ids = {r[0] for r in present}

        c.execute("SELECT user_id, full_name, group_name FROM users WHERE is_admin = 0 AND is_active = 1")
        all_active = c.fetchall()

    absent = [u for u in all_active if u[0] not in present_ids]

    text = f"📋 <b>JONLI DARS DAVOMATI ({session_id}):</b>\n━━━━━━━━━━━━━━━━━━\n"
    text += f"✅ <b>Vaqtida kirganlar ({len(present)} ta):</b>\n"
    for p in present[:40]:
        t_only = p[2].split()[1] if " " in p[2] else p[2]
        text += f"  • {p[1]} — <code>{t_only}</code>\n"

    text += f"\n❌ <b>Kirmagan aktiv oʻquvchilar ({len(absent)} ta):</b>\n"
    for a in absent[:40]:
        text += f"  • {a[1]} [{a[2]}]\n"

    bot.send_message(uid, text)

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "🚫 Muddati tugaganlarni chetlatish")
def manual_expired_check(message):
    uid = message.from_user.id
    if not db_is_admin(uid):
        return
    bot.send_message(uid, "⏳ 30 kunlik toʻlov muddati tugagan oʻquvchilar tekshirilmoqda...")
    check_expired_subscriptions(manual_admin_id=uid)

# ================= SHAXSIY KABINET VA REFERAL =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "👤 Shaxsiy kabinet")
def user_profile(message):
    uid = message.from_user.id
    if not check_subscription(uid):
        return ask_to_subscribe(uid)
    update_user_activity(uid)

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name, phone, group_name, bonus_points, paid_until, is_active FROM users WHERE user_id = ?", (uid,))
        u = c.fetchone()
        c.execute("SELECT COUNT(*), COALESCE(AVG(rash_score), 0), COALESCE(MAX(rash_score), 0) FROM results WHERE user_id = ?", (uid,))
        stats = c.fetchone()

    status_txt = "🟢 Aktiv (Guruhda ruxsat bor)" if u[5] == 1 else "🔴 Muddati tugagan (Guruhdan chetlatilgan)"
    text = (
        f"👤 <b>SHAXSIY KABINET</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📛 <b>Ism:</b> {u[0]}\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"👥 <b>Guruh:</b> {u[2]}\n"
        f"📞 <b>Tel:</b> {u[1] or 'Kiritilmagan'}\n"
        f"💎 <b>Bonus ballar:</b> <b>{u[3]} ball</b>\n"
        f"📅 <b>Toʻlov muddati:</b> {u[4] or 'Belgilanmagan'}\n"
        f"📡 <b>Holat:</b> {status_txt}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Ishlangan testlar:</b> {stats[0]} ta\n"
        f"📈 <b>Oʻrtacha ball:</b> {round(stats[1], 1)} ball\n"
        f"🏆 <b>Rekord natija:</b> {round(stats[2], 1)} ball"
    )
    bot.send_message(uid, text)

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "🔗 Doʻstlarni taklif qilish")
def referral_link(message):
    uid = message.from_user.id
    if not check_subscription(uid):
        return ask_to_subscribe(uid)
    update_user_activity(uid)
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

# ================= NAMUNA DARSLAR =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "🎬 Namuna darslar")
def show_sample_lessons(message):
    if not check_subscription(message.from_user.id):
        return ask_to_subscribe(message.chat.id)
    update_user_activity(message.from_user.id)
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
    if not row:
        return bot.answer_callback_query(call.id, "Topilmadi!")

    title, desc, file_id, ftype = row
    caption = f"🎬 <b>{title}</b>\n\n{desc}\n\n👨‍🏫 {ADMIN_LICHKA} | 📢 {KANAL_USER}"
    if ftype == "video":
        bot.send_video(call.message.chat.id, file_id, caption=caption)
    elif ftype == "document":
        bot.send_document(call.message.chat.id, file_id, caption=caption)
    elif ftype == "photo":
        bot.send_photo(call.message.chat.id, file_id, caption=caption)
    bot.answer_callback_query(call.id)

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "🎬 Namuna dars qoʻshish")
def adm_add_lesson_1(message):
    uid = message.from_user.id
    if not db_is_admin(uid):
        return
    user_states[uid] = "les_title"
    bot.send_message(uid, "🎬 <b>Namuna dars nomini kiriting:</b>", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], func=lambda m: user_states.get(m.from_user.id) == "les_title")
def adm_add_lesson_2(message):
    uid = message.from_user.id
    user_data[uid] = {"title": message.text}
    user_states[uid] = "les_desc"
    bot.send_message(uid, "📝 <b>Izoh yozing</b> (yoki <code>-</code> yuboring):")

@bot.message_handler(chat_types=["private"], func=lambda m: user_states.get(m.from_user.id) == "les_desc")
def adm_add_lesson_3(message):
    uid = message.from_user.id
    user_data[uid]["desc"] = "" if message.text == "-" else message.text
    user_states[uid] = "les_file"
    bot.send_message(uid, "📎 Endi <b>Video, PDF yoki Rasmni</b> yuboring:")

@bot.message_handler(chat_types=["private"], content_types=['video', 'document', 'photo'], func=lambda m: user_states.get(m.from_user.id) == "les_file")
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
            (info["title"], info["desc"], fid, ftype, uz_now().strftime("%Y-%m-%d %H:%M"))
        )
        conn.commit()
    user_states.pop(uid, None)
    bot.send_message(uid, f"✅ <b>«{info['title']}»</b> qoʻshildi!", reply_markup=admin_menu())

# ================= WEB APP (40 TALIK TITR — KECHKI 20:00 GACHA OCHIQ) =================
@bot.message_handler(content_types=['web_app_data'])
def handle_webapp_data(message):
    uid = message.from_user.id
    if not check_subscription(uid):
        return ask_to_subscribe(uid)

    update_user_activity(uid)
    payload = json.loads(message.web_app_data.data)
    mode, meta, answers = payload.get("mode"), payload.get("meta"), payload.get("answers")

    # 1. ADMIN TEST YARATSA (Kechki soat 20:00 gacha muddat belgilanadi)
    if mode == "create":
        if not db_is_admin(uid):
            return

        while True:
            code = random.randint(100000, 999999)
            with sqlite3.connect("database.db") as conn:
                c = conn.cursor()
                c.execute("SELECT test_code FROM tests WHERE test_code = ?", (code,))
                if not c.fetchone():
                    break

        now_str = uz_now().strftime("%Y-%m-%d %H:%M")
        deadline_dt = next_8pm_deadline()
        deadline_str = deadline_dt.strftime("%Y-%m-%d %H:%M")

        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO tests (test_code, title, answers, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (code, meta, json.dumps(answers), now_str, deadline_str)
            )
            conn.commit()

        bot.send_message(
            uid,
            f"✅ <b>Yangi 40 talik Vazifa/Test yaratildi!</b>\n\n"
            f"🔢 <b>Maxsus Test kodi:</b> <code>{code}</code>\n"
            f"📘 Mavzu: <b>{meta}</b>\n"
            f"⏰ <b>Yopilish vaqti:</b> <code>{deadline_str}</code> (kechki 20:00 da avtomatik yopiladi)\n\n"
            f"Oʻquvchilar ushbu kodni kiritib belgilangan vaqtgacha vazifani topshirishadi.",
            reply_markup=admin_menu()
        )

    # 2. O'QUVCHI VAZIFA/TEST TOPSHIRSA (Kechki 20:00 dan o'tgan-o'tmaganini tekshiramiz)
    elif mode == "solve":
        if not meta.isdigit():
            return bot.send_message(uid, "⚠️ Test kodi faqat raqam boʻlishi kerak!", reply_markup=main_menu(uid))
        code = int(meta)
        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute("SELECT title, answers, expires_at FROM tests WHERE test_code = ?", (code,))
            row = c.fetchone()
        if not row:
            return bot.send_message(uid, "❌ Bunday kodli test topilmadi! Qaytadan tekshirib ko'ring.", reply_markup=main_menu(uid))

        title, correct_keys_json, expires_at_str = row

        # Muddatni tekshirish (kechki 20:00 da yopiladi)
        if expires_at_str:
            try:
                exp_dt = datetime.strptime(expires_at_str, "%Y-%m-%d %H:%M")
                if uz_now() > exp_dt:
                    return bot.send_message(
                        uid,
                        f"⛔ <b>VAZIFA TOPSHIRISH VAQTI TUGAGAN!</b>\n\n"
                        f"📘 Mavzu: <b>{title}</b> (#{code})\n"
                        f"⏰ Yopilgan vaqti: <code>{expires_at_str}</code> (kechki 20:00 da yopilgan)\n\n"
                        f"Afsuski, muddat oʻtib ketgani sababli javoblar qabul qilinmaydi.",
                        reply_markup=main_menu(uid)
                    )
            except ValueError:
                pass

        correct_keys = json.loads(correct_keys_json)
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

        rash_score = round(rash_score, 1)
        percent = round((rash_score / 75.0) * 100, 1)

        if rash_score >= 70.0:
            daraja = "A+ daraja (A'lo)"
        elif rash_score >= 65.0:
            daraja = "A daraja (A'lo)"
        elif rash_score >= 60.0:
            daraja = "B+ daraja (Yaxshi)"
        elif rash_score >= 55.0:
            daraja = "B daraja (Yaxshi)"
        elif rash_score >= 50.0:
            daraja = "C+ daraja (Qoniqarli)"
        elif rash_score >= 46.0:
            daraja = "C daraja (Qoniqarli)"
        else:
            daraja = "Sertifikat darajasiga yetmadi"

        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO results (user_id, full_name, test_code, raw_correct, rash_score, percent, daraja, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (uid, message.from_user.full_name, code, raw_correct, rash_score, percent, daraja, uz_now().strftime("%Y-%m-%d %H:%M"))
            )
            conn.commit()

        user_data[uid] = {
            "test_code": code,
            "title": title,
            "score": rash_score,
            "percent": percent,
            "daraja": daraja,
            "raw_correct": raw_correct,
            "details": details,
            "expires_at": expires_at_str
        }

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
                f"Milliy shablondagi rasmiy sertifikatingizni yuklab olish uchun iltimos shaxsiy <b>3x4 yoki yuzingiz aniq tushgan oddiy rasmingizni</b> rasm (photo) ko'rinishida shu yerga yuboring!"
            )
        else:
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
@bot.message_handler(chat_types=["private"], content_types=['photo'], func=lambda m: user_states.get(m.from_user.id) == "wait_user_photo")
def receive_user_photo_cert(message):
    uid = message.from_user.id
    info = user_data.get(uid, {})

    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    temp_photo_path = f"temp_user_{uid}.jpg"
    with open(temp_photo_path, "wb") as new_file:
        new_file.write(downloaded_file)

    bot.send_message(uid, "⏳ <b>Milliy Sertifikatingiz tayyorlanmoqda, iltimos biron soniya kuting...</b>")

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
                caption=f"🎓 <b>Milliy darajadagi {info['daraja']} Sertifikatingiz tayyorlandi!</b>\n\n📢 {KANAL_USER}",
                reply_markup=main_menu(uid)
            )
        os.remove(cert_file)
    except Exception:
        bot.send_message(uid, "❌ Sertifikat tayyorlashda xatolik bo'ldi. Hisobot adminga yuborildi.")

    if os.path.exists(temp_photo_path):
        os.remove(temp_photo_path)

    user_states[uid] = "wait_written_photo"
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("⏭ Yozma ish yoʻq (Oʻtkazib yuborish)"))
    bot.send_message(uid, "📸 <b>Endi esa yozma ish (yechimlar) rasmini shu yerga yuklang (ustoz tekshiruvi uchun):</b>", reply_markup=kb)

# ================= YOZMA ISH RASMINI QABUL QILISH (BU HAM KECHKI 20:00 DA YOPILADI) =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "⏭ Yozma ish yoʻq (Oʻtkazib yuborish)")
def skip_written_photo(message):
    user_states.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "✅ Test yakunlandi!", reply_markup=main_menu(message.from_user.id))

@bot.message_handler(chat_types=["private"], content_types=['photo'], func=lambda m: user_states.get(m.from_user.id) == "wait_written_photo")
def receive_written_photo(message):
    uid = message.from_user.id
    update_user_activity(uid)
    info = user_data.get(uid, {})

    exp_str = info.get("expires_at")
    if exp_str:
        try:
            if uz_now() > datetime.strptime(exp_str, "%Y-%m-%d %H:%M"):
                user_states.pop(uid, None)
                return bot.send_message(
                    uid,
                    f"⛔ <b>Yozma ish yuborish vaqti tugagan!</b> (Kechki 20:00 da yopilgan: <code>{exp_str}</code>)",
                    reply_markup=main_menu(uid)
                )
        except ValueError:
            pass

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
        try:
            bot.send_photo(adm, photo_id, caption=caption, reply_markup=kb)
        except Exception:
            pass
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

@bot.message_handler(chat_types=["private"], func=lambda m: user_states.get(m.from_user.id) == "adm_give_w_score")
def save_written_bonus(message):
    adm_id = message.from_user.id
    try:
        bonus = float(message.text.replace(",", "."))
    except ValueError:
        return bot.send_message(adm_id, "⚠️ Faqat raqam kiriting:")
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

# ================= CRM VA GURUHLAR =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "👥 Guruhlarni boshqarish (CRM)")
def crm_groups_menu(message):
    uid = message.from_user.id
    if not db_is_admin(uid):
        return
    user_states[uid] = "crm_set_user"
    bot.send_message(
        uid,
        "👥 <b>Oʻquvchini guruhga biriktirish:</b>\nOʻquvchining Telegram <b>ID raqamini</b> yuboring:",
        reply_markup=cancel_kb()
    )

@bot.message_handler(chat_types=["private"], func=lambda m: user_states.get(m.from_user.id) == "crm_set_user")
def crm_choose_group(message):
    uid = message.from_user.id
    if not message.text.isdigit():
        return bot.send_message(uid, "⚠️ ID raqam kiriting:")
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
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "🏆 Umumiy Reyting")
def show_global_rating(message):
    if not check_subscription(message.from_user.id):
        return ask_to_subscribe(message.chat.id)
    update_user_activity(message.from_user.id)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name, rash_score, raw_correct, daraja FROM results ORDER BY rash_score DESC LIMIT 20")
        rows = c.fetchall()
    if not rows:
        return bot.send_message(message.chat.id, "📭 Hali natijalar yoʻq.")
    medals = ["🥇", "🥈", "🥉"]
    text = "🏆 <b>A+ KIMYO | TOP-20 REYTING:</b>\n━━━━━━━━━━━━━━━━━━\n"
    for idx, r in enumerate(rows, 1):
        m = medals[idx - 1] if idx <= 3 else f"<b>{idx}.</b>"
        text += f"{m} {r[0]} — <b>{round(r[1], 1)} ball</b> ({r[2]}/40) | {r[3]}\n"
    bot.send_message(message.chat.id, text)

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📑 Vazifa nazorati (Qilgan/Qilmagan)")
def ask_check_test_code(message):
    uid = message.from_user.id
    if not db_is_admin(uid):
        return
    user_states[uid] = "check_hw_code"
    bot.send_message(uid, "🔢 6 xonali maxsus test kodini kiriting:", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], func=lambda m: user_states.get(m.from_user.id) == "check_hw_code")
def show_hw_status(message):
    uid = message.from_user.id
    if not message.text.isdigit():
        return bot.send_message(uid, "⚠️ Raqam kiriting!")
    code = int(message.text)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT title, expires_at FROM tests WHERE test_code = ?", (code,))
        t = c.fetchone()
        if not t:
            return bot.send_message(uid, "❌ Test topilmadi!")
        c.execute("SELECT user_id, full_name, rash_score, raw_correct FROM results WHERE test_code = ? ORDER BY rash_score DESC", (code,))
        done_rows = c.fetchall()
        done_ids = {r[0] for r in done_rows}
        c.execute("SELECT user_id, full_name, phone, group_name FROM users WHERE is_admin = 0")
        all_users = c.fetchall()

    user_states.pop(uid, None)
    not_done = [u for u in all_users if u[0] not in done_ids]

    text = f"📑 <b>VAZIFA NAZORATI: Test #{code} ({t[0]})</b>\n⏰ Muddati: <code>{t[1]}</code>\n━━━━━━━━━━━━━━━━━━\n"
    text += f"✅ <b>Vazifani bajarganlar ({len(done_rows)} ta):</b>\n"
    for r in done_rows:
        text += f"  • {r[1]} — <b>{round(r[2], 1)} ball</b>\n"
    text += f"\n❌ <b>Vazifa qilmaganlar ({len(not_done)} ta):</b>\n"
    for u in not_done:
        text += f"  • {u[1]} [{u[3]}] (Tel: {u[2] or 'yoʻq'})\n"
    bot.send_message(uid, text, reply_markup=admin_menu())

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📊 Elektron Jadval (Excel/Word/PDF)")
def export_menu(message):
    uid = message.from_user.id
    if not db_is_admin(uid):
        return
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
    if not db_is_admin(uid):
        return
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

# ================= KURSGA YOZILISH VA QAYTA TO'LOV (1 MARTALIK HAVOLA BILAN) =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "✍️ Kursga yozilish")
def reg_1(message):
    uid = message.from_user.id
    if not check_subscription(uid):
        return ask_to_subscribe(uid)
    user_states[uid] = "reg_name"
    bot.send_message(uid, "✍️ Ism va familiyangizni kiriting:", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], func=lambda m: user_states.get(m.from_user.id) == "reg_name")
def reg_2(message):
    uid = message.from_user.id
    user_data[uid] = {"ism": message.text}
    user_states[uid] = "reg_phone"
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True), KeyboardButton("❌ Bekor qilish"))
    bot.send_message(uid, "📱 Telefon raqamingizni yuboring:", reply_markup=kb)

@bot.message_handler(chat_types=["private"], content_types=['contact', 'text'], func=lambda m: user_states.get(m.from_user.id) == "reg_phone")
def reg_3(message):
    uid = message.from_user.id
    if message.text == "❌ Bekor qilish":
        return cancel_action(message)
    phone = message.contact.phone_number if message.contact else message.text
    user_data[uid]["phone"] = phone
    user_states[uid] = "reg_receipt"
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET full_name = ?, phone = ? WHERE user_id = ?", (user_data[uid]["ism"], phone, uid))
        conn.commit()
    bot.send_message(uid, f"💳 <b>Karta:</b> <code>{KARTA_RAQAM}</code> ({KARTA_EGASI})\n\n📸 Toʻlov chekini yuboring:", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], content_types=['photo'], func=lambda m: user_states.get(m.from_user.id) == "reg_receipt")
def reg_done(message):
    uid = message.from_user.id
    update_user_activity(uid)
    info = user_data.get(uid, {})
    photo = message.photo[-1].file_id
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Tasdiqlash (30 kun + Havola)", callback_data=f"pay_ok_{uid}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"pay_no_{uid}")
    )
    caption = f"🆕 <b>YANGI TOʻLOV CHEKI</b>\n👤 Ism: {info.get('ism')}\n📞 Tel: {info.get('phone')}\n🆔 ID: <code>{uid}</code>"
    for adm in db_get_admins():
        try:
            bot.send_photo(adm, photo, caption=caption, reply_markup=kb)
        except Exception:
            pass
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Chek yuborildi! Admin tasdiqlashi bilan sizga guruh havolasi keladi.", reply_markup=main_menu(uid))

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def pay_decision(call):
    _, act, target = call.data.split("_")
    target = int(target)

    if act == "ok":
        new_paid_until = (uz_now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
        now_str = uz_now().strftime("%Y-%m-%d %H:%M")

        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE users SET paid_until = ?, is_active = 1, last_active = ? WHERE user_id = ?",
                (new_paid_until, now_str, target)
            )
            conn.commit()

        try:
            bot.unban_chat_member(YOPIQ_GURUH_ID, target, only_if_banned=True)
        except Exception as e:
            print(f"Unban xatosi ({target}): {e}")

        invite_text = ""
        try:
            invite_obj = bot.create_chat_invite_link(
                chat_id=YOPIQ_GURUH_ID,
                name=f"User_{target}",
                member_limit=1
            )
            invite_text = (
                f"\n\n🔗 <b>Yopiq guruhga kirish uchun shaxsiy bir martalik havolangiz:</b>\n"
                f"{invite_obj.invite_link}\n"
                f"<i>(⚠️ Diqqat: Bu havola faqat 1 marta ishlaydi, boshqalarga bermang!)</i>"
            )
        except Exception as e:
            print(f"Invite link xatosi ({target}): {e}")
            invite_text = f"\n\n⚠️ Havola yaratishda xatolik boʻldi. Admin ({ADMIN_LICHKA}) bilan bogʻlaning."

        bot.send_message(
            target,
            f"🎉 <b>Tabriklaymiz! Toʻlovingiz tasdiqlandi!</b>\n"
            f"📅 Obunangiz <b>{new_paid_until}</b> gacha (30 kun) faollashtirildi."
            f"{invite_text}"
        )
        bot.edit_message_caption(
            caption=call.message.caption + f"\n\n✅ <b>TASDIQLANDI ({new_paid_until} gacha) + 1 martalik havola yuborildi</b>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
    else:
        bot.send_message(target, "❌ <b>Toʻlov cheki tasdiqlanmadi.</b> Admin bilan bogʻlaning.")
        bot.edit_message_caption(
            caption=call.message.caption + "\n\n❌ <b>RAD ETILDI</b>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
    bot.answer_callback_query(call.id)

# Admin boshqa funksiyalari
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📋 Testlar roʻyxati")
def list_tests(message):
    if not db_is_admin(message.from_user.id):
        return
    now = uz_now()
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT test_code, title, expires_at FROM tests ORDER BY created_at DESC LIMIT 15")
        rows = c.fetchall()
    if not rows:
        return bot.send_message(message.chat.id, "📭 Testlar yoʻq.")

    lines = []
    for code, title, exp_str in rows:
        status = "🟢 Ochiq"
        if exp_str:
            try:
                if now > datetime.strptime(exp_str, "%Y-%m-%d %H:%M"):
                    status = "🔴 Yopilgan"
            except ValueError:
                pass
        lines.append(f"🔹 Kod: <code>{code}</code> — {title} ({status} | {exp_str or '-'})")

    bot.send_message(message.chat.id, "📋 <b>Testlar roʻyxati:</b>\n\n" + "\n".join(lines))

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "🗑 Testni oʻchirish")
def del_test(message):
    if not db_is_admin(message.from_user.id):
        return
    user_states[message.from_user.id] = "del_t"
    bot.send_message(message.chat.id, "🗑 Oʻchiriladigan test kodini yuboring:", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], func=lambda m: user_states.get(m.from_user.id) == "del_t")
def del_test_do(message):
    uid = message.from_user.id
    if not message.text.isdigit():
        return bot.send_message(uid, "Faqat raqam!")
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("DELETE FROM tests WHERE test_code = ?", (int(message.text),))
        conn.commit()
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Oʻchirildi!", reply_markup=admin_menu())

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📢 Hammaga xabar")
def broadcast(message):
    if not db_is_admin(message.from_user.id):
        return
    user_states[message.from_user.id] = "broad"
    bot.send_message(message.chat.id, "📢 Hammaga yuboriladigan xabarni kiriting:", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], content_types=['text', 'photo', 'video', 'document'], func=lambda m: user_states.get(m.from_user.id) == "broad")
def broadcast_send(message):
    uid = message.from_user.id
    if message.text == "❌ Bekor qilish":
        return cancel_action(message)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        users = [r[0] for r in c.fetchall()]
    user_states.pop(uid, None)
    sent = 0
    for u in users:
        try:
            bot.copy_message(u, message.chat.id, message.message_id)
            sent += 1
        except Exception:
            pass
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
    threading.Thread(target=background_watcher, daemon=True).start()
    bot.remove_webhook()
    print("A+ Kimyo Super Bot ishga tushdi...")
    bot.infinity_polling(none_stop=True, interval=0, timeout=20)
