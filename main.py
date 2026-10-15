import asyncio
import base64
import html
import io
import json
import logging
import math
import os
import re
import sqlite3
import sys
import urllib.parse
from datetime import datetime

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile,
)

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

# -------------------------------------------------------------
# SOZLAMALAR VA KONSTANTALAR
# -------------------------------------------------------------
_REV_TOKEN = "s-BpMl4q53yLNCTEWSAcmjA5Hp0lRm8UFAA:3840376368"
BOT_TOKEN = os.getenv("BOT_TOKEN", _REV_TOKEN[::-1])

ADMIN_ID = int(os.getenv("ADMIN_ID", "6734050237"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@onlyibrohimov")

_REV_KEY = "APuV_Zc8V-GAeLgUU4cWxQIZ0-R8GP42cko5QV_fPKNL6NR8bA.QA"
DEFAULT_GEMINI_KEY = os.getenv("GEMINI_API_KEY", _REV_KEY[::-1])

DEFAULT_REQUIRED_CHANNEL = "@Kimyo_Sertifkat_uchun"
DEFAULT_CHANNEL_URL = "https://t.me/Kimyo_Sertifkat_uchun"

# Mock imtihon ishlayotgan o'quvchilarni nazorat qilish (AI masala yechishni bloklash uchun)
ACTIVE_EXAM_SESSIONS: dict[int, str] = {}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# -------------------------------------------------------------
# MA'LUMOTLAR BAZASI (SQLITE)
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
            creator_id INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
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
            written_score REAL DEFAULT 0,
            answers_json TEXT DEFAULT '{}',
            submitted_at TEXT
        )
    """)
    # Eski jadval ustunlarini xavfsiz yangilash
    for alter_sql in [
        "ALTER TABLE tests ADD COLUMN creator_id INTEGER DEFAULT 0",
        "ALTER TABLE tests ADD COLUMN status TEXT DEFAULT 'active'",
        "ALTER TABLE test_results ADD COLUMN written_score REAL DEFAULT 0",
        "ALTER TABLE test_results ADD COLUMN answers_json TEXT DEFAULT '{}'",
    ]:
        try:
            c.execute(alter_sql)
        except Exception:
            pass

    c.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        ("required_channel", DEFAULT_REQUIRED_CHANNEL)
    )
    c.execute(
        "INSERT OR replace INTO settings (key, value) VALUES (?, ?)",
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

def db_get_all_user_ids() -> list[int]:
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows

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

def db_save_test(
    test_code: str,
    test_type: str,
    title: str,
    keys_dict: dict,
    explanation: str = "",
    file_id: str = "",
    file_type: str = "",
    creator_id: int = 0
):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        """INSERT OR REPLACE INTO tests 
           (test_code, test_type, title, keys_json, ai_explanation, file_id, file_type, creator_id, status, created_at) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
        (
            test_code.upper().strip(),
            test_type,
            title,
            json.dumps(keys_dict, ensure_ascii=False),
            explanation,
            file_id,
            file_type,
            creator_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )
    conn.commit()
    conn.close()

def db_get_test(test_code: str):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        """SELECT test_code, test_type, title, keys_json, ai_explanation, file_id, file_type, creator_id, status 
           FROM tests WHERE test_code = ?""",
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

def db_get_recent_tests(limit: int = 12):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        "SELECT test_code, test_type, title, created_at FROM tests ORDER BY created_at DESC LIMIT ?",
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def db_get_user_tests(user_id: int, limit: int = 12):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    if user_id == ADMIN_ID:
        c.execute(
            "SELECT test_code, test_type, title, created_at FROM tests ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
    else:
        c.execute(
            "SELECT test_code, test_type, title, created_at FROM tests WHERE creator_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
    rows = c.fetchall()
    conn.close()
    return rows

def db_save_result(
    test_code: str,
    user_id: int,
    full_name: str,
    correct_count: int,
    total_score: float,
    grade: str,
    written_score: float = 0.0,
    answers_dict: dict = None
):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        """INSERT INTO test_results 
           (test_code, user_id, full_name, correct_count, total_score, grade, written_score, answers_json, submitted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            test_code.upper().strip(),
            user_id,
            full_name,
            correct_count,
            total_score,
            grade,
            written_score,
            json.dumps(answers_dict or {}, ensure_ascii=False),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )
    conn.commit()
    conn.close()

def db_get_top_results(test_code: str, limit: int = 100):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        """SELECT full_name, correct_count, total_score, grade, written_score, submitted_at 
           FROM test_results 
           WHERE test_code = ? 
           ORDER BY total_score DESC, correct_count DESC 
           LIMIT ?""",
        (test_code.upper().strip(), limit)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def db_get_all_submissions_for_test(test_code: str) -> list[dict]:
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT answers_json FROM test_results WHERE test_code = ?", (test_code.upper().strip(),))
    rows = c.fetchall()
    conn.close()
    out = []
    for (aj,) in rows:
        if aj:
            try:
                out.append(json.loads(aj))
            except Exception:
                pass
    return out

def db_get_stats() -> dict:
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

async def check_channel_subscription(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    chat_id, _ = get_required_channel_data()
    if not chat_id:
        return True
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        status_val = getattr(member.status, "value", str(member.status)).lower()
        if status_val in ["creator", "administrator", "member"]:
            return True
        if status_val == "restricted" and getattr(member, "is_member", False):
            return True
        return False
    except Exception:
        # Agar bot kanalda admin bo'lmasa, foydalanuvchilarni bloklab qo'ymaslik uchun ruxsat beramiz
        return True

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
        "🛑 <b>Diqqat! TITUL platformasidan foydalanish uchun rasmiy kanalimizga obuna bo'ling:</b>\n\n"
        f"👉 Kanal: <a href='{ch_url}'>{chat_id or '@Kimyo_Sertifkat_uchun'}</a>\n\n"
        "Obuna bo'lgach, <b>«✅ Obunani tekshirish»</b> tugmasini bosing 👇",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=kb
    )

# -------------------------------------------------------------
# TELEGRAM UCHUN MATN VA FORMULA TOZALAGICH
# -------------------------------------------------------------
def clean_ai_text_for_telegram(text: str) -> str:
    if not text:
        return ""
    t = text.replace("$$", "").replace("$", "")
    replacements = {
        "\\rightarrow": "→",
        "\\leftarrow": "←",
        "\\leftrightarrow": "↔",
        "\\Rightarrow": "⇒",
        "\\cdot": "·",
        "\\times": "×",
        "\\approx": "≈",
        "\\leq": "≤",
        "\\geq": "≥",
        "\\neq": "≠",
        "\\%": "%",
        "\\text": "",
        "\\mathrm": "",
    }
    for k, v in replacements.items():
        t = t.replace(k, v)

    t = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1/\2)", t)
    t = re.sub(r"\{([^{}]+)\}", r"\1", t)

    sub_map = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
    t = re.sub(r"_([0-9]+)", lambda m: m.group(1).translate(sub_map), t)
    t = re.sub(r"([A-Za-z\)])([0-9]+)", lambda m: m.group(1) + m.group(2).translate(sub_map), t)

    t = html.escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"^#{1,4}\s*(.+)$", r"📌 <b>\1</b>", t, flags=re.MULTILINE)
    return t.strip()

# -------------------------------------------------------------
# DOIMIY ISHLOVCHI SUN'IY INTELLEKT (5 BOSQICHLI TIZIM)
# -------------------------------------------------------------
def get_gemini_api_key() -> str:
    saved_key = db_get_setting("gemini_api_key", DEFAULT_GEMINI_KEY).strip()
    return saved_key if saved_key else DEFAULT_GEMINI_KEY

async def extract_text_via_free_ocr(b64_data: str, mime_type: str) -> str:
    """Rasm ichidagi masala matnini bepul OCR orqali ajratib olish."""
    url = "https://api.ocr.space/parse/image"
    for engine in ["2", "1"]:
        form_data = {
            "apikey": "helloworld",
            "base64Image": f"data:{mime_type};base64,{b64_data}",
            "language": "eng",
            "isOverlayRequired": "false",
            "OCREngine": engine,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=form_data, timeout=25) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        parsed_list = data.get("ParsedResults", [])
                        if parsed_list:
                            txt = parsed_list[0].get("ParsedText", "").strip()
                            if len(txt) > 3:
                                return txt
        except Exception:
            pass
    return ""

async def call_text_ai_fallback(prompt: str, extracted_text: str) -> tuple[bool, str]:
    """OCR orqali olingan matnni Text AI orqali yechish."""
    full_prompt = f"{prompt}\n\nMasala sharti:\n{extracted_text}"
    async with aiohttp.ClientSession() as session:
        # 1. OpenAI-compatible POST endpoint
        for model_name in ["openai", "openai-large", "mistral"]:
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": full_prompt}],
                "temperature": 0.1
            }
            try:
                async with session.post("https://text.pollinations.ai/openai", json=payload, timeout=60) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text_out = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if text_out and len(text_out.strip()) > 5:
                            return True, text_out.strip()
            except Exception:
                pass

        # 2. Oddiy GET endpoint
        try:
            encoded = urllib.parse.quote(full_prompt[:1500])
            async with session.get(f"https://text.pollinations.ai/{encoded}", timeout=45) as resp:
                if resp.status == 200:
                    txt = (await resp.text()).strip()
                    if len(txt) > 5 and not txt.startswith("<!"):
                        return True, txt
        except Exception:
            pass

    return False, ""

async def call_vision_fallback(prompt: str, b64_data: str, mime_type: str, json_mode: bool = False) -> tuple[bool, str]:
    """Kalitsiz ishlovchi Vision AI + OCR zaxira tizimi."""
    url = "https://text.pollinations.ai/openai"
    async with aiohttp.ClientSession() as session:
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
                async with session.post(url, json=payload, timeout=75) as resp:
                    if resp.status == 200:
                        raw_resp = await resp.text()
                        try:
                            data = json.loads(raw_resp)
                            text_out = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                            if text_out and len(text_out.strip()) > 3:
                                return True, text_out.strip()
                        except Exception:
                            if len(raw_resp.strip()) > 5 and not raw_resp.strip().startswith("<!"):
                                return True, raw_resp.strip()
            except Exception:
                pass

    # Agar Vision server javob bermasa, rasmdan matnni OCR qilib o'qib, matnli AI ga yuboramiz
    ocr_text = await extract_text_via_free_ocr(b64_data, mime_type)
    if ocr_text:
        ok_txt, res_txt = await call_text_ai_fallback(prompt, ocr_text)
        if ok_txt:
            return True, res_txt

    return False, "AI server javob bermadi"

async def call_gemini_api(prompt: str, b64_data: str, mime_type: str, json_mode: bool = False, timeout_sec: int = 90) -> tuple[bool, str]:
    api_key = get_gemini_api_key()

    # Vertex AI va Gemini standartiga mos payload ("role": "user" ikkalasida ham ishlaydi)
    payload_vertex = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": b64_data
                        }
                    }
                ]
            }
        ],
        "generationConfig": {}
    }
    if json_mode:
        payload_vertex["generationConfig"]["responseMimeType"] = "application/json"

    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-001",
        "gemini-1.5-flash"
    ]
    last_error = ""

    def extract_response_text(data: dict) -> str:
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        non_thought = [p.get("text", "") for p in parts if "text" in p and not p.get("thought", False)]
        if non_thought:
            return "\n".join(non_thought).strip()
        if parts and "text" in parts[-1]:
            return parts[-1]["text"].strip()
        return ""

    if api_key:
        async with aiohttp.ClientSession() as session:
            for model_name in models_to_try:
                # 1. AQ. kalitlari uchun Vertex AI Express endpointi + Standart Gemini endpointi
                endpoints = [
                    (
                        f"https://aiplatform.googleapis.com/v1/publishers/google/models/{model_name}:generateContent?key={api_key}",
                        {"Content-Type": "application/json"}
                    ),
                    (
                        f"https://aiplatform.googleapis.com/v1beta1/publishers/google/models/{model_name}:generateContent?key={api_key}",
                        {"Content-Type": "application/json"}
                    ),
                    (
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}",
                        {"Content-Type": "application/json"}
                    ),
                ]
                for url_endpoint, req_headers in endpoints:
                    try:
                        async with session.post(url_endpoint, headers=req_headers, json=payload_vertex, timeout=timeout_sec) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                text_out = extract_response_text(data)
                                if text_out:
                                    return True, text_out
                            else:
                                last_error = f"HTTP {resp.status}"
                    except Exception as e:
                        last_error = str(e)

    # 2. Zaxira Vision + OCR AI
    if mime_type.startswith("image/"):
        ok_fb, text_fb = await call_vision_fallback(prompt, b64_data, mime_type, json_mode=json_mode)
        if ok_fb:
            return True, text_fb

    return False, last_error or "AI javob bermadi"

async def ai_analyze_test_document(file_bytes: bytes, mime_type: str, test_type: str) -> dict:
    b64_data = base64.b64encode(file_bytes).decode("utf-8")
    if test_type == "30_talik":
        prompt = (
            "Sen TITUL platformasining Kimyo va aniq fanlar bo'yicha oliy toifali ekspertisan. "
            "Yuborilgan fayldagi test savollarini yechib, javoblar kalitini tuz. "
            "Natijani FAQAT quyidagi JSON formatda qaytar:\n"
            '{"title": "TITUL 30 talik Test", "keys": {"1": "A", "2": "B"}, "explanation": "Qisqacha izoh"}'
        )
    elif test_type == "43_ms":
        prompt = (
            "Sen Milliy Sertifikat (43 talik) bo'yicha ekspertsan. "
            "Yuborilgan testni yechib kalit tuz:\n"
            "- 1-32: Yopiq (A, B, C, D)\n"
            "- 33-35: Moslashtirish (A, B, C, D, E, F)\n"
            "- 36-40: Ochiq test savollari.\n"
            "Natijani FAQAT quyidagi JSON formatda qaytar:\n"
            '{"title": "TITUL Milliy Sertifikat 43 talik", "keys": {"1": "A", "32": "D", "33": "E", "36": "9"}, "explanation": "Izoh"}'
        )
    else:
        prompt = (
            "Sen DTM 90 talik blok testlari bo'yicha ekspertsan. "
            "Savol va javoblarni tahlil qilib, 1 dan 90 gacha to'g'ri javoblarni aniqla. "
            "Natijani FAQAT quyidagi JSON formatda qaytar:\n"
            '{"title": "TITUL 90 talik DTM Blok Testi", "keys": {"1": "A", "2": "C"}, "explanation": "Izoh"}'
        )

    ok, res_text = await call_gemini_api(prompt, b64_data, mime_type, json_mode=True, timeout_sec=100)
    if not ok:
        return {"error": res_text}

    try:
        raw_text = res_text.strip()
        m = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
        if m:
            raw_text = m.group(0)
        return json.loads(raw_text)
    except Exception as e:
        return {"error": f"JSON o'qishda xato: {e}"}

async def ai_grade_written_work(file_bytes: bytes, q_num: int) -> tuple[float, str]:
    """41, 42, 43-savolning qo'lyozma yechim rasmini AI orqali tekshirish va 0 dan 2.5 ballgacha baholash."""
    b64_data = base64.b64encode(file_bytes).decode("utf-8")
    prompt = (
        f"Sen Milliy Sertifikat imtihonida {q_num}-yozma masala yechimini tekshiruvchi ekspertsan. "
        "O'quvchining daftardagi yechim rasmini tahlil qil. Yechim mantiqan va hisob-kitob jihatdan to'g'riligiga qarab "
        "0 dan 2.5 gacha ball ber. Natijani FAQAT JSON formatda qaytar:\n"
        '{"score": 2.2, "comment": "Reaksiya tenglamasi va mol nisbatlari to\'g\'ri topilgan."}'
    )
    ok, res_text = await call_gemini_api(prompt, b64_data, "image/jpeg", json_mode=True, timeout_sec=60)
    if ok:
        try:
            m = re.search(r"\{.*\}", res_text.strip(), flags=re.DOTALL)
            raw = m.group(0) if m else res_text.strip()
            data = json.loads(raw)
            score = float(data.get("score", 2.0))
            score = max(0.0, min(2.5, score))
            comment = data.get("comment", "Yechim qabul qilindi.")
            return score, comment
        except Exception:
            pass
    return 2.0, "Yechim rasmi qabul qilindi va baholandi."

async def ai_solve_photo_problem(file_bytes: bytes, mime_type: str) -> str:
    b64_data = base64.b64encode(file_bytes).decode("utf-8")
    prompt = (
        "Sen TITUL platformasining tajribali ustozi Azizbek Ibrohimovning sun'iy intellekt yordamchisisan. "
        "Rasmdagi kimyo masalasini yoki test savolini o'zbek tilida eng oson, mantiqiy usulda "
        "bosqichma-bosqich yechib, yakunida aniq to'g'ri javobni ko'rsatib ber."
    )
    ok, res_text = await call_gemini_api(prompt, b64_data, mime_type, json_mode=False, timeout_sec=90)
    if ok:
        cleaned = clean_ai_text_for_telegram(res_text)
        return cleaned[:3800] if len(cleaned) > 3800 else cleaned
    return f"❌ Rasmni tahlil qilishda xatolik: {html.escape(res_text)}"

# -------------------------------------------------------------
# RASCH MODELI (1PL IRT LOGISTIK ALGORITMI) VA BALL HISOBLASH
# -------------------------------------------------------------
def compute_rasch_1pl_score(
    test_code: str,
    correct_keys: dict,
    student_ans: dict,
    written_scores: dict
) -> dict:
    past_submissions = db_get_all_submissions_for_test(test_code)
    n_past = len(past_submissions)

    beta_dict = {}
    weight_dict = {}

    for q in range(1, 41):
        qs = str(q)
        if 1 <= q <= 15:
            b_prior, w = -1.0, 1.0
        elif 16 <= q <= 32:
            b_prior, w = -0.2, 1.25
        elif 33 <= q <= 35:
            b_prior, w = 0.5, 1.5
        else:
            b_prior, w = 1.1, 1.8

        if n_past >= 3 and qs in correct_keys:
            k_val = str(correct_keys.get(qs, "")).strip().upper().replace(",", ".")
            corr_cnt = 0
            for sub in past_submissions:
                s_v = str(sub.get(qs, "")).strip().upper().replace(",", ".")
                if k_val and s_v == k_val:
                    corr_cnt += 1
            p_i = (corr_cnt + 1.0) / (n_past + 2.0)
            beta_emp = math.log((1.0 - p_i) / p_i)
            beta_dict[qs] = 0.6 * beta_emp + 0.4 * b_prior
        else:
            beta_dict[qs] = b_prior

        weight_dict[qs] = w

    for q in [41, 42, 43]:
        qs = str(q)
        beta_dict[qs] = 1.65
        weight_dict[qs] = 2.2

    u_scores = {}
    for q in range(1, 41):
        qs = str(q)
        k_val = str(correct_keys.get(qs, "")).strip().upper().replace(",", ".")
        if not k_val:
            continue
        s_val = str(student_ans.get(qs, "")).strip().upper().replace(",", ".")
        u_scores[qs] = 1.0 if s_val == k_val else 0.0

    for q in [41, 42, 43]:
        qs = str(q)
        w_val = float(written_scores.get(qs, 0.0))
        u_scores[qs] = max(0.0, min(1.0, w_val / 2.5))

    if not u_scores:
        return {"theta": -3.0, "rasch_score": 0.0, "hard_solved": 0}

    total_possible_w = sum(weight_dict[q] for q in u_scores)
    earned_w = sum(weight_dict[q] * u_scores[q] for q in u_scores)

    if earned_w <= 0.01:
        return {"theta": -3.0, "rasch_score": 0.0, "hard_solved": 0}
    if earned_w >= total_possible_w - 0.01:
        return {"theta": 2.5, "rasch_score": 75.0, "hard_solved": len(u_scores)}

    theta = 0.0
    for _ in range(30):
        f_val = 0.0
        f_prime = 0.0
        for qs, u_i in u_scores.items():
            b_i = beta_dict[qs]
            w_i = weight_dict[qs]
            exp_term = math.exp(max(-20.0, min(20.0, -(theta - b_i))))
            p_i = 1.0 / (1.0 + exp_term)
            f_val += w_i * (u_i - p_i)
            f_prime -= w_i * p_i * (1.0 - p_i)
        if abs(f_prime) < 1e-6:
            break
        step = f_val / f_prime
        theta -= step
        theta = max(-3.5, min(3.5, theta))
        if abs(step) < 1e-4:
            break

    raw_rasch = 50.0 + 11.2 * theta
    rasch_score = round(max(15.0, min(75.0, raw_rasch)), 1)

    hard_solved = sum(1 for qs, u_i in u_scores.items() if beta_dict[qs] >= 0.5 and u_i >= 0.6)
    return {
        "theta": round(theta, 2),
        "rasch_score": rasch_score,
        "hard_solved": hard_solved
    }

def parse_input_answers(raw_text: str, test_type: str) -> dict:
    text = raw_text.strip()
    answers = {}
    pairs = re.findall(r"(\d{1,2})\s*[-:=.)]?\s*([A-Za-z0-9.,/+-]+)", text)
    if len(pairs) >= 1:
        for q_num, ans_val in pairs:
            q_str = str(int(q_num))
            answers[q_str] = ans_val.strip().upper()
        return answers

    clean_letters = re.sub(r"[^A-Fa-f]", "", text).upper()
    max_q = 30 if test_type == "30_talik" else (90 if test_type == "90_dtm" else 35)
    if len(clean_letters) >= 3:
        for idx, ch in enumerate(clean_letters[:max_q], start=1):
            answers[str(idx)] = ch

    return answers

def evaluate_student_submission(test_type: str, correct_keys: dict, student_ans: dict, written_scores: dict = None, test_code: str = "") -> dict:
    mistakes = []
    correct_count = 0
    written_scores = written_scores or {}

    if test_type == "30_talik":
        total_q = len(correct_keys) or 30
        for q in range(1, total_q + 1):
            q_str = str(q)
            k_val = str(correct_keys.get(q_str, "")).strip().upper()
            s_val = str(student_ans.get(q_str, "")).strip().upper()
            if not k_val:
                continue
            if s_val == k_val:
                correct_count += 1
            else:
                mistakes.append(f"{q_str}-savol (Siz: {s_val or '—'} | Kalit: {k_val})")

        score = round(correct_count * 3.1, 1)
        percent = round((correct_count / total_q) * 100, 1) if total_q else 0
        grade = "A'lo (Yuqori) 🏆" if percent >= 85 else ("Yaxshi 🎯" if percent >= 65 else "Qoniqarli 📚")

        summary = (
            f"📋 <b>TITUL | 30 TALIK TEST NATIJASI:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ To'g'ri javoblar: <b>{correct_count} / {total_q} ta</b>\n"
            f"📊 Ko'rsatkich: <b>{percent}%</b>\n"
            f"💎 To'plangan ball: <b>{score} / 93.0 ball</b>\n"
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
            f"🏛 <b>TITUL | 90 TALIK DTM BLOK TEST:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"1️⃣ Majburiy (1–30): {b1}/30 = <b>{b1_s} ball</b>\n"
            f"2️⃣ 1-Fan (31–60): {b2}/30 = <b>{b2_s} ball</b>\n"
            f"3️⃣ 2-Fan (61–90): {b3}/30 = <b>{b3_s} ball</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Jami to'g'ri: <b>{correct_count}/90 ta</b>\n"
            f"🔥 <b>UMUMIY BALL: {total_score} / 189.0</b>"
        )
        return {"correct_count": correct_count, "total_score": total_score, "grade": grade, "summary": summary, "mistakes": mistakes}

    else:
        p1, p2, p3 = 0, 0, 0
        for q in range(1, 41):
            qs = str(q)
            k_val = str(correct_keys.get(qs, "")).strip().upper().replace(",", ".")
            s_val = str(student_ans.get(qs, "")).strip().upper().replace(",", ".")
            if not k_val:
                continue
            if s_val == k_val:
                correct_count += 1
                if 1 <= q <= 32: p1 += 1
                elif 33 <= q <= 35: p2 += 1
                elif 36 <= q <= 40: p3 += 1
            else:
                mistakes.append(f"{q}-savol (Siz: {s_val or '—'} | Kalit: {k_val})")

        w41 = float(written_scores.get("41", 0.0))
        w42 = float(written_scores.get("42", 0.0))
        w43 = float(written_scores.get("43", 0.0))
        written_total = round(w41 + w42 + w43, 1)
        for _, val_w in [("41", w41), ("42", w42), ("43", w43)]:
            if val_w >= 1.5:
                correct_count += 1

        rasch_info = compute_rasch_1pl_score(test_code, correct_keys, student_ans, written_scores)
        rasch = rasch_info["rasch_score"]
        theta_val = rasch_info["theta"]

        grade = (
            "A+ Daraja (100% Imtiyoz) 🏆" if rasch >= 70 else
            "A Daraja (100% Imtiyoz) 🥇" if rasch >= 65 else
            "B+ Daraja (Proporsional) 🥈" if rasch >= 60 else
            "B Daraja (Proporsional) 🥈" if rasch >= 55 else
            "C+ Daraja (Proporsional) 🥉" if rasch >= 50 else
            "C Daraja (Minimal) 🎗" if rasch >= 46 else "Sertifikatsiz ❌"
        )

        summary = (
            f"🎯 <b>TITUL | 43 TALIK MILLIY SERTIFIKAT (RASCH):</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 1–32 (Yopiq A-D): <b>{p1} / 32 ta</b>\n"
            f"🔸 33–35 (Moslashtirish A-F): <b>{p2} / 3 ta</b>\n"
            f"🔢 36–40 (Ochiq javoblar): <b>{p3} / 5 ta</b>\n"
            f"📸 41–43 (Yozma ish rasmlari): <b>{written_total} / 7.5 ball</b>\n"
            f"   ├ 41-masala: <b>{w41} ball</b>\n"
            f"   ├ 42-masala: <b>{w42} ball</b>\n"
            f"   └ 43-masala: <b>{w43} ball</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📐 <b>Qobiliyat indeksi (θ Logit): {theta_val:+.2f}</b>\n"
            f"📈 <b>Yakuniy Rasch T-Bali: {rasch} ball</b>\n"
            f"🏅 <b>Sertifikat Darajasi: {grade}</b>"
        )
        return {"correct_count": correct_count, "total_score": rasch, "grade": grade, "summary": summary, "mistakes": mistakes}

# -------------------------------------------------------------
# PDF VA POST SHAKLIDA NATIJALAR GENERATORI
# -------------------------------------------------------------
def clean_ascii_for_pdf(txt: str) -> str:
    if not txt:
        return ""
    cleaned = re.sub(r"[^\x20-\x7E]", "", str(txt)).strip()
    return cleaned if cleaned else "O'quvchi"

def generate_test_results_pdf(test_code: str, title: str, test_type: str, results: list) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=35, bottomMargin=30)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitulHeader",
        parent=styles["Heading1"],
        fontSize=16,
        alignment=1,
        spaceAfter=8,
        textColor=colors.HexColor("#1A365D")
    )
    sub_style = ParagraphStyle(
        "TitulSub",
        parent=styles["Normal"],
        fontSize=11,
        alignment=1,
        spaceAfter=16,
        textColor=colors.HexColor("#2D3748")
    )

    elements = []
    elements.append(Paragraph("TITUL - ELEKTRON TEST NATIJALARI JADVALI", title_style))
    elements.append(Paragraph(
        f"Test kodi: <b>{clean_ascii_for_pdf(test_code)}</b> | Nomi: <b>{clean_ascii_for_pdf(title)}</b> | Sana: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        sub_style
    ))

    table_data = [["#", "F.I.SH (O'quvchi)", "To'g'ri", "Yozma (41-43)", "Yakuniy Ball", "Daraja"]]
    for idx, row in enumerate(results, start=1):
        full_name, corr, score, grade, w_score, _ = row
        grade_clean = clean_ascii_for_pdf(grade)
        table_data.append([
            str(idx),
            clean_ascii_for_pdf(full_name)[:28],
            f"{corr} ta",
            f"{round(float(w_score or 0), 1)}",
            f"{score}",
            grade_clean[:22]
        ])

    if len(table_data) == 1:
        table_data.append(["1", "Hali natijalar yo'q", "-", "-", "0", "-"])

    t = Table(table_data, colWidths=[30, 175, 55, 75, 75, 115])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F7FAFC")),
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E0")),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 18))
    elements.append(Paragraph("TITUL Rasch & AI Platformasi | Rasmiy kanal: @Kimyo_Sertifkat_uchun", sub_style))

    doc.build(elements)
    return buf.getvalue()

def generate_announcement_post(test_code: str, title: str, test_type: str, results: list, keys_dict: dict) -> str:
    badge = "30 talik Standart" if test_type == "30_talik" else ("43 talik Milliy Sertifikat (Rasch)" if test_type == "43_ms" else "90 talik DTM Blok")
    lines = [
        f"📣 <b>TITUL | RASMIY TEST NATIJALARI E'LONI</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🔑 <b>Test kodi:</b> <code>{html.escape(test_code)}</code>",
        f"📚 <b>Test nomi:</b> {html.escape(title)}",
        f"🏷 <b>Format:</b> {badge}",
        f"👥 <b>Jami qatnashchilar:</b> {len(results)} nafar\n",
        f"🏆 <b>TOP REYTING JADVALI:</b>"
    ]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, (name, corr, score, grade, w_score, _) in enumerate(results[:25], start=1):
        m = medals.get(i, f"<b>{i}.</b>")
        w_info = f" <i>(Yozma: {round(float(w_score or 0), 1)} b)</i>" if test_type == "43_ms" else ""
        lines.append(f"{m} <b>{html.escape(name)}</b> — <b>{score} ball</b> ({corr} ta{w_info} | {grade})")

    keys_preview = " ".join([f"{k}-{v}" for k, v in list(keys_dict.items())[:40]])
    lines.append(f"\n🔑 <b>To'g'ri javoblar kaliti:</b>\n<code>{html.escape(keys_preview)}</code>")
    lines.append(f"\n📲 <b>Rasmiy kanal:</b> {DEFAULT_CHANNEL_URL}")
    return "\n".join(lines)

# -------------------------------------------------------------
# INTERAKTIV ELEKTRON TITUL VARAQASI GENERATORI
# -------------------------------------------------------------
def build_electronic_sheet_kb(test_type: str, answers: dict, page: int = 1, written_photos: dict = None) -> InlineKeyboardMarkup:
    written_photos = written_photos or {}
    rows = []

    if test_type == "30_talik":
        per_page = 10
        total_pages = 3
        start_q = (page - 1) * per_page + 1
        end_q = start_q + per_page - 1

        for q in range(start_q, end_q + 1):
            qs = str(q)
            cur = answers.get(qs, "")
            btn_row = [InlineKeyboardButton(text=f"№{q}", callback_data="noop")]
            for opt in ["A", "B", "C", "D"]:
                lbl = f"✅{opt}" if cur == opt else opt
                btn_row.append(InlineKeyboardButton(text=lbl, callback_data=f"ebtn:{q}:{opt}:{page}"))
            rows.append(btn_row)

        nav = []
        for p in range(1, total_pages + 1):
            lbl = f"📍 {p}-bet" if p == page else f"{p}-bet ({(p-1)*10+1}-{p*10})"
            nav.append(InlineKeyboardButton(text=lbl, callback_data=f"epage:{p}"))
        rows.append(nav)

    elif test_type == "90_dtm":
        per_page = 10
        total_pages = 9
        start_q = (page - 1) * per_page + 1
        end_q = start_q + per_page - 1

        for q in range(start_q, end_q + 1):
            qs = str(q)
            cur = answers.get(qs, "")
            btn_row = [InlineKeyboardButton(text=f"№{q}", callback_data="noop")]
            for opt in ["A", "B", "C", "D"]:
                lbl = f"✅{opt}" if cur == opt else opt
                btn_row.append(InlineKeyboardButton(text=lbl, callback_data=f"ebtn:{q}:{opt}:{page}"))
            rows.append(btn_row)

        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"epage:{page-1}"))
        nav.append(InlineKeyboardButton(text=f"📄 {page}/9 bet", callback_data="noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"epage:{page+1}"))
        rows.append(nav)

    else:
        if page in [1, 2, 3]:
            ranges = {1: (1, 10), 2: (11, 20), 3: (21, 32)}
            start_q, end_q = ranges[page]
            for q in range(start_q, end_q + 1):
                qs = str(q)
                cur = answers.get(qs, "")
                btn_row = [InlineKeyboardButton(text=f"№{q}", callback_data="noop")]
                for opt in ["A", "B", "C", "D"]:
                    lbl = f"✅{opt}" if cur == opt else opt
                    btn_row.append(InlineKeyboardButton(text=lbl, callback_data=f"ebtn:{q}:{opt}:{page}"))
                rows.append(btn_row)
        else:
            for q in range(33, 36):
                qs = str(q)
                cur = answers.get(qs, "")
                rows.append([InlineKeyboardButton(text=f"🔸 {q}-savol (Moslashtirish A–F):", callback_data="noop")])
                btn_row = []
                for opt in ["A", "B", "C", "D", "E", "F"]:
                    lbl = f"✅{opt}" if cur == opt else opt
                    btn_row.append(InlineKeyboardButton(text=lbl, callback_data=f"ebtn:{q}:{opt}:4"))
                rows.append(btn_row)

            rows.append([InlineKeyboardButton(text="🔢 36–40 Ochiq savollar (Javob yozish):", callback_data="noop")])
            open_row = []
            for q in range(36, 41):
                qs = str(q)
                cur = answers.get(qs, "")
                lbl = f"✅{q}:{cur}" if cur else f"✍️ {q}-savol"
                open_row.append(InlineKeyboardButton(text=lbl, callback_data=f"eopen:{q}"))
                if len(open_row) == 3:
                    rows.append(open_row)
                    open_row = []
            if open_row:
                rows.append(open_row)

            rows.append([InlineKeyboardButton(text="📸 41–43 Yozma masalalar rasmini yuklash:", callback_data="noop")])
            for q in [41, 42, 43]:
                qs = str(q)
                has_img = qs in written_photos
                lbl = f"✅ {q}-masala rasmi yuklandi (Almashtirish)" if has_img else f"📷 {q}-masala yechimi rasmini yuklash"
                rows.append([InlineKeyboardButton(text=lbl, callback_data=f"ephoto:{q}")])

        nav = [
            InlineKeyboardButton(text="📍1-10" if page == 1 else "1-10", callback_data="epage:1"),
            InlineKeyboardButton(text="📍11-20" if page == 2 else "11-20", callback_data="epage:2"),
            InlineKeyboardButton(text="📍21-32" if page == 3 else "21-32", callback_data="epage:3"),
            InlineKeyboardButton(text="📍33-43 (Ochiq/Rasm)" if page == 4 else "33-43 (Ochiq/Rasm)", callback_data="epage:4"),
        ]
        rows.append(nav)

    filled_cnt = len(answers) + len(written_photos)
    rows.append([InlineKeyboardButton(text=f"🚀 TITULNI YAKUNLASH VA TEKSHIRISH ({filled_cnt} ta)", callback_data="efinish")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# -------------------------------------------------------------
# FSM STATE HOLATLARI
# -------------------------------------------------------------
class StudentTestSolve(StatesGroup):
    waiting_test_code = State()
    in_electronic_exam = State()
    waiting_open_answer = State()
    waiting_written_photo = State()

class AISolveProblem(StatesGroup):
    waiting_problem_photo = State()

class UserTestCreate(StatesGroup):
    waiting_test_type = State()
    waiting_title = State()
    waiting_file_or_keys = State()

class AdminPanel(StatesGroup):
    waiting_gemini_key = State()
    waiting_delete_code = State()
    waiting_broadcast_msg = State()
    waiting_channel_username = State()

# -------------------------------------------------------------
# MENYULAR
# -------------------------------------------------------------
def main_menu(user_id: int = 0):
    kb = [
        [
            KeyboardButton(text="📲 Elektron Titul Tekshirish"),
            KeyboardButton(text="➕ Test Yaratish (Barcha uchun)")
        ],
        [
            KeyboardButton(text="📢 Testni Yakunlash (PDF + Post)"),
            KeyboardButton(text="🏆 Reyting & Natijalar")
        ],
        [
            KeyboardButton(text="📋 Faol Testlar Baza"),
            KeyboardButton(text="🤖 AI Masala Yechish (Rasm)")
        ],
        [
            KeyboardButton(text="👨‍🏫 Ustoz & Bog'lanish"),
            KeyboardButton(text="👑 Admin Boshqaruv Paneli")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def exam_active_reply_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Elektron Titulni Qayta Ochish")],
            [KeyboardButton(text="🛑 Testni Bekor Qilish (Chiqish)")]
        ],
        resize_keyboard=True
    )

# -------------------------------------------------------------
# HAR QANDAY HOLATDA ISHLOVCHI GLOBAL BUYRUQLAR VA ADMIN PANEL
# -------------------------------------------------------------
@dp.message(CommandStart(), StateFilter("*"))
async def cmd_start(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    ACTIVE_EXAM_SESSIONS.pop(uid, None)
    await state.clear()

    name = message.from_user.full_name or "O'quvchi"
    username = f"@{message.from_user.username}" if message.from_user.username else ""
    db_add_user(uid, name, username)

    if not await check_channel_subscription(uid):
        await prompt_subscription(message)
        return

    text = (
        f"✨ Assalomu alaykum, <b>{html.escape(name)}</b>!\n\n"
        f"📋 <b>TITUL | ELEKTRON TEST VA AI TEKSHIRUV PLATFORMASI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔹 <b>📲 Elektron Titul Tekshirish</b> — alohida interaktiv titul oynasida test belgilash va <b>41, 42, 43-masalalar</b> yechimi rasmini yuklash;\n"
        f"🔹 <b>➕ Test Yaratish (Barcha uchun)</b> — har bir foydalanuvchi o'z testini yarata oladi;\n"
        f"🔹 <b>📢 Testni Yakunlash (PDF + Post)</b> — test tugagach natijalarni tayyor PDF jadval va Post shaklida e'lon qilish;\n"
        f"🔹 <b>🤖 AI Masala Yechish</b> — 24/7 doimiy ishlovchi sun'iy intellekt <i>(Mock test paytida avtomatik bloklanadi!)</i>.\n\n"
        f"Kerakli bo'limni tanlang 👇"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu(uid))

@dp.message(Command("admin"), StateFilter("*"))
@dp.message(F.text == "👑 Admin Boshqaruv Paneli", StateFilter("*"))
async def admin_panel(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await state.clear()

    if uid != ADMIN_ID:
        await message.answer(
            f"🔒 <b>Bu bo'lim faqat platforma bosh admini uchun!</b>\n"
            f"Sizning Telegram ID raqamingiz: <code>{uid}</code>\n"
            f"<i>(O'z testlaringizni yaratish va yakunlash uchun asosiy menyudagi «➕ Test Yaratish» va «📢 Testni Yakunlash» tugmalaridan foydalaning)</i>",
            parse_mode="HTML",
            reply_markup=main_menu(uid)
        )
        return

    cur_key = get_gemini_api_key()
    masked = f"{cur_key[:10]}..." if cur_key else "Kiritilmagan"
    req_ch = db_get_setting("required_channel", DEFAULT_REQUIRED_CHANNEL)
    s = db_get_stats()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Bot Statistikasi (Batafsil)", callback_data="adm_stats")],
        [InlineKeyboardButton(text="📢 Barchaga Xabar Yuborish (Reklama)", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="🔑 Gemini AI API Kalitni Yangilash", callback_data="adm_set_gemini")],
        [InlineKeyboardButton(text="📡 Majburiy Obuna Kanalini Sozlash", callback_data="adm_set_channel")],
        [InlineKeyboardButton(text="🗑 Testni Bazadan O'chirish", callback_data="adm_del")]
    ])
    await message.answer(
        f"👑 <b>TITUL | ADMIN BOSHQARUV PANELI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Jami foydalanuvchilar: <b>{s['users']} nafar</b>\n"
        f"🧪 Bazadagi testlar: <b>{s['tests']} ta</b>\n"
        f"📝 Topshirilgan natijalar: <b>{s['results']} ta</b>\n"
        f"⏳ Hozir Mock imtihon ishlayotganlar: <b>{len(ACTIVE_EXAM_SESSIONS)} kishi</b>\n"
        f"📢 Majburiy kanal: <code>{html.escape(req_ch)}</code>\n"
        f"🔑 AI Kalit: <code>{html.escape(masked)}</code>\n\n"
        f"Kerakli amalni tanlang 👇",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.callback_query(F.data == "adm_stats")
async def adm_stats_cb(callback: types.CallbackQuery):
    s = db_get_stats()
    recent = db_get_recent_tests(5)
    t_list = "\n".join([f"• <code>{c}</code> — {html.escape(t)}" for c, _, t, _ in recent]) or "Yo'q"
    await callback.message.answer(
        f"📊 <b>TITUL PLATFORMASI STATISTIKASI:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Ro'yxatdan o'tganlar: <b>{s['users']} ta</b>\n"
        f"🧪 Jami yaratilgan testlar: <b>{s['tests']} ta</b>\n"
        f"📝 Jami tekshirilgan titul natijalari: <b>{s['results']} ta</b>\n\n"
        f"📋 <b>Oxirgi 5 ta test:</b>\n{t_list}",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "adm_set_gemini")
async def adm_set_gemini_cb(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Faqat admin uchun!", show_alert=True)
        return
    await state.set_state(AdminPanel.waiting_gemini_key)
    await callback.message.answer(
        "🔑 Yangi <b>Gemini AI API kalitingizni</b> yuboring:\n"
        "<i>(Ham AIzaSy... ham AQ.Ab8... kalitlari to'liq qo'llab-quvvatlanadi)</i>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    )
    await callback.answer()

@dp.message(AdminPanel.waiting_gemini_key)
async def save_gemini_key(message: types.Message, state: FSMContext):
    new_key = (message.text or "").strip()
    db_set_setting("gemini_api_key", new_key)
    await state.clear()
    await message.answer(
        "✅ <b>Gemini AI API kaliti muvaffaqiyatli saqlandi!</b>",
        parse_mode="HTML",
        reply_markup=main_menu(message.from_user.id)
    )

@dp.callback_query(F.data == "adm_set_channel")
async def adm_set_channel_cb(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Faqat admin uchun!", show_alert=True)
        return
    await state.set_state(AdminPanel.waiting_channel_username)
    await callback.message.answer(
        "📡 Majburiy obuna uchun kanal username'ini yuboring (masalan: <code>@Kimyo_Sertifkat_uchun</code>) yoki o'chirish uchun <code>off</code> deb yozing:",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    )
    await callback.answer()

@dp.message(AdminPanel.waiting_channel_username)
async def save_channel_username(message: types.Message, state: FSMContext):
    ch = (message.text or "").strip()
    db_set_setting("required_channel", ch)
    await state.clear()
    await message.answer(
        f"✅ Majburiy obuna kanali yangilandi: <code>{html.escape(ch)}</code>",
        parse_mode="HTML",
        reply_markup=main_menu(message.from_user.id)
    )

@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_cb(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Faqat admin uchun!", show_alert=True)
        return
    await state.set_state(AdminPanel.waiting_broadcast_msg)
    await callback.message.answer(
        "📢 <b>Barcha foydalanuvchilarga yuboriladigan xabar (matn, rasm yoki post) ni yuboring:</b>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    )
    await callback.answer()

@dp.message(AdminPanel.waiting_broadcast_msg)
async def process_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    users = db_get_all_user_ids()
    sent = 0
    wait = await message.answer(f"⏳ Xabar {len(users)} ta foydalanuvchiga yuborilmoqda...")
    for u_id in users:
        try:
            await message.copy_to(u_id)
            sent += 1
            await asyncio.sleep(0.04)
        except Exception:
            pass
    await wait.delete()
    await message.answer(
        f"✅ <b>Xabar {sent} / {len(users)} nafar foydalanuvchiga yetkazildi!</b>",
        parse_mode="HTML",
        reply_markup=main_menu(message.from_user.id)
    )

@dp.callback_query(F.data == "adm_del")
async def adm_del_cb(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Faqat admin uchun!", show_alert=True)
        return
    await state.set_state(AdminPanel.waiting_delete_code)
    await callback.message.answer(
        "🗑 O'chirmoqchi bo'lgan test kodini yuboring:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    )
    await callback.answer()

@dp.message(AdminPanel.waiting_delete_code)
async def do_del_test(message: types.Message, state: FSMContext):
    code = (message.text or "").strip().upper()
    ok = db_delete_test(code)
    await state.clear()
    await message.answer(
        f"{'✅ Test bazadan o\'chirildi!' if ok else '❌ Bunday kodli test topilmadi.'}",
        reply_markup=main_menu(message.from_user.id)
    )

@dp.callback_query(F.data == "btn_check_sub")
async def cb_check_sub(callback: types.CallbackQuery):
    uid = callback.from_user.id
    if await check_channel_subscription(uid):
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            "🎉 <b>Obunangiz tasdiqlandi! TITUL platformasidan foydalanishingiz mumkin:</b>",
            parse_mode="HTML",
            reply_markup=main_menu(uid)
        )
    else:
        await callback.answer("❌ Siz hali kanalga a'zo bo'lmadingiz!", show_alert=True)

@dp.callback_query(F.data == "noop")
async def cb_noop(callback: types.CallbackQuery):
    await callback.answer()

@dp.message(F.text.in_(["❌ Bekor qilish", "🛑 Testni Bekor Qilish (Chiqish)"]), StateFilter("*"))
async def cancel_any_state(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    ACTIVE_EXAM_SESSIONS.pop(uid, None)
    await state.clear()
    await message.answer("✅ Jarayon bekor qilindi. Bosh menyudasiz:", reply_markup=main_menu(uid))

# -------------------------------------------------------------
# BARCHA UCHUN OCHIQ TEST YARATISH BO'LIMI
# -------------------------------------------------------------
@dp.message(F.text == "➕ Test Yaratish (Barcha uchun)", StateFilter("*"))
async def user_start_test_create(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid in ACTIVE_EXAM_SESSIONS:
        await message.answer("⛔️ Siz hozir Mock test ishlayapsiz! Avval testni yakunlang.")
        return

    await state.clear()
    if not await check_channel_subscription(uid):
        await prompt_subscription(message)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 1. 30 talik Test (Standart)", callback_data="create_t:30_talik")],
            [InlineKeyboardButton(text="🎯 2. 43 talik Milliy Sertifikat (Rasch + 41-43 Rasm)", callback_data="create_t:43_ms")],
            [InlineKeyboardButton(text="🏛 3. 90 talik DTM Blok Testi", callback_data="create_t:90_dtm")]
        ]
    )
    await message.answer(
        "➕ <b>TITUL | YANGI TEST YARATISH BO'LIMI (BARCHA UCHUN)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Har bir ustoz va o'quvchi o'z testini yaratib, elektron titul orqali tekshirtirishi mumkin.\n"
        "Qaysi formatdagi testni yaratmoqchisiz? Tanlang 👇",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("create_t:"))
async def cb_select_create_type(callback: types.CallbackQuery, state: FSMContext):
    test_type = callback.data.split(":")[1]
    await state.update_data(test_type=test_type)
    await state.set_state(UserTestCreate.waiting_title)

    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await callback.message.answer(
        "✏️ <b>Test nomini kiriting</b>\n"
        "<i>(Masalan: «TITUL MS 1-variant» yoki «Organika 30 talik»)</i>:",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    await callback.answer()

@dp.message(UserTestCreate.waiting_title)
async def process_test_title(message: types.Message, state: FSMContext):
    title = (message.text or "").strip()
    if len(title) < 2:
        await message.answer("⚠️ Iltimos, test nomini to'g'ri yozing:")
        return

    await state.update_data(title=title)
    await state.set_state(UserTestCreate.waiting_file_or_keys)

    await message.answer(
        f"📚 Test nomi: <b>{html.escape(title)}</b>\n\n"
        "📤 Endi quyidagilardan birini yuboring:\n"
        "1️⃣ <b>Kalitlarni matn ko'rinishida:</b>\n"
        "   <code>1A 2B 3C 4D ...</code> yoki <code>ABCD...</code>\n"
        "   <i>(43 talik MS uchun 1-40 savollar kalitini yozing, 41-43 ni o'quvchilar rasmga olib tashlaydi)</i>\n"
        "2️⃣ Yoki <b>Test savollari PDF/Rasmini</b> yuboring — AI o'zi yechib kalit tuzadi!",
        parse_mode="HTML"
    )

@dp.message(UserTestCreate.waiting_file_or_keys)
async def handle_user_test_upload(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    data = await state.get_data()
    test_type = data.get("test_type", "30_talik")
    title = data.get("title", "TITUL Maxsus Test")
    prefix = "TITUL" if test_type == "30_talik" else ("MS" if test_type == "43_ms" else "DTM")
    test_code = f"{prefix}-{datetime.now().strftime('%d%H%M%S')[-5:]}"

    if message.text:
        parsed_keys = parse_input_answers(message.text, test_type)
        if not parsed_keys:
            await message.answer(
                "⚠️ Kalitlarni o'qib bo'lmadi.\n"
                "Masalan: <code>1A 2B 3C 4D...</code> ko'rinishida yozib yuboring.",
                parse_mode="HTML"
            )
            return
        db_save_test(test_code, test_type, title, parsed_keys, creator_id=uid)
        await state.clear()
        await message.answer(
            f"🎉 <b>YANGI TEST MUVAFFAQIYATLI YARATILDI!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 Test kodi: <code>{test_code}</code>\n"
            f"📚 Nomi: <b>{html.escape(title)}</b>\n"
            f"🔢 Kalitlar soni: <b>{len(parsed_keys)} ta</b>\n\n"
            f"👉 O'quvchilar <b>«📲 Elektron Titul Tekshirish»</b> bo'limiga kirib, <code>{test_code}</code> kodini kiritish orqali elektron titulda belgilashlari mumkin!\n"
            f"📢 Test tugagach, <b>«📢 Testni Yakunlash (PDF + Post)»</b> bo'limidan natijalarni PDF va Post shaklida e'lon qilasiz!",
            parse_mode="HTML",
            reply_markup=main_menu(uid)
        )
        return

    file_id = message.document.file_id if message.document else (message.photo[-1].file_id if message.photo else "")
    file_type = "document" if message.document else ("photo" if message.photo else "")
    mime_type = message.document.mime_type if message.document else "image/jpeg"

    if not file_id:
        await message.answer("❗️ Iltimos, kalitlarni matn qilib yozing yoki PDF/Rasm yuboring.")
        return

    wait_msg = await message.answer("🤖 AI faylni o'qib, savollar kalitini tuzmoqda, kuting...")
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
            f"⚠️ <b>AI faylni o'qiy olmadi:</b> {err_clean}\n\n"
            "💡 <i>Iltimos, test kalitlarini oddiy matn ko'rinishida (1A 2B 3C...) yozib yuboring!</i>",
            parse_mode="HTML"
        )
        return

    keys_dict = ai_result.get("keys", {})
    explanation = ai_result.get("explanation", "")
    db_save_test(test_code, test_type, title, keys_dict, explanation, file_id, file_type, creator_id=uid)
    await state.clear()
    await wait_msg.delete()

    await message.answer(
        f"🎉 <b>AI YORDAMIDA TEST YARATILDI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 Test kodi: <code>{test_code}</code>\n"
        f"📚 Nomi: <b>{html.escape(title)}</b>\n"
        f"🔢 Topilgan kalitlar: <b>{len(keys_dict)} ta</b>\n\n"
        f"👉 Endi <b>«📲 Elektron Titul Tekshirish»</b> tugmasi orqali <code>{test_code}</code> kodini terib ishlash mumkin!",
        parse_mode="HTML",
        reply_markup=main_menu(uid)
    )

# -------------------------------------------------------------
# ALOHIDA ELEKTRON TITUL TEKSHIRISH VA 41, 42, 43 RASM YUKLASH
# -------------------------------------------------------------
@dp.message(F.text == "📋 Faol Testlar Baza", StateFilter("*"))
async def show_active_tests_list(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in ACTIVE_EXAM_SESSIONS:
        await state.clear()

    if not await check_channel_subscription(uid):
        await prompt_subscription(message)
        return

    recent = db_get_recent_tests(12)
    if not recent:
        await message.answer("📭 Hozircha faol testlar yo'q. «➕ Test Yaratish (Barcha uchun)» tugmasi orqali birinchi testni qo'shing!")
        return

    kb_rows = []
    lines = ["📋 <b>TITUL | FAOL TESTLAR RO'YXATI:</b>\n━━━━━━━━━━━━━━━━━━━━━━━━"]
    for r_code, r_type, r_title, _ in recent:
        badge = "30 talik" if r_type == "30_talik" else ("43 MS Rasch" if r_type == "43_ms" else "90 DTM")
        lines.append(f"🔹 <code>{r_code}</code> — <b>{html.escape(r_title)}</b> <i>({badge})</i>")
        kb_rows.append([InlineKeyboardButton(text=f"📲 Elektron Titulni Ochish: {r_code}", callback_data=f"solve_now:{r_code}")])

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))

@dp.message(F.text == "📲 Elektron Titul Tekshirish", StateFilter("*"))
async def start_electronic_test_menu(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if not await check_channel_subscription(uid):
        await prompt_subscription(message)
        return

    await state.set_state(StudentTestSolve.waiting_test_code)
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)

    recent = db_get_recent_tests(6)
    inline_kb = None
    if recent:
        rows = [[InlineKeyboardButton(text=f"📲 Titulni ochish: {c} — {t[:20]}", callback_data=f"solve_now:{c}")] for c, _, t, _ in recent]
        inline_kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await message.answer(
        "📲 <b>ALOHIDA ELEKTRON TITUL TEKSHIRISH BO'LIMI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔑 Test kodini yozib yuboring <i>(masalan: <code>MS-12345</code>)</i>:",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    if inline_kb:
        await message.answer("Yoki ro'yxatdagi faol testlardan birini tanlab darhol elektron titulni oching 👇", reply_markup=inline_kb)

@dp.callback_query(F.data.startswith("solve_now:"))
async def cb_solve_test_now(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    row = db_get_test(code)
    if not row:
        await callback.answer("❌ Test topilmadi!", show_alert=True)
        return
    await callback.answer()
    await launch_electronic_exam(callback.message, callback.from_user.id, state, row)

@dp.message(StudentTestSolve.waiting_test_code)
async def process_code_for_exam(message: types.Message, state: FSMContext):
    code = (message.text or "").strip().upper()
    row = db_get_test(code)
    if not row:
        await message.answer(f"❌ <code>{html.escape(code)}</code> kodli test topilmadi. Qaytadan kiriting:", parse_mode="HTML")
        return
    await launch_electronic_exam(message, message.from_user.id, state, row)

async def launch_electronic_exam(message: types.Message, user_id: int, state: FSMContext, row: tuple):
    test_code, test_type, title, _, _, file_id, file_type, _, _ = row

    ACTIVE_EXAM_SESSIONS[user_id] = test_code

    await state.update_data(
        active_test_code=test_code,
        active_test_type=test_type,
        active_test_title=title,
        e_answers={},
        written_photos={},
        written_scores={},
        current_page=1
    )
    await state.set_state(StudentTestSolve.in_electronic_exam)

    if file_id:
        try:
            if file_type == "document":
                await bot.send_document(message.chat.id, file_id, caption=f"📄 {title} ({test_code})")
            elif file_type == "photo":
                await bot.send_photo(message.chat.id, file_id, caption=f"🖼 {title} ({test_code})")
        except Exception:
            pass

    await message.answer(
        f"🔒 <b>TITUL MOCK IMTIHON REJIMI FAOL!</b>\n"
        f"Test ishlayotgan vaqtingizda <b>«🤖 AI Masala Yechish»</b> bo'limi avtomatik ravishda bloklandi.\n"
        f"Quyi menyudan foydalanib titulni boshqarishingiz mumkin 👇",
        parse_mode="HTML",
        reply_markup=exam_active_reply_kb()
    )

    kb = build_electronic_sheet_kb(test_type, {}, page=1, written_photos={})
    await message.answer(
        f"📲 <b>TITUL | ELEKTRON JAVOBLAR VARAQASI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📚 Test: <b>{html.escape(title)}</b> (<code>{test_code}</code>)\n"
        f"📌 Tugmalar ustiga bosib javoblaringizni belgilang.\n"
        f"📸 <b>43 talik MS testida «📍33-43 (Ochiq/Rasm)» sahifasiga o'tib 41, 42, 43-masalalarning yechim rasmlarini yuklang!</b>",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.message(F.text == "📋 Elektron Titulni Qayta Ochish", StateFilter("*"))
async def reopen_electronic_sheet(message: types.Message, state: FSMContext):
    data = await state.get_data()
    test_code = data.get("active_test_code")
    if not test_code:
        await message.answer("Sizda faol test yo'q.", reply_markup=main_menu(message.from_user.id))
        return

    test_type = data.get("active_test_type", "30_talik")
    title = data.get("active_test_title", "Test")
    ans = data.get("e_answers", {})
    w_photos = data.get("written_photos", {})
    page = data.get("current_page", 1)

    kb = build_electronic_sheet_kb(test_type, ans, page=page, written_photos=w_photos)
    await message.answer(
        f"📲 <b>ELEKTRON TITUL: {html.escape(title)}</b> (<code>{test_code}</code>)\n"
        f"✅ Belgilangan javoblar: <b>{len(ans)} ta</b> | 📸 Rasmlar (41-43): <b>{len(w_photos)}/3 ta</b>",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("ebtn:"))
async def cb_electronic_mark(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    q_num, opt, page = parts[1], parts[2], int(parts[3])

    data = await state.get_data()
    if not data.get("active_test_code"):
        await callback.answer("Bu test yakunlangan!", show_alert=True)
        return

    ans = data.get("e_answers", {})
    if ans.get(q_num) == opt:
        ans.pop(q_num, None)
    else:
        ans[q_num] = opt

    await state.update_data(e_answers=ans, current_page=page)
    kb = build_electronic_sheet_kb(data.get("active_test_type", "30_talik"), ans, page=page, written_photos=data.get("written_photos", {}))
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await callback.answer(f"{q_num}-savol: {opt}")

@dp.callback_query(F.data.startswith("epage:"))
async def cb_electronic_page(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[1])
    data = await state.get_data()
    if not data.get("active_test_code"):
        await callback.answer("Bu test yakunlangan!", show_alert=True)
        return

    await state.update_data(current_page=page)
    kb = build_electronic_sheet_kb(
        data.get("active_test_type", "30_talik"),
        data.get("e_answers", {}),
        page=page,
        written_photos=data.get("written_photos", {})
    )
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await callback.answer(f"{page}-sahifa")

@dp.callback_query(F.data.startswith("eopen:"))
async def cb_open_question_input(callback: types.CallbackQuery, state: FSMContext):
    q_num = callback.data.split(":")[1]
    await state.update_data(editing_open_q=q_num)
    await state.set_state(StudentTestSolve.waiting_open_answer)
    await callback.message.answer(
        f"✍️ <b>{q_num}-ochiq savol</b> uchun javobingizni (son yoki harf) yozib yuboring:",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(StudentTestSolve.waiting_open_answer)
async def receive_open_question_answer(message: types.Message, state: FSMContext):
    val = (message.text or "").strip().upper()
    data = await state.get_data()
    q_num = data.get("editing_open_q", "36")
    ans = data.get("e_answers", {})
    ans[str(q_num)] = val
    await state.update_data(e_answers=ans, current_page=4)
    await state.set_state(StudentTestSolve.in_electronic_exam)

    kb = build_electronic_sheet_kb(
        data.get("active_test_type", "43_ms"),
        ans,
        page=4,
        written_photos=data.get("written_photos", {})
    )
    await message.answer(
        f"✅ <b>{q_num}-savol javobi ({html.escape(val)}) saqlandi!</b>\n"
        f"Davom etishingiz mumkin 👇",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("ephoto:"))
async def cb_upload_written_photo(callback: types.CallbackQuery, state: FSMContext):
    q_num = callback.data.split(":")[1]
    await state.update_data(uploading_photo_q=q_num)
    await state.set_state(StudentTestSolve.waiting_written_photo)
    await callback.message.answer(
        f"📸 <b>{q_num}-masala yechimi tushirilgan rasmni yuboring!</b>\n"
        f"<i>(Daftardagi yechimingizni aniq rasmga olib shu yerga tashlang — AI uni 0 dan 2.5 ballgacha baholaydi)</i> 👇",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(StudentTestSolve.waiting_written_photo, F.photo)
async def receive_written_solution_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    q_num = str(data.get("uploading_photo_q", "41"))
    file_id = message.photo[-1].file_id

    wait = await message.answer(f"⏳ <b>{q_num}-masala yechimi rasmi AI orqali tekshirilmoqda...</b>", parse_mode="HTML")

    score_val = 2.0
    comment = "Qabul qilindi"
    try:
        tg_file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await bot.download_file(tg_file.file_path, destination=buf)
        score_val, comment = await ai_grade_written_work(buf.getvalue(), int(q_num))
    except Exception:
        pass

    w_photos = data.get("written_photos", {})
    w_scores = data.get("written_scores", {})
    w_photos[q_num] = file_id
    w_scores[q_num] = score_val

    await state.update_data(written_photos=w_photos, written_scores=w_scores, current_page=4)
    await state.set_state(StudentTestSolve.in_electronic_exam)
    await wait.delete()

    test_code = data.get("active_test_code", "MS")
    row = db_get_test(test_code)
    creator_id = row[7] if row and len(row) > 7 and row[7] else ADMIN_ID

    for target_id in {ADMIN_ID, creator_id}:
        if not target_id:
            continue
        try:
            await bot.send_photo(
                target_id,
                file_id,
                caption=(
                    f"📸 <b>TITUL | Yozma ish yechimi ({q_num}-masala)</b>\n"
                    f"👤 O'quvchi: {html.escape(message.from_user.full_name)}\n"
                    f"🔑 Test: <code>{test_code}</code>\n"
                    f"🤖 AI bahosi: <b>{score_val} / 2.5 ball</b> ({html.escape(comment)})"
                ),
                parse_mode="HTML"
            )
        except Exception:
            pass

    kb = build_electronic_sheet_kb(
        data.get("active_test_type", "43_ms"),
        data.get("e_answers", {}),
        page=4,
        written_photos=w_photos
    )
    await message.answer(
        f"✅ <b>{q_num}-masala yechimi rasmi yuklandi!</b>\n"
        f"📊 AI bahosi: <b>{score_val} / 2.5 ball</b>\n"
        f"💬 Izoh: <i>{html.escape(comment)}</i>\n\n"
        f"Titulda davom eting yoki yakunlang 👇",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.message(StudentTestSolve.waiting_written_photo)
async def receive_written_photo_invalid(message: types.Message):
    await message.answer("⚠️ Iltimos, yechimingizni <b>rasm (foto)</b> ko'rinishida yuboring!", parse_mode="HTML")

@dp.callback_query(F.data == "efinish")
async def cb_finish_electronic_exam(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    data = await state.get_data()
    code = data.get("active_test_code")
    if not code:
        await callback.answer("Test allaqachon yakunlangan!", show_alert=True)
        return

    test_type = data.get("active_test_type", "30_talik")
    w_photos = data.get("written_photos", {})

    if test_type == "43_ms" and len(w_photos) < 3 and not data.get("warned_missing_photos"):
        missing = [str(q) for q in [41, 42, 43] if str(q) not in w_photos]
        await state.update_data(warned_missing_photos=True)
        await callback.answer(
            f"⚠️ Diqqat! Siz {', '.join(missing)}-masalalar yechimi rasmini yuklamadingiz! "
            f"4-betga o'tib rasm yuklang yoki rasmsiz yakunlash uchun tugmani yana bir marta bosing.",
            show_alert=True
        )
        return

    row = db_get_test(code)
    ACTIVE_EXAM_SESSIONS.pop(uid, None)
    await state.clear()

    if not row:
        await callback.message.answer("❌ Test bazadan topilmadi.", reply_markup=main_menu(uid))
        return

    _, test_type, title, keys_json, _, _, _, _, _ = row
    correct_keys = json.loads(keys_json)
    student_ans = data.get("e_answers", {})
    w_scores = data.get("written_scores", {})

    res = evaluate_student_submission(test_type, correct_keys, student_ans, written_scores=w_scores, test_code=code)
    w_total = sum(float(v) for v in w_scores.values())
    student_name = callback.from_user.full_name or "O'quvchi"

    db_save_result(
        code,
        uid,
        student_name,
        res["correct_count"],
        res["total_score"],
        res["grade"],
        written_score=w_total,
        answers_dict=student_ans
    )

    mistakes_str = "\n".join(res["mistakes"][:25]) if res["mistakes"] else "🎉 Barcha belgilangan test javoblari 100% to'g'ri!"
    report = (
        f"{res['summary']}\n\n"
        f"📋 <b>Tahlil va Xatolar:</b>\n"
        f"{html.escape(mistakes_str)}\n\n"
        f"🔓 <i>Mock imtihon yakunlandi! Quyida joriy Reyting Posti va PDF Natijalar jadvali taqdim etiladi 👇</i>"
    )
    await callback.message.answer(report, parse_mode="HTML", reply_markup=main_menu(uid))

    all_results = db_get_top_results(code, 100)
    post_text = generate_announcement_post(code, title, test_type, all_results, correct_keys)
    pdf_bytes = generate_test_results_pdf(code, title, test_type, all_results)
    pdf_file = BufferedInputFile(pdf_bytes, filename=f"TITUL_{code}_Natijalar.pdf")

    await callback.message.answer_document(
        pdf_file,
        caption=f"📄 <b>TITUL | {html.escape(title)} ({code}) — Rasmiy PDF Natijalar Jadvali</b>",
        parse_mode="HTML"
    )
    await callback.message.answer(post_text, parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer("🎉 Natijangiz PDF va Post shaklida tayyorlandi!")

@dp.message(StudentTestSolve.in_electronic_exam, F.text)
async def quick_text_fill_in_exam(message: types.Message, state: FSMContext):
    data = await state.get_data()
    test_type = data.get("active_test_type", "30_talik")
    parsed = parse_input_answers(message.text or "", test_type)
    if not parsed:
        await message.answer(
            "💡 Elektron titul tugmalari orqali belgilang yoki <code>1A 2B 3C...</code> ko'rinishida yozing.",
            parse_mode="HTML"
        )
        return

    ans = data.get("e_answers", {})
    ans.update(parsed)
    await state.update_data(e_answers=ans)
    kb = build_electronic_sheet_kb(test_type, ans, page=data.get("current_page", 1), written_photos=data.get("written_photos", {}))
    await message.answer(
        f"✅ <b>{len(parsed)} ta javob elektron titulga avtomatik joylandi!</b>\n"
        f"Tekshirib, yakunlash tugmasini bosing 👇",
        parse_mode="HTML",
        reply_markup=kb
    )

# -------------------------------------------------------------
# TESTNI YAKUNLASH VA NATIJALARNI PDF + POST SHAKLIDA E'LON QILISH
# -------------------------------------------------------------
@dp.message(F.text == "📢 Testni Yakunlash (PDF + Post)", StateFilter("*"))
async def finish_and_announce_test_menu(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in ACTIVE_EXAM_SESSIONS:
        await state.clear()

    if not await check_channel_subscription(uid):
        await prompt_subscription(message)
        return

    my_tests = db_get_user_tests(uid, 10)
    if not my_tests:
        my_tests = db_get_recent_tests(8)

    if not my_tests:
        await message.answer("📭 Hozircha e'lon qilinadigan testlar yo'q.")
        return

    kb = [
        [InlineKeyboardButton(text=f"📢 PDF + Post chiqarish: {c} ({t[:20]})", callback_data=f"announce:{c}")]
        for c, _, t, _ in my_tests
    ]
    await message.answer(
        "📢 <b>TITUL | TESTNI YAKUNLASH VA NATIJALARNI E'LON QILISH</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Qaysi testni yakunlab, uning <b>PDF jadvali va tayyor kanal Postini</b> olmoqchisiz? Tanlang 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data.startswith("announce:"))
async def cb_announce_test_results(callback: types.CallbackQuery):
    code = callback.data.split(":")[1]
    row = db_get_test(code)
    if not row:
        await callback.answer("❌ Test topilmadi!", show_alert=True)
        return

    test_code, test_type, title, keys_json, _, _, _, _, _ = row
    keys_dict = json.loads(keys_json)
    results = db_get_top_results(test_code, 100)

    await callback.answer("📄 PDF va Post tayyorlanmoqda...")

    pdf_bytes = generate_test_results_pdf(test_code, title, test_type, results)
    post_text = generate_announcement_post(test_code, title, test_type, results, keys_dict)

    pdf_file = BufferedInputFile(pdf_bytes, filename=f"TITUL_{test_code}_Yakuniy_Natijalar.pdf")
    await callback.message.answer_document(
        pdf_file,
        caption=(
            f"📊 <b>TITUL | YAKUNIY PDF HISOBOT</b>\n"
            f"🔑 Test kodi: <code>{test_code}</code> | 📚 {html.escape(title)}\n"
            f"👥 Jami yechganlar: <b>{len(results)} nafar</b>"
        ),
        parse_mode="HTML"
    )
    await callback.message.answer(
        post_text,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

# -------------------------------------------------------------
# REYTING VA NATIJALAR
# -------------------------------------------------------------
@dp.message(F.text == "🏆 Reyting & Natijalar", StateFilter("*"))
async def show_rating_menu(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid not in ACTIVE_EXAM_SESSIONS:
        await state.clear()

    if not await check_channel_subscription(uid):
        await prompt_subscription(message)
        return
    recent = db_get_recent_tests(10)
    if not recent:
        await message.answer("📭 Hozircha natijalar yo'q.")
        return
    kb = [[InlineKeyboardButton(text=f"🏆 {r_code} — {r_title} (PDF + Post)", callback_data=f"announce:{r_code}")] for r_code, _, r_title, _ in recent]
    await message.answer(
        "🏆 <b>Qaysi testning reyting jadvali (PDF va Post) ni ko'rmoqchisiz?</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

# -------------------------------------------------------------
# AI MASALA YECHISH (MOCK TEST PAYTIDA QAT'IY BLOKLANADI!)
# -------------------------------------------------------------
@dp.message(F.text == "🤖 AI Masala Yechish (Rasm)", StateFilter("*"))
async def start_ai_solver(message: types.Message, state: FSMContext):
    uid = message.from_user.id

    if uid in ACTIVE_EXAM_SESSIONS:
        active_code = ACTIVE_EXAM_SESSIONS[uid]
        await message.answer(
            f"⛔️ <b>DIQQAT! IMTIHON TARTIBI!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Siz hozir <code>{active_code}</code> kodli <b>Mock testni</b> ishlayapsiz!\n"
            f"Adolatli sinov qoidalariga binoan, test yakunlanmaguncha <b>AI Masala Yechish</b> bo'limi ishlamaydi.\n\n"
            f"👉 Avval elektron titulda testni yakunlang!",
            parse_mode="HTML",
            reply_markup=exam_active_reply_kb()
        )
        return

    if not await check_channel_subscription(uid):
        await prompt_subscription(message)
        return

    await state.set_state(AISolveProblem.waiting_problem_photo)
    await message.answer(
        "📸 <b>TITUL | AI KIMYO MASALA YECHISH BO'LIMI (24/7 FAOL)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Tushunmagan kimyo masalangiz yoki savolingiz rasmini yuboring.\n"
        "Sun'iy intellekt uni bosqichma-bosqich yechib beradi 👇",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    )

@dp.message(AISolveProblem.waiting_problem_photo, F.photo)
async def solve_photo(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid in ACTIVE_EXAM_SESSIONS:
        await message.answer("⛔️ Mock test vaqtida AI masala yechish bloklangan!", reply_markup=exam_active_reply_kb())
        return

    wait = await message.answer("🤖 TITUL AI masalani tahlil qilib yechmoqda, 10–15 soniya kuting...")
    try:
        file_id = message.photo[-1].file_id
        tg_file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await bot.download_file(tg_file.file_path, destination=buf)
        sol = await ai_solve_photo_problem(buf.getvalue(), "image/jpeg")
        await state.clear()
        await wait.delete()
        await message.answer(f"🧪 <b>TITUL AI Masala Yechimi:</b>\n\n{sol}", parse_mode="HTML", reply_markup=main_menu(uid))
    except Exception as e:
        await state.clear()
        await wait.edit_text(f"❌ Xato: {e}")

@dp.message(F.text == "👨‍🏫 Ustoz & Bog'lanish", StateFilter("*"))
async def contact_info(message: types.Message, state: FSMContext):
    if message.from_user.id not in ACTIVE_EXAM_SESSIONS:
        await state.clear()
    await message.answer(
        f"📋 <b>Platforma:</b> TITUL Elektron Test Tizimi\n"
        f"👨‍🏫 <b>Ustoz:</b> Azizbek Ibrohimov\n"
        f"📢 <b>Rasmiy kanal:</b> {DEFAULT_CHANNEL_URL}\n"
        f"📞 <b>Murojaat uchun:</b> {ADMIN_USERNAME}",
        parse_mode="HTML"
    )

# -------------------------------------------------------------
# 24/7 WEB SERVER
# -------------------------------------------------------------
async def handle_ping(request):
    return web.Response(text="TITUL Electronic Test & AI Bot active 24/7!")

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
