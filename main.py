################################################################################
#                                                                              #
#  PROJECT: ONEASPAL BOT (ASSET RECOVERY)                                      #
#  VERSION: 6.70                                                               #
#  ROLE   : MAIN APPLICATION CORE                                              #
#  AUTHOR : CTO (GEMINI) & CEO (BAONK)                                         #
#                                                                              #
#  UPDATE LOG v6.70:                                                           #
#  1. Integrated with 'utils_log' for automatic daily activity recording.      #
#  2. Added 'catat_log_kendaraan' in background upload execution.              #
#  3. Fixed batch processing for better database stability.                    #
#                                                                              #
################################################################################

import os
import logging
import pandas as pd
import io
import numpy as np
import time
import re
import asyncio 
import csv 
import zipfile 
import json
import html
import difflib
import pytz
import urllib.parse
import shutil
import secrets # Pastikan import ini ada di bagian paling atas file
from dotenv import load_dotenv
from collections import Counter
from datetime import datetime, timedelta, timezone, time as dt_time
from flask import make_response, redirect
from flask import Flask, render_template, request, redirect
import threading
import asyncio

# ==========================================================================
# 1. Inisialisasi Flask untuk Landing Page & PIC Dashboard
# ==========================================================================
app_web = Flask(__name__, 
            template_folder='templates', # Nama foldernya harus templates
            static_folder='static')      # Nanti untuk CSS/Gambar

@app_web.route('/')
def home():
    # Menampilkan Landing Page B-One Asset Management
    return render_template('index.html')

@app_web.route('/send-inquiry', methods=['POST'])
def send_inquiry():
    name = request.form.get('name')
    company = request.form.get('company')
    phone = request.form.get('phone')
    email = request.form.get('email')
    message = request.form.get('message')

    # Logika membersihkan nomor telepon untuk link WhatsApp
    clean_phone = ''.join(filter(str.isdigit, phone))
    if clean_phone.startswith('0'):
        clean_phone = '62' + clean_phone[1:]
    
    wa_link = f"https://wa.me/{clean_phone}"

    text_notif = (
        "🚀 <b>NEW ENTERPRISE INQUIRY</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>PIC:</b> {name}\n"
        f"🏢 <b>Company:</b> {company}\n"
        f"📞 <b>Phone:</b> <a href='{wa_link}'>{phone} (Klik Chat WA)</a>\n"
        f"📧 <b>Email:</b> {email}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💬 <b>Message:</b>\n<i>{message}</i>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📢 <i>Action: Klik nomor di atas untuk lobi langsung.</i>"
    )

    try:
        from telegram import Bot
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        temp_bot = Bot(token=TOKEN)
        loop.run_until_complete(temp_bot.send_message(
            chat_id=ADMIN_ID, 
            text=text_notif, 
            parse_mode='HTML',
            disable_web_page_preview=True 
        ))
        loop.close()
    except Exception as e:
        print(f"❌ Error: {e}")

    # Response setelah submit
    return """
    <body style="background:#0a0e14; color:white; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:100vh; text-align:center; padding:20px;">
        <div>
            <div style="font-size:50px; color:#00ffcc; margin-bottom:20px;">✔</div>
            <h1 style="color:#00ffcc; margin-bottom:10px;">Inquiry Sent Successfully!</h1>
            <p style="color:#a0aec0; margin-bottom:30px;">Thank you for reaching out. Our team will contact you shortly.</p>
            <a href="/" style="background:#0088ff; color:white; padding:12px 25px; border-radius:50px; text-decoration:none; font-weight:bold;">Back to Homepage</a>
        </div>
    </body>
    """

# ==============================================================================
# JALUR MAGIC LINK & VALIDASI (GEMBOK BAJA B-ONE ENTERPRISE)
# ==============================================================================
@app_web.route('/login-sso')
def login_sso():
    uid = request.args.get('uid')
    token = request.args.get('token')

    if not uid or not token:
        return "⛔ Akses Ditolak: Link tidak valid atau rusak.", 400

    try:
        # 1. Cek Token ke Supabase (FIX: pakai 'user_id' bukan 'id')
        res = supabase.table('users').select('session_token, session_expiry, role').eq('user_id', uid).execute()
        if not res.data:
            return "⛔ Akses Ditolak: User tidak ditemukan.", 403

        user_data = res.data[0]
        
        # 2. Cocokkan Token Rahasia
        if user_data.get('session_token') != token:
            return "⛔ Akses Ditolak: Token tidak valid, atau sesi sudah di-reset dari Telegram.", 403

        # 3. Cek Batas Waktu Kadaluarsa (15 Menit)
        expiry_str = user_data.get('session_expiry')
        if not expiry_str:
            return "⛔ Akses Ditolak: Sesi tidak valid.", 403
        
        # Parse waktu dari database dan bandingkan dengan waktu sekarang
        expiry_time = datetime.fromisoformat(expiry_str)
        if datetime.now(timezone.utc) > expiry_time:
            return "⛔ Akses Ditolak: Magic Link sudah KADALUARSA! Silakan ketik /dashboard lagi di Telegram.", 403

        # --- JIKA SEMUA VALID (LOLOS SENSOR) ---
        
        # 4. HANCURKAN TOKEN (One-Time Use) (FIX: pakai 'user_id' bukan 'id')
        supabase.table('users').update({
            'session_token': None,
            'session_expiry': None
        }).eq('user_id', uid).execute()

        # 5. BERIKAN KARTU AKSES (Device Binding via Cookies)
        response = make_response(redirect('/dashboard'))
        
        # Tanamkan Cookies selama 8 Jam kerja
        response.set_cookie(
            'bone_session', 
            value=uid, 
            max_age=8 * 3600, # 8 Jam
            httponly=True, 
            secure=True,     # <--- MENGUNCI COOKIES HANYA UNTUK HTTPS (GO-LIVE)
            samesite='Lax'
        )
        return response

    except Exception as e:
        logger.error(f"SSO Error: {e}")
        return f"⚠️ Terjadi kesalahan sistem: {str(e)}", 500


# --- [UPDATE FINAL] ROUTE DASHBOARD PIC LEASING DENGAN COOKIE VALIDATION ---
@app_web.route('/dashboard')
def dashboard_pic_gate():
    # 1. BACA KARTU AKSES (Cookies)
    user_id = request.cookies.get('bone_session')
    
    # 2. JIKA TIDAK ADA KARTU, TENDANG KELUAR!
    if not user_id:
        return """
        <body style="background:#0a1219; color:white; font-family:sans-serif; display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh;">
            <div style="text-align:center; border: 1px solid #ff4d4d; padding: 40px; border-radius: 20px; background: rgba(255, 77, 77, 0.05);">
                <h2 style="color:#ff4d4d;">⛔ Akses Ditolak (403)</h2>
                <p>Anda tidak memiliki izin untuk membuka halaman ini.</p>
                <p>Silakan masuk melalui <b>Magic Link</b> dari Bot Telegram Resmi B-One Enterprise.</p>
            </div>
        </body>
        """, 403

    # 3. Cek Identitas ke Database Supabase
    user_db = get_user(user_id)
    
    if not user_db:
        return """
        <body style="background:#0a1219; color:white; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:100vh;">
            <div style="text-align:center; border: 1px solid #ff4d4d; padding: 40px; border-radius: 20px;">
                <h2 style="color:#ff4d4d;">❌ User Tidak Ditemukan</h2>
                <p>Sesi valid, tetapi ID Anda tidak ditemukan dalam sistem B-One Enterprise.</p>
            </div>
        </body>
        """, 403

    # 4. Logika Bypass untuk CEO (Super Admin)
    is_ceo = (str(user_id) == str(ADMIN_ID) or user_db.get('role') == 'superadmin')

    if is_ceo:
        if not user_db.get('agency'):
            user_db['agency'] = 'B-ONE ENTERPRISE'
    else:
        # Validasi Ketat untuk User Biasa
        if user_db.get('role') != 'pic' or user_db.get('status') != 'active':
            return f"""
            <body style="background:#0a1219; color:white; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:100vh;">
                <div style="text-align:center; border: 1px solid #ff4d4d; padding: 40px; border-radius: 20px;">
                    <h2 style="color:#ff4d4d;">⛔ Akses Terbatas</h2>
                    <p>Maaf, akun ID {user_id} tidak memiliki izin akses Enterprise.</p>
                    <p style="color: #64748b; font-size: 0.9rem;">Hanya akun level PIC yang diizinkan masuk.</p>
                </div>
            </body>
            """, 403

    # 5. HITUNG STATISTIK RIIL DARI SUPABASE
    total_aset = 0
    try:
        res_total = supabase.table('kendaraan') \
            .select('nopol', count='exact') \
            .eq('finance', user_db.get('agency')) \
            .execute()
        
        total_aset = res_total.count if res_total.count else 0
    except Exception as e:
        print(f"❌ Error Fetching Stats: {e}")
        total_aset = 0

    # Kirim variabel ke template HTML
    return render_template('dashboard_pic.html', 
                           user=user_db, 
                           is_admin=is_ceo, 
                           total_aset=total_aset)

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ==========================================================================
# 2. Inisialisasi Telegram & Supabase
# ==========================================================================
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, 
    ReplyKeyboardRemove, 
    constants,
    LinkPreviewOptions
)

from telegram.ext import (
    Application,
    ApplicationBuilder, 
    ContextTypes, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    filters, 
    ConversationHandler
)

from supabase import create_client, Client
from utils_log import catat_log_kendaraan

# [FIX] Import ClientOptions untuk menangani Timeout
try:
    from supabase.lib.client_options import ClientOptions
except ImportError:
    from supabase import ClientOptions

from flask import jsonify

# --- HELPER: INTEGRASI KEKUATAN BOT & STREAMLIT ---
def fix_header_position(df):
    target = COLUMN_ALIASES['nopol']
    # 1. Cek apakah header sudah benar di kolom saat ini
    col_vals = [normalize_text(str(x)) for x in df.columns]
    if any(alias in col_vals for alias in target):
        return df
    # 2. Jika tidak, cari di 30 baris pertama
    for i in range(min(30, len(df))): 
        vals = [normalize_text(str(x)) for x in df.iloc[i].values]
        if any(alias in vals for alias in target):
            df.columns = df.iloc[i] 
            df = df.iloc[i+1:].reset_index(drop=True) 
            return df
    return df
# ==============================================================================
# [NEW] PIC DASHBOARD: TAHAP 1 (HANYA PREVIEW, TIDAK MENYIMPAN)
# ==============================================================================
@app_web.route('/analyze-upload', methods=['POST'])
def analyze_upload():
    file = request.files.get('file')
    if not file: return jsonify({"status": "error", "message": "File tidak terdeteksi."}), 400
    
    try:
        content = file.read()
        df = read_file_robust(content, file.filename)
        
        # Cari Header Cerdas
        target_aliases = COLUMN_ALIASES['nopol']
        if not any(normalize_text(str(c)) in target_aliases for c in df.columns):
            for i in range(min(30, len(df))):
                row_values = [normalize_text(str(x)) for x in df.iloc[i].values]
                if any(alias in row_values for alias in target_aliases):
                    df.columns = df.iloc[i]
                    df = df.iloc[i+1:].reset_index(drop=True)
                    break
                    
        df, _ = smart_rename_columns(df)
        
        if 'nopol' not in df.columns:
            return jsonify({"status": "error", "message": f"Gagal: Kolom NOPOL tidak ditemukan."}), 400
            
        # Ambil 5 baris pertama untuk ditampilkan
        preview_data = df.head(5).replace({np.nan: "-"}).to_dict('records')
        return jsonify({"status": "success", "preview": preview_data, "total_rows": len(df)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==============================================================================
# [NEW] PIC DASHBOARD UPLOAD ENGINE (MENGADOPSI KEKUATAN STREAMLIT)
# ==============================================================================
@app_web.route('/upload-dashboard', methods=['POST'])
def upload_dashboard():
    file = request.files.get('file')
    uid = request.form.get('uid')
    
    if not file: return jsonify({"status": "error", "message": "File tidak terdeteksi."}), 400
    
    user_db = get_user(uid)
    if not user_db: return jsonify({"status": "error", "message": "Akses Ditolak"}), 403
    
    # Agency default dari DB jika di file tidak ada kolom finance
    agency_db = user_db.get('agency', 'UNKNOWN')

    try:
        content = file.read()
        
        # 1. KEKUATAN STREAMLIT: Read File Robust
        df = read_file_robust(content, file.filename)
        
        # 2. KEKUATAN STREAMLIT: Cari Header di baris manapun
        target_aliases = COLUMN_ALIASES['nopol']
        if not any(normalize_text(str(c)) in target_aliases for c in df.columns):
            for i in range(min(30, len(df))):
                row_values = [normalize_text(str(x)) for x in df.iloc[i].values]
                if any(alias in row_values for alias in target_aliases):
                    df.columns = df.iloc[i]
                    df = df.iloc[i+1:].reset_index(drop=True)
                    break
                    
        # 3. KEKUATAN STREAMLIT: Smart Rename
        df, _ = smart_rename_columns(df)
        
        if 'nopol' not in df.columns:
            return jsonify({"status": "error", "message": f"Gagal: Kolom NOPOL tidak ditemukan."}), 400

        # ---> PERBAIKAN: MENGAMBIL NAMA LEASING DARI KOLOM FINANCE DI FILE <---
        if 'finance' in df.columns and not df['finance'].dropna().empty:
            # Ambil baris pertama dari kolom finance yang tidak kosong
            nama_leasing_aktual = str(df['finance'].dropna().iloc[0]).strip().upper()
        else:
            # Jika file tidak punya kolom finance, pakai data dari profil user
            nama_leasing_aktual = agency_db

        # 4. DATA CLEANING & AUTO-STAMPING
        df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        df['nopol'] = df['nopol'].replace({'': np.nan, 'NAN': np.nan, 'NONE': np.nan})
        df = df.dropna(subset=['nopol']) 
        df = df.drop_duplicates(subset=['nopol']) 
        
        # Terapkan nama leasing aktual ke seluruh baris data
        df['finance'] = nama_leasing_aktual
        
        # Stamping Label Bulan Tahun (Contoh: '0326')
        label_bulan = datetime.now().strftime('%m%y')
        df['data_month'] = label_bulan
        
        valid_cols = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'branch', 'finance', 'data_month']
        for c in valid_cols:
            if c not in df.columns: df[c] = None 
            
        final_df = df[valid_cols].replace({np.nan: None})
        recs = final_df.to_dict('records')
        total_recs = len(recs)

        if total_recs == 0:
            return jsonify({"status": "error", "message": "Data kosong setelah dibersihkan."}), 400

        # 5. KEKUATAN STREAMLIT: Batch Upsert (200 data) dengan 5x Auto-Retry
        BATCH_SIZE = 200
        sukses = 0
        gagal = 0
        
        for i in range(0, total_recs, BATCH_SIZE):
            batch = recs[i:i+BATCH_SIZE]
            
            for attempt in range(5):
                try: 
                    supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
                    sukses += len(batch)
                    break 
                except Exception as e: 
                    time.sleep((attempt + 1) * 2)
                    if attempt == 4: 
                        gagal += len(batch)

        # 6. MENGGUNAKAN UTILS_LOG DENGAN NAMA LEASING DARI FILE
        try:
            catat_log_kendaraan(sumber="DASHBOARD_PIC", leasing=nama_leasing_aktual, jumlah=sukses)
        except Exception as log_e:
            print(f"Peringatan Log: {log_e}")

        if gagal == 0:
            return jsonify({"status": "success", "message": f"✅ SUKSES TOTAL! {sukses} Data Berhasil Diupdate (Label: {label_bulan})."})
        else:
            return jsonify({"status": "success", "message": f"⚠️ SELESAI. Sukses: {sukses} | Gagal: {gagal} (Cek koneksi server)."})
            
    except Exception as e:
        print(f"❌ Error Upload: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
# ==============================================================================
# [NEW] PIC DASHBOARD ASSET INVENTORY (FAST LOAD & SAFE PAGINATION)
# ==============================================================================
@app_web.route('/get-assets')
def get_assets():
    user_id = request.args.get('uid')
    search_query = request.args.get('search', '')
    
    try:
        page = int(request.args.get('page', 1))
    except (ValueError, TypeError):
        page = 1
        
    per_page = 100 
    
    user_db = get_user(user_id)
    if not user_db: return jsonify({"status": "error", "message": "Akses Ditolak"}), 403
        
    agency_name = user_db.get('agency', 'UNKNOWN')

    try:
        query = supabase.table('kendaraan').select('*', count='estimated').eq('finance', agency_name)
        
        if search_query:
            query = query.ilike('nopol', f'%{search_query}%')
            
        start = (page - 1) * per_page
        end = start + per_page - 1
        
        # PERBAIKAN: Ganti ascending=True menjadi desc=False (Sesuai versi Supabase terbaru)
        res = query.order('nopol', desc=False).range(start, end).execute()
        
        total = res.count if res.count is not None else len(res.data)
        
        return jsonify({
            "status": "success", 
            "data": res.data,
            "total_count": total,
            "page": page,
            "per_page": per_page
        })
    except Exception as e:
        print(f"❌ Error Get Assets: {e}") 
        return jsonify({"status": "error", "message": str(e)}), 500

# --- [POINT 6] FITUR AUDIT LOG ---    
@app_web.route('/get-audit-logs')
def get_audit_logs():
    user_id = request.args.get('uid')
    u = get_user(user_id)
    if not u: return jsonify({"status": "error", "message": "Unauthorized"}), 403

    try:
        # Menampilkan riwayat aktivitas yang berkaitan dengan agency PIC tersebut
        # Kita filter berdasarkan agency agar mereka hanya melihat log milik tim mereka
        res = supabase.table('audit_logs') \
            .select('*') \
            .eq('agency_leasing', u.get('agency')) \
            .order('created_at', desc=True) \
            .limit(20) \
            .execute()
        return jsonify({"status": "success", "data": res.data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app_web.route('/delete-asset', methods=['POST'])
def delete_asset():
    data = request.json
    uid = data.get('uid')
    nopol = data.get('nopol')
    reason = data.get('reason')

    user_db = get_user(uid)
    if not user_db: return jsonify({"status": "error", "message": "Unauthorized"}), 403

    try:
        # 1. Eksekusi Hapus di Supabase
        # Filter berdasarkan nopol DAN agency (supaya PIC tidak bisa hapus nopol leasing lain)
        res = supabase.table('kendaraan') \
            .delete() \
            .eq('nopol', nopol) \
            .eq('finance', user_db.get('agency')) \
            .execute()

        # 2. Catat ke Audit Log (Penting untuk UU PDP)
        supabase.table('audit_logs').insert({
            "user_id": uid,
            "agency_leasing": user_db.get('agency'),
            "action": "DELETE",
            "details": f"Menghapus Nopol {nopol} (Alasan: {reason})"
        }).execute()

        return jsonify({"status": "success", "message": "Data terhapus"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- KONFIGURASI ADMIN ---
# Masukkan ID Telegram Anda di sini agar fitur /rekap dan Notifikasi jalan
ADMIN_IDS = ['7530512170']

# ##############################################################################
# BAGIAN 1: KONFIGURASI SISTEM
# ##############################################################################

load_dotenv()

# Logger level diset ke INFO agar terlihat di terminal
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
TOKEN = os.environ.get("TELEGRAM_TOKEN")

TZ_JAKARTA = pytz.timezone('Asia/Jakarta')

DAILY_LIMIT_MATEL = 500  
DAILY_LIMIT_KORLAP = 2000 

GLOBAL_INFO = ""

BANK_INFO = """
🏧 <b>METODE PEMBAYARAN</b>
━━━━━━━━━━━━━━━━━━
<b>BCA:</b> UNDER CONSTRUCTION
<b>A/N:</b> UNDER CONSTRUCTION
━━━━━━━━━━━━━━━━━━
👇 <b>LANGKAH SELANJUTNYA:</b>
1. Transfer sesuai nominal paket.
2. <b>FOTO</b> bukti transfer Anda.
3. <b>KIRIM FOTO</b> tersebut ke chat ini.
4. Admin akan memproses akun Anda.
"""

# --- DIAGNOSTIC STARTUP ---
print("\n" + "="*50)
print("🔍 SYSTEM DIAGNOSTIC STARTUP (v6.30)")
print("="*50)

try:
    # Cek ENV dulu
    env_id = int(os.environ.get("ADMIN_ID", 0))
    
    # [FIX] Jika ENV 0/Error, Ambil dari HARDCODED LIST di atas
    if env_id == 0 and 'ADMIN_IDS' in globals() and len(ADMIN_IDS) > 0:
        ADMIN_ID = int(ADMIN_IDS[0])
        print(f"⚠️ FORCE ADMIN ID: {ADMIN_ID}")
    else:
        ADMIN_ID = env_id

    LOG_GROUP_ID = int(os.environ.get("LOG_GROUP_ID", 0))
    print(f"✅ ADMIN ID AKTIF: {ADMIN_ID}")
    
    if LOG_GROUP_ID == 0:
        print("⚠️ PERINGATAN: LOG_GROUP_ID BERNILAI 0!")
    else:
        print(f"✅ LOG_GROUP_ID TERDETEKSI: {LOG_GROUP_ID}")
        
except ValueError:
    ADMIN_ID = 0
    LOG_GROUP_ID = 0
    print("❌ ERROR: ADMIN_ID atau LOG_GROUP_ID bukan angka!")

if not URL or not KEY or not TOKEN:
    print("❌ CRITICAL: TOKEN/URL/KEY Supabase Hilang dari .env")
    exit()
else:
    print("✅ Credential Database & Bot: OK")

try:
    # [FIX] Set Timeout ke 300 detik (5 Menit) agar upload besar tidak putus
    opts = ClientOptions(postgrest_client_timeout=300)
    supabase: Client = create_client(URL, KEY, options=opts)
    print("✅ Koneksi Supabase: BERHASIL (Timeout 300s)")
except Exception as e:
    print(f"⚠️ Warning ClientOptions: {e}")
    # Fallback ke default jika library lama
    supabase: Client = create_client(URL, KEY)
    print("✅ Koneksi Supabase: BERHASIL (Default Mode)")

print("="*50 + "\n")


# ##############################################################################
# BAGIAN 2: KAMUS DATA
# ##############################################################################

COLUMN_ALIASES = {
    'nopol': ['nopolisi', 'nomorpolisi', 'nopol', 'noplat', 'tnkb', 'licenseplate', 'plat', 'police_no', 'no polisi', 'plate_number', 'platenumber', 'plate_no'],
    'type': ['type', 'tipe', 'unit', 'model', 'vehicle', 'jenis', 'deskripsiunit', 'merk', 'object', 'kendaraan', 'item', 'brand', 'tipeunit', 'unit_type', 'nama_unit'],
    'tahun': ['tahun', 'year', 'thn', 'rakitan', 'th', 'yearofmanufacture'],
    'warna': ['warna', 'color', 'colour', 'cat'],
    'noka': ['noka', 'norangka', 'nomorrangka', 'chassis', 'chasis', 'vin', 'rangka', 'no rangka', 'chassis_number'],
    'nosin': ['nosin', 'nomesin', 'nomormesin', 'engine', 'mesin', 'no mesin', 'engine_number'],
    'finance': ['finance', 'leasing', 'lising', 'multifinance', 'mitra', 'principal', 'client'],
    'ovd': ['ovd', 'overdue', 'dpd', 'keterlambatan', 'odh', 'hari', 'telat', 'aging', 'days_overdue', 'lates', 'over_due', 'od'],
    'branch': ['branch', 'area', 'kota', 'pos', 'cabang', 'lokasi', 'wilayah']
}

VALID_DB_COLUMNS = ['nopol', 'type', 'finance', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'branch']

# ##############################################################################
# BAGIAN 3: DEFINISI STATE CONVERSATION
# ##############################################################################

# UPDATE: Tambahkan R_BRANCH (Jadi range 9)
R_ROLE_CHOICE, R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_BRANCH, R_PHOTO_ID, R_CONFIRM = range(9)
# Definisi State untuk Percakapan Tambah Manual
ADD_NOPOL, ADD_UNIT, ADD_LEASING, ADD_PHONE, ADD_NOTE, ADD_CONFIRM = range(6)
L_NOPOL, L_REASON, L_CONFIRM = range(14, 17) 
D_NOPOL, D_CONFIRM = range(17, 19)
U_LEASING_USER, U_LEASING_ADMIN, U_CONFIRM_UPLOAD = range(19, 22)
# [NEW] STATE KHUSUS BUKTI BAYAR
WAIT_BUKTI = 26

REJECT_REASON = 22
ADMIN_ACT_REASON = 23
SUPPORT_MSG = 24
VAL_REJECT_REASON = 25


# ##############################################################################
# BAGIAN 4: FUNGSI HELPER UTAMA
# ##############################################################################

async def post_init(application: Application):
    await application.bot.set_my_commands([
        ("start", "🔄 Restart / Menu"),
        ("cekkuota", "💳 Cek Masa Aktif"),
        ("stop", "⛔ Stop Proses Upload"),
        ("infobayar", "💰 Perpanjang Langganan"),
        ("tambah", "➕ Input Manual"),
        ("lapor", "🗑️ Lapor Unit Selesai"),
        ("register", "📝 Daftar Mitra"),
        ("admin", "📩 Hubungi Admin"),
        ("panduan", "📖 Buku Panduan"),
        ("bagikan", "🚀 Bagikan Bot"), # <--- Tambahkan Baris Ini
        ("dashboard", "🏢 Buka Command Center"), # <--- TAMBAHAN BARU
        ("reset_dashboard", "🔒 Reset Sesi Dashboard") # <--- TAMBAHAN BARU
    ])
    print("✅ [INIT] Command List Updated!")

def get_user(user_id):
    try:
        response = supabase.table('users').select("*").eq('user_id', user_id).execute()
        return response.data[0] if response.data else None
    except: return None

def catat_audit(user_id, action, details="-"):
    """
    Fungsi Audit Trail B-One Enterprise.
    Menarik data identitas legal (Email & No HP) dari tabel users 
    dan mencatatnya ke audit_logs sesuai kepatuhan UU PDP.
    """
    try:
        # 1. Ambil data profil terbaru dari fungsi di atas
        u = get_user(user_id)
        if not u:
            return

        # 2. Pemetaan kolom sesuai struktur tabel users & audit_logs yang diselaraskan
        payload = {
            "user_id": user_id,
            "nama_lengkap": u.get('nama_lengkap', 'Unknown'),
            "no_hp": u.get('no_hp', '-'),
            "email": u.get('email', '-'),
            "role": u.get('role', 'matel'),
            "agency_leasing": u.get('agency', '-'), # Kolom agency berisi nama Leasing/PT
            "wilayah": u.get('wilayah_korlap', '-'), # Wilayah otoritas
            "action": action,
            "details": details,
            "bot_version": "6.70"
        }

        # 3. Eksekusi simpan ke tabel audit_logs
        supabase.table('audit_logs').insert(payload).execute()
        
    except Exception as e:
        logger.error(f"❌ Error pada sistem audit: {e}")

# --- FUNGSI HELPER BARU (PASTIKAN ADA DI ATAS) ---
def get_korlaps_by_agency(agency_name):
    """Mencari list ID Korlap berdasarkan nama Agency (Case Insensitive)"""
    try:
        # Cari Korlap yang nama agency-nya mengandung kata kunci yang diinput
        # Contoh: Input "Elang", akan nemu Korlap "PT Elang Perkasa"
        res = supabase.table('users').select("user_id, nama_lengkap").eq('role', 'korlap').ilike('agency', f"%{agency_name}%").execute()
        return res.data 
    except Exception as e:
        logger.error(f"Error finding Korlap: {e}")
        return []
    
# ==============================================================================
# 🔥 [SISIPKAN FITUR BARU DI SINI] SMART TYPO DETECTION (AUTO-CORRECT AGENCY)
# ==============================================================================
def find_best_match_agency(user_input):
    """
    Logika Fuzzy: Mencari nama Agency Korlap yang paling mirip dengan ketikan user.
    Contoh: User ketik "PTMITRASYADARMA" -> Hasil: "PT MITRA RASYA DARMA"
    """
    try:
        # 1. Ambil semua User Korlap untuk dijadikan "Kamus Kata"
        response = supabase.table('users').select('agency').eq('role', 'korlap').execute()
        
        if not response.data: return None 
            
        # 2. List Unik Agency (Uppercase & Bersih)
        valid_agencies = list(set([item['agency'].upper().strip() for item in response.data if item.get('agency')]))
        
        # 3. Bersihkan Input User
        clean_input = user_input.upper().replace('.', ' ').replace(',', ' ').strip()
        clean_input = " ".join(clean_input.split()) 
        
        # 4. Cari Kemiripan (Cutoff 0.5 = 50% mirip sudah dianggap ketemu)
        matches = difflib.get_close_matches(clean_input, valid_agencies, n=1, cutoff=0.5)
        
        if matches:
            return matches[0] # Kembalikan nama yang BENAR
        else:
            return None
            
    except Exception as e:
        print(f"Error Smart Detect: {e}")
        return None
# ==============================================================================

def update_user_status(user_id, status):
    try:
        supabase.table('users').update({'status': status}).eq('user_id', user_id).execute()
        return True
    except: return False

def check_subscription_access(user):
    try:
        if user.get('role') == 'pic': return True, "OK"

        expiry_str = user.get('expiry_date')
        if not expiry_str: return False, "EXPIRED"
        
        expiry_dt = datetime.fromisoformat(expiry_str.replace('Z', '+00:00')).astimezone(TZ_JAKARTA)
        now_dt = datetime.now(TZ_JAKARTA)
        
        if now_dt > expiry_dt: return False, "EXPIRED"

        last_usage_str = user.get('last_usage_date')
        today_str = now_dt.strftime('%Y-%m-%d')
        daily_usage = user.get('daily_usage', 0)

        if last_usage_str != today_str:
            supabase.table('users').update({'daily_usage': 0, 'last_usage_date': today_str}).eq('user_id', user['user_id']).execute()
            daily_usage = 0
        
        limit = DAILY_LIMIT_KORLAP if user.get('role') == 'korlap' else DAILY_LIMIT_MATEL
        if daily_usage >= limit: return False, "DAILY_LIMIT"

        return True, "OK"
    except Exception as e:
        print(f"Sub Check Error: {e}")
        return False, "ERROR"

def increment_daily_usage(user_id, current_usage):
    try:
        # Ambil waktu sekarang format ISO lengkap (Jam:Menit:Detik)
        now_iso = datetime.now(TZ_JAKARTA).isoformat()
        
        # Update daily usage DAN last_seen
        supabase.table('users').update({
            'daily_usage': current_usage + 1,
            'last_seen': now_iso  # <--- INI KUNCINYA
        }).eq('user_id', user_id).execute()
    except: pass

def add_subscription_days(user_id, days_to_add):
    try:
        user = get_user(user_id)
        if not user: return False, None
        
        now = datetime.now(TZ_JAKARTA)
        current_expiry_str = user.get('expiry_date')
        
        if current_expiry_str:
            current_expiry = datetime.fromisoformat(current_expiry_str.replace('Z', '+00:00')).astimezone(TZ_JAKARTA)
            if current_expiry > now:
                new_expiry = current_expiry + timedelta(days=days_to_add)
            else:
                new_expiry = now + timedelta(days=days_to_add)
        else:
            new_expiry = now + timedelta(days=days_to_add)
            
        supabase.table('users').update({'expiry_date': new_expiry.isoformat()}).eq('user_id', user_id).execute()
        return True, new_expiry
    except Exception as e:
        print(f"Topup Error: {e}")
        return False, None

def clean_text(text):
    # Cek explisit None atau string kosong, tapi biarkan angka 0 lewat
    if text is None or str(text).strip() == "": return "-"
    return html.escape(str(text))

def format_wa_link(phone_number):
    """Mengubah format HP 08xx jadi Link WA."""
    if not phone_number: return "-"
    clean_hp = re.sub(r'[^0-9]', '', str(phone_number))
    if clean_hp.startswith('0'): 
        clean_hp = '62' + clean_hp[1:]
    return f'<a href="https://wa.me/{clean_hp}">{phone_number}</a>'

def standardize_leasing_name(raw_name):
    """
    Kamus Cerdas Standarisasi Nama Leasing Indonesia (V3.0 - FINAL COMPLETE).
    Mendeteksi Nama PT Panjang -> Mengubah ke Label Singkatan Resmi.
    """
    if not raw_name: return "UNKNOWN"
    
    text = str(raw_name).upper().strip()
    
    # DICTIONARY: "KATA KUNCI (NAMA PT)": "LABEL STANDAR (SINGKATAN)"
    keywords = {
        # === 1. GROUP JTRUST & OLYMPINDO ===
        "JTRUST INVESTMENT": "JTII",
        "J TRUST INVESTMENT": "JTII",
        "JTRUST OLYMPINDO": "JTO FINANCE",
        "OLYMPINDO": "JTO FINANCE",
        "JTO": "JTO FINANCE",
        
        # === 2. GROUP ASTRA & ANAK USAHA ===
        "FEDERAL INTERNATIONAL": "FIF GROUP",
        "FIF": "FIF GROUP",
        "SPEKTRA": "FIF GROUP",
        "ASTRA SEDAYA": "ACC",
        "ACC": "ACC",
        "TOYOTA ASTRA": "TAF",
        "TAF": "TAF",
        "ASTRA MULTI": "AMF",
        "KOMATSU": "KOMATSU",
        "SAN FINANCE": "SANF",
        "SURYA ARTHA": "SANF",
        
        # === 3. GROUP BANK & BUMN ===
        "BCA FINANCE": "BCA FINANCE",
        "CSUL": "CSUL FINANCE", # Ciptadana
        "MANDIRI TUNAS": "MTF",
        "MANDIRI UTAMA": "MUF",
        "CIMB NIAGA": "CNAF",
        "CNAF": "CNAF",
        "BNI MULTI": "BNI MULTIFINANCE",
        "BRI FINANCE": "BRI FINANCE",
        "BRI MULTI": "BRI FINANCE",
        "BSI OTO": "BSI OTO",
        "SYARIAH INDONESIA": "BSI OTO",
        "MNC FINANCE": "MNC FINANCE",
        "MNC GUNA": "MNC FINANCE",
        "MEGA FINANCE": "MEGA FINANCE",
        "MEGA AUTO": "MACF",
        "MEGA CENTRAL": "MACF",
        "KB BUKOPIN": "BUKOPIN",
        "BUKOPIN": "BUKOPIN",
        
        # === 4. GROUP SWASTA BESAR (MAJOR PLAYERS) ===
        "ADIRA": "ADIRA",
        "BUSSAN AUTO": "BAF",
        "BAF": "BAF",
        "YAMAHA": "BAF", # Sering disebut Yamaha Finance
        "WAHANA OTTOMITRA": "WOM FINANCE",
        "WOM": "WOM FINANCE",
        "BFI": "BFI FINANCE",
        "SUMMIT OTO": "OTO/SUMMIT",
        "OTO MULTI": "OTO/SUMMIT",
        "CLIPAN": "CLIPAN",
        "SINAR MAS": "SINARMAS",
        "SINARMAS": "SINARMAS",
        "SIMAS": "SINARMAS",
        "MANDALA": "MANDALA FINANCE", # [BARU] Wajib ada
        
        # === 5. DEALER & BRAND AFFILIATED ===
        "SUZUKI": "SFI",
        "SFI": "SFI",
        "INDOMOBIL": "IMFI",
        "IMFI": "IMFI",
        "DIPO STAR": "DIPO STAR",
        "MITSUBISHI": "DIPO STAR",
        "HINO": "HINO FINANCE",
        "CHAILEASE": "CHAILEASE",
        "WULING": "WULING FINANCE", # [BARU]
        
        # === 6. CONSUMER & FINTECH (SERING ADA MOTOR) ===
        "HOME CREDIT": "HCI",
        "HCI": "HCI",
        "AEON": "AEON CREDIT",
        "KREDIVO": "KREDIVO",
        "AKULAKU": "AKULAKU",

        # === 7. MULTIFINANCE LAINNYA (A-Z) ===
        "AL IJARAH": "AL IJARAH",
        "ANDALAN": "ANDALAN FINANCE",
        "ARTHA PRIMA": "ARTHA PRIMA",
        "ARTHAASIA": "ARTHAASIA", # [BARU]
        "BATAVIA": "BATAVIA PROSPERINDO",
        "BENTARA": "BESS FINANCE",
        "BESS": "BESS FINANCE",
        "BIMA MULTI": "BIMA FINANCE",
        "BUANA": "BUANA FINANCE",
        "CAPITAL": "CAPITAL",
        "CLEMENT": "CLEMENT", # Ejaan yang benar Clement
        "CLEMONT": "CLEMENT",
        "COLUMBIA": "COLUMBIA",
        "DANASUPRA": "DANASUPRA",
        "ESTA DANA": "ESTA DANA",
        "FINANSIA": "KREDIT PLUS",
        "KREDIT PLUS": "KREDIT PLUS",
        "KPLUS": "KREDIT PLUS",
        "GLOBALINDO": "GLOBAL FINANCE",
        "HEXA": "HEXA",
        "INTAN BARU": "IBF",
        "IBF": "IBF",
        "INTRA ASIA": "INTRA ASIA",
        "ISTANA": "ISTANA", # IMG
        "KEMBANG 88": "KEMBANG 88",
        "KRESNA": "KRESNA REKSA",
        "MAYBANK": "MAYBANK FINANCE",
        "MITSUI": "MITSUI LEASING",
        "MULTI INDO": "MULTI INDO",
        "NUSA SURYA": "NSC FINANCE",
        "NSC": "NSC FINANCE",
        "ORICO": "ORICO BALIMOR", # [BARU] Ex Mizuho
        "BALIMOR": "ORICO BALIMOR",
        "PRO CAR": "PRO CAR",
        "PRO MITRA": "PRO CAR",
        "RADANA": "RADANA",
        "REKSA": "REKSA FINANCE",
        "RESURSA": "RESURSA",
        "SMS": "SMS FINANCE",
        "SINAR MITRA": "SMS FINANCE",
        "SMART MULTI": "SMART FINANCE",
        "SMART FINANCE": "SMART FINANCE",
        "SUNINDO": "SUNINDO",
        "SWADHARMA": "SWADHARMA",
        "TIFA": "TIFA",
        "TOPAZ": "TOPAZ", # [BARU]
        "TRUST": "TRUST FINANCE",
        "VERENA": "VERENA",
        "WOKA": "WOKA FINANCE"
    }

    # LOGIKA PENCARIAN
    # Kita cari string input user di dalam key dictionary
    for key, label in keywords.items():
        if key in text:
            return label

    # Jika nama PT sangat asing dan tidak ada di kamus,
    # Kembalikan nama aslinya (Upper Case) agar admin sadar ada leasing baru
    return text

# [CRITICAL UPDATE] LOGIC PENCATATAN LOG DIUBAH MENERIMA USER OBJECT
def log_successful_hit(user_db, unit_data):
    try:
        leasing_raw = str(unit_data.get('finance', 'UNKNOWN')).upper().strip()
        nopol_val = unit_data.get('nopol', '-')
        unit_val = unit_data.get('type', '-')

        # Ambil data dari object user_db yang sudah dipassing
        user_id = user_db.get('user_id')
        user_name = user_db.get('nama_lengkap', 'Unknown')
        user_hp = user_db.get('no_hp', '-')
        user_agency = user_db.get('agency', '-')

        payload = {
            "leasing": leasing_raw,
            "nopol": nopol_val,
            "unit": unit_val,
            "user_id": user_id,
            "nama_matel": user_name,
            "no_hp": user_hp,      # SEKARANG TERISI
            "nama_pt": user_agency # SEKARANG TERISI
        }
        supabase.table('finding_logs').insert(payload).execute()
        
    except Exception as e:
        print(f"⚠️ Gagal menyimpan log ke database: {e}")

# ##############################################################################
# BAGIAN 5: ENGINE FILE
# ##############################################################################

def normalize_text(text):
    if not isinstance(text, str): return str(text).lower()
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()

def fix_header_position(df):
    target = COLUMN_ALIASES['nopol']
    for i in range(min(30, len(df))): 
        vals = [normalize_text(str(x)) for x in df.iloc[i].values]
        if any(alias in vals for alias in target):
            df.columns = df.iloc[i] 
            df = df.iloc[i+1:].reset_index(drop=True) 
            return df
    return df

def smart_rename_columns(df):
    new_cols = {}
    found_std = set()
    
    # 1. Bersihkan nama kolom dari spasi, tanda kutip, dan karakter aneh
    df.columns = [str(c).strip().replace('"', '').replace("'", "").lower() for c in df.columns]
    
    for col in df.columns:
        renamed = False
        # Hilangkan karakter non-alfanumerik untuk pencocokan alias
        clean_col = re.sub(r'[^a-z0-9]', '', col)
        
        for std_name, aliases in COLUMN_ALIASES.items():
            # Jika kolom ini adalah standar atau ada di daftar alias, dan belum ditemukan sebelumnya
            if (clean_col == std_name or clean_col in aliases) and std_name not in found_std:
                new_cols[col] = std_name
                found_std.add(std_name)
                renamed = True
                break
        
        if not renamed:
            new_cols[col] = col
            
    df.rename(columns=new_cols, inplace=True)
    return df, list(found_std)

def read_file_robust(content, fname):
    """
    Versi INTELLIGENT: 
    Otomatis mencari separator yang benar (Koma atau Titik Koma)
    agar tidak gagal baca kolom.
    """
    fname = fname.lower()
    
    # 1. Cek ZIP
    if fname.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            valid = [f for f in z.namelist() if f.endswith(('.csv','.xlsx','.xls'))]
            if not valid: raise ValueError("ZIP Kosong")
            with z.open(valid[0]) as f: 
                content = f.read()
                fname = valid[0].lower()
    
    # 2. Cek EXCEL (.xlsx / .xls)
    if fname.endswith(('.xlsx', '.xls')):
        try: return pd.read_excel(io.BytesIO(content), dtype=str)
        except Exception as e: raise ValueError(f"Gagal baca Excel: {e}")

    # 3. Cek CSV (SMART SEPARATOR DETECTION)
    # Kita coba berbagai kemungkinan separator
    separators = [';', ',', '\t', '|']
    
    # Percobaan 1: Encoding UTF-8 (Standar)
    for sep in separators:
        try:
            df = pd.read_csv(io.BytesIO(content), sep=sep, dtype=str, on_bad_lines='skip', encoding='utf-8')
            # [LOGIKA PINTAR] Jika kolom terdeteksi lebih dari 1, berarti separator BENAR!
            if len(df.columns) > 1: 
                print(f"✅ CSV Terbaca dengan separator: '{sep}'")
                return df
        except: continue

    # Percobaan 2: Encoding Latin-1 (Jika file jadul/Windows lama)
    for sep in separators:
        try:
            df = pd.read_csv(io.BytesIO(content), sep=sep, dtype=str, on_bad_lines='skip', encoding='latin1')
            if len(df.columns) > 1: 
                print(f"✅ CSV (Latin1) Terbaca dengan separator: '{sep}'")
                return df
        except: continue

    # Jika semua gagal, coba paksa baca koma sebagai fallback terakhir
    try:
        return pd.read_csv(io.BytesIO(content), sep=',', dtype=str, on_bad_lines='skip', encoding='utf-8')
    except:
        raise ValueError("Format file tidak dikenali. Pastikan Excel atau CSV yang valid.")


# ##############################################################################
# BAGIAN 6: FITUR ADMIN - ACTION
# ##############################################################################

async def angkat_korlap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        if len(context.args) < 2:
            return await update.message.reply_text("⚠️ Format: `/angkat_korlap [ID] [KOTA]`", parse_mode='Markdown')
        target_id = int(context.args[0]); wilayah = " ".join(context.args[1:]).upper()
        data = {"role": "korlap", "wilayah_korlap": wilayah, "quota": 5000} 
        supabase.table('users').update(data).eq('user_id', target_id).execute()
        await update.message.reply_text(f"✅ **SUKSES!**\nUser ID `{target_id}` sekarang adalah **KORLAP {wilayah}**.\nLimit Harian: 2000 Cek.", parse_mode='Markdown')
    except Exception as e: await update.message.reply_text(f"❌ Gagal: {e}")

async def reject_start(update, context):
    query = update.callback_query; await query.answer()
    context.user_data['reg_msg_id'] = query.message.message_id
    context.user_data['reg_chat_id'] = query.message.chat_id
    context.user_data['reject_target_uid'] = query.data.split("_")[1]
    await context.bot.send_message(chat_id=update.effective_chat.id, text="📝 Ketik **ALASAN** Penolakan:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True))
    return REJECT_REASON

async def reject_complete(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    target_uid = context.user_data.get('reject_target_uid'); reason = update.message.text
    try: supabase.table('users').delete().eq('user_id', target_uid).execute()
    except: pass
    try: 
        msg_user = (f"⛔ **PENDAFTARAN DITOLAK**\n\n⚠️ <b>Alasan:</b> {reason}\n\n<i>Data Anda telah dihapus. Silakan lakukan registrasi ulang dengan data yang benar via /register</i>")
        await context.bot.send_message(target_uid, msg_user, parse_mode='HTML')
    except: pass
    try:
        mid = context.user_data.get('reg_msg_id'); cid = context.user_data.get('reg_chat_id')
        await context.bot.edit_message_reply_markup(chat_id=cid, message_id=mid, reply_markup=None)
        await context.bot.send_message(chat_id=cid, text=f"❌ User {target_uid} berhasil DITOLAK & DIHAPUS.\nAlasan: {reason}")
    except: pass
    await update.message.reply_text("✅ Proses Selesai.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

async def val_reject_start(update, context):
    query = update.callback_query; await query.answer()
    data = query.data.split("_")
    context.user_data['val_rej_nopol'] = data[2]
    context.user_data['val_rej_uid'] = data[3]
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"❌ **TOLAK PENGAJUAN**\nUnit: {data[2]}\n\nKetik ALASAN Penolakan:",
        reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
    )
    return VAL_REJECT_REASON

async def val_reject_complete(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    nopol = context.user_data.get('val_rej_nopol')
    uid = context.user_data.get('val_rej_uid')
    reason = update.message.text
    try:
        msg = (f"⛔ **PENGAJUAN DITOLAK**\nUnit: {nopol}\n⚠️ <b>Alasan:</b> {reason}\n\nSilakan perbaiki data dan ajukan ulang jika perlu.")
        await context.bot.send_message(chat_id=int(uid), text=msg, parse_mode='HTML')
    except Exception as e: logger.error(f"Gagal kirim notif tolak: {e}")
    await update.message.reply_text(f"✅ Notifikasi penolakan dikirim ke User.\nAlasan: {reason}", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def admin_action_start(update, context):
    query = update.callback_query; await query.answer()
    parts = query.data.split("_"); context.user_data['adm_act_type'] = parts[1]; context.user_data['adm_act_uid'] = parts[2]
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🛡️ **ACTION: {parts[1].upper()}**\nKetik ALASAN:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True))
    return ADMIN_ACT_REASON

async def admin_action_complete(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    act = context.user_data.get('adm_act_type'); uid = context.user_data.get('adm_act_uid'); reason = update.message.text
    if act == "ban": update_user_status(uid, 'rejected'); msg = f"⛔ **BANNED**\nAlasan: {reason}"
    elif act == "unban": update_user_status(uid, 'active'); msg = f"✅ **UNBANNED**\nCatatan: {reason}"
    elif act == "del": supabase.table('users').delete().eq('user_id', uid).execute(); msg = f"🗑️ **DELETED**\nAlasan: {reason}"
    try: await context.bot.send_message(uid, msg)
    except: pass
    await update.message.reply_text(f"✅ Action {act} Sukses.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END


# ##############################################################################
# BAGIAN 7: FITUR ADMIN - USER MANAGER & ANALYTICS
# ##############################################################################

async def admin_help(update, context):
    # Menggunakan ADMIN_IDS (List) agar konsisten dengan perbaikan error sebelumnya
    if str(update.effective_user.id) not in ADMIN_IDS: return

    msg = (
        "🔐 **ADMIN COMMANDS v6.31**\n\n"
        
        "📊 **ANALYTICS & AUDIT (NEW)**\n"
        "• `/rekap` (Global Summary Hari Ini)\n"
        "• `/rekap [Leasing]` (Audit Leasing. Cth: `/rekap BCA`)\n"
        "• `/cekagency [PT]` (Audit Mitra. Cth: `/cekagency ELANG`) 🆕\n"
        "• `/stats` (Total Database Unit)\n"
        "• `/leasing` (Ranking Jumlah Data per Leasing)\n\n"

        "📢 **INFO & PENGUMUMAN**\n"
        "• `/setinfo [Pesan]` (Pasang Banner Info)\n"
        "• `/delinfo` (Hapus Banner Info)\n\n"

        "👮‍♂️ **ROLE & AGENCY**\n"
        "• `/angkat_korlap [ID] [KOTA]`\n"
        "• `/addagency [NAMA_PT]` (Tambah Database Agency)\n"
        "• `/rekap_member` (Cek Registrasi Member Baru)\n\n"

        "🏢 **SETUP GROUP NOTIFIKASI**\n"
        "• `/setgroup [NAMA_LEASING]` (Set Group Leasing)\n"
        "• `/setagency [NAMA_PT]` (Set Group Agency/Korlap)\n"
        "• `/testgroup` (Tes Koneksi Bot ke Group)\n\n"

        "👥 **USER MANAGEMENT**\n"
        "• `/users` (List User Aktif)\n"
        "• `/m_ID` (Edit User via ID. Cth: `/m_12345`)\n"
        "• `/topup [ID] [HARI]` (Tambah Masa Aktif)\n"
        "• `/balas [ID] [MSG]` (Balas Chat User)\n\n"

        "⚙️ **SYSTEM & DATA**\n"
        "• `/stop` (Emergency Stop Upload)\n"
        "• `/hapus` (Hapus Unit Manual)\n"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def rekap_harian(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    msg = await update.message.reply_text("⏳ **Sedang menghitung data MURNI MATEL hari ini...**", parse_mode='Markdown')
    
    try:
        now = datetime.now(TZ_JAKARTA)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Tarik data (Data di finding_logs otomatis sudah terfilter bersih)
        res = supabase.table('finding_logs').select("leasing").gte('created_at', start_of_day.isoformat()).execute()
        data = res.data
        
        if not data:
            return await msg.edit_text("📊 **REKAP HARIAN (MURNI LAPANGAN)**\n\nBelum ada unit ditemukan (HIT) hari ini.")

        counts = Counter([d['leasing'] for d in data])
        total_hits = len(data)
        
        report = (
            f"📊 **REKAP TEMUAN (HIT) HARI INI**\n"
            f"📅 Tanggal: {now.strftime('%d %b %Y')}\n"
            f"🔥 **Total Unit Ketemu:** {total_hits} Unit\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
        
        for leasing, jumlah in counts.most_common():
            if leasing in ["-", "UNKNOWN", "NAN"]: leasing = "LAIN-LAIN"
            report += f"🔹 **{leasing}:** {jumlah} Unit\n"
            
        report += "━━━━━━━━━━━━━━━━━━\n#OneAspalAnalytics (Clean Data)"
        
        await msg.edit_text(report, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Rekap Error: {e}")
        await msg.edit_text(f"❌ Gagal menarik data rekap: {e}")

# ==============================================================================
# HELPER: PEMBERSIH NAMA PT (Agar "PT. ABC" match dengan "ABC")
# ==============================================================================
def clean_pt_name(text):
    if not text: return ""
    # Hapus PT, CV, titik, dan spasi berlebih
    text = str(text).upper().replace("PT.", "").replace("PT ", "").replace("CV.", "").replace("CV ", "")
    return text.strip()

# ==============================================================================
# BAGIAN 11: REKAP ENGINE & CEK AGENCY (FIXED)
# ==============================================================================

async def rekap_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    
    # 1. CEK OTORITAS
    # Hanya Admin, Superadmin, Korlap, dan PIC yang boleh akses
    if not u or u.get('role') not in ['admin', 'superadmin', 'korlap', 'pic']:
        return 
    
    role = u.get('role')
    my_agency = str(u.get('agency', '')).upper().strip()
    
    # 2. PARSING KEYWORD
    # Support format: "/rekap" atau "/rekapBCA" atau "/cekagency ELANG"
    full_text = update.message.text.strip()
    if " " in full_text:
        keyword = full_text.split(" ", 1)[1].upper().strip()
    else:
        command = full_text.split()[0] 
        base_cmd = "/cekagency" if "/cekagency" in command.lower() else "/rekap"
        keyword = command.lower().replace(base_cmd, "").upper().strip()

    status_msg = await update.message.reply_text(f"⏳ **Sedang mengaudit data...**", parse_mode='Markdown')

    try:
        # 3. TARIK DATA HARIAN (DATABASE)
        now = datetime.now(TZ_JAKARTA)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Ambil semua log temuan hari ini
        res = supabase.table('finding_logs').select("*").gte('created_at', start_of_day.isoformat()).execute()
        all_logs = res.data
        
        if not all_logs:
            return await status_msg.edit_text(f"📊 **REKAP HARIAN**\n\nNihil. Belum ada unit ditemukan hari ini (Global).")

        # 4. LOGIKA FILTERING (SESUAI JABATAN)
        target_data = []
        header_context = "GLOBAL"
        mode_tampilan = "SUMMARY"

        # --- A. LOGIKA ADMIN (Bisa lihat semua) ---
        if role in ['admin', 'superadmin']:
            if not keyword: 
                target_data = all_logs
                header_context = "GLOBAL (ADMIN)"
            else:
                target_data = []
                keyword_clean = clean_pt_name(keyword)
                for l in all_logs:
                    l_leasing = str(l.get('leasing','')).upper()
                    l_pt = clean_pt_name(l.get('nama_pt',''))
                    if keyword_clean in l_leasing or keyword_clean in l_pt:
                        target_data.append(l)
                mode_tampilan = "DETAIL"
                header_context = f"SEARCH: {keyword}"

        # --- B. LOGIKA PIC LEASING (Hanya lihat leasing sendiri) ---
        elif role == 'pic':
            my_leasing_std = standardize_leasing_name(my_agency)
            # Filter hanya data milik leasing dia
            target_data = [l for l in all_logs if my_leasing_std in str(l.get('leasing','')).upper()]
            
            header_context = f"INTERNAL {my_leasing_std}"
            mode_tampilan = "DETAIL" # PIC Selalu melihat detail

        # --- C. LOGIKA KORLAP (Hanya lihat tim sendiri) ---
        elif role == 'korlap':
            my_agency_clean = clean_pt_name(my_agency)
            if not keyword:
                target_data = []
                for l in all_logs:
                    log_pt_clean = clean_pt_name(l.get('nama_pt',''))
                    # Match nama PT (Flexible)
                    if my_agency_clean in log_pt_clean or log_pt_clean in my_agency_clean:
                        target_data.append(l)
                header_context = f"AGENCY {my_agency}"
            else:
                # Filter tim sendiri + leasing tertentu
                target_data = []
                for l in all_logs:
                    log_pt_clean = clean_pt_name(l.get('nama_pt',''))
                    log_leasing = str(l.get('leasing','')).upper()
                    if (my_agency_clean in log_pt_clean or log_pt_clean in my_agency_clean) and (keyword in log_leasing):
                        target_data.append(l)
                mode_tampilan = "DETAIL"
                header_context = f"{my_agency} ({keyword})"

        # 5. RENDER TAMPILAN (FORMAT LENGKAP)
        if not target_data:
             return await status_msg.edit_text(f"🔍 **HASIL PENCARIAN KOSONG**\n\nKonteks: {header_context}\nKeyword: {keyword}\n\n_Tidak ada data yang cocok hari ini._", parse_mode='Markdown')

        # === TAMPILAN DETAIL (BERLAKU UNTUK ADMIN, PIC, DAN KORLAP) ===
        if mode_tampilan == "DETAIL":
            rpt = (
                f"📋 **RINCIAN TEMUAN HARIAN**\n"
                f"🔍 **Filter:** {header_context}\n"
                f"📅 **Tanggal:** {now.strftime('%d %b %Y')}\n"
                f"🔥 **Total:** {len(target_data)} Unit\n"
                f"━━━━━━━━━━━━━━━━━━\n"
            )
            body = ""
            for i, d in enumerate(target_data):
                nopol = d.get('nopol', '-')
                unit = d.get('unit', '-')
                matel = d.get('nama_matel', 'Anonim')
                leasing_lbl = d.get('leasing', '-')
                pt_lbl = d.get('nama_pt', '-')
                
                # --- FORMAT BARIS LENGKAP (ADMIN/PIC/KORLAP SAMA) ---
                # Baris 1: Nomor Urut | Plat Nomor | Nama Unit
                row = f"{i+1}. **{nopol}** | {unit}\n"
                # Baris 2: Nama Matel | Nama PT/Agency | Nama Leasing
                row += f"   👤 {matel} | 🏢 {pt_lbl} | 🏦 {leasing_lbl}\n"
                # ----------------------------------------------------
                
                if len(rpt + body + row) > 3800:
                    body += "\n...(Data terpotong, terlalu banyak)..."
                    break
                body += row
            
            await status_msg.edit_text(rpt + body, parse_mode='Markdown')

        else:
            # TAMPILAN SUMMARY (HANYA MUNCUL JIKA ADMIN KETIK /REKAP TANPA KEYWORD)
            stats = {}
            for x in target_data:
                k = x.get('leasing', 'UNKNOWN')
                stats[k] = stats.get(k, 0) + 1
            sorted_stats = sorted(stats.items(), key=lambda item: item[1], reverse=True)
            
            rpt = (
                f"📊 **REKAP STATISTIK HARIAN**\n"
                f"🏢 **Level:** {header_context}\n"
                f"📅 **Tanggal:** {now.strftime('%d %b %Y')}\n"
                f"🔥 **TOTAL GLOBAL:** {len(target_data)} Unit\n"
                f"━━━━━━━━━━━━━━━━━━\n"
            )
            for k, count in sorted_stats:
                rpt += f"🔹 **{k}:** {count} Unit\n"
            
            rpt += "\n💡 *Gunakan /cekagency [Nama PT] untuk detail.*"
            await status_msg.edit_text(rpt, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Master Rekap Error: {e}")
        await status_msg.edit_text(f"❌ Terjadi kesalahan sistem: {e}")

# Agar /cekagency juga jalan, kita arahkan ke handler yang sama
async def cek_agency_redirect(update, context):
    await rekap_handler(update, context)

async def list_users(update, context):
    if update.effective_user.id != ADMIN_ID: return
    
    await context.bot.send_chat_action(update.effective_chat.id, constants.ChatAction.TYPING)
    
    try:
        res = supabase.table('users').select("*").execute()
        active_list = [u for u in res.data if u.get('status') == 'active']
        pic_list = [u for u in active_list if u.get('role') == 'pic']
        field_list = [u for u in active_list if u.get('role') != 'pic'] 
        
        pic_list.sort(key=lambda x: (x.get('nama_lengkap') or "").lower())
        field_list.sort(key=lambda x: (x.get('nama_lengkap') or "").lower())
        
        if not active_list: 
            return await update.message.reply_text("📂 Tidak ada mitra aktif.")
        
        msg = f"📋 <b>DAFTAR MITRA (Total: {len(active_list)})</b>\n━━━━━━━━━━━━━━━━━━\n"
        now = datetime.now(TZ_JAKARTA)
        no_preview = LinkPreviewOptions(is_disabled=True)

        if pic_list:
            msg += "🏦 <b>INTERNAL LEASING (PIC)</b>\n"
            for i, u in enumerate(pic_list, 1):
                nama = clean_text(u.get('nama_lengkap'))
                agency = clean_text(u.get('agency'))
                uid = u['user_id']
                wa_link = format_wa_link(u.get('no_hp'))
                entry = (f"{i}. 🤝 <b>{nama}</b>\n   📱 {wa_link} | 🏢 {agency}\n   ⚙️ /m_{uid}\n\n")
                if len(msg) + len(entry) > 4000: 
                    await update.message.reply_text(msg, parse_mode='HTML', link_preview_options=no_preview)
                    msg = ""
                msg += entry
            msg += "━━━━━━━━━━━━━━━━━━\n"

        if field_list:
            msg += "🛡️ <b>MITRA LAPANGAN</b>\n"
            for i, u in enumerate(field_list, 1):
                role = u.get('role', 'matel')
                icon = "🎖️" if role == 'korlap' else "🛡️"
                exp_str = u.get('expiry_date')
                if exp_str:
                    exp_dt = datetime.fromisoformat(exp_str.replace('Z', '+00:00')).astimezone(TZ_JAKARTA)
                    delta = exp_dt - now
                    days_left_str = "❌ EXP" if delta.days < 0 else f"⏳ {delta.days} Hari"
                else: days_left_str = "❌ NULL"
                nama = clean_text(u.get('nama_lengkap'))
                agency = clean_text(u.get('agency'))
                uid = u['user_id']
                wa_link = format_wa_link(u.get('no_hp'))
                entry = (f"{i}. {icon} <b>{nama}</b>\n   {days_left_str} | 🏢 {agency}\n   📱 {wa_link} | ⚙️ /m_{uid}\n\n")
                if len(msg) + len(entry) > 4000: 
                    await update.message.reply_text(msg, parse_mode='HTML', link_preview_options=no_preview)
                    msg = ""
                msg += entry
        if msg: 
            await update.message.reply_text(msg, parse_mode='HTML', link_preview_options=no_preview)
    except Exception as e: 
        await update.message.reply_text(f"❌ Error: {e}")

async def manage_user_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid = int(update.message.text.split('_')[1])
        u = get_user(tid)
        if not u: return await update.message.reply_text("❌ User tidak ditemukan.")
        role_now = u.get('role', 'matel')
        status_now = u.get('status', 'active')
        info_role = "🎖️ KORLAP" if role_now == 'korlap' else f"🛡️ {role_now.upper()}"
        wilayah = f"({u.get('wilayah_korlap', '-')})" if role_now == 'korlap' else ""
        icon_status = "✅ AKTIF" if status_now == 'active' else "⛔ BANNED"
        expiry = u.get('expiry_date', 'EXPIRED')
        if expiry != 'EXPIRED': expiry = datetime.fromisoformat(expiry.replace('Z', '+00:00')).astimezone(TZ_JAKARTA).strftime('%d %b %Y')
        wa_link = format_wa_link(u.get('no_hp'))
        msg = (f"👮‍♂️ <b>USER MANAGER</b>\n━━━━━━━━━━━━━━━━━━\n👤 <b>Nama:</b> {clean_text(u.get('nama_lengkap'))}\n📱 <b>WA:</b> {wa_link}\n🏅 <b>Role:</b> {info_role} {wilayah}\n📊 <b>Status:</b> {icon_status}\n📱 <b>ID:</b> <code>{tid}</code>\n📅 <b>Exp:</b> {expiry}\n🏢 <b>Agency:</b> {clean_text(u.get('agency'))}\n━━━━━━━━━━━━━━━━━━")
        btn_role = InlineKeyboardButton("⬇️ BERHENTIKAN KORLAP", callback_data=f"adm_demote_{tid}") if role_now == 'korlap' else InlineKeyboardButton("🎖️ ANGKAT KORLAP", callback_data=f"adm_promote_{tid}")
        btn_ban = InlineKeyboardButton("⛔ BAN USER", callback_data=f"adm_ban_{tid}") if status_now == 'active' else InlineKeyboardButton("✅ UNBAN (PULIHKAN)", callback_data=f"adm_unban_{tid}")
        kb = [[InlineKeyboardButton("📅 +5 Hari", callback_data=f"adm_topup_{tid}_5"), InlineKeyboardButton("📅 +30 Hari", callback_data=f"adm_topup_{tid}_30")], [btn_role], [btn_ban, InlineKeyboardButton("🗑️ HAPUS DATA", callback_data=f"adm_del_{tid}")], [InlineKeyboardButton("❌ TUTUP PANEL", callback_data="close_panel")]]
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML', link_preview_options=LinkPreviewOptions(is_disabled=True))
    except Exception as e: await update.message.reply_text(f"❌ Error Panel: {e}")

async def rekap_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Validasi Admin (Pastikan variable ini sesuai dengan config Anda: ADMIN_ID atau ADMIN_IDS)
    user_id = str(update.effective_user.id)
    # Cek akses (Support list ADMIN_IDS atau single ADMIN_ID)
    if 'ADMIN_IDS' in globals() and user_id not in ADMIN_IDS: return
    elif 'ADMIN_ID' in globals() and user_id != str(ADMIN_ID): return

    msg = await update.message.reply_text("⏳ <b>Sedang menarik data member...</b>", parse_mode='HTML')

    try:
        # 1. Ambil Waktu Sekarang
        now = datetime.now(TZ_JAKARTA)
        today_str = now.strftime('%Y-%m-%d')
        display_date = now.strftime('%d %B %Y')
        
        # 2. Hitung Register Hari Ini (Semua status)
        res_today = supabase.table('users').select('user_id', count='exact').gte('created_at', f"{today_str} 00:00:00").execute()
        count_today = res_today.count if res_today.count else 0

        # 3. Ambil Data Pending
        res_pending = supabase.table('users').select('*').eq('status', 'pending').execute()
        pending_users = res_pending.data
        count_pending = len(pending_users)

        # 4. Susun Laporan (PAKAI HTML TAGS: <b>, <i>)
        rpt = (
            f"📊 <b>REKAP MEMBER HARIAN</b>\n"
            f"📅 Tanggal: {display_date}\n\n"
            f"➕ <b>Daftar Hari Ini:</b> {count_today} Orang\n"
            f"⏳ <b>Pending Approval:</b> {count_pending} Orang\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )

        if count_pending > 0:
            rpt += "<b>ANTREAN REVIEW:</b>\n(Klik command utk validasi)\n\n"
            for u in pending_users:
                uid = u['user_id']
                # clean_text agar nama yg ada simbol aneh tidak bikin error
                raw_nama = u.get('nama_lengkap') or u.get('full_name') or 'Tanpa Nama'
                nama = clean_text(raw_nama) 
                
                # Command /cek_ID aman di mode HTML
                rpt += f"👉 /cek_{uid} | {nama}\n"
        else:
            rpt += "✅ <i>Tidak ada antrean pending.</i>"

        await msg.edit_text(rpt, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Rekap Error: {e}")
        # Fallback kalau error, kirim text polos aja biar ketahuan errornya apa
        await msg.edit_text(f"❌ Error: {str(e)}")

# ==============================================================================
# BAGIAN 8: FITUR AUDIT & ADMIN UTILS
# ==============================================================================

async def auto_cleanup_logs(context: ContextTypes.DEFAULT_TYPE):
    try:
        cutoff_date = datetime.now(TZ_JAKARTA) - timedelta(days=5)
        cutoff_str = cutoff_date.isoformat()
        supabase.table('finding_logs').delete().lt('created_at', cutoff_str).execute()
        print(f"🧹 [AUTO CLEANUP] Log lama (< {cutoff_date.strftime('%d-%b')}) berhasil dihapus.")
    except Exception as e:
        logger.error(f"❌ AUTO CLEANUP ERROR: {e}")

async def get_stats(update, context):
    if update.effective_user.id != ADMIN_ID: return
    try:
        t = supabase.table('kendaraan').select("*", count="exact", head=True).execute().count
        u = supabase.table('users').select("*", count="exact", head=True).execute().count
        k = supabase.table('users').select("*", count="exact", head=True).eq('role', 'korlap').execute().count
        await update.message.reply_text(f"📊 **STATS v6.0**\n📂 Data: `{t:,}`\n👥 Total User: `{u}`\n🎖️ Korlap: `{k}`", parse_mode='Markdown')
    except: pass

async def get_leasing_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = await update.message.reply_text("⏳ **Menghitung Statistik Data...**", parse_mode='Markdown')
    try:
        response = await asyncio.to_thread(lambda: supabase.rpc('get_leasing_summary').execute())
        data = response.data 
        if not data: return await msg.edit_text("❌ Database Kosong atau Fungsi SQL belum dipasang.")
        total_global = sum(item['total'] for item in data)
        rpt = (f"🏦 **AUDIT LEASING (LIVE)**\n📦 Total Data: `{total_global:,}` Unit\n━━━━━━━━━━━━━━━━━━\n")
        for item in data:
            k = str(item.get('finance', 'UNKNOWN')).upper()
            v = item.get('total', 0)
            if k not in ["UNKNOWN", "NONE", "NAN", "-", "", "NULL"]: 
                entry = f"🔹 **{k}:** `{v:,}`\n"
                if len(rpt) + len(entry) > 4000:
                    rpt += "\n...(dan leasing kecil lainnya)"
                    break 
                rpt += entry
        await msg.edit_text(rpt, parse_mode='Markdown')
    except Exception as e: 
        logger.error(f"Audit Error: {e}")
        await msg.edit_text(f"❌ **Error:** {e}\n\n_Pastikan sudah run script SQL 'get_leasing_summary' di Supabase._")

async def set_info(update, context):
    global GLOBAL_INFO; 
    if update.effective_user.id==ADMIN_ID: GLOBAL_INFO = " ".join(context.args); await update.message.reply_text("✅ Info Set.")
async def del_info(update, context):
    global GLOBAL_INFO; 
    if update.effective_user.id==ADMIN_ID: GLOBAL_INFO = ""; await update.message.reply_text("🗑️ Info Deleted.")
async def test_group(update, context):
    if update.effective_user.id==ADMIN_ID:
        try: await context.bot.send_message(LOG_GROUP_ID, "🔔 TEST GROUP NOTIFIKASI"); await update.message.reply_text("✅ OK")
        except Exception as e: await update.message.reply_text(f"❌ Fail: {e}")

async def admin_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid, days = int(context.args[0]), int(context.args[1])
        suc, new_exp = add_subscription_days(tid, days)
        if suc: await update.message.reply_text(f"✅ Sukses! User {tid} aktif s/d {new_exp.strftime('%d-%m-%Y')}.")
        else: await update.message.reply_text("❌ Gagal Topup.")
    except: await update.message.reply_text("⚠️ Format: `/topup ID HARI`")

async def add_agency(update, context):
    if update.effective_user.id != ADMIN_ID: return
    try:
        name = " ".join(context.args)
        if not name: return await update.message.reply_text("⚠️ Nama Agency kosong.")
        supabase.table('agencies').insert({"name": name}).execute()
        await update.message.reply_text(f"✅ Agency '{name}' ditambahkan.")
    except: await update.message.reply_text("❌ Error.")

import secrets # Pastikan import ini ada di bagian paling atas file main.py

# ==============================================================================
# FUNGSI MAGIC LINK DASHBOARD (B-ONE ENTERPRISE)
# ==============================================================================
async def request_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Men-generate Magic Link eksklusif untuk PIC Leasing yang terdaftar."""
    user_id = str(update.effective_user.id)
    user_data = get_user(user_id)
    
    # 1. Validasi: Apakah User Terdaftar?
    if not user_data:
        return await update.message.reply_text("⛔ Anda belum terdaftar di sistem B-One Enterprise.")
    
    # 2. Validasi Eksklusif: HANYA UNTUK PIC LEASING, ADMIN, & SUPERADMIN!
    role = user_data.get('role', '').lower()
    is_ceo = (str(user_id) == str(ADMIN_ID)) # Jalur VIP Superadmin
    
    if role not in ['pic', 'admin', 'superadmin'] and not is_ceo:
        return await update.message.reply_text(
            "⛔ AKSES DITOLAK!\n"
            "Dashboard ini dikhususkan untuk PIC Perusahaan Pembiayaan (Leasing).\n"
            "Mitra Lapangan silakan gunakan menu pencarian langsung di bot ini."
        )
    
    # 3. Generate Token Unik (Kunci Baja) & Batas Waktu 15 Menit
    token = secrets.token_urlsafe(32)
    expiry_time = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    
    # 4. Simpan ke Supabase (Gembok dipasang)
    try:
        # FIX: Menggunakan kolom 'user_id' sesuai database Bapak
        supabase.table('users').update({
            'session_token': token,
            'session_expiry': expiry_time
        }).eq('user_id', user_id).execute()
    except Exception as e:
        logger.error(f"Gagal update token: {e}")
        return await update.message.reply_text("⚠️ Sistem sibuk. Gagal membuat token akses.")
    
    # 5. Kirim Magic Link ke Telegram PIC
    domain = "https://b-one.pro" # <--- KEMBALI KE DOMAIN RESMI GO-LIVE
    magic_link = f"{domain}/login-sso?uid={user_id}&token={token}"
    
    # FIX: Gunakan tanda kutip ganda (") untuk href agar Telegram membacanya sebagai Link
    pesan = (
        "🔐 <b>AKSES DASHBOARD B-ONE ENTERPRISE</b>\n\n"
        "Klik tautan di bawah ini untuk masuk ke Ruang Kendali Anda.\n"
        "⚠️ <i>Tautan ini HANYA VALID SELAMA 15 MENIT dan hanya bisa digunakan di SATU perangkat.</i>\n\n"
        f'👉 <a href="{magic_link}">MASUK KE DASHBOARD</a>\n\n'
        "💡 <b>TIPS PRO:</b> Setelah terbuka, klik <b>titik tiga di pojok kanan atas</b> lalu pilih <b>'Buka di Chrome / Browser'</b> agar Anda bisa bolak-balik ke Telegram tanpa menutup Dashboard.\n\n"
        "Jika Anda berganti perangkat, ketik /reset_dashboard terlebih dahulu."
    )
    
    await update.message.reply_text(pesan, parse_mode="HTML", disable_web_page_preview=True)

async def reset_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menghapus sesi/token agar PIC bisa login dari perangkat baru."""
    user_id = str(update.effective_user.id)
    try:
        # FIX: Menggunakan kolom 'user_id'
        supabase.table('users').update({
            'session_token': None,
            'session_expiry': None
        }).eq('user_id', user_id).execute()
        await update.message.reply_text("✅ Sesi Dashboard berhasil di-reset. Anda sekarang bisa membuka Dashboard di perangkat/browser baru dengan mengetik /dashboard.")
    except Exception as e:
        logger.error(f"Gagal reset sesi: {e}")
        await update.message.reply_text("⚠️ Gagal mereset sesi. Coba lagi.")

async def admin_reply(update, context):
    if update.effective_user.id != ADMIN_ID: return
    try:
        if len(context.args) < 2: return await update.message.reply_text("⚠️ Format: `/balas [ID] [Pesan]`", parse_mode='Markdown')
        target_uid = int(context.args[0]); msg_reply = " ".join(context.args[1:])
        await context.bot.send_message(target_uid, f"📩 **BALASAN ADMIN**\n━━━━━━━━━━━━━━━━━━\n💬 {msg_reply}", parse_mode='Markdown')
        await update.message.reply_text(f"✅ Terkirim ke `{target_uid}`.")
    except Exception as e: await update.message.reply_text(f"❌ Gagal: {e}")

async def contact_admin(update, context):
    await update.message.reply_text("📝 **LAYANAN BANTUAN**\n\nSilakan ketik pesan/kendala Anda di bawah ini:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True))
    return SUPPORT_MSG

async def support_send(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    u = get_user(update.effective_user.id); msg_content = update.message.text
    msg_admin = (f"📩 **PESAN DARI MITRA**\n━━━━━━━━━━━━━━━━━━\n👤 <b>Nama:</b> {clean_text(u.get('nama_lengkap'))}\n🏢 <b>Agency:</b> {clean_text(u.get('agency'))}\n📱 <b>ID:</b> <code>{u['user_id']}</code>\n━━━━━━━━━━━━━━━━━━\n💬 <b>Pesan:</b>\n{msg_content}\n━━━━━━━━━━━━━━━━━━\n👉 <b>Balas:</b> <code>/balas {u['user_id']} [Pesan]</code>")
    await context.bot.send_message(ADMIN_ID, msg_admin, parse_mode='HTML')
    await update.message.reply_text("✅ **Pesan Terkirim!**\nMohon tunggu balasan dari Admin.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

# --- FITUR BARU: CEK USER (JUMP TO CONFIRM) ---
async def cek_user_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in str(ADMIN_ID): return
    
    # 1. Ambil ID dari text /cek_12345
    try: target_uid = int(update.message.text.split('_')[1])
    except: return
    
    # 2. Ambil data dari Database
    res = supabase.table('users').select('*').eq('user_id', target_uid).execute()
    if not res.data: return await update.message.reply_text("❌ Data hilang/sudah diproses.")
    
    d = res.data[0] # Data user
    
    # 3. Format Pesan (SAMA PERSIS DENGAN REGISTER_CONFIRM)
    role_db = d.get('role', 'matel')
    wa_link = format_wa_link(d.get('no_hp'))
    
    msg_admin = (
        f"🔔 <b>REVIEW REGISTRASI ({role_db.upper()})</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Nama:</b> {clean_text(d.get('nama_lengkap'))}\n"
        f"🆔 <b>User ID:</b> <code>{d['user_id']}</code>\n"
        f"🏢 <b>Agency:</b> {clean_text(d.get('agency'))}\n"
        f"📍 <b>Domisili:</b> {clean_text(d.get('alamat'))}\n"
        f"📱 <b>HP/WA:</b> {wa_link}\n"
        f"📧 <b>Email:</b> {clean_text(d.get('email'))}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<i>Silakan validasi data mitra ini.</i>"
    )
    
    # 4. Tombol Aksi (Approve & Reject)
    kb = [
        [InlineKeyboardButton("✅ TERIMA (AKTIFKAN)", callback_data=f"appu_{d['user_id']}")], 
        [InlineKeyboardButton("❌ TOLAK (HAPUS)", callback_data=f"reju_{d['user_id']}")]
    ]
    
    await update.message.reply_text(
        msg_admin, 
        reply_markup=InlineKeyboardMarkup(kb), 
        parse_mode='HTML', 
        link_preview_options=LinkPreviewOptions(is_disabled=True)
    )    

# ##############################################################################
# BAGIAN 9: USER FEATURES & NOTIFIKASI (UPDATE: SHARE WA & COPY BUTTON)
# ##############################################################################

async def cek_kuota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    if not u or u['status'] != 'active': return
    
    global GLOBAL_INFO
    info_banner = f"📢 <b>INFO PUSAT:</b> {clean_text(GLOBAL_INFO)}\n━━━━━━━━━━━━━━━━━━\n" if GLOBAL_INFO else ""

    is_admin = (str(user_id) in ADMIN_IDS)
    is_pic = (u.get('role') == 'pic')
    is_korlap = (u.get('role') == 'korlap')

    now = datetime.now(TZ_JAKARTA)
    month_name = now.strftime('%B %Y')
    start_month = now.replace(day=1, hour=0, minute=0, second=0).isoformat()

    # === SKENARIO 1: DASHBOARD KORLAP (NEW FEATURE) ===
    if is_korlap:
        my_agency = clean_pt_name(u.get('agency', ''))
        
        # Hitung Total Temuan Tim Bulan Ini
        # Filter: nama_pt ILIKE %my_agency%
        q_hits = supabase.table('finding_logs').select('*', count='exact', head=True)\
            .ilike('nama_pt', f"%{my_agency}%")\
            .gte('created_at', start_month)
            
        try: total_hits = q_hits.execute().count or 0
        except: total_hits = 0
        
        # Hitung Total Anggota Tim
        q_members = supabase.table('users').select('*', count='exact', head=True)\
            .ilike('agency', f"%{my_agency}%")
        try: total_members = q_members.execute().count or 0
        except: total_members = 0

        msg = (
            f"{info_banner}"
            f"🛡️ <b>DASHBOARD KORLAP</b>\n"
            f"🏢 <b>Agency:</b> {u.get('agency')}\n"
            f"📅 <b>Periode:</b> {month_name}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👥 <b>Total Anggota:</b> {total_members} Personil\n"
            f"🔥 <b>Total Temuan Tim:</b> {total_hits} Unit\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💡 <i>Download laporan kinerja tim Anda:</i>"
        )
        
        kb = [[InlineKeyboardButton("📈 DOWNLOAD LAPORAN TIM (BULAN INI)", callback_data="dl_korlap_mtd")]]
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
        return

    # === SKENARIO 2: DASHBOARD PIC / ADMIN ===
    elif is_pic or is_admin:
        # (Kode lama Komandan tetap dipakai di sini, tidak berubah)
        if is_admin:
            leasing_name = "GLOBAL (ADMIN)"
            query_total = supabase.table('kendaraan').select('*', count='exact', head=True)
            query_hits = supabase.table('finding_logs').select('*', count='exact', head=True).gte('created_at', start_month)
        else:
            leasing_name = standardize_leasing_name(u.get('agency'))
            query_total = supabase.table('kendaraan').select('*', count='exact', head=True).eq('finance', leasing_name)
            # Filter Cabang untuk PIC
            user_branch = str(u.get('wilayah_korlap', '')).strip().upper()
            if user_branch not in ['HO', 'PUSAT', 'NASIONAL', '']:
                query_total = query_total.ilike('branch', f"%{user_branch}%")
            
            query_hits = supabase.table('finding_logs').select('*', count='exact', head=True)\
                .ilike('leasing', f"%{leasing_name}%").gte('created_at', start_month)

        try: total_unit = query_total.execute().count or 0
        except: total_unit = 0
        try: total_hits = query_hits.execute().count or 0
        except: total_hits = 0

        msg = (
            f"{info_banner}"
            f"🏢 <b>DASHBOARD: {leasing_name}</b>\n"
            f"📅 <b>Periode:</b> {month_name}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>Total Aset Terpantau:</b> {total_unit:,} Unit\n"
            f"🎯 <b>Temuan Bulan Ini:</b> {total_hits:,} Unit\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💡 <i>Pilih jenis laporan yang ingin diunduh:</i>"
        )
        
        kb = [
            [InlineKeyboardButton("📂 DOWNLOAD DATABASE ASET", callback_data="dl_assets")],
            [InlineKeyboardButton("📈 DOWNLOAD LAPORAN TEMUAN", callback_data="dl_findings")]
        ]
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
        return

    # === SKENARIO 3: MATEL BIASA ===
    else:
        # (Kode lama Komandan untuk Matel tetap dipakai)
        exp_date = u.get('expiry_date')
        status_aktif = "❌ SUDAH EXPIRED" 
        
        if exp_date:
            try:
                clean_date = str(exp_date).replace('Z', '+00:00')
                exp_dt = datetime.fromisoformat(clean_date)
                if exp_dt.tzinfo is None: exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                exp_dt_wib = exp_dt.astimezone(TZ_JAKARTA)
                now_wib = datetime.now(TZ_JAKARTA)
                formatted_date = exp_dt_wib.strftime('%d %b %Y %H:%M')
                
                if exp_dt_wib > now_wib:
                    remaining = exp_dt_wib - now_wib
                    status_aktif = f"✅ AKTIF s/d {formatted_date}\n⏳ Sisa Waktu: {remaining.days} Hari"
                else:
                    status_aktif = f"❌ SUDAH EXPIRED (Sejak {formatted_date})"
            except ValueError:
                status_aktif = "❌ ERROR: Format Tanggal Invalid"

        msg = (
            f"{info_banner}💳 **INFO LANGGANAN**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ **MITRA LAPANGAN**\n"
            f"👤 {u.get('nama_lengkap')}\n\n"
            f"{status_aktif}\n"
            f"📊 <b>Cek Hari Ini:</b> {u.get('daily_usage', 0)}x\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<i>Perpanjang? Ketik /infobayar</i>"
        )
        await update.message.reply_text(msg, parse_mode='HTML')

async def download_asset_data(update, context):
    query = update.callback_query
    user_id = update.effective_user.id
    u = get_user(user_id)
    
    # 1. CEK OTORITAS
    is_admin = (user_id == ADMIN_ID) or (str(user_id) in ADMIN_IDS)
    is_pic = (u.get('role') == 'pic')

    if not (is_pic or is_admin): 
        return await query.answer("⛔ Akses Ditolak.", show_alert=True)

    # 2. DETEKSI LEASING & CABANG USER
    if is_admin: 
        leasing_filter = "GLOBAL"
        user_branch = "HO" # Admin dianggap HO
    else: 
        leasing_filter = standardize_leasing_name(u.get('agency'))
        # Ambil input cabang user (disimpan di kolom wilayah_korlap)
        user_branch = str(u.get('wilayah_korlap', '')).strip().upper()

    # LOGIKA AKSES NASIONAL (HO / PUSAT / NASIONAL)
    IS_NASIONAL = user_branch in ['HO', 'HEAD OFFICE', 'PUSAT', 'NASIONAL']

    await query.answer("⏳ Menyiapkan Database...", show_alert=False)
    
    # Info Tampilan
    branch_display = "NASIONAL (ALL BRANCH)" if IS_NASIONAL else f"CABANG {user_branch}"
    
    sts = await context.bot.send_message(
        query.message.chat_id, 
        f"⏳ <b>MENGUNDUH DATABASE ASET</b>\n"
        f"🏢 Leasing: {leasing_filter}\n"
        f"📍 Akses: <b>{branch_display}</b>\n"
        f"🔄 <i>Memfilter data...</i>", 
        parse_mode='HTML'
    )
    
    try:
        def fetch_excel():
            q = supabase.table('kendaraan').select('*')
            
            # Filter Leasing (Wajib bagi Non-Admin)
            if not is_admin: 
                q = q.eq('finance', leasing_filter)
                
                # === FILTER CABANG ===
                # Jika BUKAN HO/Nasional, maka filter spesifik
                if not IS_NASIONAL:
                    q = q.ilike('branch', f"%{user_branch}%")
            
            # Limit Aman
            res = q.limit(100000).execute()
            
            if not res.data: return None
            
            df = pd.DataFrame(res.data)
            
            # Pilih Kolom
            cols = ['nopol', 'unit', 'finance', 'branch', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'nama_nasabah']
            final_cols = [c for c in cols if c in df.columns]
            df = df[final_cols]
            
            # Rename Header
            df.rename(columns={
                'nopol': 'NOPOL', 'unit': 'UNIT', 'finance': 'LEASING', 
                'branch': 'CABANG', 'tahun': 'TAHUN', 'warna': 'WARNA', 
                'ovd': 'OVERDUE', 'nama_nasabah': 'NASABAH'
            }, inplace=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Database Aset')
                ws = writer.sheets['Database Aset']
                header_fmt = writer.book.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})
                for col_num, value in enumerate(df.columns.values):
                    ws.write(0, col_num, value, header_fmt)
                ws.set_column('A:Z', 15) 

            output.seek(0)
            return output

        excel_file = await asyncio.to_thread(fetch_excel)
        
        if not excel_file:
            msg = f"⚠️ <b>DATABASE KOSONG.</b>\nTidak ada data aset untuk akses: {branch_display}."
            await sts.edit_text(msg, parse_mode='HTML')
            return

        fname = f"DATABASE_{leasing_filter}_{user_branch}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        await context.bot.send_document(
            chat_id=query.message.chat_id, 
            document=excel_file, 
            filename=fname, 
            caption=f"📂 <b>DATABASE ASET SAYA</b>\n🏢 {leasing_filter}\n📍 {branch_display}"
        )
        await sts.delete()

    except Exception as e:
        logger.error(f"DL Asset Error: {e}")
        await sts.edit_text(f"❌ Error: {e}")

async def download_finding_report(update, context):
    query = update.callback_query
    user_id = update.effective_user.id
    u = get_user(user_id)
    
    # 1. CEK OTORITAS
    is_admin = (user_id == ADMIN_ID) or (str(user_id) in ADMIN_IDS)
    is_pic = (u.get('role') == 'pic')

    if not (is_pic or is_admin): 
        return await query.answer("⛔ Akses Ditolak.", show_alert=True)

    # 2. SET FILTER
    if is_admin: 
        leasing_filter = "GLOBAL"
        display_name = "DATA GLOBAL (ADMIN)"
    else: 
        leasing_filter = standardize_leasing_name(u.get('agency'))
        display_name = f"DATA {leasing_filter}"

    await query.answer("⏳ Menyiapkan Laporan...", show_alert=False)
    
    # 3. RANGE WAKTU
    now = datetime.now(TZ_JAKARTA)
    start_date = now.replace(day=1, hour=0, minute=0, second=0)
    end_date_str = now.strftime('%d %B %Y')
    
    sts = await context.bot.send_message(
        query.message.chat_id, 
        f"⏳ <b>GENERATING REPORT: {display_name}</b>\n"
        f"📅 Periode: 1 {now.strftime('%B')} - {end_date_str}\n"
        f"🔄 <i>Mengambil SEMUA data (Teknik Looping)...</i>", 
        parse_mode='HTML'
    )
    
    try:
        def generate_report():
            # --- STEP A: QUERY LOGS DENGAN LOOPING (PAGINATION) ---
            all_logs = []
            batch_size = 1000 # Tarik per 1000 baris
            start_row = 0
            
            while True:
                # 1. Bangun Query Dasar
                q = supabase.table('finding_logs').select('*')
                if not is_admin: q = q.ilike('leasing', f"%{leasing_filter}%")
                q = q.gte('created_at', start_date.isoformat())
                q = q.order('created_at', desc=True)
                
                # 2. Pakai Range untuk ambil batch tertentu
                # (Misal: 0-999, lalu 1000-1999, dst)
                res = q.range(start_row, start_row + batch_size - 1).execute()
                data = res.data
                
                if not data:
                    break # Stop jika data habis
                
                all_logs.extend(data) # Gabungkan ke list utama
                
                # Cek apakah data yg ditarik kurang dari batch (artinya ini halaman terakhir)
                if len(data) < batch_size:
                    break
                    
                start_row += batch_size # Lanjut ke halaman berikutnya
                
                # Safety Limit (Misal max 100rb baris biar gak crash memori)
                if len(all_logs) >= 100000:
                    break

            if not all_logs: return None

            # --- STEP B: AMBIL DATA PROFIL USER (BATCH LOOKUP) ---
            # Kita juga harus batching lookup user-nya agar URL tidak kepanjangan error
            all_user_ids = list(set([log['user_id'] for log in all_logs if log.get('user_id')]))
            users_map = {}
            
            # Pecah ID user jadi chunk kecil (misal per 100 ID)
            chunk_size = 100
            for i in range(0, len(all_user_ids), chunk_size):
                chunk_ids = all_user_ids[i:i + chunk_size]
                try:
                    res_users = supabase.table('users')\
                        .select('user_id, nama_lengkap, alamat, agency, no_hp')\
                        .in_('user_id', chunk_ids)\
                        .execute()
                    for usr in res_users.data:
                        users_map[str(usr['user_id'])] = usr
                except Exception as e:
                    logger.error(f"Error fetching user chunk: {e}")

            # --- STEP C: MAPPING DATA ---
            report_data = []
            for item in all_logs:
                # Format Waktu
                raw_time = item.get('created_at', '')
                try: 
                    dt_obj = datetime.fromisoformat(raw_time.replace('Z', '+00:00')).astimezone(TZ_JAKARTA)
                    tgl_temuan = dt_obj.strftime('%d/%m/%Y')
                    jam_temuan = dt_obj.strftime('%H:%M:%S')
                except: 
                    tgl_temuan = raw_time
                    jam_temuan = ""
                
                # Profil User
                uid_str = str(item.get('user_id', ''))
                profile = users_map.get(uid_str, {})
                
                # Logic Fallback Data
                # 1. Nama
                finder_name = item.get('nama_matel')
                if not finder_name or finder_name in ['-', '']:
                    finder_name = profile.get('nama_lengkap', 'Unknown User')
                
                # 2. Lokasi (Alamat)
                lokasi = profile.get('alamat', '-')
                    
                # 3. Agency
                pt_matel = item.get('nama_pt')
                if not pt_matel or pt_matel in ['-', '']:
                    pt_matel = profile.get('agency', '-')

                # 4. No HP
                hp = item.get('no_hp')
                if not hp or hp in ['-', '']:
                    hp = profile.get('no_hp', '-')

                report_data.append({
                    'TANGGAL': tgl_temuan,
                    'JAM': jam_temuan,
                    'NOPOL': item.get('nopol', '-'),
                    'UNIT / TIPE': item.get('unit', '-'),
                    'LEASING': item.get('leasing', '-'),
                    'NAMA PENEMU': finder_name,
                    'NO HP MATEL': hp,
                    'AGENCY / PT MATEL': pt_matel,
                    'LOKASI / DOMISILI': lokasi,
                    'INPUT PENCARIAN': item.get('query_text', '-') # Tambahan info
                })

            # --- STEP D: BUAT EXCEL ---
            df = pd.DataFrame(report_data)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Laporan Temuan')
                ws = writer.sheets['Laporan Temuan']
                
                # Style Header
                format_header = writer.book.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})
                for col_num, value in enumerate(df.columns.values):
                    ws.write(0, col_num, value, format_header)
                
                # Lebar Kolom
                ws.set_column('A:A', 12) 
                ws.set_column('B:B', 10) 
                ws.set_column('C:C', 12) 
                ws.set_column('D:D', 25) 
                ws.set_column('E:E', 15) 
                ws.set_column('F:F', 25) 
                ws.set_column('G:G', 15) 
                ws.set_column('H:H', 25) 
                ws.set_column('I:I', 35) 
                ws.set_column('J:J', 15)

            output.seek(0)
            return output

        excel_file = await asyncio.to_thread(generate_report)
        
        if not excel_file:
            await sts.edit_text(f"⚠️ <b>DATA KOSONG.</b>")
            return
            
        # --- CATAT AUDIT (UU PDP COMPLIANCE) ---
        # Kita hapus len(all_logs) agar tidak memicu error variable undefined
        catat_audit(
            user_id=user_id, 
            action="DOWNLOAD_FINDING_REPORT", 
            details=f"Pimpinan mengunduh laporan temuan bulanan ({leasing_filter})."
        )

        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        fname = f"REPORT_{leasing_filter}_{timestamp}.xlsx"
        caption = (
            f"📈 <b>LAPORAN KINERJA BULANAN</b>\n"
            f"🏢 User: {leasing_filter}\n"
            f"📅 Periode: 1 - {end_date_str}\n"
            f"📊 Status: FULL DATA (Looping Mode)"
        )
        
        await context.bot.send_document(
            chat_id=query.message.chat_id, 
            document=excel_file, 
            filename=fname, 
            caption=caption
        )
        await sts.delete()
        
    except Exception as e:
        logger.error(f"DL Report Err: {e}")
        try: await sts.edit_text(f"❌ Error: {e}")
        except: pass

async def download_korlap_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    u = get_user(user_id)
    
    if u.get('role') != 'korlap':
        return await query.answer("⛔ Anda bukan Korlap.", show_alert=True)
        
    my_agency = clean_pt_name(u.get('agency', ''))
    
    await query.answer("⏳ Menyiapkan Laporan Tim...", show_alert=False)
    sts = await context.bot.send_message(query.message.chat_id, f"⏳ <b>GENERATING REPORT</b>\n🏢 Agency: {u.get('agency')}\n🔄 <i>Mengambil data performa tim...</i>", parse_mode='HTML')

    try:
        def fetch_report():
            now = datetime.now(TZ_JAKARTA)
            start_month = now.replace(day=1, hour=0, minute=0, second=0).isoformat()
            
            # Ambil Finding Logs Tim Bulan Ini (Filter by Agency Name)
            res = supabase.table('finding_logs').select('*')\
                .ilike('nama_pt', f"%{my_agency}%")\
                .gte('created_at', start_month)\
                .order('created_at', desc=True)\
                .execute()
                
            if not res.data: return None
            
            df = pd.DataFrame(res.data)
            
            # Formatting Kolom (Bahasa Indonesia)
            cols_export = {
                'created_at': 'WAKTU',
                'nopol': 'NOPOL',
                'unit': 'UNIT',
                'leasing': 'LEASING',
                'nama_matel': 'ANGGOTA',
                'no_hp': 'NO HP',
                'lokasi': 'LOKASI'
            }
            avail_cols = [c for c in cols_export.keys() if c in df.columns]
            df = df[avail_cols].rename(columns=cols_export)
            
            # Bersihkan Waktu
            if 'WAKTU' in df.columns:
                df['WAKTU'] = pd.to_datetime(df['WAKTU']).dt.strftime('%d-%m-%Y %H:%M')
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='KINERJA TIM')
                ws = writer.sheets['KINERJA TIM']
                # Style Header
                format_header = writer.book.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})
                for col_num, value in enumerate(df.columns.values):
                    ws.write(0, col_num, value, format_header)
                ws.set_column('A:Z', 18)
                
            output.seek(0)
            return output

        excel_file = await asyncio.to_thread(fetch_report)
        
        if not excel_file:
            await sts.edit_text("⚠️ <b>DATA KOSONG</b>\nTim Anda belum mendapatkan unit bulan ini.")
            return

        # --- CATAT AUDIT (UU PDP COMPLIANCE) ---
        catat_audit(
            user_id=user_id, 
            action="DOWNLOAD_KORLAP_REPORT", 
            details=f"Korlap mengunduh rekap kinerja tim agency: {u.get('agency')}."
        )

        fname = f"LAPORAN_TIM_{my_agency.replace(' ','_')}_{datetime.now().strftime('%b%Y')}.xlsx"
        await context.bot.send_document(
            chat_id=query.message.chat_id,
            document=excel_file,
            filename=fname,
            caption=f"📈 <b>LAPORAN KINERJA TIM</b>\n🏢 {u.get('agency')}\n📅 Bulan: {datetime.now().strftime('%B %Y')}"
        )
        await sts.delete()

    except Exception as e:
        logger.error(f"Korlap DL Error: {e}")
        await sts.edit_text(f"❌ Error: {e}")

# ==============================================================================
# [UPDATED V2] FITUR REKAP ANGGOTA (FUZZY LOGIC - ANTI TYPO)
# ==============================================================================
async def rekap_anggota_korlap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)

    # 1. Validasi Keamanan (Hanya Korlap)
    if not u or u.get('role') != 'korlap':
        return await update.message.reply_text("⛔ **AKSES DITOLAK**\nFitur ini khusus untuk akun KORLAP.", parse_mode='Markdown')

    my_agency_raw = u.get('agency', '')
    if not my_agency_raw:
        return await update.message.reply_text("⚠️ Data Agency Anda tidak valid. Hubungi Admin.")

    # Feedback Loading
    sts = await update.message.reply_text("⏳ **Sedang mengaudit pasukan (Deep Scan)...**", parse_mode='Markdown')

    try:
        # 2. Query Database (AMBIL SEMUA MATEL DULU)
        # Kita tarik semua user non-PIC agar bisa kita filter sendiri pakai Python (Fuzzy Logic)
        res = supabase.table('users').select('*')\
            .neq('role', 'pic')\
            .neq('role', 'admin')\
            .execute()

        all_matels = res.data
        if not all_matels:
            return await sts.edit_text("📂 Database User Kosong.", parse_mode='Markdown')

        # 3. LOGIKA PENCOCOKAN CERDAS (FUZZY MATCHING)
        target_agency_clean = clean_pt_name(my_agency_raw) # Bersihkan nama PT Korlap
        members = []

        for m in all_matels:
            user_agency_raw = m.get('agency', '')
            user_agency_clean = clean_pt_name(user_agency_raw)
            
            is_match = False
            
            # A. Cek Substring (Pasti Benar) -> Contoh: "ELANG" ada di "PT ELANG PERKASA"
            if target_agency_clean in user_agency_clean or user_agency_clean in target_agency_clean:
                is_match = True
            
            # B. Cek Typo (Fuzzy Logic) -> Contoh: "LUKRETIA" vs "LUCRETIA"
            if not is_match:
                # Hitung rasio kemiripan (0.0 - 1.0)
                similarity = difflib.SequenceMatcher(None, target_agency_clean, user_agency_clean).ratio()
                if similarity > 0.80: # Jika 80% mirip, anggap SAMA!
                    is_match = True
            
            if is_match:
                members.append(m)

        if not members:
            return await sts.edit_text(f"📂 **DATA KOSONG**\nTidak ditemukan anggota yang cocok dengan: **{my_agency_raw}**", parse_mode='Markdown')

        # 4. Proses Data ke Excel
        data_export = []
        active_count = 0
        expired_count = 0
        now = datetime.now(TZ_JAKARTA)

        for m in members:
            # Format Tanggal Expired
            raw_exp = m.get('expiry_date')
            exp_fmt = "-"
            status_calc = "NON-AKTIF"

            if raw_exp:
                try:
                    dt = datetime.fromisoformat(str(raw_exp).replace('Z', '+00:00')).astimezone(TZ_JAKARTA)
                    exp_fmt = dt.strftime('%d-%m-%Y')
                    
                    if dt > now:
                        status_calc = "AKTIF"
                        active_count += 1
                    else:
                        status_calc = "EXPIRED"
                        expired_count += 1
                except: pass
            else:
                expired_count += 1

            # Masukkan ke list export
            data_export.append({
                "NAMA LENGKAP": str(m.get('nama_lengkap', '-')).upper(),
                "NO HP (WA)": m.get('no_hp', '-'),
                "AGENCY (INPUT USER)": m.get('agency', '-').upper(), # Biar ketahuan kalau ada yg typo
                "DOMISILI": m.get('alamat', '-'),
                "EMAIL": m.get('email', '-'),
                "TGL EXPIRED": exp_fmt,
                "STATUS": status_calc
            })

        # Buat DataFrame Pandas
        df = pd.DataFrame(data_export)

        # 5. Tulis ke Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='DATA ANGGOTA')
            ws = writer.sheets['DATA ANGGOTA']
            
            # Styling
            fmt_header = writer.book.add_format({'bold': True, 'bg_color': '#4F81BD', 'font_color': 'white', 'border': 1})
            for col_num, value in enumerate(df.columns.values):
                ws.write(0, col_num, value, fmt_header)
                ws.set_column(col_num, col_num, 22)

        output.seek(0)

        # 6. Kirim Laporan
        caption_msg = (
            f"👥 **AUDIT ANGGOTA (SMART SCAN)**\n"
            f"🏢 Agency: {my_agency_raw}\n"
            f"📅 Tanggal: {now.strftime('%d %B %Y')}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✅ **Aktif:** {active_count}\n"
            f"💀 **Expired:** {expired_count}\n"
            f"∑ **Total Terdeteksi:** {len(members)}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💡 _Sistem menggunakan 'Fuzzy Logic' untuk mendeteksi anggota yang salah ketik nama Agency._"
        )

        clean_filename = target_agency_clean.replace(" ", "_")[:20]
        fname = f"SQUAD_{clean_filename}_{now.strftime('%d%m%y')}.xlsx"

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=output,
            filename=fname,
            caption=caption_msg,
            parse_mode='Markdown'
        )
        await sts.delete()

    except Exception as e:
        logger.error(f"Rekap Anggota Error: {e}")
        try: await sts.edit_text(f"❌ Error: {e}")
        except: pass

# ==============================================================================
# BAGIAN 5: HANDLER TOPUP & BUKTI BAYAR (CLEAN & FIXED)
# ==============================================================================

# 1. INFO BAYAR (Tampilkan QRIS & Instruksi)
async def info_bayar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qris_filename = 'qris.jpg'
    caption_msg = (
        "💰 **PAKET LANGGANAN (UNLIMITED CEK)**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ **10 HARI** = Rp 50.000\n"
        "2️⃣ **20 HARI** = Rp 75.000\n"
        "🔥 **30 HARI** = Rp 100.000 (BEST DEAL!)\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "💳 **METODE BAYAR: QRIS (B-ONE ENTERPRISE)**\n"
        "✅ *Support: BCA, Mandiri, BRI, BNI, GoPay, Dana, OVO, ShopeePay.*\n\n"
        "📝 **SUDAH TRANSFER?**\n"
        "Silakan upload bukti transfer Anda dengan mengetik perintah:\n"
        "👉 /buktibayar\n"
        "⚠️ *Pastikan nominal sesuai dengan paket yang dipilih dan bukti bayar sesuai nominal transfer.*"
    )

    try:
        if os.path.exists(qris_filename):
            with open(qris_filename, 'rb') as photo_file:
                await update.message.reply_photo(photo=photo_file, caption=caption_msg, parse_mode='Markdown')
        else:
            await update.message.reply_text(caption_msg + "\n⚠️ *Gambar QRIS belum tersedia. Hubungi Admin.*", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal memuat info pembayaran: {e}")

# 2. FITUR KHUSUS: /buktibayar (Jalur VIP)
async def buktibayar_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Langkah 1: User mengetik /buktibayar"""
    msg = (
        "📸 **UPLOAD BUKTI BAYAR**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Silakan **Kirim Foto / File Gambar** bukti transfer Anda sekarang.\n\n"
        "❌ *Ketik /cancel untuk membatalkan.*"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')
    return WAIT_BUKTI

async def buktibayar_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Langkah 2: User mengirim foto (Jalur VIP)"""
    # Panggil fungsi handle_photo_topup secara manual agar tidak duplikasi kode
    # Karena handle_photo_topup sudah punya logika deteksi foto/file yang canggih
    await handle_photo_topup(update, context)
    return ConversationHandler.END

# 3. PANDUAN TEKS (Hanya Teks Bantuan)
async def panduan_buktibayar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Fungsi ini HANYA dipanggil jika user ketik /buktibayar tapi handler conversation tidak jalan
    # (Sebagai fallback)
    await buktibayar_start(update, context) 

# 4. HANDLER INTI: PROSES FOTO TOPUP (Bisa dipanggil dari mana saja)
async def handle_photo_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Debugging: Kasih respon loading dulu biar tau bot hidup
    msg_wait = await update.message.reply_text("⏳ *Memproses bukti bayar...*", parse_mode='Markdown')
    
    file_id = None
    msg = update.message
    
    # 1. Cek Sumber Gambar (LOGIKA INI TIDAK DIUBAH -> AMAN)
    try:
        if msg.photo:
            file_id = msg.photo[-1].file_id
        elif msg.document:
            mime = str(msg.document.mime_type).lower()
            fname = str(msg.document.file_name).lower()
            if "image" in mime or fname.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                file_id = msg.document.file_id
    except Exception as e:
        await msg_wait.edit_text(f"❌ Error saat baca file: {e}")
        return ConversationHandler.END

    # 2. Jika File Tidak Ditemukan
    if not file_id: 
        await msg_wait.edit_text("❌ **Gagal Membaca Gambar!**\nPastikan yang dikirim adalah FOTO atau FILE GAMBAR (JPG/PNG).")
        return ConversationHandler.END

    # 3. Cek User di Database
    uid = update.effective_user.id
    u = get_user(uid)
    if not u:
        await msg_wait.edit_text("⚠️ **User Tidak Terdaftar.**\nKetik /start untuk register.")
        return ConversationHandler.END

    # 4. Format Tanggal Expired (Agar Rapi: DD-MM-YYYY)
    raw_exp = u.get('expiry_date')
    formatted_exp = "BELUM AKTIF"
    if raw_exp:
        try:
            # Coba parsing ISO format
            if isinstance(raw_exp, str):
                raw_exp = raw_exp.replace('Z', '+00:00')
                dt_obj = datetime.fromisoformat(raw_exp)
                formatted_exp = dt_obj.strftime('%d-%m-%Y %H:%M')
            else:
                formatted_exp = str(raw_exp)
        except:
            formatted_exp = str(raw_exp)[:10] # Fallback aman

    # 5. Kirim ke Admin (TAMPILAN BARU LENGKAP)
    try:
        # Gunakan ID Admin Manual Komandan
        target_admin = ADMIN_ID if ADMIN_ID != 0 else 7530512170 
        
        # Susun Pesan Laporan
        caption = (
            f"💰 <b>PERMINTAAN TOPUP BARU</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Nama:</b> {u.get('nama_lengkap', 'Unknown')}\n"
            f"🆔 <b>ID:</b> <code>{u['user_id']}</code>\n"
            f"🏢 <b>PT/Agency:</b> {u.get('agency', '-')}\n"
            f"📱 <b>WhatsApp:</b> {u.get('no_hp', '-')}\n"
            f"📅 <b>Exp Saat Ini:</b> {formatted_exp}\n"
            f"📝 <b>Catatan User:</b> {msg.caption or '-'}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👇 <i>Pilih Paket Durasi untuk di-ACC:</i>"
        )
        
        # KEYBOARD TOMBOL (LENGKAP: 5, 10, 20, 30, Manual, Tolak)
        kb = [
            [
                InlineKeyboardButton("✅ 5 HARI", callback_data=f"topup_{uid}_5"),
                InlineKeyboardButton("✅ 10 HARI", callback_data=f"topup_{uid}_10")
            ],
            [
                InlineKeyboardButton("✅ 20 HARI", callback_data=f"topup_{uid}_20"),
                InlineKeyboardButton("🔥 30 HARI", callback_data=f"topup_{uid}_30")
            ],
            [
                InlineKeyboardButton("✏️ MANUAL", callback_data=f"man_topup_{uid}"),
                InlineKeyboardButton("❌ TOLAK", callback_data=f"topup_{uid}_rej")
            ]
        ]
        
        await context.bot.send_photo(
            chat_id=target_admin, 
            photo=file_id, 
            caption=caption, 
            reply_markup=InlineKeyboardMarkup(kb), 
            parse_mode='HTML'
        )
        
        # Sukses ke User
        await msg_wait.edit_text("✅ **BUKTI DITERIMA!**\nAdmin telah menerima foto Anda. Mohon tunggu verifikasi.")
        
    except Exception as e:
        # Error Handler (Penting biar bot gak diem aja kalau gagal kirim ke admin)
        print(f"ERROR KIRIM KE ADMIN: {e}")
        await msg_wait.edit_text(f"❌ **Gagal Kirim ke Admin:**\nBot gagal menghubungi Admin ID {target_admin}.\nError: {e}")
        
    return ConversationHandler.END

# --- [BARU] HELPER: TOMBOL AKSI GRUP (HUBUNGI + SHARE WA + SALIN) ---
def get_action_buttons(matel_user, unit_data):
    # 1. Link WA Penemu
    user_hp = matel_user.get('no_hp', '-')
    clean_num = re.sub(r'[^0-9]', '', str(user_hp))
    if clean_num.startswith('0'): clean_num = '62' + clean_num[1:]
    wa_penemu = f"https://wa.me/{clean_num}"
    
    # 2. Format Teks Share WA (SAMA PERSIS DENGAN FORMAT LAPORAN)
    share_text = (
        f"*LAPORAN TEMUAN UNIT (ONE ASPAL)*\n"
        f"----------------------------------\n"
        f"🚙 Unit: {unit_data.get('type', '-')}\n"
        f"🔢 Nopol: {unit_data.get('nopol', '-')}\n"
        f"🎨 Warna: {unit_data.get('warna', '-')}\n"
        f"📅 Tahun: {unit_data.get('tahun', '-')}\n"
        f"🔧 Noka: {unit_data.get('noka', '-')}\n"
        f"⚙️ Nosin: {unit_data.get('nosin', '-')}\n"
        f"🏦 Finance: {unit_data.get('finance', '-')}\n"
        f"⚠️ OVD: {unit_data.get('ovd', '-')}\n"
        f"🏢 Branch: {unit_data.get('branch', '-')}\n"
        f"📍 Lokasi: {matel_user.get('alamat', '-')}\n"
        f"👤 Penemu: {matel_user.get('nama_lengkap', '-')} ({matel_user.get('agency', '-')})\n"
        f"----------------------------------\n"
        f"⚠️ *PENTING & DISCLAIMER:*\n"
        f"Informasi ini BUKAN alat yang SAH untuk penarikan unit (Eksekusi).\n"
        f"Mohon untuk konfirmasi ke Pic Leasing atau Kantor."
    )
    encoded_share = urllib.parse.quote(share_text)
    share_link = f"https://wa.me/?text={encoded_share}"
    
    # 3. Callback Copy (Safe Nopol)
    nopol_safe = str(unit_data.get('nopol', '-')).replace(" ", "")
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 Hubungi Penemu", url=wa_penemu)],
        [
            InlineKeyboardButton("📲 Share WA", url=share_link), 
            InlineKeyboardButton("📋 Salin Data", callback_data=f"cp_{nopol_safe}")
        ]
    ])

# --- FUNGSI FORMAT PESAN NOTIFIKASI (PUSAT) ---
def create_notification_text(matel_user, unit_data, header_title):
    # 1. LOGIKA VERSI DATA (SMART FALLBACK)
    version_code = unit_data.get('data_month')
    if not version_code or version_code in ['-', None, '']:
        raw_date = unit_data.get('created_at')
        if raw_date:
            try:
                # Parse timestamp dari Supabase
                dt = datetime.fromisoformat(str(raw_date).replace('Z', '+00:00'))
                version_code = dt.strftime('%m%y') 
            except:
                version_code = "-"
        else:
            version_code = "-"

    # 2. FORMAT TEXT STANDAR (SAMA DENGAN HASIL CARI)
    clean_nopol = clean_text(unit_data.get('nopol'))
    clean_unit = clean_text(unit_data.get('type'))
    
    return (
        f"{header_title}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Penemu:</b> {clean_text(matel_user.get('nama_lengkap'))} ({clean_text(matel_user.get('agency'))})\n"
        f"📍 <b>Lokasi:</b> {clean_text(matel_user.get('alamat'))}\n"
        f"----------------------------------\n"
        f"🚙 <b>Unit:</b> {clean_unit}\n"
        f"🔢 <b>Nopol:</b> {clean_nopol}\n"
        f"📅 <b>Tahun:</b> {clean_text(unit_data.get('tahun'))}\n"
        f"🎨 <b>Warna:</b> {clean_text(unit_data.get('warna'))}\n"
        f"----------------------------------\n"
        f"🔧 <b>Noka:</b> {clean_text(unit_data.get('noka'))}\n"
        f"⚙️ <b>Nosin:</b> {clean_text(unit_data.get('nosin'))}\n"
        f"----------------------------------\n"
        f"🏦 <b>Finance:</b> {clean_text(unit_data.get('finance'))}\n"
        f"🗓️ <b>DATA: {version_code}</b>\n" # <--- FITUR BARU
        f"⚠️ <b>OVD:</b> {clean_text(unit_data.get('ovd'))}\n"       
        f"🏢 <b>Branch:</b> {clean_text(unit_data.get('branch'))}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

# 1. NOTIFIKASI KE ADMIN PUSAT (LOG GROUP)
async def notify_hit_to_group(context, u, d):
    try:
        if LOG_GROUP_ID == 0: return
        msg = create_notification_text(u, d, "🚨 <b>UNIT DITEMUKAN! (LOG PUSAT)</b>")
        kb = get_action_buttons(u, d) # Pakai Helper Baru
        await context.bot.send_message(LOG_GROUP_ID, msg, reply_markup=kb, parse_mode='HTML')
    except Exception as e: print(f"❌ Gagal Kirim Notif Admin Pusat: {e}")

# 2. NOTIFIKASI KE GROUP LEASING (PIC)
async def notify_leasing_group(context, matel_user, unit_data):
    leasing_unit = str(unit_data.get('finance', '')).strip().upper()
    if len(leasing_unit) < 3: return
    try:
        res = supabase.table('leasing_groups').select("*").execute()
        groups = res.data
        target_group_ids = []
        for g in groups:
            g_name = str(g['leasing_name']).upper()
            if g_name in leasing_unit or leasing_unit in g_name:
                target_group_ids.append(g['group_id'])
        if not target_group_ids: return
        
        msg = create_notification_text(matel_user, unit_data, "🚨 <b>UNIT DITEMUKAN! (HIT LEASING)</b>")
        kb = get_action_buttons(matel_user, unit_data) # Pakai Helper Baru
        
        for gid in target_group_ids:
            if int(gid) == int(LOG_GROUP_ID): continue 
            try: await context.bot.send_message(gid, msg, reply_markup=kb, parse_mode='HTML')
            except: pass
    except Exception as e: logger.error(f"Error Notify Leasing: {e}")

# 3. NOTIFIKASI KE GROUP AGENCY (MONITORING)
async def notify_agency_group(context, matel_user, unit_data):
    user_agency = str(matel_user.get('agency', '')).strip().upper()
    if len(user_agency) < 3: return
    try:
        res = supabase.table('agency_groups').select("*").execute()
        groups = res.data
        target_group_ids = []
        for g in groups:
            g_name = str(g['agency_name']).upper()
            is_match = g_name in user_agency or user_agency in g_name
            if not is_match:
                similarity = difflib.SequenceMatcher(None, g_name, user_agency).ratio()
                if similarity > 0.8: is_match = True
            if is_match:
                target_group_ids.append(g['group_id'])
        if not target_group_ids: return
        
        msg = create_notification_text(matel_user, unit_data, f"👮‍♂️ <b>LAPORAN ANGGOTA ({user_agency})</b>")
        kb = get_action_buttons(matel_user, unit_data) # Pakai Helper Baru
        
        for gid in target_group_ids:
            if int(gid) == int(LOG_GROUP_ID): continue
            try: await context.bot.send_message(gid, msg, reply_markup=kb, parse_mode='HTML')
            except: pass
    except Exception as e: logger.error(f"Error Notify Agency: {e}")

# [V5.5] REGISTER LEASING GROUP
async def set_leasing_group(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if update.effective_chat.type not in ['group', 'supergroup']:
        return await update.message.reply_text("⚠️ Perintah ini hanya bisa digunakan di dalam GRUP Leasing.")
    if not context.args:
        return await update.message.reply_text("⚠️ Format: `/setgroup [NAMA_LEASING]`\nContoh: `/setgroup BCA`")
    leasing_name = " ".join(context.args).upper()
    chat_id = update.effective_chat.id
    try:
        supabase.table('leasing_groups').delete().eq('group_id', chat_id).execute()
        supabase.table('leasing_groups').insert({"group_id": chat_id, "leasing_name": leasing_name}).execute()
        await update.message.reply_text(f"✅ <b>GRUP TERDAFTAR!</b>\n\nGrup ini sekarang adalah <b>OFFICIAL ALERT GROUP</b> untuk: <b>{leasing_name}</b>.\nSetiap unit '{leasing_name}' ditemukan, notifikasi akan masuk ke sini.", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal set grup: {e}")

# [V6.0] REGISTER AGENCY GROUP
async def set_agency_group(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if update.effective_chat.type not in ['group', 'supergroup']:
        return await update.message.reply_text("⚠️ Perintah ini hanya bisa digunakan di dalam GRUP Agency.")
    if not context.args:
        return await update.message.reply_text("⚠️ Format: `/setagency [NAMA_PT]`\nContoh: `/setagency PT ELANG PERKASA`")
    agency_name = " ".join(context.args).upper()
    chat_id = update.effective_chat.id
    try:
        supabase.table('agency_groups').delete().eq('group_id', chat_id).execute()
        supabase.table('agency_groups').insert({"group_id": chat_id, "agency_name": agency_name}).execute()
        await update.message.reply_text(f"✅ <b>AGENCY TERDAFTAR!</b>\n\nGrup ini sekarang adalah <b>MONITORING ROOM</b> untuk: <b>{agency_name}</b>.\nSetiap Matel dari PT ini menemukan unit, notifikasi masuk sini.", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal set grup: {e}")

# ==============================================================================
# BAGIAN 10:[UPDATE v2.2] UPLOAD ENGINE: BACKGROUND TASK (AUTO LOG INTEGRATED)
# ==============================================================================

# [GLOBAL] Set Task agar tidak di-kill
BACKGROUND_TASKS = set()

async def run_background_upload(app, chat_id, user_id, message_id, data_ctx):
    """
    Versi UPDATE v2.2 (Integrated): 
    - Batch Size 200 (Aman untuk Supabase)
    - Retry Logic 5x (Tahan banting koneksi)
    - Auto Month Code (0226)
    - [NEW] Auto Log ke Tabel Riwayat Harian
    """
    print(f"🚀 [BG] START Task User {user_id}")
    
    # 1. GENERATE KODE BULAN (MMYY)
    now = datetime.now(TZ_JAKARTA)
    code_version = now.strftime('%m%y') 
    
    # 2. SETUP VARIABEL
    mode = data_ctx.get('upload_mode', 'UPSERT')
    path = data_ctx.get('upload_path')
    is_pic = False
    
    # Helper: Kirim Pesan
    async def send_update(text):
        try: await app.bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
        except Exception as e: print(f"⚠️ Gagal Kirim Pesan: {e}")

    try:
        # --- A. DOWNLOAD FILE ---
        if not path:
            is_pic = True
            fname = data_ctx.get('upload_file_name', 'data.xlsx')
            path = f"temp_{user_id}_{int(time.time())}_{fname}"
            try:
                new_file = await app.bot.get_file(data_ctx.get('upload_file_id'))
                await new_file.download_to_drive(path)
            except Exception as e:
                await send_update(f"❌ Gagal Download File: {e}")
                return

        # --- B. BACA & BERSIHKAN FILE ---
        if not os.path.exists(path):
            await send_update("❌ Error: File hilang dari server.")
            return

        print("📂 [BG] Membaca File...")
        with open(path, 'rb') as fr: content = fr.read()
        
        # Gunakan read_file_robust yang sudah support TOPAZ/ZIP
        df = read_file_robust(content, path)
        df = fix_header_position(df)
        df, _ = smart_rename_columns(df)
        
        # Standarisasi Leasing
        target = data_ctx.get('target_leasing')
        if target and target != 'SKIP':
            df['finance'] = standardize_leasing_name(target)
        else:
            if 'finance' in df.columns: df['finance'] = df['finance'].apply(standardize_leasing_name)
            else: df['finance'] = 'UNKNOWN'

        # Bersihkan Nopol
        df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        df = df.dropna(subset=['nopol'])
        df = df[df['nopol'].str.len() > 2]
        df = df.drop_duplicates(subset=['nopol'], keep='last')
        
        # Pastikan Kolom Lengkap
        for c in VALID_DB_COLUMNS:
            if c not in df.columns: df[c] = None
            
        # Masukkan Kode Bulan
        df['data_month'] = code_version
        
        df = df.replace({np.nan: None})
        
        # Siapkan Data untuk Insert
        cols_to_use = VALID_DB_COLUMNS + ['data_month']
        recs = json.loads(json.dumps(df[cols_to_use].to_dict('records'), default=str))
        
        total_data = len(recs)
        print(f"✅ [BG] Total Data: {total_data} (Versi: {code_version})")

        if total_data == 0:
            await send_update("⚠️ <b>FILE KOSONG / TIDAK VALID SETELAH FILTER.</b>")
            if os.path.exists(path): os.remove(path)
            return

        # --- C. UPLOAD BATCH (BAGIAN KRUSIAL) ---
        # Kita set 200 agar database tidak timeout (Error 57014)
        BATCH_SIZE = 200 
        
        suc = 0; fail = 0; start_time = time.time()
        leasing_info = clean_text(data_ctx.get('target_leasing') or 'MIX')
        action_txt = "MENGHAPUS" if mode == 'DELETE' else "MENGUPDATE"

        await send_update(
            f"🔄 <b>SEDANG MEMPROSES...</b>\n"
            f"📂 Total: {total_data:,} Data\n"
            f"🗓️ <b>Versi Data: {code_version}</b>\n"
            f"📝 Mode: {action_txt}\n\n"
            f"<i>Bot sedang bekerja... (Estimasi: {int(total_data/BATCH_SIZE*1.5)} detik)</i>"
        )

        for i in range(0, total_data, BATCH_SIZE):
            await asyncio.sleep(0.01) # Jeda nafas CPU
            batch = recs[i:i+BATCH_SIZE]
            
            # --- RETRY LOGIC (JARING PENGAMAN) ---
            # Jika gagal, coba lagi sampai 5 kali
            batch_success = False
            for attempt in range(5):
                try:
                    if mode == 'DELETE':
                        nopols = [d['nopol'] for d in batch]
                        q = supabase.table('kendaraan').delete().in_('nopol', nopols)
                        if target and target != 'SKIP':
                            q = q.eq('finance', standardize_leasing_name(target))
                        q.execute()
                    else:
                        # Upsert Data
                        supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
                    
                    suc += len(batch)
                    batch_success = True
                    break # Berhasil! Keluar dari loop retry
                
                except Exception as e:
                    # Gagal? Tunggu sebentar lalu coba lagi
                    await asyncio.sleep((attempt + 1) * 2)
                    if attempt == 4: # Jika sudah 5x tetap gagal
                        print(f"⚠️ Batch Gagal: {e}")
            
            if not batch_success:
                fail += len(batch)
            
            # Update Log di Console
            if i % 2000 == 0: print(f"⏳ [BG] Progress: {i}/{total_data}")

        # --- D. LAPORAN SELESAI ---
        duration = int(time.time() - start_time)
        final_rpt = (
            f"✅ <b>PROSES SELESAI!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📂 Total: {total_data:,}\n"
            f"🗓️ <b>Versi Data: {code_version}</b>\n"
            f"✅ Sukses: {suc:,}\n"
            f"❌ Gagal: {fail:,}\n"
            f"⏱️ Waktu: {duration} detik\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Data <b>{leasing_info}</b> telah terupdate."
        )
        await send_update(final_rpt)
        print(f"🏁 [BG] Done. Suc: {suc}")

        # --- [INTEGRASI LOG HARIAN] ---
        # Bagian ini yang kita tambahkan agar tercatat di Laporan Pagi
        if suc > 0 and mode == 'UPSERT':
            try:
                catat_log_kendaraan(
                    sumber="BOT_TELEGRAM", 
                    leasing=leasing_info, 
                    jumlah=suc
                )
            except Exception as log_err:
                print(f"⚠️ Gagal Catat Log Harian: {log_err}")
        # ------------------------------

    except Exception as e:
        logger.error(f"Upload Fatal: {e}")
        await send_update(f"❌ <b>ERROR FATAL:</b> {str(e)[:200]}")
    finally:
        # Bersihkan file temp
        if path and os.path.exists(path):
            try: os.remove(path)
            except: pass

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. BERIKAN FEEDBACK LANGSUNG (Supaya tidak dikira Stuck)
    status_msg = await update.message.reply_text("⏳ **Menganalisa File...**", parse_mode='Markdown')
    
    msg = update.message
    fname = ""
    
    # 2. DETEKSI JENIS FILE
    if msg.document:
        fname = (msg.document.file_name or "").lower()
        
        # A. JIKA GAMBAR -> OPER KE FITUR BUKTI BAYAR
        if fname.endswith(('.jpg', '.jpeg', '.png', '.webp')):
            await status_msg.delete() # Hapus pesan loading
            return await handle_photo_topup(update, context)
            
        # B. JIKA BUKAN EXCEL DAN BUKAN GAMBAR -> TOLAK
        valid_ext = ('.xlsx', '.xls', '.csv', '.zip', '.topaz', '.txt', '.json')
        if not fname.endswith(valid_ext):
            await status_msg.edit_text("❌ **Format File Ditolak.**\nHanya menerima: Excel, CSV, ZIP, Topaz, atau Foto (JPG/PNG).")
            return ConversationHandler.END

    # 3. CEK USER
    uid = update.effective_user.id
    u = get_user(uid)
    if not u or u['status'] != 'active': 
        await status_msg.edit_text("⛔ Akses Ditolak. Akun tidak aktif.")
        return ConversationHandler.END
    
    # Simpan info file
    context.user_data['upload_file_id'] = update.message.document.file_id
    context.user_data['upload_file_name'] = update.message.document.file_name
    
    # 4. MODE PIC (USER LEASING)
    if u.get('role') == 'pic':
        await status_msg.delete()
        my_leasing = standardize_leasing_name(u.get('agency'))
        context.user_data['target_leasing'] = my_leasing
        kb = [["📂 UPDATE DATA", "🗑️ HAPUS DATA"], ["❌ BATAL"]]
        await update.message.reply_text(
            f"📥 **FILE DITERIMA (PIC MODE)**\nUser: {u.get('nama_lengkap')}\nTarget: {my_leasing}", 
            reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
        )
        return U_CONFIRM_UPLOAD

    # 5. MODE ADMIN (SUPER USER)
    # Cek apakah user ini Admin
    is_admin = (uid == ADMIN_ID) or (str(uid) in ADMIN_IDS)
    
    if is_admin:
        try:
            # Download dan Baca File
            path = f"temp_{uid}_{int(time.time())}_{fname}"
            f = await update.message.document.get_file()
            await f.download_to_drive(path)
            
            with open(path, 'rb') as fr: content = fr.read()
            df = read_file_robust(content, path)
            df = fix_header_position(df)
            df, found = smart_rename_columns(df)
            
            # Validasi Kolom NOPOL
            if 'nopol' not in df.columns: 
                if os.path.exists(path): os.remove(path)
                await status_msg.edit_text("❌ **ERROR:** Kolom NOPOL tidak ditemukan dalam file.")
                return ConversationHandler.END
            
            # Simpan Data Sementara
            context.user_data['upload_path'] = path
            context.user_data['preview'] = df.head(1).to_dict('records')
            context.user_data['cols'] = df.columns.tolist()
            
            await status_msg.delete()
            await update.message.reply_text(
                f"✅ **SCAN OK**\nCols: {', '.join(found)}\nTotal Baris: {len(df):,}\n\n👉 **Masukkan Nama Leasing** (atau pilih SKIP):", 
                reply_markup=ReplyKeyboardMarkup([["SKIP"], ["❌ BATAL"]], resize_keyboard=True)
            )
            return U_LEASING_ADMIN
            
        except Exception as e:
            if os.path.exists(path): os.remove(path)
            await status_msg.edit_text(f"❌ Error System: {e}")
            return ConversationHandler.END
            
    # 6. MODE USER BIASA (Mungkin Lapor Unit)
    else:
        await status_msg.delete()
        await update.message.reply_text("📄 File diterima. Leasing?", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
        return U_LEASING_USER

async def upload_leasing_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nm = update.message.text.upper()
    if nm == "❌ BATAL": return await cancel(update, context)

    # 1. AMBIL DATA
    preview_data = context.user_data.get('preview')
    if not preview_data:
        await update.message.reply_text("❌ **Sesi Habis.** Upload ulang.", parse_mode='Markdown')
        return ConversationHandler.END

    # 2. LOGIKA NAMA LEASING
    if nm != 'SKIP':
        clean_name = standardize_leasing_name(nm)
        fin_display = clean_name
        context.user_data['target_leasing'] = nm
    else:
        context.user_data['target_leasing'] = 'SKIP'
        fin_display = "SESUAI FILE (Otomatis)" if 'finance' in preview_data[0] else "UNKNOWN"

    # 3. PREVIEW DATA BARIS 1
    s = preview_data[0].copy()
    labels = {'nopol':'🔢 Nopol', 'type':'🚙 Unit', 'finance':'🏦 Leasing', 'noka':'🔧 Noka', 'ovd':'⚠️ OVD'}
    detail_str = ""
    for k, label in labels.items():
        val = clean_name if k == 'finance' and nm != 'SKIP' else s.get(k)
        if val and str(val).strip().lower() not in ['nan', 'none', '', '-']:
            detail_str += f"   {label}: {clean_text(val)}\n"
            
    preview_msg = (
        f"🔎 <b>PREVIEW FILE</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"🏦 <b>Target:</b> {fin_display}\n\n"
        f"📝 <b>Sample Baris 1:</b>\n{detail_str or '   (Data Kosong)'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <b>PILIH AKSI:</b>\n"
        f"• <b>UPDATE:</b> Menambah/Update data baru.\n"
        f"• <b>HAPUS:</b> Menghapus data berdasarkan Nopol."
    )
    
    # TOMBOL PILIHAN GANDA
    keyboard = [
        ["📂 UPDATE DATA", "🗑️ HAPUS DATA"],
        ["❌ BATAL"]
    ]
    
    await update.message.reply_text(preview_msg, parse_mode='HTML', reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return U_CONFIRM_UPLOAD

# --- EKSEKUSI UPLOAD (CORE ENGINE) ---
# Digunakan oleh Admin (setelah konfirmasi) DAN PIC (Langsung)
async def upload_confirm_admin(update, context):
    choice = update.message.text
    
    # 1. Tentukan Mode
    if choice == "📂 UPDATE DATA":
        mode = 'UPSERT'
        action_msg = "MENGUPDATE"
    elif choice == "🗑️ HAPUS DATA":
        mode = 'DELETE'
        action_msg = "MENGHAPUS"
    elif choice == "❌ BATAL":
        return await cancel(update, context)
    else:
        # Jika user ketik aneh-aneh
        return await cancel(update, context)
        
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # 2. Siapkan Context Data (Aman untuk Background)
    # PIC tidak punya 'upload_path' (karena belum download), tapi punya 'upload_file_id'
    safe_context = {
        'upload_mode': mode,
        'upload_path': context.user_data.get('upload_path'), 
        'upload_file_name': context.user_data.get('upload_file_name'),
        'upload_file_id': context.user_data.get('upload_file_id'),
        'target_leasing': context.user_data.get('target_leasing')
    }
    
    # 3. Kirim Pesan Konfirmasi Awal
    msg = await update.message.reply_text(
        f"🚀 **PERINTAH DITERIMA!**\n"
        f"⚙️ Mode: {action_msg}\n"
        f"⏳ <i>Menyiapkan antrean proses...</i>",
        parse_mode='HTML',
        reply_markup=ReplyKeyboardRemove()
    )
    
    # 4. JALANKAN BACKGROUND TASK (Anti-Stuck & Anti-Kill)
    task = context.application.create_task(
        run_background_upload(context.application, chat_id, user_id, msg.message_id, safe_context)
    )
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)
    
    # Bersihkan memori user
    context.user_data.clear()
    
    return ConversationHandler.END

async def upload_leasing_user(update, context):
    nm = update.message.text
    if nm == "❌ BATAL": return await cancel(update, context)
    
    u = get_user(update.effective_user.id)
    file_id = context.user_data.get('upload_file_id')
    
    # Forward ke Admin
    caption = f"📥 **UPLOAD MITRA**\n👤 {u['nama_lengkap']}\n🏦 {nm}"
    try:
        # Kirim ke ADMIN_ID utama
        if 'ADMIN_ID' in globals() and ADMIN_ID != 0:
            await context.bot.send_document(ADMIN_ID, file_id, caption=caption)
    except: pass

    await update.message.reply_text("✅ Terkirim ke Admin.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def stop_upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # 1. Hentikan sinyal upload jika sedang berjalan
    context.user_data['stop_signal'] = True
    
    # 2. Hapus file sampah jika ada proses upload yang batal
    path = context.user_data.get('upload_path')
    if path and os.path.exists(path): 
        try: os.remove(path)
        except: pass

    # 3. BERSIHKAN SEMUA MEMORI (Agar registrasi tidak nyangkut)
    context.user_data.clear()
    
    await update.message.reply_text(
        "🛑 <b>PROSES DIHENTIKAN</b>\n"
        "Seluruh sesi dan memori sementara telah dibersihkan.\n"
        "Silakan mulai kembali dengan /start atau /register.",
        parse_mode='HTML',
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE): 
    # 1. Bersihkan semua memori User Data
    context.user_data.clear()
    
    # 2. Hapus file sampah jika ada proses upload yang nyangkut
    path = context.user_data.get('upload_path')
    if path and os.path.exists(path): 
        try: os.remove(path)
        except: pass
        
    # 3. Kirim konfirmasi
    await update.message.reply_text("🚫 **PROSES DIBATALKAN & MEMORI DIRESET.**\nSistem kembali ke posisi netral.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
    return ConversationHandler.END

# ==============================================================================
# BAGIAN 11: REGISTRASI & START
# ==============================================================================

async def register_start(update, context):
    if get_user(update.effective_user.id): return await update.message.reply_text("✅ Anda sudah terdaftar.")
    msg = ("🤖 **ONEASPAL REGISTRATION**\n\nSilakan pilih **Jalur Profesi** Anda:\n\n1️⃣ **MITRA LAPANGAN (MATEL)**\n_(Untuk Profcoll & Jasa Pengamanan Aset)_\n\n2️⃣ **PIC LEASING (INTERNAL)**\n_(Khusus Staff Internal Leasing/Finance)_")
    kb = [["1️⃣ MITRA LAPANGAN"], ["2️⃣ PIC LEASING"], ["❌ BATAL"]]
    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)); return R_ROLE_CHOICE

async def register_role_choice(update, context):
    choice = update.message.text
    if choice == "❌ BATAL": return await cancel(update, context)
    if "1️⃣" in choice: context.user_data['reg_role'] = 'matel'; await update.message.reply_text("🛡️ **FORMULIR MITRA LAPANGAN**\n\n1️⃣ Masukkan **Nama Lengkap**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]])); return R_NAMA
    elif "2️⃣" in choice: context.user_data['reg_role'] = 'pic'; await update.message.reply_text("🤝 **FORMULIR INTERNAL LEASING**\n\n1️⃣ Masukkan **Nama Lengkap**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]])); return R_NAMA
    else: return await register_start(update, context)

async def register_nama(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['r_nama'] = update.message.text; await update.message.reply_text("2️⃣ No HP (WA):"); return R_HP
async def register_hp(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    hp = update.message.text; context.user_data['r_hp'] = hp
    await update.message.reply_text("3️⃣ **Alamat Email:**\n_(Kami butuh email untuk backup data akun Anda)_\n\n👉 _Silakan ketik Email Anda:_", parse_mode='Markdown'); return R_EMAIL

async def register_email(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    
    # Simpan Email
    context.user_data['r_email'] = update.message.text
    role = context.user_data.get('reg_role', 'matel')
    
    # --- LOGIKA PERCABANGAN ---
    if role == 'pic':
        # JIKA PIC: SKIP pertanyaan Kota, LANGSUNG tanya Nama Leasing
        txt = (
            "4️⃣ **Nama Leasing / Finance:**\n"
            "⚠️ _Wajib Nama Resmi (JANGAN DISINGKAT)_\n"
            "_(Contoh: BCA FINANCE, ADIRA DINAMIKA, ACC)_\n\n"
            "👉 _Ketik Nama FINANCE Anda:_"
        )
        await update.message.reply_text(txt, parse_mode='Markdown')
        return R_AGENCY
        
    else:
        # JIKA MATEL: Tanya Domisili/Kota (Ini dianggap Branch mereka)
        txt = (
            "4️⃣ **Domisili / Wilayah Operasi:**\n"
            "_(Contoh: Jakarta Timur, Bekasi, Surabaya)_\n\n"
            "👉 _Ketik KOTA/DOMISILI Anda:_"
        )
        await update.message.reply_text(txt, parse_mode='Markdown')
        return R_KOTA

async def register_kota(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    
    # Simpan Kota (Domisili Matel)
    context.user_data['r_kota'] = update.message.text
    
    # Lanjut tanya Agency
    txt = (
        "5️⃣ **Nama Agency / PT:**\n"
        "⚠️ _Wajib Nama Lengkap Sesuai Legalitas_\n"
        "_(Contoh: PT ELANG PERKASA, PT MAJU JAYA)_\n\n"
        "👉 _Ketik Nama AGENCY Anda:_"
    )
    await update.message.reply_text(txt, parse_mode='Markdown')
    return R_AGENCY

async def register_agency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    
    raw_text = update.message.text.strip()
    role = context.user_data.get('reg_role', 'matel')
    
    final_agency_name = raw_text # Default
    
    if role == 'matel':
        # Cari tebakan terbaik dari database
        suggested = find_best_match_agency(raw_text)
        
        # --- LOGIKA REM 80% (THE GATEKEEPER) ---
        if suggested:
            # Bersihkan dari kata PT/CV untuk menghitung murni hurufnya
            clean_input = raw_text.upper().replace("PT.", "").replace("PT ", "").replace("CV.", "").replace("CV ", "").strip()
            clean_suggested = suggested.upper().replace("PT.", "").replace("PT ", "").replace("CV.", "").replace("CV ", "").strip()
            
            # Hitung persentase kemiripan (0.0 sampai 1.0)
            similarity = difflib.SequenceMatcher(None, clean_input, clean_suggested).ratio()
            
            # JIKA KEMIRIPAN DI BAWAH 80%, TOLAK TEBAKANNYA! (Anggap PT Baru)
            if similarity < 0.8:
                suggested = None 
        # ---------------------------------------

        if suggested:
            final_agency_name = suggested
            if raw_text.upper() != final_agency_name:
                await update.message.reply_text(
                    f"🤖 **AUTO-CORRECT:**\n"
                    f"Input: _{raw_text}_\n"
                    f"Terdeteksi sebagai: **{final_agency_name}**\n"
                    f"✅ Data dikoreksi otomatis agar persetujuan masuk ke Korlap.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(f"✅ Agency Terkonfirmasi: **{final_agency_name}**", parse_mode='Markdown')
        else:
            final_agency_name = raw_text.upper()
            await update.message.reply_text(f"⚠️ **AGENCY BARU:** {final_agency_name}\nBelum terdaftar. Data akan diverifikasi Admin Pusat.", parse_mode='Markdown')

    else:
        # Jika PIC Leasing, pakai kamus standar
        final_agency_name = standardize_leasing_name(raw_text)

    # Simpan ke memori
    context.user_data['r_agency'] = final_agency_name
    
    # --- LOGIKA LANJUTAN ---
    if role == 'pic':
        msg = (
            f"✅ Leasing Terdeteksi: <b>{final_agency_name}</b>\n\n"
            f"5️⃣ <b>INPUT KODE CABANG (BRANCH)</b>\n"
            f"Masukkan nama cabang tempat Anda bertugas:\n\n"
            f"🔸 <b>PIC CABANG:</b> Ketik nama cabang (Contoh: <code>TEBET</code>, <code>SURABAYA</code>)\n"
            f"🔹 <b>PIC NASIONAL:</b> Ketik kode <b>HO</b> (Akses Seluruh Indonesia)."
        )
        await update.message.reply_text(msg, parse_mode='HTML')
        return R_BRANCH 
        
    else:
        context.user_data['r_branch_code'] = context.user_data.get('r_kota')
        d = context.user_data
        summary = (
            f"📝 **KONFIRMASI PENDAFTARAN**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 **Nama:** {d['r_nama']}\n"
            f"📱 **HP:** {d['r_hp']}\n"
            f"📧 **Email:** {d['r_email']}\n"
            f"📍 **Domisili:** {d['r_kota']}\n"
            f"🛡️ **Agency:** {d['r_agency']}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Apakah data di atas sudah benar?"
        )
        await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True), parse_mode='Markdown')
        return R_CONFIRM
    
async def register_branch(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    
    branch_input = update.message.text.strip().upper()
    
    # Validasi input pendek
    if len(branch_input) < 2:
        await update.message.reply_text("⚠️ Nama cabang terlalu pendek. Silakan ulangi.")
        return R_BRANCH

    # Simpan Input Cabang
    context.user_data['r_branch_code'] = branch_input
    
    # PENTING: Simpan juga sebagai 'r_kota' agar kolom 'alamat' di database tidak kosong
    context.user_data['r_kota'] = branch_input 
    
    # Cek HO atau Cabang Biasa
    if branch_input in ['HO', 'PUSAT', 'NASIONAL', 'HEAD OFFICE']:
        context.user_data['r_branch_code'] = "HO" # Standarkan jadi HO
        access_info = "🌍 NASIONAL (ALL DATA)"
    else:
        access_info = f"📍 LOKAL: {branch_input}"

    # Lanjut Minta Foto ID Card
    await update.message.reply_text(
        f"✅ Cabang: <b>{branch_input}</b>\n"
        f"🔐 Akses: {access_info}\n\n"
        f"📸 <b>VERIFIKASI IDENTITAS (WAJIB)</b>\n"
        f"Silakan **Kirim Foto ID CARD / NAMETAG KANTOR** Anda sekarang.",
        parse_mode='HTML',
        reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
    )
    return R_PHOTO_ID
    
async def register_photo_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    photo_file = None

    # [FIX] LOGIKA PENANGKAPAN CERDAS
    # 1. Cek apakah dikirim sebagai Foto Biasa (Compressed)
    if message.photo:
        photo_file = message.photo[-1]
        
    # 2. Cek apakah dikirim sebagai File Dokumen (Uncompressed)
    elif message.document:
        # Pastikan ini file gambar (image/jpeg, image/png, dll)
        if 'image' in str(message.document.mime_type).lower():
            photo_file = message.document

    # Jika BUKAN foto dan BUKAN dokumen gambar -> Tolak
    if not photo_file:
        await message.reply_text(
            "⚠️ **FORMAT DITOLAK**\nMohon kirimkan FOTO ID Card (Boleh dari Galeri atau File Gambar).", 
            reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)
        )
        return R_PHOTO_ID

    # Ambil File ID dari sumber manapun
    context.user_data['r_photo_proof'] = photo_file.file_id
    
    d = context.user_data
    summary = (
        f"📝 **KONFIRMASI REGISTRASI (PIC)**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Nama:** {d.get('r_nama')}\n"
        f"📱 **HP:** {d.get('r_hp')}\n"
        f"📧 **Email:** {d.get('r_email')}\n"
        f"🏢 **Cabang:** {d.get('r_kota')}\n"
        f"🏦 **Finance:** {d.get('r_agency')}\n"
        f"📸 **ID Card:** [Terlampir]\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Kirim data ke Admin untuk verifikasi?"
    )
    await message.reply_text(summary, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True), parse_mode='Markdown')
    return R_CONFIRM

# --- UPDATE FUNGSI REGISTER CONFIRM ---
# --- UPDATE FIX: PIC UNLIMITED ---
async def register_confirm(update, context):
    if update.message.text != "✅ KIRIM": return await cancel(update, context)
    
    d = context.user_data
    role_db = d.get('reg_role', 'matel')
    
    # ==========================================================================
    # ⚙️ FIX LOGIC: MASA AKTIF & KUOTA (PIC vs MATEL) - UPDATED v6.70
    # ==========================================================================
    now = datetime.now(TZ_JAKARTA)
    
    if role_db == 'pic':
        # PIC LEASING: Aktif sampai akhir tahun 2030
        expiry_dt = datetime(2030, 12, 31, 23, 59, 59, tzinfo=TZ_JAKARTA)
        quota_init = 999999 
    else:
        # MATEL: Trial 1 Hari (24 Jam)
        expiry_dt = now + timedelta(days=1)
        quota_init = 1000   # Kuota trial tetap 1000 pencarian, tapi waktunya dipepet   

    expiry_str = expiry_dt.isoformat()
    # ==========================================================================
    
    # Ambil data cabang (Jika PIC), jika Matel kosongkan/pakai data kota
    branch_val = d.get('r_branch_code') if role_db == 'pic' else None

    # Masukkan ke Database
    data_user = {
        "user_id": update.effective_user.id, 
        "nama_lengkap": d['r_nama'], 
        "no_hp": d['r_hp'], 
        "email": d['r_email'], 
        "alamat": d['r_kota'], 
        "agency": d['r_agency'], 
        "quota": quota_init,        # <--- UPDATED
        "expiry_date": expiry_str,  # <--- UPDATED (KUNCI FIX-NYA DI SINI)
        "status": "pending", 
        "role": role_db, 
        "ref_korlap": None,
        "wilayah_korlap": branch_val
    }
    
    try:
        # 1. Simpan ke Database
        supabase.table('users').insert(data_user).execute()
        
        # 2. Tentukan Siapa yang Harus Meng-Approve
        approver_list = [] 
        is_routed_to_korlap = False
        
        # Jika pendaftar adalah MATEL, cek apakah ada KORLAP di agency tersebut?
        if role_db == 'matel':
            # Pastikan fungsi helper ini ada di atas
            korlap_data = get_korlaps_by_agency(d['r_agency'])
            if korlap_data:
                approver_list = [k['user_id'] for k in korlap_data]
                is_routed_to_korlap = True
        
        # Jika tidak ada Korlap (atau user adalah PIC), kirim ke ADMIN PUSAT
        if not approver_list:
            approver_list = [ADMIN_ID] 

        # 3. Kirim Balasan ke User Pendaftar
        if role_db == 'pic': 
            await update.message.reply_text("✅ **PENDAFTARAN TERKIRIM**\nAkses Enterprise Workspace sedang diverifikasi Admin.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
        else:
            verifikator = "KORLAP AGENCY" if is_routed_to_korlap else "ADMIN PUSAT"
            await update.message.reply_text(f"✅ **PENDAFTARAN TERKIRIM**\nData Anda telah dikirim ke **{verifikator}** untuk verifikasi.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
        
        # 4. Susun Pesan Notifikasi untuk Approver
        wa_link = format_wa_link(d['r_hp']) 
        
        header_title = f"🔔 <b>PERMINTAAN ANGGOTA BARU</b>" if is_routed_to_korlap else f"🔔 <b>REGISTRASI BARU ({role_db.upper()})</b>"
        sub_info = f"<i>User ini mendaftar di Agency Anda: <b>{d['r_agency']}</b></i>" if is_routed_to_korlap else "<i>Silakan validasi data mitra ini.</i>"

        msg_notif = (
            f"{header_title}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Nama:</b> {clean_text(d['r_nama'])}\n"
            f"🆔 <b>User ID:</b> <code>{update.effective_user.id}</code>\n"
            f"🏢 <b>Agency/Fin:</b> {clean_text(d['r_agency'])}\n"
            f"📍 <b>Area:</b> {clean_text(d['r_kota'])}\n"
            f"📱 <b>HP/WA:</b> {wa_link}\n"
            f"📧 <b>Email:</b> {clean_text(d['r_email'])}\n"
            f"⏳ <b>Masa Aktif:</b> {'UNLIMITED (PIC)' if role_db=='pic' else '1 HARI (TRIAL)'}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{sub_info}\n"
        )
        
        kb = [[InlineKeyboardButton("✅ TERIMA", callback_data=f"appu_{update.effective_user.id}")], [InlineKeyboardButton("❌ TOLAK", callback_data=f"reju_{update.effective_user.id}")]]
        
        # 5. Eksekusi Pengiriman Notif
        for target_id in approver_list:
            try:
                if 'r_photo_proof' in d and role_db == 'pic':
                    await context.bot.send_photo(
                        chat_id=target_id, 
                        photo=d['r_photo_proof'], 
                        caption=msg_notif + "📸 <i>Bukti ID Card terlampir.</i>", 
                        reply_markup=InlineKeyboardMarkup(kb), 
                        parse_mode='HTML'
                    )
                else:
                    await context.bot.send_message(
                        chat_id=target_id, 
                        text=msg_notif, 
                        reply_markup=InlineKeyboardMarkup(kb), 
                        parse_mode='HTML',
                        # 👇👇👇 INI DIA OBATNYA 👇👇👇
                        link_preview_options=LinkPreviewOptions(is_disabled=True)
                    )
            except Exception as e:
                logger.error(f"Gagal kirim notif ke approver {target_id}: {e}")
            
    except Exception as e: 
        logger.error(f"Reg Error: {e}")
        await update.message.reply_text("❌ Gagal Terkirim. User ID Anda mungkin sudah terdaftar.", reply_markup=ReplyKeyboardRemove())
        
    return ConversationHandler.END

# ==============================================================================
# BAGIAN 12: START & CORE SEARCH ENGINE
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    try:
        # 1. Cek User di Database
        data = supabase.table("users").select("*").eq("user_id", user.id).execute()
        
        # === SKENARIO 1: USER BARU (BELUM TERDAFTAR) ===
        if not data.data:
            msg_guest = (
                f"🤖 <b>SELAMAT DATANG DI ONE ASPAL BOT</b>\n"
                f"<i>Sistem Manajemen Aset & Recovery Terpadu</i>\n\n"
                f"Halo, <b>{clean_text(user.full_name)}</b>! 👋\n"
                f"Anda belum terdaftar sebagai mitra kami.\n\n"
                f"🚀 <b>LANGKAH SELANJUTNYA:</b>\n"
                f"Silakan daftarkan diri Anda untuk akses penuh.\n"
                f"👉 <b>Ketik /register</b>\n\n"
                f"<i>Kami melayani Mitra Lapangan (Matel) & PIC Leasing Resmi.</i>"
            )
            await update.message.reply_text(msg_guest, parse_mode='HTML')
            return

        # === SKENARIO 2: USER SUDAH ADA DI DATABASE ===
        user_db = data.data[0]
        status = user_db.get('status', 'pending')
        
        # Cek Status Akun
        if status == 'pending':
            await update.message.reply_text(
                f"⏳ <b>AKUN SEDANG DIVERIFIKASI</b>\n"
                f"Halo {clean_text(user_db.get('nama_lengkap'))}, data pendaftaran Anda sudah masuk dan sedang direview Admin.\n"
                f"Mohon tunggu notifikasi selanjutnya.",
                parse_mode='HTML'
            )
            return
        elif status == 'rejected':
            await update.message.reply_text("⛔ <b>PENDAFTARAN DITOLAK</b>\nSilakan hubungi Admin untuk info lebih lanjut.", parse_mode='HTML')
            return
        elif status != 'active':
            await update.message.reply_text("⛔ <b>AKUN NONAKTIF</b>\nHubungi Admin untuk mengaktifkan kembali.", parse_mode='HTML')
            return

        # === SKENARIO 3: USER AKTIF (Tampilkan Menu Sesuai Role) ===
        role_user = user_db.get('role', 'matel')
        
        # Ambil Info Global (Jika ada)
        global GLOBAL_INFO
        info_txt = f"📢 <b>INFO:</b> {clean_text(GLOBAL_INFO)}\n━━━━━━━━━━━━━━━━━━\n\n" if GLOBAL_INFO else ""

        # A. TAMPILAN PIC LEASING (TEKS ORIGINAL SESUAI REQUEST)
        if role_user == 'pic':
            nama_pic = clean_text(user_db.get('nama_lengkap'))
            
            # [PENTING] Kalimat ini dikembalikan ke versi Original SOP
            welcome_text = (
                f"{info_txt}"
                f"Selamat Pagi, Pak {nama_pic}.\n\n"
                f"Izin memperkenalkan fitur <b>Private Enterprise</b> di OneAspal Bot.\n\n"
                f"Kami menyediakan <b>Private Cloud</b> agar Bapak bisa menyimpan data kendaraan dengan aman menggunakan <b>Blind Check System</b>.\n\n"
                f"🔐 <b>Keamanan Data:</b>\n"
                f"Di sistem ini, Bapak <b>TIDAK</b> dikategorikan menyebarkan data kepada orang lain (Aman secara SOP). Bapak hanya mengarsipkan data digital untuk menunjang <b>Performance Pekerjaan</b> Bapak sendiri.\n\n"
                f"Data Bapak <b>TIDAK BISA</b> dilihat atau didownload user lain. Sistem hanya akan memberi notifikasi kepada Bapak jika unit tersebut ditemukan di lapangan.\n\n"
                f"Silakan dicoba fitur <b>Upload Data</b>-nya, Pak (Menu Sinkronisasi).\n\n"
                f"<i>Jika ada pertanyaan, silakan balas pesan ini melalui tombol <b>📞 BANTUAN TEKNIS</b> di menu utama.</i>"
            )
            
            kb = [["🔄 SINKRONISASI DATA", "📂 DATABASE SAYA"], ["📞 BANTUAN TEKNIS"]]
            await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

        # B. TAMPILAN MITRA LAPANGAN (MATEL/KORLAP)
        else:
            welcome_text = (
                f"{info_txt}"
                f"🦅 <b>ONE ASPAL BOT: ASSET RECOVERY</b>\n"
                f"Halo, <b>{clean_text(user_db.get('nama_lengkap'))}</b>! 🫡\n\n"
                f"⚡ <b>READY TO SERVE:</b>\n"
                f"Database <b>Terlengkap & Terupdate</b> siap digunakan.\n"
                f"Bot didesain <b>Super Cepat & Hemat Kuota</b>.\n\n"
                f"🔎 <b>CARA PENCARIAN:</b>\n"
                f"Ketik NOPOL / NOKA / NOSIN langsung di sini.\n"
                f"Contoh: <code>B1234ABC</code>\n\n"
                f"💡 <b>SHORTCUT:</b>\n"
                f"/cekkuota - Sisa paket\n"
                f"/infobayar - Info Rekening & QRIS\n"
                f"/buktibayar - Cara Upload Bukti\n"
                f"/lapor - Lapor unit aman\n"
                f"/admin - Bantuan Admin\n\n"
                f"<i>Salam Satu Aspal! 🏴‍☠️</i>"
            )
            await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=ReplyKeyboardRemove())

    except Exception as e:
        logger.error(f"Error start: {e}")
        await update.message.reply_text(f"⚠️ <b>SISTEM SEDANG SIBUK</b>\nSilakan coba lagi.\n<i>Error: {e}</i>", parse_mode='HTML')

async def panduan(update, context):
    """
    Panduan Cerdas v3 (Final Fix):
    - PIC: Monitoring + Manajemen + Upload Format (Lengkap) + Hapus + Keamanan.
    - Mitra: Tetap standar operasional lapangan.
    """
    user = update.effective_user
    u = get_user(user.id)
    
    # === 1. PANDUAN PIC LEASING (LENGKAP & SOLID) ===
    if u and u.get('role') == 'pic': 
        agency = standardize_leasing_name(u.get('agency'))
        
        msg = (
            f"🏢 <b>PANDUAN ENTERPRISE WORKSPACE</b>\n"
            f"User: <b>{agency}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            
            f"1️⃣ <b>MONITORING KINERJA (BARU!)</b>\n"
            f"• Ketik <b>/rekap</b> : Lihat total temuan & ranking agency hari ini.\n"
            f"• Ketik <b>/cekagency [NamaPT]</b> : Audit mitra tertentu.\n"
            f"• Ketik <b>/broadcast</b> : Kirim info penting ke Matel.\n\n"
            
            f"2️⃣ <b>MANAJEMEN DATA (DASHBOARD)</b>\n"
            f"• Klik tombol <b>📂 DATABASE SAYA</b> di menu bawah.\n"
            f"• Lihat statistik total aset & temuan secara real-time.\n"
            f"• Klik <b>📥 DOWNLOAD DATA</b> untuk menarik data aset Anda ke Excel.\n\n"
            
            f"3️⃣ <b>UPDATE DATA (PENAMBAHAN)</b>\n"
            f"• Kirim file <b>Excel (.xlsx), CSV, ZIP, atau TOPAZ</b> ke bot.\n"
            f"• ⚠️ <b>FORMAT KOLOM WAJIB (Header):</b>\n"
            f"  🔸 <b>NOPOL</b> (Wajib, cth: B 1234 XY)\n"
            f"  🔸 <b>UNIT</b> (Merk/Tipe Kendaraan)\n"
            f"  🔸 <b>OVD</b> (Jumlah Hari Keterlambatan)\n"
            f"  🔸 <b>BRANCH</b> (Nama Cabang/Area)\n"
            f"  🔸 <b>FINANCE</b> (Opsional/Nama Leasing)\n"
            f"• Bot otomatis mendeteksi format & leasing Anda.\n"
            f"• Data akan diproses otomatis di background.\n\n"
            
            f"4️⃣ <b>PENGHAPUSAN DATA (PELUNASAN)</b>\n"
            f"• Login ke Dashboard Web -> Menu Hapus Massal.\n"
            f"• Upload daftar Nopol lunas -> Klik Hapus.\n"
            f"• <i>Sistem hanya menghapus data milik {agency}.</i>\n\n"
            
            f"5️⃣ <b>KEAMANAN DATA</b>\n"
            f"Data Anda terisolasi (Private Cloud). Mitra leasing lain tidak dapat melihat, menghapus, atau mendownload aset Anda.\n\n"
            
            f"<i>Butuh bantuan teknis? Hubungi Administrator Pusat.</i>"
        )

    # === 2. PANDUAN MITRA LAPANGAN (TETAP SAMA) ===
    else: 
        msg = (
            "📖 <b>PANDUAN PENGGUNAAN ONEASPAL</b>\n\n"
            "1️⃣ <b>Cari Data Kendaraan</b>\n"
            "   - Ketik Nopol secara lengkap atau sebagian.\n"
            "   - Contoh: <code>B 1234 ABC</code> atau <code>1234</code>\n\n"
            "2️⃣ <b>Upload File (Mitra)</b>\n"
            "   - Kirim file Excel/CSV/ZIP/TOPAZ ke bot ini.\n"
            "   - Bot akan membaca otomatis.\n\n"
            "3️⃣ <b>Upload Satuan / Kiriman</b>\n"
            "   - Gunakan perintah /tambah untuk input data manual.\n\n"
            "4️⃣ <b>Lapor Unit Selesai</b>\n"
            "   - Gunakan perintah /lapor jika unit sudah ditarik.\n\n"
            "5️⃣ <b>Cek Kuota</b>\n"
            "   - Ketik /cekkuota untuk melihat sisa HIT.\n\n"
            "6️⃣ <b>Bantuan Admin</b>\n"
            "   - Ketik /admin [pesan] untuk support.\n\n"
            "7️⃣ <b>Perpanjang Langganan</b>\n"
            "   - Ketik /infobayar untuk Topup."
        )
    
    await update.message.reply_text(msg, parse_mode='HTML')

async def bagikan_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Kalimat promosi sesuai keinginan Bapak
    promo_text = (
        "Ijin info rekan-rekan, untuk cek data kendaraan dan update leasing terbaru "
        "sekarang lebih mudah pakai One Aspal Bot. Data update tiap hari, akurat, "
        "hemat kouta dan sangat membantu di lapangan. Yuk cek di sini: https://t.me/Oneaspal_bot"
    )
    
    # 2. Membuat Link Share WhatsApp (Agar otomatis terisi teksnya)
    wa_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(promo_text)}"
    
    # 3. Pesan instruksi di dalam bot
    msg = (
        "🚀 **BAGIKAN ONE ASPAL BOT**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Bantu rekan tim Anda bekerja lebih mudah dengan membagikan bot ini.\n\n"
        "Silakan pilih metode berbagi:"
    )
    
    # 4. Tombol aksi (Inline)
    kb = [
        [InlineKeyboardButton("📲 Kirim ke WhatsApp", url=wa_url)],
        [InlineKeyboardButton("📋 Salin Pesan Promosi", callback_data="copy_promo")]
    ]
    
    await update.message.reply_text(
        msg, 
        parse_mode='Markdown', 
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def handle_message(update, context):
    text = update.message.text
    if text == "🔄 SINKRONISASI DATA": return await upload_start(update, context)
    if text == "📂 DATABASE SAYA": return await cek_kuota(update, context)
    u = get_user(update.effective_user.id)
    if not u: return await update.message.reply_text("⛔ **AKSES DITOLAK**\nSilakan ketik /register.", parse_mode='Markdown')
    if u['status'] != 'active': return await update.message.reply_text("⏳ **AKUN PENDING**\nTunggu Admin.", parse_mode='Markdown')
    is_active, reason = check_subscription_access(u)
    if not is_active:
        if reason == "EXPIRED": return await update.message.reply_text("⛔ **MASA AKTIF HABIS**\nSilakan ketik /infobayar untuk perpanjang.", parse_mode='Markdown')
        elif reason == "DAILY_LIMIT": return await update.message.reply_text("⛔ **BATAS HARIAN TERCAPAI**\nAnda telah mencapai limit cek hari ini. Reset otomatis jam 00:00.", parse_mode='Markdown')
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    kw = re.sub(r'[^a-zA-Z0-9]', '', text.upper())
    if len(kw) < 3: return await update.message.reply_text("⚠️ Minimal 3 karakter.")
    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.ilike.%{kw}%,noka.eq.{kw},nosin.eq.{kw}").limit(20).execute()
        data_found = res.data
        if not data_found: return await update.message.reply_text(f"❌ <b>TIDAK DITEMUKAN</b>\n<code>{kw}</code>", parse_mode='HTML')
        final_result = None; exact_match = False
        for item in data_found:
            clean_db_nopol = re.sub(r'[^a-zA-Z0-9]', '', item['nopol']).upper()
            if clean_db_nopol == kw: final_result = item; exact_match = True; break
        # [UPDATE v10.9: LOGIKA WAJIB KONFIRMASI (ANTI FALSE-POSITIVE)]
        if exact_match:
            # Jika 100% sama persis (B2345ABC = B2345ABC), langsung keluar datanya
            await show_unit_detail_original(update, context, final_result, u)
        else:
            # Jika tidak sama persis (Meskipun HANYA ADA 1 DATA KEMIRIPAN), 
            # TETAP paksa keluar Tombol Konfirmasi agar Matel verifikasi visual.
            await show_multi_choice(update, context, data_found, kw)
    except Exception as e: logger.error(f"Search error: {e}"); await update.message.reply_text("❌ Error DB.")

async def show_unit_detail_original(update, context, d, u):
    # --- LOGIKA CERDAS: DETEKSI VERSI DATA ---
    version_code = d.get('data_month')
    
    # Jika data_month kosong (Data Lama), ambil dari created_at
    if not version_code or version_code in ['-', None, '']:
        raw_date = d.get('created_at')
        if raw_date:
            try:
                # Parse timestamp dari Supabase (String ISO)
                # Contoh: 2026-01-25T14:30:00+00:00 -> ambil Bulan & Tahun
                dt = datetime.fromisoformat(str(raw_date).replace('Z', '+00:00'))
                version_code = dt.strftime('%m%y') # Hasil: 0126
            except:
                version_code = "-"
        else:
            version_code = "-"
    # -----------------------------------------

    txt = (
        f"🚨 <b>UNIT DITEMUKAN! (HIT)</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🚙 <b>Unit:</b> {clean_text(d.get('type', '-'))}\n"
        f"🔢 <b>Nopol:</b> {clean_text(d.get('nopol', '-'))}\n"
        f"🎨 <b>Warna:</b> {clean_text(d.get('warna', '-'))}\n"
        f"📅 <b>Tahun:</b> {clean_text(d.get('tahun', '-'))}\n"
        f"----------------------------------\n"
        f"🔧 <b>Noka:</b> {clean_text(d.get('noka', '-'))}\n"
        f"⚙️ <b>Nosin:</b> {clean_text(d.get('nosin', '-'))}\n"
        f"----------------------------------\n"
        f"🏦 <b>Finance:</b> {clean_text(d.get('finance', '-'))}\n"
        f"🗓️ <b>DATA: {version_code}</b>\n"  # <--- AKAN MUNCUL '0126' OTOMATIS
        f"⚠️ <b>OVD:</b> {clean_text(d.get('ovd', '-'))}\n"
        f"🏢 <b>Branch:</b> {clean_text(d.get('branch', '-'))}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Informasi ini BUKAN alat yang SAH untuk penarikan unit (Eksekusi).\n"
        f"Mohon untuk konfirmasi ke Pic Leasing atau Kantor."
    )
    
    # Format Share WA (Juga update agar sinkron)
    share_text = (
        f"*LAPORAN TEMUAN UNIT (ONE ASPAL)*\n"
        f"----------------------------------\n"
        f"🚙 Unit: {d.get('type', '-')}\n"
        f"🔢 Nopol: {d.get('nopol', '-')}\n"
        f"🎨 Warna: {d.get('warna', '-')}\n"
        f"📅 Tahun: {d.get('tahun', '-')}\n"
        f"🔧 Noka: {d.get('noka', '-')}\n"
        f"⚙️ Nosin: {d.get('nosin', '-')}\n"
        f"🏦 Finance: {d.get('finance', '-')}\n"
        f"🗓️ Data: {version_code}\n"
        f"⚠️ OVD: {d.get('ovd', '-')}\n"
        f"🏢 Branch: {d.get('branch', '-')}\n"
        f"📍 Lokasi: {u.get('alamat', '-')}\n"
        f"👤 Penemu: {u.get('nama_lengkap', '-')} ({u.get('agency', '-')})\n"
        f"----------------------------------\n"
        f"⚠️ *PENTING & DISCLAIMER:*\n"
        f"Informasi ini BUKAN alat yang SAH untuk penarikan unit (Eksekusi).\n"
        f"Mohon untuk konfirmasi ke Pic Leasing atau Kantor."
    )
    
    encoded_text = urllib.parse.quote(share_text)
    wa_url = f"https://wa.me/?text={encoded_text}"
    nopol_safe = d['nopol'].replace(" ", "") 
    
    kb = [
        [InlineKeyboardButton("📲 SHARE KE WA (Lapor PIC)", url=wa_url)], 
        [InlineKeyboardButton("📋 SALIN TEKS LENGKAP", callback_data=f"cp_{nopol_safe}")]
    ]
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text=txt, 
        reply_markup=InlineKeyboardMarkup(kb), 
        parse_mode='HTML'
    )
    
    await notify_hit_to_group(context, u, d)
    await notify_leasing_group(context, u, d)
    await notify_agency_group(context, u, d)
    increment_daily_usage(u['user_id'], u.get('daily_usage', 0))
    log_successful_hit(u, d)

async def show_multi_choice(update, context, data_list, keyword):
    global GLOBAL_INFO; info_txt = f"📢 INFO: {GLOBAL_INFO}\n\n" if GLOBAL_INFO else ""
    txt = f"{info_txt}🔎 Ditemukan **{len(data_list)} data** mirip '`{keyword}`':\n\n"
    keyboard = []
    for i, item in enumerate(data_list):
        nopol = item['nopol']; unit = item.get('type', 'Unknown')[:10]; leasing = item.get('finance', 'Unknown')
        btn_text = f"{nopol} | {unit} | {leasing}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"view_{item['nopol']}")])
        if i >= 9: break 
    if len(data_list) > 10: txt += "_(Menampilkan 10 hasil teratas)_"
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


# ==============================================================================
# BAGIAN 13: HANDLER KONVERSASI
# ==============================================================================

async def add_manual_start(update, context):
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return
    
    await update.message.reply_text(
        "📝 **TAMBAH DATA MANUAL (DIRECT)**\n"
        "Data yang Anda input akan **LANGSUNG TAYANG** di database.\n"
        "Pastikan data valid!\n\n"
        "1️⃣ **Ketik NOPOL Kendaraan:**\n"
        "_(Contoh: B 1234 ABC)_", 
        parse_mode='Markdown', 
        reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
    )
    return ADD_NOPOL

async def add_nopol(update, context):
    text = update.message.text
    if text == "❌ BATAL": return await cancel(update, context)
    
    # Bersihkan Nopol
    nopol_clean = re.sub(r'[^a-zA-Z0-9]', '', text).upper()
    if len(nopol_clean) < 3: 
        await update.message.reply_text("⚠️ Nopol terlalu pendek. Ketik ulang:")
        return ADD_NOPOL
        
    context.user_data['new_nopol'] = nopol_clean
    await update.message.reply_text(f"✅ Nopol: **{nopol_clean}**\n\n2️⃣ **Ketik Tipe / Merk Unit:**", parse_mode='Markdown')
    return ADD_UNIT

async def add_unit(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['new_unit'] = update.message.text.upper()
    await update.message.reply_text(f"✅ Unit: **{context.user_data['new_unit']}**\n\n3️⃣ **Ketik Nama Leasing / Finance:**", parse_mode='Markdown')
    return ADD_LEASING

async def add_leasing(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['new_finance'] = update.message.text.upper()
    
    # [REVISI] No HP Wajib Diisi (Tidak ada tombol SKIP)
    await update.message.reply_text(
        f"✅ Leasing: **{context.user_data['new_finance']}**\n\n"
        "4️⃣ **Ketik No HP / Kontak Pelapor:**\n"
        "⚠️ _Wajib diisi agar rekan lain bisa menghubungi Anda._", 
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
    )
    return ADD_PHONE

async def add_phone(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    
    # Validasi Panjang No HP
    hp = update.message.text
    if len(hp) < 5:
        await update.message.reply_text("⚠️ Nomor HP tidak valid. Masukkan nomor yang benar:")
        return ADD_PHONE
        
    context.user_data['new_phone'] = hp
    
    # Keterangan Boleh Skip
    await update.message.reply_text(
        "5️⃣ **Keterangan Tambahan (Opsional):**\n"
        "_(Lokasi, Kondisi, Warna, dll)_", 
        parse_mode='Markdown', 
        reply_markup=ReplyKeyboardMarkup([["⏩ LEWATI", "❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
    )
    return ADD_NOTE

async def add_note(update, context):
    text = update.message.text
    if text == "❌ BATAL": return await cancel(update, context)
    
    note = "-" if text == "⏩ LEWATI" else text
    context.user_data['new_note'] = note
    
    d = context.user_data
    msg = (
        f"📋 **KONFIRMASI UPLOAD**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔢 **Nopol:** {d['new_nopol']}\n"
        f"🚙 **Unit:** {d['new_unit']}\n"
        f"🏦 **Leasing:** {d['new_finance']}\n"
        f"📱 **Kontak:** {d['new_phone']}\n"
        f"📝 **Ket:** {d['new_note']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Data akan langsung ditayangkan. Lanjut?"
    )
    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["✅ UPLOAD SEKARANG", "❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True))
    return ADD_CONFIRM

async def add_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Cek konfirmasi user
    if update.message.text != "✅ UPLOAD SEKARANG": 
        return await cancel(update, context)
    
    d = context.user_data
    user = update.effective_user
    u_db = get_user(user.id)
    
    # 1. SIAPKAN DATA UTAMA
    # Mapping: Branch -> No HP, OVD -> Keterangan
    payload = {
        "nopol": d['new_nopol'], 
        "type": d['new_unit'], 
        "finance": d['new_finance'], 
        "ovd": f"{d['new_note']} (Manual Input)", 
        "branch": d['new_phone'], 
        "tahun": str(datetime.now().year), 
        "warna": "-", 
        "noka": "-", 
        "nosin": "-"
    }
    
    msg_wait = await update.message.reply_text("⏳ **Sedang menyimpan ke database...**", parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
    
    try:
        # 2. EKSEKUSI LANGSUNG KE DATABASE (Tanpa Approval)
        supabase.table('kendaraan').upsert(payload).execute()
        
        # 3. INFO SUKSES KE USER
        await msg_wait.edit_text(
            f"✅ **SUKSES! DATA TAYANG**\n\n"
            f"Unit `{d['new_nopol']}` berhasil disimpan & aktif.\n"
            f"Terima kasih atas kontribusi Anda! 🦅",
            parse_mode='Markdown'
        )
        
        # 4. NOTIFIKASI KE ADMIN (HANYA INFO)
        sender_name = clean_text(u_db.get('nama_lengkap', user.full_name))
        sender_agency = clean_text(u_db.get('agency', '-'))
        
        msg_admin = (
            f"🔔 <b>INFO: DATA BARU MASUK (MANUAL)</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Penginput:</b> {sender_name}\n"
            f"🏢 <b>Agency:</b> {sender_agency}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔢 <b>Nopol:</b> <code>{d['new_nopol']}</code>\n"
            f"🚙 <b>Unit:</b> {d['new_unit']}\n"
            f"🏦 <b>Leasing:</b> {d['new_finance']}\n"
            f"📱 <b>Kontak:</b> {d['new_phone']}\n"
            f"📝 <b>Ket:</b> {d['new_note']}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✅ <i>Data sudah otomatis tayang di database.</i>"
        )
        
        # Kirim ke Admin tanpa tombol Approval
        try:
            await context.bot.send_message(ADMIN_ID, msg_admin, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Gagal lapor admin: {e}")

    except Exception as e:
        logger.error(f"Manual Upload Error: {e}")
        await msg_wait.edit_text(f"❌ **GAGAL SIMPAN:** {e}")
        
    return ConversationHandler.END

async def lapor_delete_start(update, context):
    if not get_user(update.effective_user.id): return
    msg = ("🗑️ **LAPOR UNIT SELESAI/AMAN**\n\nAdmin akan memverifikasi laporan ini sebelum data dihapus.\n\n👉 **Masukkan Nomor Polisi (Nopol) unit:**")
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True), parse_mode='Markdown'); return L_NOPOL
async def lapor_delete_check(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    n = update.message.text.upper().replace(" ", ""); res = supabase.table('kendaraan').select("*").eq('nopol', n).execute()
    if not res.data: await update.message.reply_text(f"❌ Nopol `{n}` tidak ditemukan di database.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown'); return ConversationHandler.END
    unit_data = res.data[0]; context.user_data['lapor_nopol'] = n; context.user_data['lapor_type'] = unit_data.get('type', '-'); context.user_data['lapor_finance'] = unit_data.get('finance', '-')
    await update.message.reply_text(f"✅ **Unit Ditemukan:**\n🚙 {unit_data.get('type')}\n🏦 {unit_data.get('finance')}\n\n👉 **Masukkan ALASAN penghapusan:**", parse_mode='Markdown'); return L_REASON
async def lapor_reason(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['lapor_reason'] = update.message.text
    msg = (f"⚠️ **KONFIRMASI LAPORAN**\n\nHapus Unit: `{context.user_data['lapor_nopol']}`?\nAlasan: {context.user_data['lapor_reason']}")
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM LAPORAN", "❌ BATAL"]]), parse_mode='Markdown'); return L_CONFIRM
async def lapor_delete_confirm(update, context):
    if update.message.text != "✅ KIRIM LAPORAN": return await cancel(update, context)
    n = context.user_data['lapor_nopol']; reason = context.user_data['lapor_reason']; u = get_user(update.effective_user.id)
    await update.message.reply_text("✅ **Laporan Terkirim!** Admin sedang meninjau.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
    msg_admin = (f"🗑️ **PENGAJUAN HAPUS UNIT**\n━━━━━━━━━━━━━━━━━━\n👤 **Pelapor:** {clean_text(u.get('nama_lengkap'))}\n🏢 **Agency:** {clean_text(u.get('agency'))}\n━━━━━━━━━━━━━━━━━━\n🔢 **Nopol:** `{n}`\n🚙 **Unit:** {context.user_data['lapor_type']}\n🏦 **Leasing:** {context.user_data['lapor_finance']}\n📝 **Alasan:** {reason}\n━━━━━━━━━━━━━━━━━━")
    kb = [[InlineKeyboardButton("✅ Setujui Hapus", callback_data=f"del_acc_{n}_{u['user_id']}"), InlineKeyboardButton("❌ Tolak", callback_data=f"del_rej_{u['user_id']}")]]
    await context.bot.send_message(ADMIN_ID, msg_admin, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML'); return ConversationHandler.END

async def delete_unit_start(update, context): 
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🗑️ **HAPUS MANUAL**\nNopol:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]])); return D_NOPOL
async def delete_unit_check(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    n = update.message.text.upper().replace(" ", ""); context.user_data['del_nopol'] = n
    await update.message.reply_text(f"Hapus `{n}`?", reply_markup=ReplyKeyboardMarkup([["✅ YA", "❌ BATAL"]])); return D_CONFIRM
async def delete_unit_confirm(update, context):
    if update.message.text == "✅ YA": supabase.table('kendaraan').delete().eq('nopol', context.user_data['del_nopol']).execute(); await update.message.reply_text("✅ Terhapus.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def stop_upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['stop_signal'] = True
    await update.message.reply_text("⚠️ **Menghentikan proses...** (Tunggu sebentar)")
    return ConversationHandler.END

async def cancel(update, context): 
    context.user_data.clear()
    await update.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- MASTER CALLBACK HANDLER (CLEAN VERSION) ---
async def callback_handler(update, context):
    query = update.callback_query
    await query.answer() # Wajib agar loading di tombol hilang
    data = query.data 
    
    # [DEBUG] Cek tombol apa yang ditekan di Terminal
    print(f"🔘 Tombol Ditekan: {data}")

    # 1. STOP UPLOAD
    if data == "stop_upload_task":
        context.user_data['stop_signal'] = True
        await query.edit_message_text("🛑 <b>BERHENTI!</b>\nMenunggu proses batch terakhir selesai...", parse_mode='HTML')

    # 2. VIEW DETAIL UNIT
    elif data.startswith("view_"):
        nopol_target = data.replace("view_", "")
        u = get_user(update.effective_user.id)
        res = supabase.table('kendaraan').select("*").eq('nopol', nopol_target).execute()
        if res.data: 
            await show_unit_detail_original(update, context, res.data[0], u)
        else: 
            await query.edit_message_text("❌ Data unit sudah tidak tersedia.")
    
    # 3. MANUAL TOPUP ADMIN (PERBAIKAN FEEDBACK)
    elif data.startswith("topup_") or data.startswith("adm_topup_"):
        parts = data.split("_")
        uid = int(parts[-2])
        days_str = parts[-1] 
        
        if days_str == "rej":
            await context.bot.send_message(uid, "❌ Permintaan Topup DITOLAK Admin.")
            await query.edit_message_caption("❌ DITOLAK.")
        else:
            days = int(days_str)
            suc, new_exp = add_subscription_days(uid, days)
            
            if suc:
                exp_str = new_exp.strftime('%d %b %Y')
                
                # 1. FEEDBACK KE USER (Notifikasi)
                try:
                    msg_topup_user = (
                        f"🎉 <b>TOPUP BERHASIL DISETUJUI!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"➕ <b>Tambahan:</b> {days} Hari\n"
                        f"📅 <b>Aktif s/d:</b> {exp_str}\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"Terima kasih telah mempercayakan pencarian Anda pada <b>One Aspal Bot</b>.\n"
                        f"<i>Selamat bertugas, semoga hari ini panen unit! Salam Satu Aspal! 🦅</i>"
                    )
                    await context.bot.send_message(uid, msg_topup_user, parse_mode='HTML')
                except: pass

                # 2. FEEDBACK KE ADMIN (Visual Alert & Laporan)
                # Pop-up di layar (Toast)
                await query.answer(f"✅ SUKSES! Kuota User +{days} Hari.", show_alert=True)
                
                # Update Caption Tombol (Agar ketahuan sudah diproses)
                try:
                    await query.edit_message_caption(f"✅ SUKSES (+{days} Hari)\nExp Baru: {exp_str}")
                except Exception:
                    pass # Abaikan jika pesan tidak berubah
                
                # Laporan Chat ke Admin (Sesuai Request + Agency)
                try:
                    user_info = get_user(uid)
                    nama_user = user_info.get('nama_lengkap', 'Unknown')
                    nama_agency = user_info.get('agency', 'Tidak Ada/Mandiri')
                    
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=(
                            f"👮‍♂️ <b>LAPORAN TOPUP MANUAL</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"👤 <b>User:</b> {nama_user}\n"
                            f"🏢 <b>Agency:</b> {nama_agency}\n"
                            f"🆔 <b>ID:</b> <code>{uid}</code>\n"
                            f"➕ <b>Tambah:</b> {days} Hari\n"
                            f"📅 <b>Expired Baru:</b> {exp_str}\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"✅ <i>Transaksi Berhasil Dicatat.</i>"
                        ),
                        parse_mode='HTML'
                    )
                except: pass
                
            else: 
                await query.answer("❌ GAGAL! Cek Log Server.", show_alert=True)

    # 4. MENU PEMBAYARAN
    elif data == "buy_manual":
        msg = (
            f"🏦 <b>TRANSFER MANUAL</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"<b>BCA:</b> 1234-5678-900 (Budi Baonk)\n"
            f"<b>DANA:</b> 0812-3456-7890\n\n"
            f"👇 <b>LANGKAH SELANJUTNYA:</b>\n"
            f"1. Transfer sesuai nominal.\n"
            f"2. <b>FOTO</b> bukti transfer.\n"
            f"3. <b>KIRIM FOTO</b> ke bot ini."
        )
        await query.message.reply_text(msg, parse_mode='HTML')

    elif data.startswith("buy_"):
        await query.message.reply_text("⚠️ Fitur QRIS Otomatis sedang maintenance. Silakan gunakan Transfer Manual.")

    elif data.startswith("man_topup_"):
        uid = data.split("_")[2]
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"ℹ️ **MODE MANUAL**\n\nSilakan ketik perintah berikut:\n<code>/topup {uid} [JUMLAH_HARI]</code>", parse_mode='HTML')

    # 5. ADMIN USER MANAGEMENT
    elif data.startswith("adm_promote_"):
        uid = int(data.split("_")[2])
        supabase.table('users').update({'role': 'korlap'}).eq('user_id', uid).execute()
        await query.edit_message_text(f"✅ User {uid} DIPROMOSIKAN jadi KORLAP.")
        try: await context.bot.send_message(uid, "🎉 **SELAMAT!** Anda telah diangkat menjadi **KORLAP**.")
        except: pass
        
    elif data.startswith("adm_demote_"): 
        uid = int(data.split("_")[2])
        supabase.table('users').update({'role': 'matel'}).eq('user_id', uid).execute()
        await query.edit_message_text(f"⬇️ User {uid} DITURUNKAN jadi MATEL.")
        
    elif data == "close_panel": 
        await query.delete_message()
    
    # 6. APPROVE REGISTER (appu_)
    elif data.startswith("appu_"): 
        target_uid = int(data.split("_")[1])
        target_user = get_user(target_uid) # Ambil data pendaftaran dulu
        
        if not target_user:
            await query.answer("❌ Data user tidak ditemukan.")
            return

        now = datetime.now(TZ_JAKARTA)
        role_db = target_user.get('role', 'matel')

        # TENTUKAN EXPIRED BERDASARKAN ROLE
        if role_db == 'pic':
            final_expiry = datetime(2030, 12, 31, 23, 59, 59, tzinfo=TZ_JAKARTA)
            success_msg = f"🚀 <b>PIC {target_uid} DIAKTIFKAN</b>\n━━━━━━━━━━━━━━━\n✅ Akses Enterprise s/d 2030"
        else:
            final_expiry = now + timedelta(days=1)  # UPDATE: Trial menjadi 1 hari
            exp_display = final_expiry.strftime('%d %b %Y')
            success_msg = f"✅ <b>User {target_uid} DIAKTIFKAN</b>\n━━━━━━━━━━━━━━━\n🎁 Trial: 1 Hari/24 Jam (s/d {exp_display})"
        
        # 1. Update Database
        supabase.table('users').update({
            'status': 'active',
            'expiry_date': final_expiry.isoformat()
        }).eq('user_id', target_uid).execute()
        
        # 2. Feedback ke Admin (Satu kali saja agar tidak error)
        try:
            await query.edit_message_caption(success_msg, parse_mode='HTML')
        except:
            await query.edit_message_text(success_msg, parse_mode='HTML')
        
        # 3. Kirim notifikasi ke User
        exp_display = final_expiry.strftime('%d %b %Y')
        
        if role_db == 'pic':
            # PESAN UNTUK PIC (Enterprise Welcome)
            nama_pic = target_user.get('nama_lengkap', 'Partner')
            msg_pic = (
                f"Selamat Pagi, Pak <b>{nama_pic}</b>.\n\n"
                f"Izin memperkenalkan fitur <b>Private Enterprise</b> di OneAspal Bot.\n"
                f"Kami menyediakan <b>Private Cloud</b> agar Bapak bisa menyimpan data kendaraan dengan aman menggunakan <b>Blind Check System</b>.\n\n"
                f"🔐 <b>Keamanan Data:</b>\n"
                f"Sesuai standar POJK & UU PDP, Bapak <b>TIDAK</b> dikategorikan menyebarkan data pribadi. Bapak hanya mengarsipkan data digital untuk menunjang performa kerja internal.\n\n"
                f"Data Bapak <b>TERISOLASI</b> (Tidak bisa dilihat user lain). Sistem hanya memberi notifikasi jika unit ditemukan di lapangan.\n\n"
                f"Silakan dicoba fitur <b>Upload Data</b> di menu Sinkronisasi, Pak.\n\n"
                f"<i>Jika ada pertanyaan, silakan hubungi Bantuan Teknis.</i>"
            )
            try: await context.bot.send_message(target_uid, msg_pic, parse_mode='HTML')
            except: pass

        else:
            # PESAN UNTUK MATEL (Trial 1 Hari / 24 Jam - Full HTML)
            nama_user = target_user.get('nama_lengkap', 'Mitra')
            msg_mitra = (
                f"🦅 <b>SELAMAT BERGABUNG DI ONE ASPAL BOT</b> 🦅\n\n"
                f"Halo, <b>{nama_user}</b>! Akun Anda telah <b>DISETUJUI</b> ✅.\n\n"
                f"🎁 <b>BONUS PENDAFTARAN:</b>\n"
                f"Anda mendapatkan akses <b>TRIAL GRATIS 24 JAM</b> (1 Hari).\n"
                f"📅 <b>Aktif s/d:</b> {exp_display}\n\n"
                f"Fitur kami dirancang <b>Super Cepat</b> ⚡ dan <b>Hemat Kuota</b> 📉 untuk menunjang kinerja Anda di lapangan.\n\n"
                f"🔎 <b>CARA PENCARIAN:</b>\n"
                f"Cukup ketik NOPOL, NOKA, atau NOSIN langsung di sini.\n"
                f"Contoh: <code>B1234ABC</code>\n\n"
                f"💡 <b>MENU UTAMA:</b>\n"
                f"/cekkuota - Cek masa aktif\n"
                f"/infobayar - Perpanjang Langganan\n"
                f"/admin - Bantuan Teknis\n\n"
                f"Selamat bekerja! Salam Satu Aspal. 🏴‍☠️"
            )
            try: await context.bot.send_message(target_uid, msg_mitra, parse_mode='HTML')
            except: pass
            
    # 7. REJECT REGISTER (reju_)
    elif data.startswith("reju_"):
        target_uid = int(data.split("_")[1])
        # Hapus User
        supabase.table('users').delete().eq('user_id', target_uid).execute()
        
        try:
            await query.edit_message_caption(f"❌ User {target_uid} DITOLAK & DIHAPUS.")
        except:
            await query.edit_message_text(f"❌ User {target_uid} DITOLAK & DIHAPUS.")
            
        try: await context.bot.send_message(target_uid, "⛔ Pendaftaran Ditolak. Silakan daftar ulang dengan data yang benar.")
        except: pass
    
    # 8. COPY TEXT BUTTON
    # COPY TEXT BUTTON (Clean Version)
    elif data.startswith("cp_"):
        nopol_target = data.replace("cp_", "")
        u = get_user(update.effective_user.id)
        if not u: return
        try:
            res = supabase.table('kendaraan').select("*").eq('nopol', nopol_target).execute()
            if not res.data:
                await query.answer("❌ Data unit tidak ditemukan.", show_alert=True)
                return
            d = res.data[0]
            
            # Format Text (Sudah sesuai standar WA)
            share_text = (
                f"*LAPORAN TEMUAN UNIT (ONE ASPAL)*\n"
                f"----------------------------------\n"
                f"🚙 Unit: {d.get('type', '-')}\n"
                f"🔢 Nopol: {d.get('nopol', '-')}\n"
                f"🎨 Warna: {d.get('warna', '-')}\n"
                f"📅 Tahun: {d.get('tahun', '-')}\n"
                f"🔧 Noka: {d.get('noka', '-')}\n"
                f"⚙️ Nosin: {d.get('nosin', '-')}\n"
                f"🏦 Finance: {d.get('finance', '-')}\n"
                f"⚠️ OVD: {d.get('ovd', '-')}\n"
                f"🏢 Branch: {d.get('branch', '-')}\n"
                f"📍 Lokasi: {u.get('alamat', '-')}\n"
                f"👤 Penemu: {u.get('nama_lengkap', '-')} ({u.get('agency', '-')})\n"
                f"----------------------------------\n"
                f"⚠️ *PENTING & DISCLAIMER:*\n"
                f"Informasi ini BUKAN alat yang SAH untuk penarikan unit (Eksekusi).\n"
                f"Mohon untuk konfirmasi ke Pic Leasing atau Kantor."
            )
            
            # [REVISI] Langsung Code Block (Tanpa Kata-Kata Pengantar)
            msg_copy = f"<code>{share_text}</code>"
            
            await query.message.reply_text(msg_copy, parse_mode='HTML')
            await query.answer("✅ Teks siap disalin!")
            
        except Exception as e:
            await query.answer("❌ Gagal Copy.", show_alert=True)

    # 9. APPROVE / REJECT INPUT MANUAL
    elif data.startswith("v_acc_"): 
        parts = data.split("_")
        nopol = parts[2]
        user_id_sender = parts[3]
        item = context.bot_data.get(f"prop_{nopol}")
        if item:
            try:
                supabase.table('kendaraan').upsert(item).execute()
                del context.bot_data[f"prop_{nopol}"]
                await query.edit_message_text(f"✅ Data `{nopol}` DISETUJUI & Sudah Tayang di Database.")
                try:
                    await context.bot.send_message(user_id_sender, f"✅ **DATA DISETUJUI!**\nUnit `{nopol}` yang Anda input sudah tayang di database.", parse_mode='Markdown')
                except: pass
            except Exception as e:
                await query.edit_message_text(f"❌ Error Database: {e}")
        else:
            await query.edit_message_text("⚠️ Data kadaluwarsa (Bot sempat restart). Minta user input ulang.")

    elif data.startswith("v_rej_"):
        parts = data.split("_")
        nopol = parts[2]
        user_id_sender = parts[3]
        if f"prop_{nopol}" in context.bot_data:
            del context.bot_data[f"prop_{nopol}"]
        
        context.user_data['val_rej_nopol'] = nopol
        context.user_data['val_rej_uid'] = user_id_sender
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ **TOLAK PENGAJUAN MANUAL**\nUnit: {nopol}\n\nKetik ALASAN Penolakan:",
            reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
        )
        return VAL_REJECT_REASON

    # 10. APPROVE / REJECT LAPOR DELETE (FIX: Text Message Handling)
    elif data.startswith("del_acc_"):
        parts = data.split("_")
        nopol_target = parts[2]
        user_id_pelapor = parts[3]
        
        try:
            # 1. Hapus dari Database
            supabase.table('kendaraan').delete().eq('nopol', nopol_target).execute()
            
            # 2. Feedback Visual ke Admin (Pop-up)
            await query.answer("✅ Unit Berhasil Dihapus!", show_alert=True)
            
            # 3. Update Pesan Admin (GANTI JADI edit_message_text)
            await query.edit_message_text(
                f"✅ <b>DISETUJUI & DIHAPUS</b>\nUnit: {nopol_target} telah dibersihkan dari database.", 
                parse_mode='HTML'
            )
            
            # 4. Notifikasi ke Pelapor
            try: 
                await context.bot.send_message(user_id_pelapor, f"✅ <b>LAPORAN DISETUJUI</b>\nUnit <code>{nopol_target}</code> telah kami hapus dari database. Terima kasih kontribusinya.", parse_mode='HTML')
            except: pass
            
        except Exception as e:
            await query.answer(f"❌ Gagal Hapus: {e}", show_alert=True)

    elif data.startswith("del_rej_"):
        user_id_pelapor = data.split("_")[2]
        
        # 1. Feedback Visual
        await query.answer("❌ Laporan Ditolak.", show_alert=True)
        
        # 2. Update Pesan Admin (GANTI JADI edit_message_text)
        await query.edit_message_text("❌ <b>LAPORAN DITOLAK</b>", parse_mode='HTML')
        
        # 3. Notifikasi ke Pelapor
        try: 
            await context.bot.send_message(user_id_pelapor, "⚠️ Laporan penghapusan unit Anda ditolak oleh Admin. Data dinilai masih valid.", parse_mode='HTML')
        except: pass

# === HANDLER DOWNLOAD CENTER ===
    if data == "dl_assets":
        # Download Database Aset (PIC/Admin)
        await download_asset_data(update, context)
        
    elif data == "dl_findings":
        # Download Laporan Temuan (PIC/Admin)
        await download_finding_report(update, context)
        
    elif data == "dl_korlap_mtd":
        # Download Laporan Tim (Korlap) --> INI YANG BARU
        await download_korlap_report(update, context)

    # 11.Tambahkan logika ini di dalam fungsi callback_handler
    elif data == "copy_promo":
        promo_msg = (
            "Ijin info rekan-rekan, untuk cek data kendaraan dan update leasing terbaru "
            "sekarang lebih mudah pakai One Aspal Bot. Data update tiap hari, akurat, "
            "hemat kouta dan sangat membantu di lapangan. Yuk cek di sini: https://t.me/Oneaspal_bot"
        )
        
        # Kirim pesan dengan format <code> agar sekali sentuh langsung tersalin
        await query.message.reply_text(
            f"<code>{promo_msg}</code>", 
            parse_mode='HTML'
        )
        
        # Memberikan notifikasi kecil di atas layar Telegram
        await query.answer("✅ Pesan siap disalin!")

if __name__ == '__main__':
    # 1. Jalankan Landing Page di Background
    threading.Thread(target=run_flask, daemon=True).start()
    print("🌐 [WEB] Landing Page B-One Enterprise Running...")

    # 2. Jalankan Bot Telegram (Kode Bapak yang sudah ada)
    import asyncio
    from telegram.ext import ApplicationBuilder

    print("🚀 ONEASPAL BOT v6.60 (FINAL FIX) STARTING...")
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    
    # ==========================================================================
    # 1. STOP COMMAND (EMERGENCY)
    # ==========================================================================
    app.add_handler(CommandHandler('stop', stop_upload_command))
    
    # ==========================================================================
    # 2. FITUR KHUSUS / INTERAKTIF (CONVERSATION HANDLERS)
    # ==========================================================================
    
    # A. REGISTRASI (Perbaikan: Menangkap Foto & Dokumen Gambar)
    # --------------------------------------------------------------------------
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('register', register_start)], 
        states={
            R_ROLE_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_role_choice)], 
            R_NAMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_nama)], 
            R_HP: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_hp)], 
            R_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)], 
            R_KOTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_kota)], 
            R_AGENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_agency)], 
            R_BRANCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_branch)],
            
            # [FIX] Menerima Foto Biasa (Compressed) ATAU Dokumen Gambar (Uncompressed)
            R_PHOTO_ID: [MessageHandler(filters.PHOTO | filters.Document.IMAGE, register_photo_id)], 
            
            R_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_confirm)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]
    ))

    # B. TAMBAH DATA MANUAL (DEFINISI DULU BARU DI-ADD)
    # --------------------------------------------------------------------------
    conv_add_manual = ConversationHandler(
        entry_points=[CommandHandler('tambah', add_manual_start)], 
        states={
            ADD_NOPOL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_nopol)], 
            ADD_UNIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_unit)], 
            ADD_LEASING: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_leasing)], 
            ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)], 
            ADD_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_note)], 
            ADD_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_save)],
        }, 
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(conv_add_manual) # <--- SEKARANG AMAN KARENA SUDAH DIDEFINISIKAN DI ATAS

    # C. FORM BUKTI BAYAR (Jika user mengetik /buktibayar)
    # --------------------------------------------------------------------------
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('buktibayar', buktibayar_start)],
        states={
            WAIT_BUKTI: [
                MessageHandler(filters.PHOTO, buktibayar_process),
                MessageHandler(filters.Document.ALL, buktibayar_process)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]
    ))

    # D. FITUR ADMIN LAINNYA
    # --------------------------------------------------------------------------
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('lapor', lapor_delete_start)], 
        states={
            L_NOPOL: [MessageHandler(filters.TEXT, lapor_delete_check)], 
            L_REASON: [MessageHandler(filters.TEXT, lapor_reason)], 
            L_CONFIRM: [MessageHandler(filters.TEXT, lapor_delete_confirm)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('hapus', delete_unit_start)], 
        states={
            D_NOPOL: [MessageHandler(filters.TEXT, delete_unit_check)], 
            D_CONFIRM: [MessageHandler(filters.TEXT, delete_unit_confirm)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel)]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_action_start, pattern='^adm_(ban|unban|del)_')], 
        states={ADMIN_ACT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_action_complete)]}, 
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(reject_start, pattern='^reju_')], 
        states={REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, reject_complete)]}, 
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(val_reject_start, pattern='^v_rej_')], 
        states={VAL_REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, val_reject_complete)]}, 
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('admin', contact_admin), MessageHandler(filters.Regex('^📞 BANTUAN TEKNIS$'), contact_admin)], 
        states={SUPPORT_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_send)]}, 
        fallbacks=[CommandHandler('cancel', cancel)]
    ))

    # ==========================================================================
    # 3. COMMANDS STANDAR (ONE-SHOT)
    # ==========================================================================
    app.add_handler(MessageHandler(filters.Regex(r'^/m_\d+$'), manage_user_panel))
    app.add_handler(MessageHandler(filters.Regex(r'^/cek_\d+$'), cek_user_pending))
    app.add_handler(CommandHandler('panduan', panduan))
    app.add_handler(CommandHandler('bagikan', bagikan_bot))
    app.add_handler(CommandHandler('adminhelp', admin_help)) 
    app.add_handler(CommandHandler('setinfo', set_info)) 
    app.add_handler(CommandHandler('delinfo', del_info)) 
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('cancel', cancel)) # <--- TAMBAHAN: RESET GLOBAL
    app.add_handler(CommandHandler('cekkuota', cek_kuota))
    app.add_handler(CommandHandler('infobayar', info_bayar))
    app.add_handler(CommandHandler('buktibayar', panduan_buktibayar)) # Fallback command
    app.add_handler(CommandHandler('topup', admin_topup))
    app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('leasing', get_leasing_list)) 
    app.add_handler(CommandHandler('rekapanggota', rekap_anggota_korlap))
    app.add_handler(CommandHandler("rekap_member", rekap_member))
    app.add_handler(CommandHandler("cekagency", rekap_handler))
    app.add_handler(MessageHandler(filters.Regex(r'(?i)^/rekap'), rekap_handler))    
    app.add_handler(CommandHandler('users', list_users))
    app.add_handler(CommandHandler('angkat_korlap', angkat_korlap)) 
    app.add_handler(CommandHandler('testgroup', test_group))
    app.add_handler(CommandHandler('balas', admin_reply))
    app.add_handler(CommandHandler('setgroup', set_leasing_group)) 
    app.add_handler(CommandHandler('setagency', set_agency_group))
    app.add_handler(CommandHandler('addagency', add_agency)) 
    app.add_handler(CommandHandler('dashboard', request_dashboard))
    app.add_handler(CommandHandler('reset_dashboard', reset_dashboard))

    # ==========================================================================
    # 4. HANDLER UMUM / CATCH-ALL (HARUS DITARUH PALING BAWAH!)
    # ==========================================================================
    
    # A. Menangkap Foto Langsung (Auto Topup)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_topup))

    # B. Menangkap File Dokumen (Upload Data Excel / Topup File)
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Document.ALL, upload_start)],
        states={
            U_LEASING_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_leasing_user)],
            U_LEASING_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_leasing_admin)],
            U_CONFIRM_UPLOAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_confirm_admin)]
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]
    ))
    
    # C. Callback & Text Chat (Terakhir)
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("⏰ Jadwal Cleanup Otomatis: AKTIF (Jam 03:00 WIB)")
    print("🚀 ONEASPAL BOT v6.60 (READY TO SERVE) RUNNING...")
    app.run_polling()