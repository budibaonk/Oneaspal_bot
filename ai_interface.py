import os
import asyncio
from google import genai
from google.genai import types
from dotenv import load_dotenv

# 1. Load Environment
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

# Inisialisasi Client
client = None
if API_KEY:
    try:
        client = genai.Client(api_key=API_KEY)
        print("✅ AI BRAIN: ONLINE (Versi 2.0 Flash Lite)")
    except Exception as e:
        print(f"❌ AI BRAIN: ERROR ({e})")

# 2. SYSTEM PROMPT
SYSTEM_PROMPT = """
KAMU ADALAH "B-ONE BOT".
[IDENTITAS]
- Sistem AI Canggih dari "B-One Enterprise".
- Melayani Mitra Lapangan & Internal Leasing.
- Sifat: Canggih, Otomatis, Tegas, Solutif, Taat Hukum.

[GAYA BICARA]
- GANTI "Matel" dengan "Mitra Lapangan".
- GANTI "Admin" dengan "Sistem Otomatis".
- Gunakan kode: "86", "Siap Ndan", "Monitor", "Terkendali".

[TUGAS]
- Jawab singkat dan padat.
- Jika user tanya Nopol spesifik dan kamu tidak tahu, arahkan ke fitur /cek database.
"""

# 3. FUNGSI PEMANGGIL AI
async def ask_gemini(user_text, user_name="Komandan"):
    if not client:
        return "⚠️ Maaf Ndan, Sistem AI sedang offline (API Key Missing)."

    try:
        final_prompt = f"User '{user_name}' bertanya: {user_text}"
        
        # KITA PAKAI MODEL 'LITE' (Biasanya kuota lebih aman)
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.0-flash-lite-001", 
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.7,
            ),
            contents=final_prompt
        )
        
        return response.text if response.text else "Siap Ndan. Monitor."
        
    except Exception as e:
        # DIAGNOSA ERROR DI TERMINAL
        print(f"❌ DEBUG AI ERROR: {e}") 
        
        error_msg = str(e)
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            return "🙏 Maaf Ndan, server kecerdasan sedang istirahat (Overload). Mohon tunggu 1 menit."
        elif "404" in error_msg or "NOT_FOUND" in error_msg:
            return "⚠️ Maaf Ndan, Model AI sedang update sistem. (Error 404)"
            
        return "⚠️ Maaf Ndan, sinyal satelit gangguan. Coba ulangi."