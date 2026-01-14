import os
import logging
import pandas as pd
import io
import numpy as np
import time
import re
import asyncio 
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, constants
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

# ==============================================================================
#                        1. KONFIGURASI SISTEM & ENVIRONMENT
# ==============================================================================

# Load environment variables dari file .env
load_dotenv()

# Konfigurasi Logging agar kita bisa melihat status bot di terminal
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# Mengambil Credential dari Environment Variable
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
token: str = os.environ.get("TELEGRAM_TOKEN")

# Variable Global untuk menyimpan Info Pengumuman (Sticky Message)
GLOBAL_INFO = ""

# Setup Admin ID (Fallback ke default jika tidak ada di .env)
DEFAULT_ADMIN_ID = 7530512170
try:
    env_id = os.environ.get("ADMIN_ID")
    ADMIN_ID = int(env_id) if env_id else DEFAULT_ADMIN_ID
except ValueError:
    ADMIN_ID = DEFAULT_ADMIN_ID

print(f"✅ SYSTEM CHECK: ADMIN ID = {ADMIN_ID}")

# ID Group Log untuk notifikasi HIT (Ganti ID ini sesuai grup Anda)
LOG_GROUP_ID = -1003627047676  

# Validasi Kelengkapan Credential Database
if not url or not key or not token:
    print("❌ CRITICAL ERROR: Credential tidak lengkap. Cek file .env Anda.")
    print("Pastikan SUPABASE_URL, SUPABASE_KEY, dan TELEGRAM_TOKEN sudah terisi.")
    exit()

# Inisialisasi Koneksi ke Supabase
try:
    supabase: Client = create_client(url, key)
    print("✅ DATABASE: Koneksi Supabase Berhasil!")
except Exception as e:
    print(f"❌ DATABASE ERROR: Gagal koneksi ke Supabase. Pesan: {e}")
    exit()


# ==============================================================================
#                        2. KAMUS DATA & DEFINISI STATE
# ==============================================================================

# --- KAMUS ALIAS KOLOM (NORMALISASI AGRESIF) ---
# Digunakan untuk mencocokkan header Excel yang berantakan menjadi standar.
# Semua alias ditulis dalam HURUF KECIL TANPA SPASI/SIMBOL.
COLUMN_ALIASES = {
    'nopol': [
        'nopolisi', 'nomorpolisi', 'nopol', 'noplat', 'nomorplat', 
        'nomorkendaraan', 'nokendaraan', 'nomer', 'tnkb', 'licenseplate', 
        'plat', 'nopolisikendaraan', 'nopil', 'polisi'
    ],
    'type': [
        'type', 'tipe', 'unit', 'model', 'vehicle', 'jenis', 
        'deskripsiunit', 'merk', 'object', 'kendaraan', 'item', 'brand',
        'typedeskripsi', 'vehiclemodel', 'namaunit', 'kend'
    ],
    'tahun': [
        'tahun', 'year', 'thn', 'rakitan', 'th', 'yearofmanufacture', 'thnrakit'
    ],
    'warna': [
        'warna', 'color', 'colour', 'cat', 'kelir'
    ],
    'noka': [
        'noka', 'norangka', 'nomorrangka', 'chassis', 'chasis', 
        'vin', 'rangka', 'chassisno', 'norangka1', 'chasisno'
    ],
    'nosin': [
        'nosin', 'nomesin', 'nomormesin', 'engine', 'mesin', 
        'engineno', 'nomesin1', 'engineno'
    ],
    'finance': [
        'finance', 'leasing', 'lising', 'multifinance', 'cabang', 
        'partner', 'mitra', 'principal', 'company', 'client', 'financecompany',
        'leasingname', 'keterangan'
    ],
    'ovd': [
        'ovd', 'overdue', 'dpd', 'keterlambatan', 'hari', 
        'telat', 'aging', 'od', 'bucket', 'daysoverdue', 'overduedays',
        'kiriman', 'kolektibilitas'
    ],
    'branch': [
        'branch', 'area', 'kota', 'pos', 'cabang', 
        'lokasi', 'wilayah', 'region', 'areaname', 'branchname'
    ]
}

# --- DEFINISI STATE CONVERSATION HANDLER ---
# State untuk Percakapan Registrasi
R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_CONFIRM = range(6)

# State untuk Percakapan Tambah Data Manual
A_NOPOL, A_TYPE, A_LEASING, A_NOKIR, A_CONFIRM = range(6, 11)

# State untuk Percakapan Lapor Hapus
L_NOPOL, L_CONFIRM = range(11, 13) 

# State untuk Percakapan Hapus Data (Admin)
D_NOPOL, D_CONFIRM = range(13, 15)

# State untuk Percakapan Smart Upload
U_LEASING_USER, U_LEASING_ADMIN, U_CONFIRM_UPLOAD = range(15, 18)


# ==============================================================================
#                        3. DATABASE & HELPER FUNCTIONS
# ==============================================================================

async def post_init(application: Application):
    """
    Fungsi ini dipanggil otomatis saat bot dinyalakan.
    Tugasnya memasang Menu Button di samping kolom chat Telegram.
    """
    await application.bot.set_my_commands([
        ("start", "🔄 Restart / Menu Utama"),
        ("cekkuota", "💳 Cek Sisa Kuota"),
        ("tambah", "➕ Tambah Unit Manual"),
        ("lapor", "🗑️ Lapor Unit Selesai"),
        ("register", "📝 Daftar Mitra Baru"),
        ("admin", "📩 Hubungi Admin"),
        ("panduan", "📖 Petunjuk Penggunaan"),
    ])
    print("✅ TELEGRAM: Menu Perintah Berhasil Di-set!")

def get_user(user_id):
    """
    Mengambil data user dari tabel 'users' berdasarkan user_id Telegram.
    Returns: Dict user data atau None jika tidak ada.
    """
    try:
        response = supabase.table('users').select("*").eq('user_id', user_id).execute()
        if response.data:
            return response.data[0]
        else:
            return None
    except Exception as e:
        logging.error(f"DB Error get_user: {e}")
        return None

def update_user_status(user_id, status):
    """
    Mengupdate status user (active/rejected/pending).
    """
    try:
        supabase.table('users').update({'status': status}).eq('user_id', user_id).execute()
        print(f"✅ User {user_id} status updated to {status}")
    except Exception as e: 
        logging.error(f"Error update status: {e}")

def update_quota_usage(user_id, current_quota):
    """
    Mengurangi kuota user sebanyak 1 poin setelah HIT sukses.
    """
    try:
        new_quota = current_quota - 1
        supabase.table('users').update({'quota': new_quota}).eq('user_id', user_id).execute()
    except Exception as e:
        logging.error(f"Error update quota: {e}")

def topup_quota(user_id, amount):
    """
    Fungsi untuk Admin menambah kuota user secara manual.
    """
    try:
        user = get_user(user_id)
        if user:
            current = user.get('quota', 0)
            new_total = current + amount
            supabase.table('users').update({'quota': new_total}).eq('user_id', user_id).execute()
            return True, new_total
        return False, 0
    except Exception as e:
        logging.error(f"Error topup: {e}")
        return False, 0

# --- FUNGSI PEMBERSIH TEKS (NUCLEAR NORMALIZER) ---
def normalize_text(text):
    """
    Membersihkan teks dari spasi, titik, koma, underscore, dan simbol lain.
    Hanya menyisakan huruf dan angka (alfanumerik) lowercase.
    Contoh: 'No. Polisi' -> 'nopolisi'
    Contoh: 'Type_Kendaraan' -> 'typekendaraan'
    """
    if not isinstance(text, str): 
        return str(text).lower()
    # Hapus karakter non-alfanumerik menggunakan Regex
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()

def smart_rename_columns(df):
    """
    Fungsi pintar untuk menstandarkan nama kolom DataFrame.
    Mencocokkan header file user dengan KAMUS ALIAS.
    """
    new_cols = {}
    found_cols = []
    
    # Loop setiap kolom asli dari Excel
    for original_col in df.columns:
        # 1. Bersihkan nama kolom asli seagresif mungkin
        clean_col = normalize_text(original_col)
        renamed = False
        
        # 2. Cek di kamus alias
        for standard_name, aliases in COLUMN_ALIASES.items():
            # Cek jika clean_col ada di dalam list alias (yg juga sudah bersih)
            if clean_col == standard_name or clean_col in aliases:
                new_cols[original_col] = standard_name
                found_cols.append(standard_name)
                renamed = True
                break
        
        # 3. Jika tidak ada di alias, biarkan nama aslinya
        if not renamed:
            new_cols[original_col] = original_col

    # Rename kolom di DataFrame
    df.rename(columns=new_cols, inplace=True)
    return df, found_cols

def read_file_robust(file_content, file_name):
    """
    Mencoba berbagai strategi encoding untuk membaca file Excel/CSV yang bandel.
    Ini mengatasi masalah file CSV dari Windows lama atau exportan sistem bank.
    """
    # Strategi 1: Jika file Excel (.xlsx / .xls)
    if file_name.lower().endswith(('.xlsx', '.xls')):
        try:
            return pd.read_excel(io.BytesIO(file_content), dtype=str)
        except Exception as e:
            raise ValueError(f"Gagal baca Excel: {e}")

    # Strategi 2: Jika CSV, coba kombinasi encoding & separator
    # Urutan prioritas: utf-8-sig (Excel CSV Modern), utf-8, latin1 (Windows Lama)
    encodings_to_try = ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']
    separators_to_try = [';', ',', '\t', '|']
    
    for enc in encodings_to_try:
        for sep in separators_to_try:
            try:
                # Reset pointer file stream
                file_stream = io.BytesIO(file_content)
                df = pd.read_csv(file_stream, sep=sep, dtype=str, encoding=enc)
                
                # Validasi sederhana: Jika kolomnya > 1, kemungkinan berhasil baca
                if len(df.columns) > 1:
                    print(f"✅ File terbaca dengan encoding: {enc} dan separator: {sep}")
                    return df
            except:
                continue
    
    # Strategi 3: Last Resort (Python Engine Auto-detect)
    try:
        return pd.read_csv(io.BytesIO(file_content), sep=None, engine='python', dtype=str)
    except Exception as e:
        raise ValueError("File tidak terbaca dengan semua metode encoding yang tersedia.")


# ==============================================================================
#                 4. HANDLER FITUR DASAR (KUOTA, TOPUP, ADMIN)
# ==============================================================================

async def cek_kuota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Menampilkan sisa kuota dan informasi akun user.
    """
    user_id = update.effective_user.id
    u = get_user(user_id)
    
    if not u or u['status'] != 'active': 
        return await update.message.reply_text("⛔ Akun Anda belum terdaftar atau belum aktif.")
    
    msg = (
        f"💳 **INFO AKUN MITRA**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Nama:** {u.get('nama_lengkap')}\n"
        f"🏢 **Agency:** {u.get('agency')}\n"
        f"📱 **ID:** `{u.get('user_id')}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔋 **SISA KUOTA:** `{u.get('quota', 0)}` HIT\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 _Kuota hanya berkurang jika data ditemukan (HIT). Pencarian ZONK tidak memotong kuota._"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def admin_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Fitur Admin untuk menambah kuota user secara manual.
    Format: /topup [User_ID] [Jumlah]
    """
    if update.effective_user.id != ADMIN_ID: 
        return # Abaikan jika bukan admin
    
    try:
        # Cek argumen
        args = context.args
        if len(args) < 2:
            return await update.message.reply_text(
                "⚠️ **Format Salah!**\n\n"
                "Gunakan: `/topup [User_ID] [Jumlah]`\n"
                "Contoh: `/topup 12345678 100`", 
                parse_mode='Markdown'
            )
        
        target_id = args[0]
        amount = int(args[1])
        
        success, new_balance = topup_quota(target_id, amount)
        
        if success:
            await update.message.reply_text(
                f"✅ **TOPUP SUKSES**\n"
                f"User ID: `{target_id}`\n"
                f"Tambah: +{amount}\n"
                f"Total Baru: {new_balance}", 
                parse_mode='Markdown'
            )
            # Kirim notifikasi ke User yang di-topup
            try:
                await context.bot.send_message(
                    chat_id=target_id, 
                    text=f"🎉 **KUOTA BERTAMBAH!**\n\nAdmin telah menambahkan +{amount} kuota ke akun Anda.\nTotal Kuota Saat Ini: {new_balance}\n\nSelamat bekerja kembali! 🚙💨"
                )
            except: 
                pass # Abaikan jika user memblokir bot
        else:
            await update.message.reply_text("❌ Gagal. Pastikan ID User benar dan sudah terdaftar.")
            
    except ValueError:
        await update.message.reply_text("⚠️ Jumlah harus berupa angka.")


# ==============================================================================
#                 5. FITUR SMART UPLOAD (DIAGNOSTIC MODE)
# ==============================================================================

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler awal saat file dokumen diterima.
    Mendukung CSV dan Excel.
    """
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    document = update.message.document
    file_name = document.file_name

    # Cek Validitas User
    if not user_data or user_data['status'] != 'active':
        if user_id != ADMIN_ID: 
            return await update.message.reply_text("⛔ **AKSES DITOLAK**\nAnda belum terdaftar aktif.")

    # Status Typing/Uploading
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.UPLOAD_DOCUMENT)
    
    # Simpan info file sementara di memory context
    context.user_data['upload_file_id'] = document.file_id
    context.user_data['upload_file_name'] = file_name

    # --- ALUR 1: USER BIASA (Forward ke Admin) ---
    if user_id != ADMIN_ID:
        await update.message.reply_text(
            f"📄 File `{file_name}` diterima.\n\n"
            "Satu langkah lagi: **Ini data dari Leasing/Finance apa?**\n"
            "(Contoh: BCA, Mandiri, Adira, Balimor)",
            parse_mode='Markdown', 
            reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)
        )
        return U_LEASING_USER

    # --- ALUR 2: ADMIN (SMART PROCESSING) ---
    else:
        msg = await update.message.reply_text("⏳ **Membaca file (Mode: Robust)...**")
        
        try:
            # Download file dari Telegram
            new_file = await document.get_file()
            file_content = await new_file.download_as_bytearray()
            
            # 1. BACA FILE DENGAN FUNGSI ROBUST (Anti-BOM & Anti-Encoding Error)
            df = read_file_robust(file_content, file_name)
            
            # 2. NORMALISASI HEADER (Anti-Spasi & Typo)
            df, found_cols = smart_rename_columns(df)
            
            # Simpan dataframe ke context
            context.user_data['df_records'] = df.to_dict(orient='records')
            
            # 3. VALIDASI KOLOM NOPOL (Wajib Ada)
            if 'nopol' not in df.columns:
                cols_detected = ", ".join(df.columns[:5])
                await msg.edit_text(
                    "❌ **GAGAL DETEKSI NOPOL**\n\n"
                    f"Kolom terbaca: {cols_detected}\n"
                    "👉 Pastikan ada kolom: 'No Polisi', 'Plat', 'TNKB' (Titik/Spasi tidak masalah)."
                )
                return ConversationHandler.END

            # Cek kolom finance
            has_finance = 'finance' in df.columns
            
            report = (
                f"✅ **SMART SCAN SUKSES**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Kolom Dikenali:** {', '.join(found_cols)}\n"
                f"📁 **Total Baris:** {len(df)}\n"
                f"🏦 **Kolom Leasing:** {'✅ ADA' if has_finance else '⚠️ TIDAK ADA'}\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"👉 **MASUKKAN NAMA LEASING UNTUK DATA INI:**\n"
                f"_(Ketik 'SKIP' jika ingin menggunakan kolom leasing dari file)_"
            )
            await msg.edit_text(report, parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
            return U_LEASING_ADMIN

        except Exception as e:
            await msg.edit_text(f"❌ Gagal memproses file: {str(e)}")
            return ConversationHandler.END

async def upload_leasing_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler untuk User Biasa: Memasukkan nama leasing sebelum diforward ke Admin.
    """
    leasing_name = update.message.text
    if leasing_name == "❌ BATAL": 
        await update.message.reply_text("🚫 Upload dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    file_id = context.user_data.get('upload_file_id')
    file_name = context.user_data.get('upload_file_name')
    user = get_user(update.effective_user.id)

    # Kirim ke Admin
    caption_admin = (
        f"📥 **UPLOAD FILE MITRA**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Pengirim:** {user.get('nama_lengkap')}\n"
        f"🏦 **Leasing:** {leasing_name.upper()}\n"
        f"📄 **File:** `{file_name}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👉 _Silakan download dan upload ulang file ini ke bot untuk memproses._"
    )
    await context.bot.send_document(chat_id=ADMIN_ID, document=file_id, caption=caption_admin, parse_mode='Markdown')
    
    await update.message.reply_text("✅ Terkirim ke Admin.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def upload_leasing_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler untuk Admin: Inject Nama Leasing & Preview Data.
    """
    leasing_input = update.message.text
    
    # Ambil data dari memory
    df = pd.DataFrame(context.user_data['df_records'])
    
    # Logic Inject Leasing Name
    final_leasing_name = leasing_input.upper()
    if final_leasing_name != 'SKIP':
        df['finance'] = final_leasing_name
    elif 'finance' not in df.columns:
        final_leasing_name = "UNKNOWN (AUTO)"
        df['finance'] = 'UNKNOWN'
    else:
        final_leasing_name = "SESUAI FILE"

    # Standardisasi Nopol (Hapus semua simbol aneh, uppercase)
    # Contoh: "B 1234 ABC" -> "B1234ABC"
    df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
    
    # Hapus Duplikat (Ambil data terbaru)
    df = df.drop_duplicates(subset=['nopol'], keep='last').replace({np.nan: None})
    
    # Filter hanya kolom yang sesuai database Supabase
    valid_cols_db = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch']
    for col in valid_cols_db:
        if col not in df.columns: df[col] = None
    
    # Ambil sampel untuk preview
    sample = df.iloc[0]
    
    # Simpan data final yang siap upload
    context.user_data['final_data_records'] = df[valid_cols_db].to_dict(orient='records')
    context.user_data['final_leasing_name'] = final_leasing_name
    
    preview_msg = (
        f"🔎 **PREVIEW DATA (SAFEGUARD)**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏦 **Leasing:** {final_leasing_name}\n"
        f"📊 **Total:** {len(df)} Unit\n\n"
        f"📝 **CONTOH DATA BARIS 1:**\n"
        f"🔹 Nopol: `{sample['nopol']}`\n"
        f"🔹 Unit: {sample['type']}\n"
        f"🔹 Noka: {sample['noka']}\n"
        f"🔹 OVD: {sample['ovd']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Klik **EKSEKUSI** jika data di atas benar."
    )
    
    await update.message.reply_text(
        preview_msg, 
        parse_mode='Markdown', 
        reply_markup=ReplyKeyboardMarkup([["🚀 EKSEKUSI", "❌ BATAL"]], one_time_keyboard=True)
    )
    return U_CONFIRM_UPLOAD

async def upload_confirm_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler Admin: Eksekusi Upload ke Database dengan DIAGNOSTIC REPORTING.
    """
    choice = update.message.text
    if choice != "🚀 EKSEKUSI":
        await update.message.reply_text("🚫 Dibatalkan.", reply_markup=ReplyKeyboardRemove())
        context.user_data.pop('final_data_records', None)
        return ConversationHandler.END
    
    status_msg = await update.message.reply_text("⏳ **Sedang mengupload ke database...**", reply_markup=ReplyKeyboardRemove())
    
    final_data = context.user_data.get('final_data_records')
    
    success_count = 0
    fail_count = 0
    last_error_msg = "" # Variable untuk menangkap pesan error asli dari Supabase
    BATCH_SIZE = 1000
    
    # Loop Batch Upload
    for i in range(0, len(final_data), BATCH_SIZE):
        batch = final_data[i : i + BATCH_SIZE]
        try:
            # Upsert: Insert or Update if exists
            supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
            success_count += len(batch)
        except Exception as e:
            last_error_msg = str(e) # Tangkap error level batch
            
            # Jika batch gagal, coba retry satu per satu (Fallback)
            for item in batch:
                try:
                    supabase.table('kendaraan').upsert([item], on_conflict='nopol').execute()
                    success_count += 1
                except Exception as inner_e:
                    fail_count += 1
                    last_error_msg = str(inner_e) # Tangkap error level item

    # Buat Laporan Akhir
    if fail_count > 0:
        report = (
            f"❌ **ADA ERROR SAAT UPLOAD!**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✅ Sukses: {success_count}\n"
            f"❌ Gagal: {fail_count}\n\n"
            f"🔍 **DIAGNOSA ERROR DATABASE:**\n"
            f"`{last_error_msg[:300]}...`\n\n"
            f"💡 _Tips: Jika errornya 'duplicate key' atau 'permission denied', cek settingan RLS dan Primary Key di Supabase._"
        )
    else:
        report = (
            f"✅ **UPLOAD SELESAI SEMPURNA!**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 **Total Upload:** {success_count}\n"
            f"❌ **Gagal:** 0"
        )
        
    await status_msg.edit_text(report, parse_mode='Markdown')
    
    # Bersihkan memori
    context.user_data.pop('final_data_records', None)
    return ConversationHandler.END


# ==============================================================================
#                 6. FITUR ADMIN EKSKLUSIF (STATS, USER MANAGEMENT)
# ==============================================================================

async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Menampilkan statistik total data dan user.
    """
    if update.effective_user.id != ADMIN_ID: return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
    msg_wait = await update.message.reply_text("⏳ *Sedang menghitung seluruh data...*")

    try:
        # Hitung Total Unit
        res_total = supabase.table('kendaraan').select("*", count="exact", head=True).execute()
        total_unit = res_total.count if res_total.count else 0

        # Hitung Total User
        res_users = supabase.table('users').select("*", count="exact", head=True).execute()
        total_user = res_users.count if res_users.count else 0

        msg = (
            f"📊 **STATISTIK ONEASPAL**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📂 **Total Data Kendaraan:** `{total_unit:,}` Unit\n"
            f"👥 **Total Mitra Terdaftar:** `{total_user:,}` User"
        )
        await msg_wait.edit_text(msg, parse_mode='Markdown')

    except Exception as e:
        logging.error(f"Stats Error: {e}")
        await msg_wait.edit_text(f"❌ Error mengambil statistik: {e}")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Menampilkan daftar 20 user terakhir yang mendaftar.
    """
    if update.effective_user.id != ADMIN_ID: return
    try:
        res = supabase.table('users').select("*").order('created_at', desc=True).limit(20).execute()
        if not res.data: return await update.message.reply_text("Belum ada user terdaftar.")
        
        msg = "📋 **DAFTAR 20 USER TERBARU**\n\n"
        for u in res.data:
            icon = "✅" if u['status'] == 'active' else "⏳"
            if u['status'] == 'rejected': icon = "⛔"
            
            msg += f"{icon} `{u['user_id']}` | {u.get('nama_lengkap','-')}\n"
            
        await update.message.reply_text(msg, parse_mode='Markdown')
    except: await update.message.reply_text("Gagal mengambil data user.")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Memblokir user agar tidak bisa menggunakan bot.
    """
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        update_user_status(uid, 'rejected')
        await update.message.reply_text(f"⛔ User `{uid}` BERHASIL DI-BAN.")
    except: await update.message.reply_text("⚠️ Format: `/ban ID`")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Membuka blokir user.
    """
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        update_user_status(uid, 'active')
        await update.message.reply_text(f"✅ User `{uid}` BERHASIL DI-UNBAN.")
    except: await update.message.reply_text("⚠️ Format: `/unban ID`")

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Menghapus user permanen dari database.
    """
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        supabase.table('users').delete().eq('user_id', uid).execute()
        await update.message.reply_text(f"🗑️ User `{uid}` DIHAPUS PERMANEN.")
    except: await update.message.reply_text("⚠️ Format: `/delete ID`")

async def test_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Mengetes apakah bot bisa mengirim pesan ke Group Log.
    """
    if update.effective_user.id != ADMIN_ID: return
    try:
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text="🔔 **TES NOTIFIKASI GROUP OK!**\nBot berfungsi dengan baik.")
        await update.message.reply_text("✅ Notifikasi terkirim ke Group Log.")
    except: await update.message.reply_text("❌ Gagal kirim ke Group Log. Cek ID Group & Pastikan Bot sudah jadi Admin di sana.")

# ==============================================================================
#                 7. FITUR INFO, KONTAK, & NOTIFIKASI
# ==============================================================================

async def set_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set pengumuman sticky di perintah /start"""
    global GLOBAL_INFO
    if update.effective_user.id != ADMIN_ID: return
    msg = " ".join(context.args)
    if not msg: 
        return await update.message.reply_text("⚠️ Contoh: `/setinfo 🔥 Bonus Hari Ini!`", parse_mode='Markdown')
    
    GLOBAL_INFO = msg
    await update.message.reply_text(f"✅ **Info Terpasang!**\n{GLOBAL_INFO}", parse_mode='Markdown')

async def del_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GLOBAL_INFO
    if update.effective_user.id != ADMIN_ID: return
    GLOBAL_INFO = ""
    await update.message.reply_text("🗑️ Info dihapus.")

async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User mengirim pesan ke Admin"""
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return
    
    msg_content = " ".join(context.args)
    if not msg_content: 
        return await update.message.reply_text("⚠️ Contoh: `/admin Lapor error...`", parse_mode='Markdown')
    
    try:
        report = (f"📩 **PESAN DARI MITRA**\n👤 {u.get('nama_lengkap')}\n📱 `{u.get('user_id')}`\n💬 {msg_content}")
        await context.bot.send_message(chat_id=ADMIN_ID, text=report)
        await update.message.reply_text("✅ Terkirim ke Admin.")
    except: 
        await update.message.reply_text("❌ Gagal mengirim pesan.")

async def notify_hit_to_group(context: ContextTypes.DEFAULT_TYPE, user_data, vehicle_data):
    """Mengirim notifikasi ke Group Log saat unit ditemukan (HIT)"""
    hp_raw = user_data.get('no_hp', '-')
    hp_wa = '62' + hp_raw[1:] if hp_raw.startswith('0') else hp_raw
    
    report_text = (
        f"🚨 **UNIT DITEMUKAN! (HIT)**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Penemu:** {user_data.get('nama_lengkap')} ({user_data.get('agency')})\n"
        f"📍 **Kota:** {user_data.get('kota', '-')}\n\n"
        f"🚙 **Unit:** {vehicle_data.get('type', '-')}\n"
        f"🔢 **Nopol:** `{vehicle_data.get('nopol', '-')}`\n"
        f"📅 **Tahun:** {vehicle_data.get('tahun', '-')}\n"
        f"🎨 **Warna:** {vehicle_data.get('warna', '-')}\n"
        f"----------------------------------\n"
        f"🔧 **Noka:** `{vehicle_data.get('noka', '-')}`\n"
        f"⚙️ **Nosin:** `{vehicle_data.get('nosin', '-')}`\n"
        f"----------------------------------\n"
        f"⚠️ **OVD:** {vehicle_data.get('ovd', '-')}\n"
        f"🏦 **Finance:** {vehicle_data.get('finance', '-')}\n"
        f"🏢 **Branch:** {vehicle_data.get('branch', '-')}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    keyboard = [[InlineKeyboardButton("📞 Hubungi Penemu (WA)", url=f"https://wa.me/{hp_wa}")]]
    try: 
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text=report_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except: pass

async def panduan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text_panduan = (
        "📖 **PANDUAN ONEASPAL**\n\n"
        "1️⃣ **CARI DATA**\n"
        "Ketik Nopol/Noka/Nosin tanpa spasi.\n"
        "✅ Contoh: `1234ABC` (Tanpa huruf depan)\n"
        "✅ Contoh: `B1234ABC` (Lengkap)\n\n"
        "2️⃣ **CEK KUOTA:** `/cekkuota`\n"
        "3️⃣ **TAMBAH DATA:** `/tambah`\n"
        "4️⃣ **LAPOR SELESAI:** `/lapor`\n"
        "5️⃣ **KONTAK ADMIN:** `/admin [pesan]`\n"
        "6️⃣ **UPLOAD:** Kirim file Excel ke chat bot langsung."
    )
    await update.message.reply_text(text_panduan, parse_mode='Markdown')


# ==============================================================================
#                 8. HANDLER CONVERSATION: LAPOR, HAPUS, REGISTER, TAMBAH
# ==============================================================================

# --- LAPOR HAPUS (USER) ---
async def lapor_delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return await update.message.reply_text("⛔ Akses ditolak.")
    
    await update.message.reply_text(
        "🗑️ **LAPOR UNIT SELESAI/AMAN**\n\n"
        "Anda melaporkan bahwa unit sudah **Selesai/Lunas** dari Leasing.\n"
        "Admin akan memverifikasi laporan ini sebelum data dihapus.\n\n"
        "👉 Masukkan **Nomor Polisi (Nopol)** unit:",
        reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True),
        parse_mode='Markdown'
    )
    return L_NOPOL

async def lapor_delete_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nopol_input = update.message.text.upper().replace(" ", "")
    try:
        res = supabase.table('kendaraan').select("*").eq('nopol', nopol_input).execute()
        if not res.data: 
            await update.message.reply_text(f"❌ Nopol `{nopol_input}` tidak ditemukan di database.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
            return ConversationHandler.END
        
        unit = res.data[0]
        context.user_data['lapor_nopol'] = nopol_input
        await update.message.reply_text(f"⚠️ Lapor Hapus `{unit['nopol']}` ({unit.get('type')})?", reply_markup=ReplyKeyboardMarkup([["✅ KIRIM LAPORAN", "❌ BATAL"]], one_time_keyboard=True), parse_mode='Markdown')
        return L_CONFIRM
    except: 
        return ConversationHandler.END

async def lapor_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ BATAL": 
        await update.message.reply_text("🚫 Dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    if update.message.text == "✅ KIRIM LAPORAN":
        nopol = context.user_data.get('lapor_nopol')
        user = get_user(update.effective_user.id)
        
        await update.message.reply_text(f"✅ Laporan `{nopol}` terkirim.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
        
        kb = [
            [InlineKeyboardButton("✅ Setujui", callback_data=f"del_acc_{nopol}_{update.effective_user.id}")],
            [InlineKeyboardButton("❌ Tolak", callback_data=f"del_rej_{update.effective_user.id}")]
        ]
        
        admin_msg = (
            f"🗑️ **REQUEST PENGHAPUSAN UNIT**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 **Pelapor:** {user.get('nama_lengkap')}\n"
            f"🏢 **Agency:** {user.get('agency')}\n"
            f"🔢 **Nopol:** `{nopol}`\n"
            f"📝 **Status:** Laporan Selesai/Aman\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👉 Klik **Setujui** untuk menghapus data ini dari database PERMANEN."
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    
    return ConversationHandler.END

# --- HAPUS MANUAL (ADMIN) ---
async def delete_unit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return await update.message.reply_text("⛔ Admin Only.")
    await update.message.reply_text("🗑️ **HAPUS MANUAL**\nMasukkan Nopol:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return D_NOPOL

async def delete_unit_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nopol_input = update.message.text.upper().replace(" ", "")
    try:
        res = supabase.table('kendaraan').select("*").eq('nopol', nopol_input).execute()
        if not res.data: 
            await update.message.reply_text(f"❌ Nopol `{nopol_input}` tidak ada.", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        
        unit = res.data[0]
        context.user_data['del_nopol'] = nopol_input
        await update.message.reply_text(f"⚠️ Hapus Permanen `{unit['nopol']}`?", reply_markup=ReplyKeyboardMarkup([["✅ YA, HAPUS", "❌ BATAL"]], one_time_keyboard=True), parse_mode='Markdown')
        return D_CONFIRM
    except: 
        return ConversationHandler.END

async def delete_unit_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ BATAL": 
        await update.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    if update.message.text == "✅ YA, HAPUS":
        nopol = context.user_data.get('del_nopol')
        supabase.table('kendaraan').delete().eq('nopol', nopol).execute()
        await update.message.reply_text(f"✅ `{nopol}` DIHAPUS.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
    
    return ConversationHandler.END

# --- REGISTRASI (FULL STEP) ---
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user:
        if user['status'] == 'pending': 
            return await update.message.reply_text("⏳ Pendaftaran Anda masih **MENUNGGU VERIFIKASI** Admin.")
        elif user['status'] == 'active': 
            return await update.message.reply_text("✅ Anda sudah terdaftar dan **AKTIF**.")
        else: 
            return await update.message.reply_text("⛔ Pendaftaran Anda sebelumnya **DITOLAK**.")
            
    await update.message.reply_text("📝 **PENDAFTARAN MITRA**\n\n1️⃣ Masukkan **NAMA LENGKAP**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return R_NAMA

async def register_nama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['r_nama'] = update.message.text
    await update.message.reply_text("2️⃣ Masukkan **NO HP (WA)**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return R_HP

async def register_hp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['r_hp'] = update.message.text
    await update.message.reply_text("3️⃣ Masukkan **EMAIL**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return R_EMAIL

async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['r_email'] = update.message.text
    await update.message.reply_text("4️⃣ Masukkan **KOTA DOMISILI**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return R_KOTA

async def register_kota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['r_kota'] = update.message.text
    await update.message.reply_text("5️⃣ Masukkan **PT / AGENCY**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return R_AGENCY

async def register_agency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['r_agency'] = update.message.text
    
    summary = (
        f"📋 **KONFIRMASI DATA PENDAFTARAN**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Nama:** {context.user_data.get('r_nama')}\n"
        f"📱 **HP:** {context.user_data.get('r_hp')}\n"
        f"📧 **Email:** {context.user_data.get('r_email')}\n"
        f"📍 **Kota:** {context.user_data.get('r_kota')}\n"
        f"🏢 **Agency:** {context.user_data.get('r_agency')}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"⚠️ **PENTING: DATA BELUM TERKIRIM!**\n"
        f"Silakan cek kembali data di atas.\n"
        f"👉 Klik tombol **✅ KIRIM SEKARANG** di bawah untuk menyelesaikan pendaftaran."
    )
    await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM SEKARANG", "❌ ULANGI"]], one_time_keyboard=True), parse_mode='Markdown')
    return R_CONFIRM

async def register_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ ULANGI": 
        await update.message.reply_text("🔄 Silakan ketik /register untuk mengisi ulang data.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    data = {
        "user_id": update.effective_user.id,
        "nama_lengkap": context.user_data.get('r_nama', '-'),
        "no_hp": context.user_data.get('r_hp', '-'),
        "email": context.user_data.get('r_email', '-'),
        "alamat": context.user_data.get('r_kota', '-'), 
        "nik": "-", 
        "agency": context.user_data.get('r_agency', '-'),
        "quota": 1000, 
        "status": "pending"
    }
    try:
        supabase.table('users').insert(data).execute()
        await update.message.reply_text(
            "✅ **PENDAFTARAN BERHASIL!**\n\n"
            "Data Anda telah kami terima dan sedang dalam antrean verifikasi Admin.\n"
            "Mohon tunggu notifikasi selanjutnya.", 
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        
        kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"appu_{data['user_id']}"), InlineKeyboardButton("❌ Reject", callback_data=f"reju_{data['user_id']}")]]
        admin_msg = (
            f"🔔 **PENDAFTAR BARU**\n"
            f"👤 {data['nama_lengkap']}\n"
            f"🏢 {data['agency']}\n"
            f"📍 {data['alamat']}\n"
            f"📱 {data['no_hp']}"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        await update.message.reply_text(f"⚠️ Gagal menyimpan data / Sudah terdaftar.", reply_markup=ReplyKeyboardRemove())
        
    return ConversationHandler.END

# --- TAMBAH DATA (USER MANUAL) ---
async def add_data_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return await update.message.reply_text("⛔ Akses ditolak.")
    await update.message.reply_text("➕ **TAMBAH UNIT BARU**\n\n1️⃣ Masukkan **Nopol**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return A_NOPOL

async def add_nopol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['a_nopol'] = update.message.text.upper().replace(" ", "")
    await update.message.reply_text("2️⃣ Masukkan **Type Mobil**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return A_TYPE

async def add_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['a_type'] = update.message.text
    await update.message.reply_text("3️⃣ Masukkan **Leasing**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return A_LEASING

async def add_leasing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['a_leasing'] = update.message.text
    await update.message.reply_text("4️⃣ Masukkan **No Kiriman**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return A_NOKIR

async def add_nokir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['a_nokir'] = update.message.text
    summary = f"📋 **KONFIRMASI UNIT**\nNopol: {context.user_data['a_nopol']}\nUnit: {context.user_data['a_type']}"
    await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM KE ADMIN", "❌ BATAL"]], one_time_keyboard=True))
    return A_CONFIRM

async def add_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ BATAL": 
        await update.message.reply_text("🚫 Tambah data dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    n = context.user_data['a_nopol']
    
    context.bot_data[f"prop_{n}"] = {
        "nopol": n, 
        "type": context.user_data['a_type'], 
        "finance": context.user_data['a_leasing'], 
        "ovd": f"Kiriman: {context.user_data['a_nokir']}"
    }
    
    u = get_user(update.effective_user.id)
    
    await update.message.reply_text("✅ Terkirim! Menunggu persetujuan Admin.", reply_markup=ReplyKeyboardRemove())
    
    kb = [[InlineKeyboardButton("✅ Terima Data", callback_data=f"v_acc_{n}_{update.effective_user.id}"), InlineKeyboardButton("❌ Tolak", callback_data="v_rej")]]
    
    admin_msg = (
        f"📥 **USULAN DATA BARU (MANUAL)**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Pengirim:** {u.get('nama_lengkap')}\n"
        f"🏢 **Agency:** {u.get('agency')}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔢 **Nopol:** `{n}`\n"
        f"🚙 **Unit:** {context.user_data['a_type']}\n"
        f"🏦 **Leasing:** {context.user_data['a_leasing']}\n"
        f"📝 **Ket:** {context.user_data['a_nokir']}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    
    await context.bot.send_message(ADMIN_ID, text=admin_msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return ConversationHandler.END


# ==============================================================================
#                 9. HANDLER UTAMA (START, MESSAGE, CALLBACK)
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler untuk perintah /start.
    """
    info_text = ""
    if GLOBAL_INFO:
        info_text = f"\n📢 **INFO:** {GLOBAL_INFO}\n━━━━━━━━━━━━━━━━━━\n"

    welcome_text = (
        f"{info_text}"
        "🤖 **Selamat Datang di Oneaspal_bot**\n\n"
        "**Salam Satu Aspal!** 👋\n"
        "Halo, Rekan Mitra Lapangan.\n\n"
        "**Oneaspal_bot** adalah asisten digital profesional untuk mempermudah pencarian data kendaraan secara real-time.\n\n"
        "Cari data melalui:\n"
        "✅ **Nomor Polisi (Nopol)**\n"
        "✅ **Nomor Rangka (Noka)**\n"
        "✅ **Nomor Mesin (Nosin)**\n\n"
        "⚠️ **PENTING:** Akses bersifat **PRIVATE**. Anda wajib mendaftar dan menunggu verifikasi Admin.\n\n"
        "--- \n"
        "👉 Jalankan perintah /register untuk mendaftar."
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler Utama Pencarian Data (Wildcard Search).
    """
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return
    
    # --- CEK KUOTA (SAFEGUARD) ---
    quota = u.get('quota', 0)
    if quota <= 0:
        return await update.message.reply_text(
            "⛔ **KUOTA HABIS!**\n\n"
            "Sisa kuota pencarian Anda: **0**.\n"
            "Silakan hubungi Admin untuk melakukan Top Up / Donasi Sukarela.\n\n"
            "👉 Ketik `/admin Mohon info topup`",
            parse_mode='Markdown'
        )

    # Bersihkan Input (Hanya Alfanumerik)
    kw = re.sub(r'[^a-zA-Z0-9]', '', update.message.text.upper())
    
    if len(kw) < 3:
        return await update.message.reply_text("⚠️ Masukkan minimal 3 karakter.")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
    await asyncio.sleep(0.5) 
    
    try:
        # WILDCARD SEARCH (SUFFIX MATCHING)
        # Mencari Nopol/Noka/Nosin yang mengandung keyword input
        res = supabase.table('kendaraan').select("*").or_(f"nopol.ilike.%{kw}%,noka.eq.{kw},nosin.eq.{kw}").execute()
        
        if res.data:
            d = res.data[0]
            # Potong Kuota (Hanya jika ketemu)
            update_quota_usage(u['user_id'], u['quota']) 
            
            header_info = f"📢 **INFO:** {GLOBAL_INFO}\n━━━━━━━━━━━━━━━━━━\n" if GLOBAL_INFO else ""
            text = (
                f"{header_info}"
                f"✅ **DATA DITEMUKAN**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🚙 **Unit:** {d.get('type','-')}\n"
                f"🔢 **Nopol:** `{d.get('nopol','-')}`\n"
                f"📅 **Tahun:** {d.get('tahun','-')}\n"
                f"🎨 **Warna:** {d.get('warna','-')}\n"
                f"----------------------------------\n"
                f"🔧 **Noka:** `{d.get('noka','-')}`\n"
                f"⚙️ **Nosin:** `{d.get('nosin','-')}`\n"
                f"----------------------------------\n"
                f"⚠️ **OVD:** {d.get('ovd', '-')}\n"
                f"🏦 **Finance:** {d.get('finance', '-')}\n"
                f"🏢 **Branch:** {d.get('branch', '-')}\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"⚠️ **CATATAN PENTING:**\n"
                f"Ini bukan alat yang SAH untuk penarikan atau menyita aset kendaraan, "
                f"Silahkan konfirmasi kepada PIC leasing terkait.\n"
                f"Terima kasih."
            )
            await update.message.reply_text(text, parse_mode='Markdown')
            
            # Lapor ke Group Log
            await notify_hit_to_group(context, u, d)
        else:
            header_info = f"📢 **INFO:** {GLOBAL_INFO}\n\n" if GLOBAL_INFO else ""
            await update.message.reply_text(f"{header_info}❌ **DATA TIDAK DITEMUKAN**\n`{update.message.text}`", parse_mode='Markdown')
            
    except Exception as e:
        await update.message.reply_text("❌ Terjadi kesalahan database.")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Menangani semua interaksi tombol Inline (Approve/Reject).
    """
    q = update.callback_query
    await q.answer()
    data = q.data
    
    # 1. Approval User
    if data.startswith("appu_"):
        uid = data.split("_")[1]
        update_user_status(uid, 'active')
        await q.edit_message_text(f"✅ User {uid} DISETUJUI.")
        await context.bot.send_message(uid, "🎉 **AKUN ANDA TELAH AKTIF!**\nSelamat bekerja, Salam Satu Aspal!")
        
    # 2. Reject User
    elif data.startswith("reju_"):
        uid = data.split("_")[1]
        update_user_status(uid, 'rejected')
        await q.edit_message_text(f"⛔ User {uid} DITOLAK.")
        await context.bot.send_message(uid, "⛔ Pendaftaran Anda ditolak Admin.")
        
    # 3. Approve Data Manual
    elif data.startswith("v_acc_"):
        _, _, n, uid = data.split("_")
        item = context.bot_data.get(f"prop_{n}")
        if item: 
            supabase.table('kendaraan').upsert(item).execute()
            await q.edit_message_text(f"✅ Data {n} Masuk Database.")
            await context.bot.send_message(uid, f"🎊 Data `{n}` yang Anda kirim telah disetujui!")
            
    # 4. Reject Data Manual
    elif data == "v_rej":
        await q.edit_message_text("❌ Data Ditolak.")
        
    # 5. Approve Lapor Hapus
    elif data.startswith("del_acc_"):
        parts = data.split("_")
        nopol = parts[2]
        uid_lapor = parts[3]
        try: 
            supabase.table('kendaraan').delete().eq('nopol', nopol).execute()
            await q.edit_message_text(f"✅ `{nopol}` DIHAPUS.")
            await context.bot.send_message(uid_lapor, f"✅ Laporan Hapus `{nopol}` DISETUJUI.")
        except: 
            await q.edit_message_text("❌ Gagal Hapus.")
            
    # 6. Reject Lapor Hapus
    elif data.startswith("del_rej_"):
        uid_lapor = data.split("_")[2]
        await q.edit_message_text("❌ Ditolak.")
        await context.bot.send_message(uid_lapor, "❌ Laporan Hapus DITOLAK.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Membatalkan percakapan (Conversation) apapun.
    """
    await update.message.reply_text("🚫 Dibatalkan.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ==============================================================================
#                        10. MAIN PROGRAM
# ==============================================================================

if __name__ == '__main__':
    # Build Application
    app = ApplicationBuilder().token(token).post_init(post_init).build()
    
    # --- REGISTRASI CONVERSATION HANDLERS ---
    
    # 1. Registrasi User
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('register', register_start)],
        states={
            R_NAMA:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), register_nama)],
            R_HP:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), register_hp)],
            R_EMAIL:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), register_email)],
            R_KOTA:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), register_kota)],
            R_AGENCY:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), register_agency)],
            R_CONFIRM:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), register_confirm)]
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)],
        conversation_timeout=300
    ))

    # 2. Tambah Data Manual
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('tambah', add_data_start)],
        states={
            A_NOPOL:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), add_nopol)],
            A_TYPE:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), add_type)],
            A_LEASING:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), add_leasing)],
            A_NOKIR:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), add_nokir)],
            A_CONFIRM:[MessageHandler(filters.TEXT, add_confirm)]
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)],
        conversation_timeout=60
    ))

    # 3. Lapor Hapus
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('lapor', lapor_delete_start)],
        states={
            L_NOPOL:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), lapor_delete_check)],
            L_CONFIRM:[MessageHandler(filters.TEXT, lapor_delete_confirm)]
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)],
        conversation_timeout=60
    ))

    # 4. Hapus Manual Admin
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('hapus', delete_unit_start)],
        states={
            D_NOPOL:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), delete_unit_check)],
            D_CONFIRM:[MessageHandler(filters.TEXT, delete_unit_confirm)]
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)],
        conversation_timeout=60
    ))

    # 5. Smart Upload (DIAGNOSTIC MODE)
    # Note: upload_confirm_admin sudah diperbaiki namanya
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Document.ALL, upload_start)],
        states={
            U_LEASING_USER: [MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), upload_leasing_user)],
            U_LEASING_ADMIN: [MessageHandler(filters.TEXT, upload_leasing_admin)],
            U_CONFIRM_UPLOAD: [MessageHandler(filters.TEXT, upload_confirm_admin)]
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)],
        conversation_timeout=120
    ))

    # --- REGISTRASI COMMAND HANDLERS ---
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('cekkuota', cek_kuota))
    app.add_handler(CommandHandler('topup', admin_topup))
    
    app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('users', list_users))
    app.add_handler(CommandHandler('ban', ban_user))
    app.add_handler(CommandHandler('unban', unban_user))
    app.add_handler(CommandHandler('delete', delete_user))
    app.add_handler(CommandHandler('testgroup', test_group))
    app.add_handler(CommandHandler('panduan', panduan))
    
    app.add_handler(CommandHandler('setinfo', set_info))
    app.add_handler(CommandHandler('delinfo', del_info))
    app.add_handler(CommandHandler('admin', contact_admin))

    # --- REGISTRASI GENERIC HANDLERS ---
    app.add_handler(CallbackQueryHandler(callback_handler))
    # Handler pesan teks (harus paling akhir)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ ONEASPAL BOT ONLINE - V2.0 (GRAND MASTER EDITION)")
    app.run_polling()