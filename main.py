import asyncio
import base64
import io
import json
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# -------------------------------------------------------------
# SOZLAMALAR VA XAVFSIZLIK
# -------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "8636730483:AAFU8mRl0pH5AjmCASWETCNLy35q4lMpB-s")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6734050237"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@onlyibrohimov")
DEFAULT_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

# Standart majburiy obuna kanali
DEFAULT_REQUIRED_CHANNEL = "@Kimyo_Sertifkat_uchun"
DEFAULT_CHANNEL_URL = "https://t.me/Kimyo_Sertifkat_uchun"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# -------------------------------------------------------------
# MA'LUMOTLAR BAZASI
# -------------------------------------------------------------
def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            joined_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tests (
            test_code TEXT PRIMARY KEY,
            test_type TEXT,
            title TEXT,
            keys_json TEXT,
            ai_explanation TEXT,
            file_id TEXT,
            file_type TEXT,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_code TEXT,
            user_id INTEGER,
            full_name TEXT,
            correct_count INTEGER,
            total_score REAL,
            grade TEXT,
            submitted_at TEXT
        )
    """)
    # Majburiy obuna kanalini standart holatda bazaga yozib qo'yamiz
    c.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        ("required_channel", DEFAULT_REQUIRED_CHANNEL)
    )
    conn.commit()
    conn.close()

def db_add_user(user_id: int, full_name: str, username: str):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, full_name, username, joined_at) VALUES (?, ?, ?, ?)",
        (user_id, full_name, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()

def db_get_setting(key: str, default: str = "") -> str:
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def db_set_setting(key: str, val: str):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val))
    conn.commit()
    conn.close()

def db_save_test(test_code: str, test_type: str, title: str, keys_dict: dict, explanation: str = "", file_id: str = "", file_type: str = ""):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        """INSERT OR REPLACE INTO tests 
           (test_code, test_type, title, keys_json, ai_explanation, file_id, file_type, created_at) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            test_code.upper(),
            test_type,
            title,
            json.dumps(keys_dict, ensure_ascii=False),
            explanation,
            file_id,
            file_type,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )
    conn.commit()
    conn.close()

def db_get_test(test_code: str):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        "SELECT test_code, test_type, title, keys_json, ai_explanation, file_id, file_type FROM tests WHERE test_code = ?",
        (test_code.upper().strip(),)
    )
    row = c.fetchone()
    conn.close()
    return row

def db_delete_test(test_code: str) -> bool:
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM tests WHERE test_code = ?", (test_code.upper().strip(),))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def db_get_recent_tests(limit: int = 10):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT test_code, test_type, title, created_at FROM tests ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def db_save_result(test_code: str, user_id: int, full_name: str, correct_count: int, total_score: float, grade: str):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        """INSERT INTO test_results (test_code, user_id, full_name, correct_count, total_score, grade, submitted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (test_code.upper(), user_id, full_name, correct_count, total_score, grade, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()

def db_get_top_results(test_code: str, limit: int = 15):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        """SELECT full_name, correct_count, total_score, grade 
           FROM test_results 
           WHERE test_code = ? 
           ORDER BY total_score DESC, correct_count DESC 
           LIMIT ?""",
        (test_code.upper().strip(), limit)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def db_get_stats():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM tests")
    tests_cnt = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM test_results")
    results_cnt = c.fetchone()[0]
    conn.close()
    return {"users": users, "tests": tests_cnt, "results": results_cnt}

def db_get_all_users():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

# -------------------------------------------------------------
# MAJBURIY OBUNA TEKSHIRUVI (https://t.me/Kimyo_Sertifkat_uchun)
# -------------------------------------------------------------
def get_required_channel_data():
    """
    Bazadagi kanal nomini (@Kimyo_Sertifkat_uchun yoki https://t.me/...)
    toza chat_id va url ko'rinishiga keltiradi.
    """
    raw = db_get_setting("required_channel", DEFAULT_REQUIRED_CHANNEL).strip()
    if not raw or raw.lower() in ["none", "0", "off"]:
        return None, None

    if "t.me/" in raw:
        uname = raw.split("t.me/")[-1].split("/")[0].split("?")[0].strip()
        return f"@{uname}", f"https://t.me/{uname}"
    if raw.startswith("@"):
        uname = raw[1:]
        return f"@{uname}", f"https://t.me/{uname}"
    if raw.startswith("-100"):
        return raw, DEFAULT_CHANNEL_URL
    return f"@{raw}", f"https://t.me/{raw}"

async def check_channel_subscription(user_id: int) -> bool:
    chat_id, _ = get_required_channel_data()
    if not chat_id:
        return True
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status in ["creator", "administrator", "member"]:
            return True
        if member.status == "restricted" and getattr(member, "is_member", False):
            return True
        return False
    except Exception as err:
        logging.warning(f"Majburiy obunani tekshirishda xato ({chat_id}): {err}")
        # Agar bot kanalda admin bo'lmasa, faqat Adminning o'zini o'tkazib yuboradi
        return user_id == ADMIN_ID

async def prompt_subscription(message: types.Message):
    chat_id, ch_url = get_required_channel_data()
    if not ch_url:
        ch_url = DEFAULT_CHANNEL_URL

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga a'zo bo'lish", url=ch_url)],
            [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="btn_check_sub")]
        ]
    )
    await message.answer(
        "🛑 <b>Diqqat! Botdan foydalanish uchun rasmiy kanalimizga obuna bo'lishingiz shart!</b>\n\n"
        f"👉 Kanal: <a href='{ch_url}'>{chat_id or '@Kimyo_Sertifkat_uchun'}</a>\n\n"
        "Pastdagi <b>«📢 Kanalga a'zo bo'lish»</b> tugmasini bosib kanalga qo'shiling, so'ng <b>«✅ Obunani tekshirish»</b> tugmasini bosing 👇",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=kb
    )

# -------------------------------------------------------------
# SUN'IY INTELLEKT (GEMINI AI) MOTORI
# -------------------------------------------------------------
def get_gemini_api_key() -> str:
    saved_key = db_get_setting("gemini_api_key", "").strip()
    return saved_key if saved_key else DEFAULT_GEMINI_KEY

async def ai_analyze_test_document(file_bytes: bytes, mime_type: str, test_type: str) -> dict:
    """
    PDF yoki rasmni o'qib, barcha savollarni yechadi va javoblar kalitini JSON ko'rinishida qaytaradi.
    test_type: '30_talik' | '43_ms' | '90_dtm'
    """
    api_key = get_gemini_api_key()
    if not api_key:
        return {"error": "API_KEY_MISSING"}

    b64_data = base64.b64encode(file_bytes).decode("utf-8")

    if test_type == "30_talik":
        prompt = (
            "Sen Kimyo va aniq fanlar bo'yicha oliy toifali ekspertsan. "
            "Yuborilgan fayldagi (PDF yoki rasm) 30 talik test savollarini (yoki tayyor javoblar varaqasini) diqqat bilan tahlil qil. "
            "Har bir savol va masalani aniq yechib chiq. "
            "Natijani FAQAT quyidagi JSON formatda qaytar (boshqa ortiqcha so'z qo'shma):\n"
            "{\n"
            '  "title": "Test mavzusi yoki nomi",\n'
            '  "keys": {"1": "A", "2": "B", "3": "C", ... "30": "D"},\n'
            '  "explanation": "Eng muhim yoki murakkab masalalarning qisqacha yechim izohi"\n'
            "}"
        )
    elif test_type == "43_ms":
        prompt = (
            "Sen O'zbekiston Milliy Sertifikat (43 talik Rasch modeli) bo'yicha oliy toifali kimyo va aniq fanlar ekspertisan. "
            "Yuborilgan PDF yoki rasmdagi testni diqqat bilan o'qi va har bir savolni yechib kalit tuz:\n"
            "- 1 dan 32 gacha: Yopiq test (A, B, C yoki D)\n"
            "- 33 dan 35 gacha: Moslashtirish testi (A, B, C, D, E yoki F)\n"
            "- 36 dan 43 gacha: Ochiq yozma masalalar (aniq son, formula yoki javob qiymati).\n"
            "Natijani FAQAT quyidagi toza JSON formatda qaytar:\n"
            "{\n"
            '  "title": "Milliy Sertifikat 43 talik test",\n'
            '  "keys": {"1": "A", ..., "32": "D", "33": "E", "34": "A", "35": "F", "36": "9", ..., "43": "22.4"},\n'
            '  "explanation": "36-43 ochiq masalalarning qisqa mantiqiy yechimlari"\n'
            "}"
        )
    else:  # 90_dtm
        prompt = (
            "Sen DTM (Bilim va malakalarni baholash agentligi) 90 talik blok testlari bo'yicha oliy toifali ekspertsan. "
            "Yuborilgan PDF yoki rasmdagi savollarni (1-30 majburiy fanlar, 31-60 1-mutaxassislik fani, 61-90 2-mutaxassislik fani) "
            "yoki javoblar jadvalini o'qib, har bir savolning to'g'ri javobini (A, B, C yoki D) aniqla. "
            "Natijani FAQAT quyidagi toza JSON formatda qaytar:\n"
            "{\n"
            '  "title": "90 talik DTM Blok Testi",\n'
            '  "keys": {"1": "A", "2": "C", ..., "90": "B"},\n'
            '  "explanation": "Asosiy bloklar bo\'yicha qisqacha tahlil"\n'
            "}"
        )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json"
        }
    }

    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    last_error = ""

    async with aiohttp.ClientSession() as session:
        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            try:
                async with session.post(url, json=payload, timeout=120) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                        raw_text = raw_text.strip()
                        if raw_text.startswith("```"):
                            raw_text = re.sub(r"^```(?:json)?|```$", "", raw_text, flags=re.MULTILINE).strip()
                        parsed = json.loads(raw_text)
                        return parsed
                    else:
                        err_body = await resp.text()
                        last_error = f"HTTP {resp.status}: {err_body[:200]}"
            except Exception as e:
                last_error = str(e)

    return {"error": f"AI tahlilda xatolik: {last_error}"}

async def ai_solve_photo_problem(file_bytes: bytes, mime_type: str) -> str:
    """
    O'quvchi yoki ustoz rasm yuborganda masalani mantiqiy usulda yechib beradi.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        return "⚠️ AI xizmati uchun Gemini API kaliti kiritilmagan. Admin paneldan (/admin) API kalitni kiriting."

    b64_data = base64.b64encode(file_bytes).decode("utf-8")
    prompt = (
        "Sen A+ Kimyo maktabining eng tajribali ustozi Azizbek Ibrohimovning yordamchi sun'iy intellektisan. "
        "Rasmdagi kimyo (yoki aniq fan) masalasini o'zbek tilida eng oson, formulalarsiz mantiqiy va proporsiya usulida "
        "bosqichma-bosqich yechib tushuntirib ber va yakuniy to'g'ri javobni ko'rsat."
    )

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": b64_data}}
            ]
        }],
        "generationConfig": {"temperature": 0.2}
    }

    async with aiohttp.ClientSession() as session:
        for model_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            try:
                async with session.post(url, json=payload, timeout=90) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["candidates"][0]["content"]["parts"][0]["text"]
            except Exception:
                continue
    return "❌ Rasmni tahlil qilishda xatolik yuz berdi. Qaytadan urinib ko'ring."

# -------------------------------------------------------------
# JAVOBLARNI O'QISH VA BALL HISOBLASH (30, 43, 90 TALIK)
# -------------------------------------------------------------
def parse_input_answers(raw_text: str, test_type: str) -> dict:
    text = raw_text.strip()
    answers = {}

    # 1. Raqamlangan formatni qidirish: 1a, 1-a, 1:a, 36=12.5, 36: 9
    pairs = re.findall(r"(\d{1,2})\s*[-:=.)]?\s*([A-Za-z0-9.,/+-]+)", text)
    if len(pairs) >= 3:
        for q_num, ans_val in pairs:
            q_str = str(int(q_num))
            answers[q_str] = ans_val.strip().upper()
        return answers

    # 2. Faqat harflar ketma-ketligi yozilgan bo'lsa: masalan ABCDABCD...
    clean_letters = re.sub(r"[^A-Fa-f]", "", text).upper()
    max_q = 30 if test_type == "30_talik" else (90 if test_type == "90_dtm" else 35)
    if len(clean_letters) >= 5:
        for idx, ch in enumerate(clean_letters[:max_q], start=1):
            answers[str(idx)] = ch

    return answers

def evaluate_student_submission(test_type: str, correct_keys: dict, student_ans: dict) -> dict:
    mistakes = []
    correct_count = 0

    if test_type == "30_talik":
        total_q = len(correct_keys) or 30
        for q in range(1, total_q + 1):
            qs = str(q)
            k_val = str(correct_keys.get(qs, "")).strip().upper()
            s_val = str(student_ans.get(qs, "")).strip().upper()
            if k_val and s_val == k_val:
                correct_count += 1
            elif k_val:
                mistakes.append(f"{q}-savol (Siz: {s_val or '—'} | To'g'ri: {k_val})")

        score = round(correct_count * 3.1, 1)
        percent = round((correct_count / total_q) * 100, 1) if total_q else 0
        grade = "A'lo (Yuqori)" if percent >= 85 else ("Yaxshi" if percent >= 65 else "Qoniqarli")

        summary = (
            f"📋 <b>30 TALIK TEST NATIJASI:</b>\n"
            f"────────────────────────\n"
            f"✅ To'g'ri javoblar: <b>{correct_count} / {total_q} ta</b>\n"
            f"📊 Ko'rsatkich: <b>{percent}%</b>\n"
            f"💎 To'plangan ball: <b>{score} ball</b> (maks. {round(total_q*3.1, 1)})\n"
            f"🏅 Daraja: <b>{grade}</b>"
        )
        return {
            "correct_count": correct_count,
            "total_score": score,
            "grade": grade,
            "summary": summary,
            "mistakes": mistakes
        }

    elif test_type == "90_dtm":
        b1_correct = 0  # 1-30: 1.1 ball
        b2_correct = 0  # 31-60: 3.1 ball
        b3_correct = 0  # 61-90: 2.1 ball

        for q in range(1, 91):
            qs = str(q)
            k_val = str(correct_keys.get(qs, "")).strip().upper()
            s_val = str(student_ans.get(qs, "")).strip().upper()
            if not k_val:
                continue
            if s_val == k_val:
                correct_count += 1
                if 1 <= q <= 30:
                    b1_correct += 1
                elif 31 <= q <= 60:
                    b2_correct += 1
                else:
                    b3_correct += 1
            else:
                mistakes.append(f"{q}:{s_val or '—'}({k_val})")

        b1_score = round(b1_correct * 1.1, 1)
        b2_score = round(b2_correct * 3.1, 1)
        b3_score = round(b3_correct * 2.1, 1)
        total_score = round(b1_score + b2_score + b3_score, 1)

        grade = "Davlat Granti darajasi 🏆" if total_score >= 150 else ("To'lov-kontrakt darajasi 🎯" if total_score >= 100 else "Qo'shimcha tayyorgarlik kerak 📚")

        summary = (
            f"🏛 <b>90 TALIK DTM BLOK TEST NATIJASI:</b>\n"
            f"────────────────────────\n"
            f"1️⃣ <b>Majburiy fanlar (1–30):</b> {b1_correct}/30 ta = <b>{b1_score} ball</b> (1.1)\n"
            f"2️⃣ <b>1-Mutaxassislik fani (31–60):</b> {b2_correct}/30 ta = <b>{b2_score} ball</b> (3.1)\n"
            f"3️⃣ <b>2-Mutaxassislik fani (61–90):</b> {b3_correct}/30 ta = <b>{b3_score} ball</b> (2.1)\n"
            f"────────────────────────\n"
            f"✅ Jami to'g'ri: <b>{correct_count} / 90 ta</b>\n"
            f"🔥 <b>UMUMIY DTM BALL: {total_score} / 189.0 ball</b>\n"
            f"🏅 Xulosa: <b>{grade}</b>"
        )
        return {
            "correct_count": correct_count,
            "total_score": total_score,
            "grade": grade,
            "summary": summary,
            "mistakes": mistakes
        }

    else:  # 43_ms (Milliy Sertifikat)
        p1_correct = 0  # 1-32 (ABCD)
        p2_correct = 0  # 33-35 (ABCDEF)
        p3_correct = 0  # 36-43 (Ochiq masalalar)
        weighted_points = 0.0

        for q in range(1, 44):
            qs = str(q)
            k_val = str(correct_keys.get(qs, "")).strip().upper().replace(",", ".")
            s_val = str(student_ans.get(qs, "")).strip().upper().replace(",", ".")
            if not k_val:
                continue

            if s_val == k_val:
                correct_count += 1
                if 1 <= q <= 32:
                    p1_correct += 1
                    weighted_points += 1.5
                elif 33 <= q <= 35:
                    p2_correct += 1
                    weighted_points += 2.0
                else:
                    p3_correct += 1
                    weighted_points += 2.65
            else:
                mistakes.append(f"{q}-savol (Siz: {s_val or '—'} | Kalit: {k_val})")

        if correct_count == 0:
            rasch_score = 0.0
        elif correct_count == 43:
            rasch_score = 75.0
        else:
            rasch_score = round(min(75.0, 25.0 + weighted_points * 0.68), 1)

        if rasch_score >= 70.0:
            grade = "A+ Daraja (100% Maksimal Imtiyoz) 🏆"
        elif rasch_score >= 65.0:
            grade = "A Daraja (A'lo) 🥇"
        elif rasch_score >= 60.0:
            grade = "B+ Daraja (Juda yaxshi) 🥈"
        elif rasch_score >= 55.0:
            grade = "B Daraja (Yaxshi) 🥉"
        elif rasch_score >= 46.0:
            grade = "C Daraja (Minimal sertifikat) 🎗"
        else:
            grade = "Sertifikat darajasiga yetmadi (<46) ❌"

        summary = (
            f"🎯 <b>43 TALIK MILLIY SERTIFIKAT NATIJASI:</b>\n"
            f"────────────────────────\n"
            f"🔹 <b>1–32 Yopiq test (A-D):</b> {p1_correct} / 32 ta\n"
            f"🔸 <b>33–35 Moslashtirish (A-F):</b> {p2_correct} / 3 ta\n"
            f"🧪 <b>36–43 Ochiq masalalar:</b> {p3_correct} / 8 ta\n"
            f"────────────────────────\n"
            f"✅ Jami to'g'ri: <b>{correct_count} / 43 ta</b>\n"
            f"📈 <b>Rasch Bali: {rasch_score} ball</b>\n"
            f"🏅 <b>Daraja: {grade}</b>"
        )
        return {
            "correct_count": correct_count,
            "total_score": rasch_score,
            "grade": grade,
            "summary": summary,
            "mistakes": mistakes
        }

# -------------------------------------------------------------
# FSM STATE HOLATLARI
# -------------------------------------------------------------
class StudentTestSolve(StatesGroup):
    waiting_test_code = State()
    waiting_answers = State()

class AISolveProblem(StatesGroup):
    waiting_problem_photo = State()

class AdminAITestCreate(StatesGroup):
    waiting_test_type = State()
    waiting_file_or_keys = State()
    waiting_manual_edit = State()

class AdminPanel(StatesGroup):
    waiting_channel = State()
    waiting_gemini_key = State()
    waiting_delete_code = State()
    waiting_broadcast = State()

# -------------------------------------------------------------
# ASOSIY MENYU TUGMALARI
# -------------------------------------------------------------
def main_menu(user_id: int = 0):
    kb = [
        [KeyboardButton(text="📝 Test Tekshirish (30 / 43 / 90)")],
        [KeyboardButton(text="📋 Faol Testlar Ro'yxati"), KeyboardButton(text="🏆 Reyting (Natijalar)")],
        [KeyboardButton(text="🤖 AI Masala Yechish (Rasm)"), KeyboardButton(text="👨‍🏫 Ustoz & Bog'lanish")]
    ]
    if user_id == ADMIN_ID:
        kb.insert(0, [KeyboardButton(text="🤖 AI Test Yaratish (PDF/Rasm - Admin)")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# -------------------------------------------------------------
# START VA MAJBURIY OBUNA HANDLERLARI
# -------------------------------------------------------------
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    name = message.from_user.full_name or "O'quvchi"
    username = f"@{message.from_user.username}" if message.from_user.username else ""
    db_add_user(uid, name, username)

    # Majburiy obunani tekshirish (@Kimyo_Sertifkat_uchun)
    if not await check_channel_subscription(uid):
        await prompt_subscription(message)
        return

    text = (
        f"Assalomu alaykum, <b>{name}</b>! 👋\n\n"
        f"🧪 <b>A+ Kimyo | AI Test Tekshirgich</b> botiga xush kelibsiz!\n\n"
        f"🤖 <b>Bot imkoniyatlari:</b>\n"
        f"• 📋 <b>30 talik Test:</b> Avtomatik tekshirish va ball hisoblash;\n"
        f"• 🎯 <b>43 talik Milliy Sertifikat:</b> Rasch modeli va darajalar (A+, A, B+, B, C);\n"
        f"• 🏛 <b>90 talik DTM Blok Test:</b> 3 ta blok (1.1 / 3.1 / 2.1) bo'yicha hisoblash;\n"
        f"• 📸 <b>AI Masala Yechish:</b> Kimyo masalasi rasmini yuborsangiz, sun'iy intellekt yechib tushuntirib beradi!\n\n"
        f"Kerakli bo'limni tanlang 👇"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu(uid))

@dp.callback_query(F.data == "btn_check_sub")
async def cb_check_sub(callback: types.CallbackQuery):
    uid = callback.from_user.id
    if await check_channel_subscription(uid):
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            "🎉 <b>Obunangiz tasdiqlandi!</b>\nMarhamat, botning barcha imkoniyatlaridan foydalanishingiz mumkin:",
            parse_mode="HTML",
            reply_markup=main_menu(uid)
        )
    else:
        await callback.answer(
            "❌ Siz hali kanalga a'zo bo'lmadingiz! Avval «📢 Kanalga a'zo bo'lish» tugmasini bosib qo'shiling.",
            show_alert=True
        )

@dp.message(F.text == "❌ Bekor qilish")
async def cancel_any_state(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Jarayon bekor qilindi. Bosh menyudasiz:", reply_markup=main_menu(message.from_user.id))

# -------------------------------------------------------------
# ADMIN: SUN'IY INTELLEKT ORQALI PDF/RASMDAN TEST VA KALIT YARATISH
# -------------------------------------------------------------
@dp.message(F.text == "🤖 AI Test Yaratish (PDF/Rasm - Admin)")
async def admin_start_ai_test(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 1. 30 talik Test yaratish", callback_data="ai_new:30_talik")],
            [InlineKeyboardButton(text="🎯 2. 43 talik Milliy Sertifikat (Rasch)", callback_data="ai_new:43_ms")],
            [InlineKeyboardButton(text="🏛 3. 90 talik DTM Blok Test", callback_data="ai_new:90_dtm")]
        ]
    )
    await message.answer(
        "🤖 <b>Sun'iy Intellekt (AI) yordamida Test va Kalit yaratish:</b>\n\n"
        "Qaysi formatdagi testni yaratmoqchisiz? Tanlang 👇",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("ai_new:"))
async def cb_select_ai_test_type(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    test_type = callback.data.split(":")[1]
    await state.update_data(test_type=test_type)
    await state.set_state(AdminAITestCreate.waiting_file_or_keys)

    type_names = {
        "30_talik": "📋 30 talik Test (1–30 A-D)",
        "43_ms": "🎯 43 talik Milliy Sertifikat (1–32 A-D, 33–35 A-F, 36–43 Ochiq)",
        "90_dtm": "🏛 90 talik DTM Test (1–30 [1.1], 31–60 [3.1], 61–90 [2.1])"
    }

    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await callback.message.answer(
        f"✅ Tanlandi: <b>{type_names.get(test_type)}</b>\n\n"
        f"📤 <b>Endi quyidagilardan birini yuboring:</b>\n"
        f"1️⃣ <b>Test PDF fayli</b> yoki <b>Test savollari rasmi</b> — <i>Sun'iy intellekt savollarni o'zi yechib, kalitni avtomatik tuzadi!</i>\n"
        f"2️⃣ <b>Tayyor kalitlar rasmi</b> — <i>AI jadvaldagi kalitlarni o'qib bazaga kiritadi.</i>\n"
        f"3️⃣ Yoki kalitlarni matn ko'rinishida yozib yuboring (masalan: <code>1a 2b 3c...</code>).",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    await callback.answer()

@dp.message(AdminAITestCreate.waiting_file_or_keys)
async def handle_admin_test_upload(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    test_type = data.get("test_type", "30_talik")
    prefix = "TEST" if test_type == "30_talik" else ("MS" if test_type == "43_ms" else "DTM")
    test_code = f"{prefix}-{datetime.now().strftime('%m%d%H%M')}"

    if message.text and not message.text.startswith("/"):
        parsed_keys = parse_input_answers(message.text, test_type)
        if not parsed_keys:
            await message.answer("⚠️ Kalitlarni o'qib bo'lmadi. Masalan: <code>1a 2b 3c...</code> ko'rinishida yuboring yoki PDF/Rasm tashlang.", parse_mode="HTML")
            return

        title = f"{prefix} Maxsus Test ({len(parsed_keys)} ta savol)"
        db_save_test(test_code, test_type, title, parsed_keys, "Ustoz tomonidan kiritilgan kalitlar")
        await state.clear()
        await message.answer(
            f"✅ <b>Test muvaffaqiyatli saqlandi!</b>\n\n"
            f"🔑 Test kodi: <code>{test_code}</code>\n"
            f"📊 Savollar soni: <b>{len(parsed_keys)} ta</b>\n\n"
            f"O'quvchilar <b>«📝 Test Tekshirish»</b> bo'limiga kirib, <code>{test_code}</code> kodini kiritishlari mumkin!",
            parse_mode="HTML",
            reply_markup=main_menu(ADMIN_ID)
        )
        return

    file_id = ""
    file_type = ""
    mime_type = ""

    if message.document:
        file_id = message.document.file_id
        file_type = "document"
        mime_type = message.document.mime_type or "application/pdf"
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
        mime_type = "image/jpeg"
    else:
        await message.answer("❗️ Iltimos, PDF fayl, Rasm yoki matnli kalit yuboring.")
        return

    wait_msg = await message.answer("🤖 <b>Sun'iy intellekt faylni o'qimoqda va savollarni yechib kalit tuzmoqda...</b>\n⏳ Iltimos, 15–40 soniya kuting...", parse_mode="HTML")

    try:
        tg_file = await bot.get_file(file_id)
        file_buffer = io.BytesIO()
        await bot.download_file(tg_file.file_path, destination=file_buffer)
        file_bytes = file_buffer.getvalue()
    except Exception as e:
        await wait_msg.edit_text(f"❌ Faylni yuklab olishda xato: {e}")
        return

    ai_result = await ai_analyze_test_document(file_bytes, mime_type, test_type)

    if "error" in ai_result:
        if ai_result["error"] == "API_KEY_MISSING":
            await wait_msg.edit_text(
                "⚠️ <b>Gemini AI API kaliti kiritilmagan!</b>\n\n"
                "1. /admin buyrug'ini bosing.\n"
                "2. <b>«🔑 Gemini AI API Kalitni kiritish»</b> tugmasini bosib, Google AI Studio kalitingizni yuboring.\n\n"
                "<i>Yoki hozirning o'zida kalitlarni oddiy matn ko'rinishida (1a 2b 3c...) yozib yuborishingiz ham mumkin!</i>",
                parse_mode="HTML"
            )
        else:
            await wait_msg.edit_text(
                f"⚠️ <b>AI tahlilda xatolik:</b> {ai_result['error']}\n\n"
                f"Kalitlarni matn ko'rinishida (<code>1a 2b 3c...</code>) yuborishingiz yoki qaytadan rasm tashlashingiz mumkin.",
                parse_mode="HTML"
            )
        return

    keys_dict = ai_result.get("keys", {})
    title = ai_result.get("title", f"{prefix} AI Testi")
    explanation = ai_result.get("explanation", "")

    sorted_items = sorted(keys_dict.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 999)
    keys_preview = ", ".join([f"<b>{k}</b>:{v}" for k, v in sorted_items])

    db_save_test(test_code, test_type, title, keys_dict, explanation, file_id, file_type)
    await state.clear()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Kalitlarni tahrirlash", callback_data=f"edit_keys:{test_code}")]
        ]
    )

    result_text = (
        f"🎉 <b>SUN'IY INTELLEKT TESTNI YECHDI VA BAZAGA SAQLADI!</b>\n"
        f"────────────────────────\n"
        f"🔑 <b>Test kodi:</b> <code>{test_code}</code>\n"
        f"📚 <b>Nomi:</b> {title}\n"
        f"🔢 <b>Aniqlangan kalitlar ({len(keys_dict)} ta):</b>\n"
        f"{keys_preview}\n"
        f"────────────────────────\n"
        f"💡 <b>AI izohi:</b> {explanation[:400]}\n\n"
        f"✅ O'quvchilar endi <code>{test_code}</code> kodi orqali javoblarini tekshirishlari mumkin!"
    )
    await wait_msg.delete()
    await message.answer(result_text, parse_mode="HTML", reply_markup=kb)
    await message.answer("Asosiy menyu:", reply_markup=main_menu(ADMIN_ID))

@dp.callback_query(F.data.startswith("edit_keys:"))
async def cb_edit_test_keys(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    test_code = callback.data.split(":")[1]
    await state.update_data(edit_test_code=test_code)
    await state.set_state(AdminAITestCreate.waiting_manual_edit)

    await callback.message.answer(
        f"✏️ <b>{test_code}</b> testining o'zgartirmoqchi bo'lgan kalitlarini yozing:\n\n"
        f"Masalan, faqat 5 va 36-savolni o'zgartirish uchun: <code>5B 36=18</code> deb yozing (yoki to'liq kalitni yuboring):",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(AdminAITestCreate.waiting_manual_edit)
async def save_edited_keys(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    test_code = data.get("edit_test_code")
    row = db_get_test(test_code)
    if not row:
        await state.clear()
        await message.answer("Test topilmadi.", reply_markup=main_menu(ADMIN_ID))
        return

    _, test_type, title, keys_json, ai_exp, f_id, f_type = row
    current_keys = json.loads(keys_json)
    new_updates = parse_input_answers(message.text, test_type)

    current_keys.update(new_updates)
    db_save_test(test_code, test_type, title, current_keys, ai_exp, f_id, f_type)
    await state.clear()

    await message.answer(
        f"✅ <b>{test_code}</b> kalitlari yangilandi! ({len(new_updates)} ta savol o'zgartirildi).",
        parse_mode="HTML",
        reply_markup=main_menu(ADMIN_ID)
    )

# -------------------------------------------------------------
# O'QUVCHILAR UCHUN: TEST TEKSHIRISH VA FAOL TESTLAR RO'YXATI
# -------------------------------------------------------------
@dp.message(F.text == "📋 Faol Testlar Ro'yxati")
async def show_active_tests_list(message: types.Message):
    if not await check_channel_subscription(message.from_user.id):
        await prompt_subscription(message)
        return

    recent = db_get_recent_tests(10)
    if not recent:
        await message.answer("📭 Hozircha bazada faol testlar yo'q.")
        return

    kb_rows = []
    text_lines = ["📋 <b>FAOL TESTLAR RO'YXATI:</b>\n"]
    for r_code, r_type, r_title, r_date in recent:
        badge = "30 talik" if r_type == "30_talik" else ("43 MS" if r_type == "43_ms" else "90 DTM")
        text_lines.append(f"🔹 <code>{r_code}</code> — <b>{r_title}</b> ({badge})")
        kb_rows.append([InlineKeyboardButton(text=f"✍️ Yechish: {r_code} ({badge})", callback_data=f"solve_now:{r_code}")])

    text_lines.append("\n👇 Testni tekshirish uchun pastdagi tugmani bosing:")
    await message.answer(
        "\n".join(text_lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )

@dp.callback_query(F.data.startswith("solve_now:"))
async def cb_solve_test_now(callback: types.CallbackQuery, state: FSMContext):
    if not await check_channel_subscription(callback.from_user.id):
        await callback.answer("❌ Avval kanalga obuna bo'ling!", show_alert=True)
        await prompt_subscription(callback.message)
        return

    code = callback.data.split(":")[1]
    row = db_get_test(code)
    if not row:
        await callback.answer("Test topilmadi!", show_alert=True)
        return

    await callback.answer()
    await send_test_prompt_to_student(callback.message, state, row)

@dp.message(F.text == "📝 Test Tekshirish (30 / 43 / 90)")
async def start_student_test_check(message: types.Message, state: FSMContext):
    if not await check_channel_subscription(message.from_user.id):
        await prompt_subscription(message)
        return

    recent = db_get_recent_tests(5)
    recent_info = ""
    if recent:
        lines = []
        for r_code, r_type, r_title, _ in recent:
            badge = "30 talik" if r_type == "30_talik" else ("43 MS" if r_type == "43_ms" else "90 DTM")
            lines.append(f"• <code>{r_code}</code> — {r_title} ({badge})")
        recent_info = "\n\n📌 <b>So'nggi faol testlar:</b>\n" + "\n".join(lines)

    await state.set_state(StudentTestSolve.waiting_test_code)
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)

    await message.answer(
        f"📝 <b>TEST JAVOBLARINI TEKSHIRISH BO'LIMI</b>\n\n"
        f"Ustoz bergan <b>Test kodini</b> yozib yuboring (masalan: <code>MS-1014</code> yoki <code>DTM-1014</code>):"
        f"{recent_info}",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )

async def send_test_prompt_to_student(message: types.Message, state: FSMContext, row: tuple):
    test_code, test_type, title, keys_json, ai_exp, file_id, file_type = row
    await state.update_data(active_test_code=test_code)
    await state.set_state(StudentTestSolve.waiting_answers)

    if file_id:
        try:
            if file_type == "document":
                await bot.send_document(message.chat.id, file_id, caption=f"📄 <b>{title}</b> ({test_code})", parse_mode="HTML")
            elif file_type == "photo":
                await bot.send_photo(message.chat.id, file_id, caption=f"🖼 <b>{title}</b> ({test_code})", parse_mode="HTML")
        except Exception:
            pass

    if test_type == "30_talik":
        example_str = "<code>1A 2B 3C 4D ... 30A</code>\nyoki ketma-ket: <code>ABCDABCD...</code>"
    elif test_type == "90_dtm":
        example_str = "<code>1A 2B 3C ... 90D</code>\nyoki ketma-ket 90 ta harf: <code>ABCD...</code>"
    else:
        example_str = (
            "1–35 savollar harflar va 36–43 ochiq savollar javobi:\n"
            "<code>1A 2B 3C ... 33E 34A 35F 36=9 37=18 38=22.4 ...</code>"
        )

    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await message.answer(
        f"✅ <b>Test topildi:</b> {title}\n"
        f"🔑 <b>Kodi:</b> <code>{test_code}</code>\n\n"
        f"✍️ <b>Javoblaringizni bitta xabarda yuboring:</b>\n"
        f"Namuna:\n{example_str}",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )

@dp.message(StudentTestSolve.waiting_test_code)
async def process_test_code_input(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    row = db_get_test(code)
    if not row:
        await message.answer(
            f"❌ <b>{code}</b> kodli test topilmadi!\n"
            f"Kod to'g'ri yozilganini tekshirib, qaytadan yuboring (yoki «❌ Bekor qilish» tugmasini bosing):",
            parse_mode="HTML"
        )
        return

    await send_test_prompt_to_student(message, state, row)

@dp.message(StudentTestSolve.waiting_answers)
async def process_student_answers(message: types.Message, state: FSMContext):
    data = await state.get_data()
    test_code = data.get("active_test_code")
    row = db_get_test(test_code)
    if not row:
        await state.clear()
        await message.answer("Test topilmadi.", reply_markup=main_menu(message.from_user.id))
        return

    _, test_type, title, keys_json, ai_exp, _, _ = row
    correct_keys = json.loads(keys_json)

    student_ans = parse_input_answers(message.text or "", test_type)
    if not student_ans:
        await message.answer(
            "⚠️ Javoblaringiz formati tushunarsiz bo'ldi.\n"
            "Iltimos, <code>1A 2B 3C 4D...</code> ko'rinishida yozib yuboring:",
            parse_mode="HTML"
        )
        return

    res = evaluate_student_submission(test_type, correct_keys, student_ans)
    uid = message.from_user.id
    full_name = message.from_user.full_name or "O'quvchi"

    db_save_result(test_code, uid, full_name, res["correct_count"], res["total_score"], res["grade"])
    await state.clear()

    mistakes_list = res["mistakes"]
    if not mistakes_list:
        mistakes_text = "\n\n🎉 <b>Barakalla! Birorta ham xato yo'q (100% natija)!</b>"
    else:
        shown_mistakes = "\n".join(mistakes_list[:25])
        more_cnt = f"\n<i>...va yana {len(mistakes_list) - 25} ta xato</i>" if len(mistakes_list) > 25 else ""
        mistakes_text = f"\n\n❌ <b>Xato qilingan savollar ({len(mistakes_list)} ta):</b>\n{shown_mistakes}{more_cnt}"

    exp_text = f"\n\n💡 <b>AI Tahlil va Yechim izohi:</b>\n{ai_exp[:600]}" if ai_exp else ""

    final_report = (
        f"👤 <b>O'quvchi:</b> {full_name}\n"
        f"🔑 <b>Test kodi:</b> <code>{test_code}</code> ({title})\n\n"
        f"{res['summary']}"
        f"{mistakes_text}"
        f"{exp_text}"
    )

    await message.answer(final_report, parse_mode="HTML", reply_markup=main_menu(uid))

# -------------------------------------------------------------
# REYTING VA NATIJALAR JADVALI
# -------------------------------------------------------------
@dp.message(F.text == "🏆 Reyting (Natijalar)")
async def show_ratings_menu(message: types.Message):
    if not await check_channel_subscription(message.from_user.id):
        await prompt_subscription(message)
        return

    recent = db_get_recent_tests(8)
    if not recent:
        await message.answer("📭 Hozircha test natijalari mavjud emas.")
        return

    kb_rows = []
    for r_code, r_type, r_title, _ in recent:
        kb_rows.append([InlineKeyboardButton(text=f"🏆 {r_code} — {r_title}", callback_data=f"rating:{r_code}")])

    await message.answer(
        "🏆 <b>Qaysi test bo'yicha reyting jadvalini ko'rmoqchisiz?</b>\nTanlang 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )

@dp.callback_query(F.data.startswith("rating:"))
async def cb_show_test_rating(callback: types.CallbackQuery):
    test_code = callback.data.split(":")[1]
    top_rows = db_get_top_results(test_code, 15)
    if not top_rows:
        await callback.answer("Bu testni hali hech kim yechmagan!", show_alert=True)
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = [f"🏆 <b>{test_code} TESTI BO'YICHA TOP NATIJALAR:</b>\n────────────────────────"]
    for idx, (f_name, corr, score, grade) in enumerate(top_rows, start=1):
        prefix = medals[idx - 1] if idx <= 3 else f"{idx}."
        lines.append(f"{prefix} <b>{f_name}</b> — <b>{score} ball</b> ({corr} ta)")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()

# -------------------------------------------------------------
# AI MASALA YECHISH (RASM ORQALI HAR QANDAY KIMYO MASALASI)
# -------------------------------------------------------------
@dp.message(F.text == "🤖 AI Masala Yechish (Rasm)")
async def start_ai_problem_solver(message: types.Message, state: FSMContext):
    if not await check_channel_subscription(message.from_user.id):
        await prompt_subscription(message)
        return

    await state.set_state(AISolveProblem.waiting_problem_photo)
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await message.answer(
        "📸 <b>AI Kimyo Masala Yechish Bo'limi</b>\n\n"
        "Tushunmagan kimyo masalangiz yoki test savolingizni <b>rasmga olib</b> shu yerga yuboring.\n"
        "Sun'iy intellekt uni mantiqiy usulda qadamma-qadam yechib beradi! 👇",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )

@dp.message(AISolveProblem.waiting_problem_photo, F.photo)
async def handle_problem_photo_solve(message: types.Message, state: FSMContext):
    wait_msg = await message.answer("🤖 <b>Sun'iy intellekt masalani yechmoqda...</b> ⏳", parse_mode="HTML")
    try:
        photo_id = message.photo[-1].file_id
        tg_file = await bot.get_file(photo_id)
        buf = io.BytesIO()
        await bot.download_file(tg_file.file_path, destination=buf)
        solution = await ai_solve_photo_problem(buf.getvalue(), "image/jpeg")
        await state.clear()
        await wait_msg.delete()
        await message.answer(
            f"🧪 <b>AI Masala Yechimi:</b>\n\n{solution}",
            reply_markup=main_menu(message.from_user.id)
        )
    except Exception as e:
        await state.clear()
        await wait_msg.edit_text(f"❌ Xatolik yuz berdi: {e}")

@dp.message(F.text == "👨‍🏫 Ustoz & Bog'lanish")
async def teacher_and_contact_info(message: types.Message):
    if not await check_channel_subscription(message.from_user.id):
        await prompt_subscription(message)
        return

    await message.answer(
        f"👨‍🏫 <b>Ustoz haqida:</b>\n"
        f"• <b>Azizbek Ibrohimov</b> — Kimyo fani bo'yicha maxsus uslubiyot muallifi;\n"
        f"• DTM va Milliy Sertifikat imtihonlariga tayyorlovchi murabbiy;\n"
        f"• Kimyo masalalarini quruq formulalarsiz, mantiqiy va tezkor yechish uslubi muallifi.\n\n"
        f"📢 <b>Rasmiy kanal:</b> {DEFAULT_CHANNEL_URL}\n"
        f"📞 <b>Bog'lanish uchun:</b> {ADMIN_USERNAME}",
        parse_mode="HTML",
        disable_web_page_preview=True
    )

# -------------------------------------------------------------
# ADMIN BOSHQARUV PANELI (/admin)
# -------------------------------------------------------------
@dp.message(Command("admin"))
async def admin_main(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    cur_ch, _ = get_required_channel_data()
    has_ai_key = "✅ Ulangan" if get_gemini_api_key() else "❌ Kiritilmagan"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 AI orqali Test Yaratish (PDF/Rasm)", callback_data="adm_btn_ai_test")],
            [InlineKeyboardButton(text="🔑 Gemini AI API Kalitni kiritish", callback_data="adm_btn_gemini")],
            [InlineKeyboardButton(text="📢 Majburiy kanalni o'zgartirish", callback_data="adm_btn_ch")],
            [InlineKeyboardButton(text="🗑 Testni o'chirish", callback_data="adm_btn_del_test")],
            [InlineKeyboardButton(text="📊 Statistika", callback_data="adm_btn_stats")],
            [InlineKeyboardButton(text="📨 Barchaga xabar yuborish", callback_data="adm_btn_sendall")]
        ]
    )
    text = (
        f"👑 <b>Ustoz & Admin Boshqaruv Paneli:</b>\n\n"
        f"🤖 Sun'iy Intellekt (Gemini API): <b>{has_ai_key}</b>\n"
        f"📢 Majburiy kanal: <b>{cur_ch or 'O`chirilgan'}</b>\n\n"
        f"<i>⚠️ Eslatma: Majburiy obuna ishlashi uchun botingiz {cur_ch or DEFAULT_REQUIRED_CHANNEL} kanalida Admin bo'lishi kerak!</i>\n\n"
        f"Kerakli amalni tanlang 👇"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_btn_ai_test")
async def cb_adm_ai_test_shortcut(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await admin_start_ai_test(callback.message, state)
    await callback.answer()

@dp.callback_query(F.data == "adm_btn_gemini")
async def adm_change_gemini_key(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminPanel.waiting_gemini_key)
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await callback.message.answer(
        "🔑 <b>Google Gemini API kalitini yuboring:</b>\n\n"
        "<i>Bepul kalitni 30 soniyada <a href='https://aistudio.google.com/app/apikey'>aistudio.google.com/app/apikey</a> saytidan olib, shu yerga tashlang (AIzaSy... bilan boshlanadi):</i>",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=cancel_kb
    )
    await callback.answer()

@dp.message(AdminPanel.waiting_gemini_key)
async def adm_save_gemini_key(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    key_val = message.text.strip()
    db_set_setting("gemini_api_key", key_val)
    await state.clear()
    await message.answer(
        "✅ <b>Gemini AI API kaliti saqlandi!</b>\n"
        "Endi botga PDF yoki rasm tashlab 30, 43 va 90 talik test kalitlarini avtomatik tuzdirishingiz mumkin!",
        parse_mode="HTML",
        reply_markup=main_menu(ADMIN_ID)
    )

@dp.callback_query(F.data == "adm_btn_del_test")
async def adm_ask_delete_test(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminPanel.waiting_delete_code)
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await callback.message.answer(
        "🗑 O'chirmoqchi bo'lgan <b>Test kodini</b> yozib yuboring (masalan: <code>MS-1014</code>):",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    await callback.answer()

@dp.message(AdminPanel.waiting_delete_code)
async def adm_perform_delete_test(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip().upper()
    ok = db_delete_test(code)
    await state.clear()
    if ok:
        await message.answer(f"✅ <b>{code}</b> kodli test bazadan o'chirildi!", parse_mode="HTML", reply_markup=main_menu(ADMIN_ID))
    else:
        await message.answer(f"❌ <b>{code}</b> kodli test topilmadi.", parse_mode="HTML", reply_markup=main_menu(ADMIN_ID))

@dp.callback_query(F.data == "adm_btn_ch")
async def adm_change_channel(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminPanel.waiting_channel)
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await callback.message.answer(
        "📢 <b>Majburiy obuna kanal havolasini yoki userini yuboring:</b>\n"
        "(Masalan: <code>https://t.me/Kimyo_Sertifkat_uchun</code> yoki <code>@Kimyo_Sertifkat_uchun</code>, o'chirish uchun <code>none</code>)",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    await callback.answer()

@dp.message(AdminPanel.waiting_channel)
async def adm_save_channel(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    val = message.text.strip()
    if val.lower() in ["none", "0", "off"]:
        db_set_setting("required_channel", "none")
        await state.clear()
        await message.answer("✅ Majburiy obuna o'chirildi!", reply_markup=main_menu(ADMIN_ID))
        return
    db_set_setting("required_channel", val)
    chat_id, ch_url = get_required_channel_data()
    await state.clear()
    await message.answer(
        f"✅ Majburiy obuna kanali saqlandi: <b>{chat_id}</b> ({ch_url})\n"
        f"⚠️ Botni ushbu kanalga <b>Admin</b> qilib qo'shishni unutmang!",
        parse_mode="HTML",
        reply_markup=main_menu(ADMIN_ID)
    )

@dp.callback_query(F.data == "adm_btn_stats")
async def adm_show_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    s = db_get_stats()
    text = (
        "📊 <b>BOT STATISTIKASI:</b>\n"
        "────────────────────────\n"
        f"👥 Jami o'quvchilar: <b>{s['users']} ta</b>\n"
        f"🧪 Yaratilgan testlar: <b>{s['tests']} ta</b>\n"
        f"📝 Tekshirilgan natijalar: <b>{s['results']} ta</b>\n"
        "────────────────────────"
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "adm_btn_sendall")
async def adm_ask_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminPanel.waiting_broadcast)
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await callback.message.answer("Barchaga jo'natiladigan xabarni yozing:", reply_markup=cancel_kb)
    await callback.answer()

@dp.message(AdminPanel.waiting_broadcast)
async def adm_run_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    users = db_get_all_users()
    count = 0
    await message.answer(f"⏳ {len(users)} ta o'quvchiga yuborilmoqda...")
    for uid in users:
        try:
            await message.send_copy(chat_id=uid)
            count += 1
            await asyncio.sleep(0.04)
        except Exception:
            pass
    await state.clear()
    await message.answer(f"✅ Xabar {count} ta o'quvchiga yetkazildi!", reply_markup=main_menu(ADMIN_ID))

# -------------------------------------------------------------
# 24/7 UPTIMEROBOT UCHUN WEB SERVER
# -------------------------------------------------------------
async def handle_ping(request):
    return web.Response(text="A+ Kimyo AI Test Bot is active 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f">>> Render Web Port {port} faol!")

# -------------------------------------------------------------
# ASOSIY ISHGA TUSHIRISH
# -------------------------------------------------------------
async def main():
    init_db()
    print("=" * 60)
    print(">>> A+ Kimyo AI Test Tekshirgich Boti (30, 43 MS, 90 DTM) ishga tushdi!")
    print(f">>> Majburiy obuna kanali: {DEFAULT_REQUIRED_CHANNEL} ({DEFAULT_CHANNEL_URL})")
    print("=" * 60)
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
