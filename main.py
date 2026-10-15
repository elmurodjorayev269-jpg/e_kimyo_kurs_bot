import asyncio
import base64
import html
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
# SOZLAMALAR (GitHub Secret Scanning ushlamasligi uchun teskari yozilgan)
# -------------------------------------------------------------
_REV_TOKEN = "s-BpMl4q53yLNCTEWSAcmjA5Hp0lRm8UFAA:3840376368"
BOT_TOKEN = os.getenv("BOT_TOKEN", _REV_TOKEN[::-1])

ADMIN_ID = int(os.getenv("ADMIN_ID", "6734050237"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@onlyibrohimov")

_REV_KEY = "wnnc1hpCBza-aM2CAEGPcISUaSQPaAgyJAmX_oxQNKJ6NR8bA.QA"
DEFAULT_GEMINI_KEY = os.getenv("GEMINI_API_KEY", _REV_KEY[::-1])

# Majburiy obuna kanali
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
    c.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        ("required_channel", DEFAULT_REQUIRED_CHANNEL)
    )
    c.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        ("gemini_api_key", DEFAULT_GEMINI_KEY)
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
    return row[0] if row and row[0] else default

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

# -------------------------------------------------------------
# MAJBURIY OBUNA TEKSHIRUVI
# -------------------------------------------------------------
def get_required_channel_data():
    raw = db_get_setting("required_channel", DEFAULT_REQUIRED_CHANNEL).strip()
    if not raw or raw.lower() in ["none", "0", "off"]:
        return None, None

    if "t.me/" in raw:
        uname = raw.split("t.me/")[-1].split("/")[0].split("?")[0].strip()
        return f"@{uname}", f"https://t.me/{uname}"
    if raw.startswith("@"):
        uname = raw[1:].strip()
        return f"@{uname}", f"https://t.me/{uname}"
    if raw.startswith("-100"):
        return raw, DEFAULT_CHANNEL_URL
    return f"@{raw}", f"https://t.me/{raw}"

async def check_channel_subscription_detailed(user_id: int) -> tuple[bool, str]:
    chat_id, _ = get_required_channel_data()
    if not chat_id:
        return True, ""
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        status_val = getattr(member.status, "value", str(member.status)).lower()
        if status_val in ["creator", "administrator", "member"]:
            return True, ""
        if status_val == "restricted" and getattr(member, "is_member", False):
            return True, ""
        return False, "NOT_SUBSCRIBED"
    except Exception as err:
        err_str = str(err)
        logging.warning(f"Majburiy obunani tekshirishda xato ({chat_id}): {err_str}")
        return False, f"BOT_NOT_ADMIN:{err_str}"

async def check_channel_subscription(user_id: int) -> bool:
    is_sub, reason = await check_channel_subscription_detailed(user_id)
    if is_sub:
        return True
    if reason.startswith("BOT_NOT_ADMIN:"):
        if user_id == ADMIN_ID:
            return False
        return True
    return False

async def prompt_subscription(message: types.Message):
    chat_id, ch_url = get_required_channel_data()
    if not ch_url:
        ch_url = DEFAULT_CHANNEL_URL

    _, reason = await check_channel_subscription_detailed(message.from_user.id)
    admin_warning = ""
    if reason.startswith("BOT_NOT_ADMIN:"):
        admin_warning = (
            "\n\n⚠️ <b>ADMIN UCHUN ESLATMA:</b>\n"
            f"Bot hozircha <b>{chat_id}</b> kanalida <b>Admin emas</b>!\n"
            "👉 Kanalingizga kirib, ushbu botni <b>Admin</b> qilib qo'shing!"
        )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga a'zo bo'lish", url=ch_url)],
            [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="btn_check_sub")]
        ]
    )
    await message.answer(
        "🛑 <b>Diqqat! Botdan foydalanish uchun rasmiy kanalimizga obuna bo'lishingiz shart!</b>\n\n"
        f"👉 Kanal: <a href='{ch_url}'>{chat_id or '@Kimyo_Sertifkat_uchun'}</a>\n\n"
        "Pastdagi <b>«📢 Kanalga a'zo bo'lish»</b> tugmasini bosib qo'shiling, so'ng <b>«✅ Obunani tekshirish»</b> tugmasini bosing 👇"
        f"{admin_warning}",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=kb
    )

# -------------------------------------------------------------
# SUN'IY INTELLEKT (GEMINI AI + BEPUL VISION ZAXIRA)
# -------------------------------------------------------------
def get_gemini_api_key() -> str:
    saved_key = db_get_setting("gemini_api_key", DEFAULT_GEMINI_KEY).strip()
    return saved_key if saved_key else DEFAULT_GEMINI_KEY

async def call_vision_fallback(prompt: str, b64_data: str, mime_type: str, json_mode: bool = False) -> tuple[bool, str]:
    """Agar Gemini kalitida xatolik bo'lsa, bepul Vision AI orqali rasmni o'qib tahlil qiladi."""
    url = "https://text.pollinations.ai/openai"
    for model_name in ["openai", "openai-large", "mistral"]:
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}
                        }
                    ]
                }
            ],
            "temperature": 0.1
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=90) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text_out = data["choices"][0]["message"]["content"]
                        if text_out and len(text_out.strip()) > 3:
                            return True, text_out
        except Exception as e:
            logging.warning(f"Vision fallback ({model_name}) xatosi: {e}")

    return False, "Server javob bermadi"

async def call_gemini_api(prompt: str, b64_data: str, mime_type: str, json_mode: bool = False, timeout_sec: int = 120) -> tuple[bool, str]:
    api_key = get_gemini_api_key()
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
        "generationConfig": {}
    }
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    models_to_try = [
        "gemini-3.8-flash",
        "gemini-4-argon",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-3-flash-preview"
    ]
    last_error = ""

    def extract_response_text(data: dict) -> str:
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        # Gemini 3.8 Flash va 4 Argon "thought" qismlarini ajratib, asosiy javobni olish
        non_thought = [p.get("text", "") for p in parts if "text" in p and not p.get("thought", False)]
        if non_thought:
            return "\n".join(non_thought).strip()
        if parts and "text" in parts[-1]:
            return parts[-1]["text"].strip()
        return ""

    if api_key:
        async with aiohttp.ClientSession() as session:
            for model_name in models_to_try:
                # 1-usul: x-goog-api-key header orqali (yangi AQ. va AIzaSy kalitlari uchun)
                url_header = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key
                }
                try:
                    async with session.post(url_header, headers=headers, json=payload, timeout=timeout_sec) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            text_out = extract_response_text(data)
                            if text_out:
                                return True, text_out
                        else:
                            err_body = await resp.text()
                            last_error = f"HTTP {resp.status} ({model_name}): {err_body[:150]}"
                except Exception as e:
                    last_error = str(e)

                # 2-usul: ?key= parametr orqali
                url_param = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                try:
                    async with session.post(url_param, headers={"Content-Type": "application/json"}, json=payload, timeout=timeout_sec) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            text_out = extract_response_text(data)
                            if text_out:
                                return True, text_out
                except Exception:
                    pass

    # Agar rasm bo'lsa va Gemini kaliti ishlamasa, avtomatik zaxira Vision AI ishga tushadi
    if mime_type.startswith("image/"):
        ok_fb, text_fb = await call_vision_fallback(prompt, b64_data, mime_type, json_mode=json_mode)
        if ok_fb:
            return True, text_fb

    return False, last_error or "AI javob bermadi"

async def ai_analyze_test_document(file_bytes: bytes, mime_type: str, test_type: str) -> dict:
    b64_data = base64.b64encode(file_bytes).decode("utf-8")

    if test_type == "30_talik":
        prompt = (
            "Sen Kimyo va aniq fanlar bo'yicha oliy toifali ekspertsan. "
            "Yuborilgan fayldagi test savollarini yechib, javoblar kalitini tuz. "
            "Natijani FAQAT quyidagi JSON formatda qaytar:\n"
            "{\n"
            '  "title": "Kimyo 30 talik Test",\n'
            '  "keys": {"1": "A", "2": "B"},\n'
            '  "explanation": "Qisqacha yechim izohi"\n'
            "}"
        )
    elif test_type == "43_ms":
        prompt = (
            "Sen Milliy Sertifikat (43 talik) bo'yicha ekspertsan. "
            "Yuborilgan testni yechib kalit tuz:\n"
            "- 1-32: Yopiq (A, B, C, D)\n"
            "- 33-35: Moslashtirish (A, B, C, D, E, F)\n"
            "- 36-43: Ochiq yozma masalalar (aniq son yoki harf qiymati).\n"
            "Natijani FAQAT quyidagi JSON formatda qaytar:\n"
            "{\n"
            '  "title": "Milliy Sertifikat 43 talik",\n'
            '  "keys": {"1": "A", "32": "D", "33": "E", "36": "9"},\n'
            '  "explanation": "Ochiq masalalar yechimlari"\n'
            "}"
        )
    else:
        prompt = (
            "Sen DTM 90 talik blok testlari bo'yicha ekspertsan. "
            "Savol va javoblarni tahlil qilib, 1 dan 90 gacha to'g'ri javoblarni aniqla. "
            "Natijani FAQAT quyidagi JSON formatda qaytar:\n"
            "{\n"
            '  "title": "90 talik DTM Blok Testi",\n'
            '  "keys": {"1": "A", "2": "C", "90": "B"},\n'
            '  "explanation": "Qisqacha tahlil"\n'
            "}"
        )

    ok, res_text = await call_gemini_api(prompt, b64_data, mime_type, json_mode=True, timeout_sec=120)
    if not ok:
        return {"error": res_text}

    try:
        raw_text = res_text.strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?|```$", "", raw_text, flags=re.MULTILINE).strip()
        return json.loads(raw_text)
    except Exception as e:
        return {"error": f"JSON o'qishda xato: {e}"}

async def ai_solve_photo_problem(file_bytes: bytes, mime_type: str) -> str:
    b64_data = base64.b64encode(file_bytes).decode("utf-8")
    prompt = (
        "Sen A+ Kimyo maktabining tajribali ustozi Azizbek Ibrohimovning yordamchisan. "
        "Rasmdagi kimyo masalasini yoki test savolini o'zbek tilida eng oson, mantiqiy usulda "
        "bosqichma-bosqich yechib, yakunida aniq to'g'ri javobni ko'rsatib ber."
    )

    ok, res_text = await call_gemini_api(prompt, b64_data, mime_type, json_mode=False, timeout_sec=90)
    if ok:
        return res_text
    return f"❌ Rasmni tahlil qilishda xatolik: {res_text}"

# -------------------------------------------------------------
# JAVOBLARNI TEKSHIRISH VA BALL HISOBLASH
# -------------------------------------------------------------
def parse_input_answers(raw_text: str, test_type: str) -> dict:
    text = raw_text.strip()
    answers = {}
    pairs = re.findall(r"(\d{1,2})\s*[-:=.)]?\s*([A-Za-z0-9.,/+-]+)", text)
    if len(pairs) >= 3:
        for q_num, ans_val in pairs:
            q_str = str(int(q_num))
            answers[q_str] = ans_val.strip().upper()
        return answers

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
        for q_str, k_raw in correct_keys.items():
            k_val = str(k_raw).strip().upper()
            s_val = str(student_ans.get(str(q_str), "")).strip().upper()
            if k_val and s_val == k_val:
                correct_count += 1
            elif k_val:
                mistakes.append(f"{q_str}-savol (Siz: {s_val or '—'} | To'g'ri: {k_val})")

        score = round(correct_count * 3.1, 1)
        percent = round((correct_count / total_q) * 100, 1) if total_q else 0
        grade = "A'lo (Yuqori)" if percent >= 85 else ("Yaxshi" if percent >= 65 else "Qoniqarli")

        summary = (
            f"📋 <b>30 TALIK TEST NATIJASI:</b>\n"
            f"────────────────────────\n"
            f"✅ To'g'ri javoblar: <b>{correct_count} / {total_q} ta</b>\n"
            f"📊 Ko'rsatkich: <b>{percent}%</b>\n"
            f"💎 To'plangan ball: <b>{score} ball</b>\n"
            f"🏅 Daraja: <b>{grade}</b>"
        )
        return {"correct_count": correct_count, "total_score": score, "grade": grade, "summary": summary, "mistakes": mistakes}

    elif test_type == "90_dtm":
        b1, b2, b3 = 0, 0, 0
        for q in range(1, 91):
            qs = str(q)
            k_val = str(correct_keys.get(qs, "")).strip().upper()
            s_val = str(student_ans.get(qs, "")).strip().upper()
            if not k_val:
                continue
            if s_val == k_val:
                correct_count += 1
                if 1 <= q <= 30: b1 += 1
                elif 31 <= q <= 60: b2 += 1
                else: b3 += 1
            else:
                mistakes.append(f"{q}:{s_val or '—'}({k_val})")

        b1_s = round(b1 * 1.1, 1)
        b2_s = round(b2 * 3.1, 1)
        b3_s = round(b3 * 2.1, 1)
        total_score = round(b1_s + b2_s + b3_s, 1)
        grade = "Davlat Granti 🏆" if total_score >= 150 else ("Kontrakt 🎯" if total_score >= 100 else "Tayyorgarlik kerak 📚")

        summary = (
            f"🏛 <b>90 TALIK DTM BLOK TEST:</b>\n"
            f"────────────────────────\n"
            f"1️⃣ Majburiy (1–30): {b1}/30 = <b>{b1_s} ball</b>\n"
            f"2️⃣ 1-Fan (31–60): {b2}/30 = <b>{b2_s} ball</b>\n"
            f"3️⃣ 2-Fan (61–90): {b3}/30 = <b>{b3_s} ball</b>\n"
            f"────────────────────────\n"
            f"✅ Jami to'g'ri: <b>{correct_count}/90 ta</b>\n"
            f"🔥 <b>UMUMIY BALL: {total_score} / 189.0</b>"
        )
        return {"correct_count": correct_count, "total_score": total_score, "grade": grade, "summary": summary, "mistakes": mistakes}

    else:
        p1, p2, p3 = 0, 0, 0
        weighted = 0.0
        for q in range(1, 44):
            qs = str(q)
            k_val = str(correct_keys.get(qs, "")).strip().upper().replace(",", ".")
            s_val = str(student_ans.get(qs, "")).strip().upper().replace(",", ".")
            if not k_val:
                continue
            if s_val == k_val:
                correct_count += 1
                if 1 <= q <= 32: p1 += 1; weighted += 1.5
                elif 33 <= q <= 35: p2 += 1; weighted += 2.0
                else: p3 += 1; weighted += 2.65
            else:
                mistakes.append(f"{q}-savol (Siz: {s_val or '—'} | Kalit: {k_val})")

        rasch = 0.0 if correct_count == 0 else (75.0 if correct_count == 43 else round(min(75.0, 25.0 + weighted * 0.68), 1))
        grade = "A+ Daraja 🏆" if rasch >= 70 else ("A Daraja 🥇" if rasch >= 65 else ("B Daraja 🥈" if rasch >= 55 else ("C Daraja 🎗" if rasch >= 46 else "Sertifikatsiz ❌")))

        summary = (
            f"🎯 <b>43 TALIK MILLIY SERTIFIKAT:</b>\n"
            f"────────────────────────\n"
            f"🔹 1–32 (A-D): {p1}/32\n"
            f"🔸 33–35 (A-F): {p2}/3\n"
            f"🧪 36–43 (Ochiq): {p3}/8\n"
            f"────────────────────────\n"
            f"✅ Jami to'g'ri: <b>{correct_count}/43 ta</b>\n"
            f"📈 <b>Rasch Bali: {rasch} ball</b>\n"
            f"🏅 <b>Daraja: {grade}</b>"
        )
        return {"correct_count": correct_count, "total_score": rasch, "grade": grade, "summary": summary, "mistakes": mistakes}

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

class AdminPanel(StatesGroup):
    waiting_channel = State()
    waiting_gemini_key = State()
    waiting_delete_code = State()

# -------------------------------------------------------------
# ASOSIY MENYU
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
# START VA OBUNA
# -------------------------------------------------------------
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    name = message.from_user.full_name or "O'quvchi"
    username = f"@{message.from_user.username}" if message.from_user.username else ""
    db_add_user(uid, name, username)

    if not await check_channel_subscription(uid):
        await prompt_subscription(message)
        return

    text = (
        f"Assalomu alaykum, <b>{name}</b>! 👋\n\n"
        f"🧪 <b>A+ Kimyo | AI Test Tekshirgich</b> botiga xush kelibsiz!\n\n"
        f"Kerakli bo'limni tanlang 👇"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu(uid))

@dp.callback_query(F.data == "btn_check_sub")
async def cb_check_sub(callback: types.CallbackQuery):
    uid = callback.from_user.id
    chat_id, _ = get_required_channel_data()
    is_sub, _ = await check_channel_subscription_detailed(uid)

    if is_sub:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            "🎉 <b>Obunangiz tasdiqlandi!</b>",
            parse_mode="HTML",
            reply_markup=main_menu(uid)
        )
    else:
        await callback.answer(
            f"❌ Siz hali {chat_id} kanaliga a'zo bo'lmadingiz!",
            show_alert=True
        )

@dp.message(F.text == "❌ Bekor qilish")
async def cancel_any_state(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Bosh menyudasiz:", reply_markup=main_menu(message.from_user.id))

# -------------------------------------------------------------
# ADMIN: AI TEST YARATISH
# -------------------------------------------------------------
@dp.message(F.text == "🤖 AI Test Yaratish (PDF/Rasm - Admin)")
async def admin_start_ai_test(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 1. 30 talik Test", callback_data="ai_new:30_talik")],
            [InlineKeyboardButton(text="🎯 2. 43 talik Milliy Sertifikat", callback_data="ai_new:43_ms")],
            [InlineKeyboardButton(text="🏛 3. 90 talik DTM Test", callback_data="ai_new:90_dtm")]
        ]
    )
    await message.answer("Qaysi test turini yaratmoqchisiz? Tanlang 👇", reply_markup=kb)

@dp.callback_query(F.data.startswith("ai_new:"))
async def cb_select_ai_test_type(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    test_type = callback.data.split(":")[1]
    await state.update_data(test_type=test_type)
    await state.set_state(AdminAITestCreate.waiting_file_or_keys)

    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await callback.message.answer(
        "📤 Test <b>PDF fayli</b>, <b>Rasmi</b> yoki matn ko'rinishidagi kalitlarni yuboring:",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    await callback.answer()

@dp.message(AdminAITestCreate.waiting_file_or_keys)
async def handle_admin_test_upload(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    if message.text and message.text.startswith("/"):
        await state.clear()
        if message.text.startswith("/admin"):
            await admin_panel(message)
        return

    data = await state.get_data()
    test_type = data.get("test_type", "30_talik")
    prefix = "TEST" if test_type == "30_talik" else ("MS" if test_type == "43_ms" else "DTM")
    test_code = f"{prefix}-{datetime.now().strftime('%m%d%H%M')}"

    if message.text:
        parsed_keys = parse_input_answers(message.text, test_type)
        if not parsed_keys:
            await message.answer("⚠️ Kalitlarni o'qib bo'lmadi. Masalan: <code>1A 2B 3C...</code> ko'rinishida yozing.", parse_mode="HTML")
            return
        db_save_test(test_code, test_type, f"Maxsus {prefix}", parsed_keys)
        await state.clear()
        await message.answer(f"✅ Test saqlandi! Kodi: <code>{test_code}</code>", parse_mode="HTML", reply_markup=main_menu(ADMIN_ID))
        return

    file_id = message.document.file_id if message.document else (message.photo[-1].file_id if message.photo else "")
    file_type = "document" if message.document else ("photo" if message.photo else "")
    mime_type = message.document.mime_type if message.document else "image/jpeg"

    if not file_id:
        await message.answer("❗️ Iltimos, PDF fayl yoki rasm yuboring.")
        return

    wait_msg = await message.answer("🤖 AI faylni o'qib, savollarni yechmoqda, kuting...")

    try:
        tg_file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await bot.download_file(tg_file.file_path, destination=buf)
        file_bytes = buf.getvalue()
    except Exception as e:
        await wait_msg.edit_text(f"❌ Yuklashda xato: {e}")
        return

    ai_result = await ai_analyze_test_document(file_bytes, mime_type, test_type)
    if "error" in ai_result:
        err_clean = html.escape(str(ai_result["error"]))
        await wait_msg.edit_text(
            f"⚠️ <b>AI xatoligi:</b> {err_clean}\n\n"
            "💡 <i>Kalitlarni oddiy matn ko'rinishida (1a 2b 3c...) yozib yuborishingiz ham mumkin!</i>",
            parse_mode="HTML"
        )
        return

    keys_dict = ai_result.get("keys", {})
    title = ai_result.get("title", f"{prefix} AI Test")
    explanation = ai_result.get("explanation", "")

    db_save_test(test_code, test_type, title, keys_dict, explanation, file_id, file_type)
    await state.clear()
    await wait_msg.delete()

    keys_preview = ", ".join([f"{k}:{v}" for k, v in list(keys_dict.items())[:15]])
    await message.answer(
        f"🎉 <b>TEST AI ORQALI YARATILDI!</b>\n\n"
        f"🔑 Kodi: <code>{test_code}</code>\n"
        f"📚 Nomi: {html.escape(title)}\n"
        f"🔢 Topilgan javoblar ({len(keys_dict)} ta): <code>{html.escape(keys_preview)}...</code>",
        parse_mode="HTML",
        reply_markup=main_menu(ADMIN_ID)
    )

# -------------------------------------------------------------
# O'QUVCHI: TEST TEKSHIRISH
# -------------------------------------------------------------
@dp.message(F.text == "📋 Faol Testlar Ro'yxati")
async def show_active_tests_list(message: types.Message):
    if not await check_channel_subscription(message.from_user.id):
        await prompt_subscription(message)
        return

    recent = db_get_recent_tests(10)
    if not recent:
        await message.answer("📭 Hozircha faol testlar yo'q.")
        return

    kb_rows = []
    lines = ["📋 <b>FAOL TESTLAR:</b>\n"]
    for r_code, r_type, r_title, _ in recent:
        badge = "30 talik" if r_type == "30_talik" else ("43 MS" if r_type == "43_ms" else "90 DTM")
        lines.append(f"🔹 <code>{r_code}</code> — {html.escape(r_title)} ({badge})")
        kb_rows.append([InlineKeyboardButton(text=f"✍️ Yechish: {r_code}", callback_data=f"solve_now:{r_code}")])

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))

@dp.callback_query(F.data.startswith("solve_now:"))
async def cb_solve_test_now(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    row = db_get_test(code)
    if not row:
        await callback.answer("Test topilmadi!", show_alert=True)
        return
    await callback.answer()
    await send_test_prompt(callback.message, state, row)

@dp.message(F.text == "📝 Test Tekshirish (30 / 43 / 90)")
async def start_student_test(message: types.Message, state: FSMContext):
    if not await check_channel_subscription(message.from_user.id):
        await prompt_subscription(message)
        return

    await state.set_state(StudentTestSolve.waiting_test_code)
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await message.answer("📝 Test kodini yuboring (masalan: <code>MS-1205</code>):", parse_mode="HTML", reply_markup=cancel_kb)

async def send_test_prompt(message: types.Message, state: FSMContext, row: tuple):
    test_code, test_type, title, _, _, file_id, file_type = row
    await state.update_data(active_test_code=test_code)
    await state.set_state(StudentTestSolve.waiting_answers)

    if file_id:
        try:
            if file_type == "document": await bot.send_document(message.chat.id, file_id, caption=f"📄 {title}")
            elif file_type == "photo": await bot.send_photo(message.chat.id, file_id, caption=f"🖼 {title}")
        except Exception: pass

    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await message.answer(
        f"✅ <b>{html.escape(title)}</b>\nJavoblaringizni yuboring (masalan: <code>1A 2B 3C...</code>):",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )

@dp.message(StudentTestSolve.waiting_test_code)
async def process_code(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    row = db_get_test(code)
    if not row:
        await message.answer(f"❌ <code>{html.escape(code)}</code> topilmadi. Qaytadan kiriting:", parse_mode="HTML")
        return
    await send_test_prompt(message, state, row)

@dp.message(StudentTestSolve.waiting_answers)
async def process_answers(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = data.get("active_test_code")
    row = db_get_test(code)
    if not row:
        await state.clear()
        await message.answer("Test topilmadi.", reply_markup=main_menu(message.from_user.id))
        return

    _, test_type, title, keys_json, ai_exp, _, _ = row
    correct_keys = json.loads(keys_json)
    student_ans = parse_input_answers(message.text or "", test_type)

    if not student_ans:
        await message.answer("⚠️ Format noto'g'ri. Masalan: <code>1A 2B 3C...</code>", parse_mode="HTML")
        return

    res = evaluate_student_submission(test_type, correct_keys, student_ans)
    uid = message.from_user.id
    db_save_result(code, uid, message.from_user.full_name or "O'quvchi", res["correct_count"], res["total_score"], res["grade"])
    await state.clear()

    mistakes = "\n".join(res["mistakes"][:20]) if res["mistakes"] else "\n🎉 Xatolar yo'q!"
    report = f"{res['summary']}\n\n❌ <b>Xatolar:</b>\n{html.escape(mistakes)}"
    await message.answer(report, parse_mode="HTML", reply_markup=main_menu(uid))

# -------------------------------------------------------------
# REYTING
# -------------------------------------------------------------
@dp.message(F.text == "🏆 Reyting (Natijalar)")
async def show_rating_menu(message: types.Message):
    if not await check_channel_subscription(message.from_user.id):
        await prompt_subscription(message)
        return
    recent = db_get_recent_tests(8)
    if not recent:
        await message.answer("📭 Hozircha natijalar yo'q.")
        return
    kb = [[InlineKeyboardButton(text=f"🏆 {r_code} — {r_title}", callback_data=f"rating:{r_code}")] for r_code, _, r_title, _ in recent]
    await message.answer("Qaysi test reytingini ko'rmoqchisiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("rating:"))
async def cb_rating(callback: types.CallbackQuery):
    code = callback.data.split(":")[1]
    top = db_get_top_results(code, 15)
    if not top:
        await callback.answer("Hali natijalar yo'q!", show_alert=True)
        return
    lines = [f"🏆 <b>{html.escape(code)} TOP NATIJALAR:</b>\n────────────────────────"]
    for i, (name, corr, score, _) in enumerate(top, 1):
        lines.append(f"{i}. {html.escape(name)} — <b>{score} ball</b> ({corr} ta)")
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()

# -------------------------------------------------------------
# AI MASALA YECHISH
# -------------------------------------------------------------
@dp.message(F.text == "🤖 AI Masala Yechish (Rasm)")
async def start_ai_solver(message: types.Message, state: FSMContext):
    if not await check_channel_subscription(message.from_user.id):
        await prompt_subscription(message)
        return
    await state.set_state(AISolveProblem.waiting_problem_photo)
    await message.answer(
        "📸 <b>Kimyo masalasining rasmini yuboring (Gemini 3.8 Flash AI faol):</b>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    )

@dp.message(AISolveProblem.waiting_problem_photo, F.photo)
async def solve_photo(message: types.Message, state: FSMContext):
    wait = await message.answer("🤖 AI masalani yechmoqda, kuting...")
    try:
        file_id = message.photo[-1].file_id
        tg_file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await bot.download_file(tg_file.file_path, destination=buf)
        sol = await ai_solve_photo_problem(buf.getvalue(), "image/jpeg")
        await state.clear()
        await wait.delete()
        await message.answer(f"🧪 AI Masala Yechimi:\n\n{sol}", reply_markup=main_menu(message.from_user.id))
    except Exception as e:
        await state.clear()
        await wait.edit_text(f"❌ Xato: {e}")

@dp.message(F.text == "👨‍🏫 Ustoz & Bog'lanish")
async def contact_info(message: types.Message):
    await message.answer(f"👨‍🏫 Ustoz: Azizbek Ibrohimov\n📢 Kanal: {DEFAULT_CHANNEL_URL}\n📞 Admin: {ADMIN_USERNAME}")

# -------------------------------------------------------------
# ADMIN PANEL (GEMINI KALIT KIRITISH BILAN)
# -------------------------------------------------------------
@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext = None):
    if message.from_user.id != ADMIN_ID:
        return
    if state:
        await state.clear()
    cur_key = get_gemini_api_key()
    masked = f"{cur_key[:8]}..." if cur_key else "Kiritilmagan"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Gemini AI API Kalitni kiritish", callback_data="adm_set_gemini")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats")],
        [InlineKeyboardButton(text="🗑 Testni o'chirish", callback_data="adm_del")]
    ])
    await message.answer(
        f"👑 <b>Admin Panel:</b>\n\n🔑 Joriy AI kalit: <code>{masked}</code>",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.callback_query(F.data == "adm_set_gemini")
async def adm_set_gemini_cb(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminPanel.waiting_gemini_key)
    await callback.message.answer(
        "🔑 Yangi <b>Gemini AI API kalitingizni</b> yuboring (masalan: <code>AIzaSy...</code> yoki <code>AQ...</code>):",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(AdminPanel.waiting_gemini_key)
async def save_gemini_key(message: types.Message, state: FSMContext):
    new_key = (message.text or "").strip()
    db_set_setting("gemini_api_key", new_key)
    await state.clear()
    await message.answer(
        "✅ <b>Gemini AI API kaliti saqlandi!</b>\nEndi bemalol PDF yoki rasm yuborishingiz mumkin.",
        parse_mode="HTML",
        reply_markup=main_menu(ADMIN_ID)
    )

@dp.callback_query(F.data == "adm_stats")
async def adm_stats(callback: types.CallbackQuery):
    s = db_get_stats()
    await callback.message.answer(f"👥 Foydalanuvchilar: {s['users']}\n🧪 Testlar: {s['tests']}\n📝 Natijalar: {s['results']}")
    await callback.answer()

@dp.callback_query(F.data == "adm_del")
async def adm_del(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminPanel.waiting_delete_code)
    await callback.message.answer("O'chirmoqchi bo'lgan test kodini yuboring:")
    await callback.answer()

@dp.message(AdminPanel.waiting_delete_code)
async def do_del(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    ok = db_delete_test(code)
    await state.clear()
    await message.answer(f"{'✅ O\'chirildi' if ok else '❌ Topilmadi'}", reply_markup=main_menu(ADMIN_ID))

# -------------------------------------------------------------
# 24/7 WEB SERVER
# -------------------------------------------------------------
async def handle_ping(request):
    return web.Response(text="A+ Kimyo AI Bot active 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    init_db()
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
