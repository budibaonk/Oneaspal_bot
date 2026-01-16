"""
PROJECT: ONEASPAL BOT
VERSION: 4.2 (Enterprise Edition)
ROLE:   Main Application File
AUTHOR: CTO (Gemini) & CEO (Baonk)
DESC:   Telegram Bot for Asset Recovery Management.
        Features: 
        - Fuzzy Search (Supabase Trigram)
        - Adaptive Polyglot Upload (.xls, .xlsx, .csv, .txt, .zip)
        - Monetization System (Quota, Topup Proof, B2B Agency)
        - User Management (Register, Reject with Reason, Ban)
        - Audit System (/stats, /leasing)
"""

# ==============================================================================
# BAGIAN 1: LIBRARY & IMPORT
# ==============================================================================
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
from collections import Counter
from datetime import datetime
from dotenv import load_dotenv

# Telegram Bot Libraries
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, 
    ReplyKeyboardRemove, 
    constants
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

# Database Library
from supabase import create_client, Client

# ==============================================================================
# BAGIAN 2: KONFIGURASI & ENVIRONMENT
# ==============================================================================

# Load Environment Variables (.env)
load_dotenv()

# Setup Logging (Agar kita tahu apa yang terjadi di server)
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ambil Credential dari Environment
URL: str = os.environ.get("SUPABASE_URL")
KEY: str = os.environ.get("SUPABASE_KEY")
TOKEN: str = os.environ.get("TELEGRAM_TOKEN")

# Global Variables
GLOBAL_INFO = ""
LOG_GROUP_ID = -1003627047676  # Ganti dengan ID Group Log Bapak

# Admin ID Setup
DEFAULT_ADMIN_ID = 7530512170
try:
    env_id = os.environ.get("ADMIN_ID")
    ADMIN_ID = int(env_id) if env_id else DEFAULT_ADMIN_ID
except ValueError:
    ADMIN_ID = DEFAULT_ADMIN_ID

print(f"✅ SYSTEM BOOT v4.2: ADMIN ID TERDETEKSI = {ADMIN_ID}")

# Cek Kelengkapan Kunci
if not URL or not KEY or not TOKEN:
    print("❌ CRITICAL ERROR: Credential (URL/KEY/TOKEN) tidak lengkap di .env!")
    exit()

# Inisialisasi Koneksi Database
try:
    supabase: Client = create_client(URL, KEY)
    print("✅ DATABASE: Koneksi Supabase Berhasil!")
except Exception as e:
    print(f"❌ DATABASE ERROR: Gagal koneksi ke Supabase. Error: {e}")
    exit()


# ==============================================================================
# BAGIAN 3: KAMUS DATA (DICTIONARY)
# ==============================================================================
# Ini adalah "Otak Bahasa" bot untuk mengenali berbagai macam header kolom Excel.
# Jika ada istilah baru, tambahkan di sini.

COLUMN_ALIASES = {
    'nopol': [
        'nopolisi', 'nomorpolisi', 'nopol', 'noplat', 'nomorplat', 
        'nomorkendaraan', 'nokendaraan', 'nomer', 'tnkb', 'licenseplate', 
        'plat', 'nopolisikendaraan', 'nopil', 'polisi', 'platnomor', 
        'platkendaraan', 'nomerpolisi', 'no.polisi', 'nopol.', 'plat_nomor'
    ],
    'type': [
        'type', 'tipe', 'unit', 'model', 'vehicle', 'jenis', 
        'deskripsiunit', 'merk', 'object', 'kendaraan', 'item', 
        'brand', 'typedeskripsi', 'vehiclemodel', 'namaunit', 'kend', 
        'namakendaraan', 'merktype', 'objek', 'jenisobjek', 'item_description'
    ],
    'tahun': [
        'tahun', 'year', 'thn', 'rakitan', 'th', 'yearofmanufacture', 
        'thnrakit', 'manufacturingyear', 'tahun_rakit'
    ],
    'warna': [
        'warna', 'color', 'colour', 'cat', 'kelir', 'warnakendaraan'
    ],
    'noka': [
        'noka', 'norangka', 'nomorrangka', 'chassis', 'chasis', 'vin', 
        'rangka', 'chassisno', 'norangka1', 'chasisno', 'vinno', 'norang',
        'no_rangka'
    ],
    'nosin': [
        'nosin', 'nomesin', 'nomormesin', 'engine', 'mesin', 'engineno', 
        'nomesin1', 'engineno', 'noengine', 'nomes', 'no_mesin'
    ],
    'finance': [
        'finance', 'leasing', 'lising', 'multifinance', 'cabang', 
        'partner', 'mitra', 'principal', 'company', 'client', 
        'financecompany', 'leasingname', 'keterangan', 'sumberdata', 
        'financetype', 'nama_leasing'
    ],
    'ovd': [
        'ovd', 'overdue', 'dpd', 'keterlambatan', 'hari', 'telat', 
        'aging', 'od', 'code', 'bucket', 'daysoverdue', 'overduedays', 
        'kiriman', 'kolektibilitas', 'kol', 'kolek', 'jml_hari'
    ],
    'branch': [
        'branch', 'area', 'kota', 'pos', 'cabang', 'lokasi', 
        'wilayah', 'region', 'areaname', 'branchname', 'dealer'
    ]
}


# ==============================================================================
# BAGIAN 4: DEFINISI STATE (ALUR PERCAKAPAN)
# ==============================================================================

# State untuk Registrasi (/register)
R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_CONFIRM = range(6)

# State untuk Tambah Manual (/tambah)
A_NOPOL, A_TYPE, A_LEASING, A_NOKIR, A_CONFIRM = range(6, 11)

# State untuk Lapor Unit (/lapor)
L_NOPOL, L_CONFIRM = range(11, 13) 

# State untuk Hapus Manual (/hapus)
D_NOPOL, D_CONFIRM = range(13, 15)

# State untuk Upload File
U_LEASING_USER, U_LEASING_ADMIN, U_CONFIRM_UPLOAD = range(15, 18)

# State untuk Admin Reject Reason (v4.1)
REJECT_REASON = 18


# ==============================================================================
# BAGIAN 5: FUNGSI HELPER (ALAT BANTU DATABASE & LOGIC)
# ==============================================================================

async def post_init(application: Application):
    """Mengatur menu perintah saat bot pertama kali nyala."""
    await application.bot.set_my_commands([
        ("start", "🔄 Menu Utama"),
        ("cekkuota", "💳 Cek Sisa Kuota"),
        ("tambah", "➕ Input Manual (User)"),
        ("lapor", "🗑️ Lapor Unit Selesai"),
        ("register", "📝 Daftar Jadi Mitra"),
        ("stats", "📊 Statistik (Admin)"),
        ("leasing", "🏦 Audit Leasing (Admin)"),
        ("admin", "📩 Hubungi Admin"),
        ("panduan", "📖 Buku Panduan"),
    ])

def get_user(user_id):
    """Mengambil data user dari database berdasarkan Telegram ID."""
    try:
        response = supabase.table('users').select("*").eq('user_id', user_id).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error get_user: {e}")
        return None

def get_agency_data(agency_name):
    """Mencari data Agency untuk fitur B2B Whitelabel."""
    try:
        res = supabase.table('agencies').select("*").ilike('name', f"%{agency_name}%").execute()
        return res.data[0] if res.data else None
    except Exception as e:
        return None

def update_user_status(user_id, status):
    """Mengupdate status user (active/rejected/pending)."""
    try:
        supabase.table('users').update({'status': status}).eq('user_id', user_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error update status: {e}")
        return False

def update_quota_usage(user_id, current_quota):
    """Mengurangi kuota user sebanyak 1 HIT."""
    try:
        new_quota = max(0, current_quota - 1)
        supabase.table('users').update({'quota': new_quota}).eq('user_id', user_id).execute()
    except Exception as e:
        logger.error(f"Error update quota: {e}")

def topup_quota(user_id, amount):
    """Menambah kuota user (Topup)."""
    try:
        user = get_user(user_id)
        if user:
            new_total = user.get('quota', 0) + amount
            supabase.table('users').update({'quota': new_total}).eq('user_id', user_id).execute()
            return True, new_total
        return False, 0
    except Exception as e:
        logger.error(f"Error topup: {e}")
        return False, 0

# ------------------------------------------------------------------------------
# FUNGSI PEMROSES TEXT & FILE (THE ENGINE)
# ------------------------------------------------------------------------------

def normalize_text(text):
    """Membersihkan teks menjadi alphanumeric lowercase."""
    if not isinstance(text, str): return str(text).lower()
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()

def fix_header_position(df):
    """Mencari baris header yang benar jika file Excel berantakan."""
    target_aliases = COLUMN_ALIASES['nopol']
    # Cek 20 baris pertama
    for i in range(min(20, len(df))):
        row_values = [normalize_text(str(x)) for x in df.iloc[i].values]
        # Jika baris ini mengandung kata 'nopol', 'plat', dll, maka ini header
        if any(alias in row_values for alias in target_aliases):
            df.columns = df.iloc[i]  # Set baris ini jadi header
            df = df.iloc[i+1:].reset_index(drop=True) # Hapus baris di atasnya
            return df
    return df

def smart_rename_columns(df):
    """Mengubah nama kolom aneh menjadi nama standar (nopol, type, finance)."""
    new_cols = {}
    found = []
    
    for original_col in df.columns:
        clean = normalize_text(original_col)
        renamed = False
        
        # Cek di kamus COLUMN_ALIASES
        for std, aliases in COLUMN_ALIASES.items():
            if clean == std or clean in aliases:
                new_cols[original_col] = std
                found.append(std)
                renamed = True
                break
        
        if not renamed:
            new_cols[original_col] = original_col # Biarkan jika tidak dikenali
            
    df.rename(columns=new_cols, inplace=True)
    return df, found

def read_file_robust(content, fname):
    """
    Fungsi Pembaca File Super (Adaptive Polyglot).
    Bisa baca: ZIP, XLS (Fake/Real), XLSX, CSV (Berbagai separator & encoding).
    """
    # 1. Handle ZIP File
    if fname.lower().endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            # Cari file yang valid di dalam zip
            valid = [f for f in z.namelist() if not f.startswith('__') and f.lower().endswith(('.csv','.xlsx','.xls','.txt'))]
            if not valid: 
                raise ValueError("ZIP Kosong atau tidak ada file valid")
            # Ambil file pertama yg valid
            with z.open(valid[0]) as f: 
                content = f.read()
                fname = valid[0] # Update nama file jadi file dalam zip

    # 2. Handle Excel (.xlsx, .xls)
    if fname.lower().endswith(('.xlsx', '.xls')):
        try:
            return pd.read_excel(io.BytesIO(content), dtype=str)
        except: 
            try:
                # Coba engine openpyxl jika default gagal
                return pd.read_excel(io.BytesIO(content), dtype=str, engine='openpyxl')
            except: 
                pass # Jika masih gagal, mungkin itu file Text yang menyamar jadi Excel

    # 3. Handle CSV / Text (Brute Force Encoding & Separator)
    encodings = ['utf-8-sig', 'utf-8', 'cp1252', 'latin1', 'utf-16']
    separators = [None, ';', ',', '\t', '|']
    
    for enc in encodings:
        for sep in separators:
            try:
                df = pd.read_csv(
                    io.BytesIO(content), 
                    sep=sep, 
                    dtype=str, 
                    encoding=enc, 
                    engine='python', 
                    on_bad_lines='skip'
                )
                if len(df.columns) > 1: # Jika berhasil memisahkan kolom
                    return df
            except:
                continue
                
    # 4. Fallback Terakhir
    return pd.read_csv(io.BytesIO(content), sep=None, engine='python', dtype=str)


# ==============================================================================
# BAGIAN 6: HANDLER ADMIN REJECT (REASONING V4.1)
# ==============================================================================

async def reject_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dipanggil saat Admin klik tombol Reject."""
    query = update.callback_query
    await query.answer()
    
    # Ambil User ID dari callback data "reju_12345"
    target_uid = query.data.split("_")[1]
    
    # Simpan ID user yg mau ditolak ke memori sementara
    context.user_data['reject_target_uid'] = target_uid
    
    # Minta alasan ke Admin
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"📝 **KONFIRMASI PENOLAKAN**\nTarget ID: `{target_uid}`\n\nSilakan ketik **ALASAN PENOLAKAN** agar user mengerti kesalahannya:",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
    )
    return REJECT_REASON

async def reject_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dipanggil setelah Admin mengetik alasan."""
    reason = update.message.text
    
    if reason == "❌ BATAL":
        await update.message.reply_text("🚫 Batal Reject.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    target_uid = context.user_data.get('reject_target_uid')
    
    # Update Status DB
    update_user_status(target_uid, 'rejected')
    
    # Kirim Pesan ke User
    msg_to_user = (
        f"⛔ **PENDAFTARAN DITOLAK**\n"
        f"Mohon maaf, akun Anda belum dapat kami setujui.\n\n"
        f"📝 **Alasan:** {reason}\n\n"
        f"Silakan perbaiki data Anda dan lakukan pendaftaran ulang via /register."
    )
    try: 
        await context.bot.send_message(chat_id=target_uid, text=msg_to_user, parse_mode='Markdown')
    except Exception as e: 
        logger.warning(f"Gagal kirim pesan ke user {target_uid}: {e}")
        
    await update.message.reply_text(f"✅ User {target_uid} berhasil DITOLAK.\nAlasan: \"{reason}\"", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ==============================================================================
# BAGIAN 7: HANDLER FITUR USER
# ==============================================================================

async def cek_kuota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan info kuota dan cara donasi."""
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': 
        return await update.message.reply_text("⛔ Akun Anda belum aktif atau belum terdaftar.")
    
    msg = (
        f"💳 **INFO KUOTA SAYA**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Nama: {u.get('nama_lengkap')}\n"
        f"🏢 Agency: {u.get('agency')}\n"
        f"🔋 **SISA KUOTA:** `{u.get('quota', 0)}` HIT\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 **KUOTA HABIS?**\n"
        f"Kami menerapkan sistem donasi sukarela untuk biaya server.\n"
        f"Silakan transfer ke Admin, lalu **KIRIM FOTO BUKTI TRANSFER** langsung ke chat ini.\n"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def handle_photo_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler otomatis saat user mengirim gambar (dianggap bukti transfer).
    """
    if update.effective_chat.type != "private": return
    
    u = get_user(update.effective_user.id)
    if not u: return
    
    # Ambil file foto resolusi tertinggi
    photo_file = await update.message.photo[-1].get_file()
    caption = update.message.caption or "Topup Quota"
    
    await update.message.reply_text("✅ **Bukti diterima!**\nSedang diteruskan ke Admin untuk verifikasi...", quote=True)
    
    # Forward ke Admin dengan tombol konfirmasi
    msg_admin = (
        f"💰 **PERMINTAAN TOPUP BARU**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Nama: {u['nama_lengkap']}\n"
        f"🏢 Agency: {u['agency']}\n"
        f"🆔 User ID: `{u['user_id']}`\n"
        f"🔋 Kuota Saat Ini: {u.get('quota', 0)}\n"
        f"📝 Catatan: {caption}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Isi 50", callback_data=f"topup_{u['user_id']}_50"), 
         InlineKeyboardButton("✅ Isi 120", callback_data=f"topup_{u['user_id']}_120")],
        [InlineKeyboardButton("✅ Isi 300", callback_data=f"topup_{u['user_id']}_300"), 
         InlineKeyboardButton("❌ TOLAK", callback_data=f"topup_{u['user_id']}_rej")]
    ]
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID, 
        photo=photo_file.file_id, 
        caption=msg_admin, 
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode='Markdown'
    )

# ------------------------------------------------------------------------------
# FITUR SMART UPLOAD (CONVERSATION HANDLER)
# ------------------------------------------------------------------------------

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Langkah 1: User kirim file, Bot analisa."""
    user_id = update.effective_user.id
    processing_msg = await update.message.reply_text("⏳ **Sedang menganalisa struktur file...**", parse_mode='Markdown')
    
    user_data = get_user(user_id)
    doc = update.message.document
    
    # Cek Izin
    if not user_data or user_data['status'] != 'active':
        if user_id != ADMIN_ID: 
            return await processing_msg.edit_text("⛔ **AKSES DITOLAK**\nHanya mitra aktif yang boleh upload.")
            return ConversationHandler.END

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.UPLOAD_DOCUMENT)
    context.user_data['upload_file_id'] = doc.file_id
    context.user_data['upload_file_name'] = doc.file_name

    # Jika User Biasa (Bukan Admin) -> Masuk mode kirim ke Admin
    if user_id != ADMIN_ID:
        await processing_msg.delete()
        await update.message.reply_text(
            f"📄 File `{doc.file_name}` diterima.\nUntuk data leasing apa ini?", 
            parse_mode='Markdown', 
            reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)
        )
        return U_LEASING_USER

    # Jika Admin -> Proses Parsing Data
    try:
        new_file = await doc.get_file()
        file_content = await new_file.download_as_bytearray()
        
        # Panggil Mesin Polyglot
        df = read_file_robust(file_content, doc.file_name)
        df = fix_header_position(df) 
        df, found_cols = smart_rename_columns(df) 
        
        # Simpan sementara di memori
        context.user_data['df_records'] = df.to_dict(orient='records')
        
        # Validasi Kolom Wajib
        if 'nopol' not in df.columns:
            det = ", ".join(df.columns[:5])
            await processing_msg.edit_text(f"❌ **GAGAL DETEKSI NOPOL**\nBot tidak menemukan kolom nopol.\nKolom terbaca: {det}")
            return ConversationHandler.END

        has_finance = 'finance' in df.columns
        report = (
            f"✅ **SCAN FILE BERHASIL**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 **Kolom Terdeteksi:** {', '.join(found_cols)}\n"
            f"📁 **Total Baris:** {len(df)}\n"
            f"🏦 **Kolom Leasing:** {'✅ ADA' if has_finance else '⚠️ TIDAK ADA (Perlu Input Manual)'}\n\n"
            f"👉 **MASUKKAN NAMA LEASING UNTUK DATA INI:**"
        )
        await processing_msg.delete()
        await update.message.reply_text(
            report, 
            parse_mode='Markdown', 
            reply_markup=ReplyKeyboardMarkup([["SKIP"], ["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
        )
        return U_LEASING_ADMIN

    except Exception as e:
        await processing_msg.edit_text(f"❌ **ERROR MEMBACA FILE:**\n`{str(e)}`", parse_mode='Markdown')
        return ConversationHandler.END

async def upload_leasing_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User mengirim nama leasing, file diteruskan ke Admin."""
    nm = update.message.text
    if nm == "❌ BATAL": return await cancel(update, context)
    
    fid, fname = context.user_data['upload_file_id'], context.user_data['upload_file_name']
    u = get_user(update.effective_user.id)
    
    # Forward ke Admin
    await context.bot.send_document(
        ADMIN_ID, 
        fid, 
        caption=f"📥 **UPLOAD DARI MITRA**\n👤 {u['nama_lengkap']}\n🏦 Leasing: {nm}\n📄 File: `{fname}`"
    )
    await update.message.reply_text("✅ File berhasil dikirim ke Admin untuk ditinjau.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def upload_leasing_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin memasukkan nama leasing, lalu preview data."""
    nm = update.message.text.upper()
    df = pd.DataFrame(context.user_data['df_records'])
    
    # Tentukan nama finance
    fin = nm if nm != 'SKIP' else ("UNKNOWN" if 'finance' not in df.columns else "SESUAI FILE")
    
    # Isi kolom finance jika belum ada atau di-override
    if nm != 'SKIP': 
        df['finance'] = fin
    elif 'finance' not in df.columns: 
        df['finance'] = 'UNKNOWN'

    # Bersihkan Data Nopol (Hapus spasi, titik, dll)
    df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
    
    # Hapus duplikat nopol di file yg sama
    df = df.drop_duplicates(subset=['nopol'], keep='last').replace({np.nan: None})
    
    # Standarisasi Kolom Akhir
    valid_cols = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch']
    for c in valid_cols: 
        if c not in df.columns: df[c] = None
    
    context.user_data['final_data_records'] = df[valid_cols].to_dict(orient='records')
    
    txt = (
        f"🔎 **PREVIEW UPLOAD**\n"
        f"🏦 Leasing: {fin}\n"
        f"📊 Jumlah Data: {len(df)}\n"
        f"⚠️ Pastikan data benar. Klik **EKSEKUSI** untuk menyimpan ke database."
    )
    await update.message.reply_text(txt, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["🚀 EKSEKUSI", "❌ BATAL"]], one_time_keyboard=True))
    return U_CONFIRM_UPLOAD

async def upload_confirm_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin melakukan eksekusi simpan ke Database."""
    if update.message.text != "🚀 EKSEKUSI": 
        await update.message.reply_text("🚫 Upload Dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    status_msg = await update.message.reply_text("⏳ **MEMULAI PROSES UPLOAD...**", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
    
    final_data = context.user_data.get('final_data_records')
    suc = 0
    fail = 0
    last_err = ""
    BATCH = 1000 # Upload per 1000 baris agar cepat
    total = len(final_data)
    start_time = time.time()
    
    for i in range(0, total, BATCH):
        batch = final_data[i : i + BATCH]
        try:
            # UPSERT: Insert or Update if Nopol exists
            supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
            suc += len(batch)
        except Exception as e:
            last_err = str(e)
            # Jika batch gagal, coba satu per satu (fallback lambat)
            for item in batch:
                try: 
                    supabase.table('kendaraan').upsert([item], on_conflict='nopol').execute()
                    suc += 1
                except Exception as ie: 
                    fail += 1
                    last_err = str(ie)
                    
        # Update status progress
        if (i + BATCH) % 5000 == 0: 
            await status_msg.edit_text(f"⏳ **MENGUPLOAD...**\n✅ {min(i+BATCH, total)} / {total} data processed...")
            await asyncio.sleep(0.5)

    duration = round(time.time() - start_time, 2)
    
    if fail == 0:
        rpt = (f"✅ **UPLOAD SUKSES!**\n📊 Total: {suc}\n⏱ Waktu: {duration} detik") 
    else:
        rpt = (f"❌ **UPLOAD SELESAI DENGAN ERROR**\n✅ Sukses: {suc}\n❌ Gagal: {fail}\n🔍 Error Terakhir: `{last_err[:200]}`")
        
    await status_msg.delete()
    await update.message.reply_text(rpt, parse_mode='Markdown')
    
    # Bersihkan memori
    context.user_data.pop('final_data_records', None)
    return ConversationHandler.END


# ==============================================================================
# BAGIAN 8: FITUR ADMIN (STATS, AUDIT, MANAGEMENT)
# ==============================================================================

async def notify_hit(context, user, data):
    """
    Mengirim notifikasi jika ada user menemukan unit.
    Dikirim ke Group Log Utama & Group Agency (jika B2B).
    """
    # 1. Kirim ke Superadmin Log
    txt = (
        f"🚨 **UNIT DITEMUKAN (HIT)!**\n"
        f"👤 User: {user['nama_lengkap']}\n"
        f"📍 Lokasi User: {user.get('kota','-')}\n"
        f"🚙 Unit: {data['type']}\n"
        f"🔢 Nopol: `{data['nopol']}`\n"
        f"🏦 Leasing: {data['finance']}"
    )
    try: await context.bot.send_message(LOG_GROUP_ID, txt, parse_mode='Markdown')
    except: pass

    # 2. Kirim ke Group Agency (Fitur B2B)
    user_agency = user.get('agency')
    if user_agency:
        agency_data = get_agency_data(user_agency)
        if agency_data and agency_data.get('group_id'):
            txt_agency = (
                f"🎯 **TEMUAN ANGGOTA (B2B)**\n"
                f"👤 Anggota: {user['nama_lengkap']}\n"
                f"🚙 Unit: {data['type']}\n"
                f"🔢 Nopol: `{data['nopol']}`\n"
                f"🏦 Leasing: {data['finance']}\n"
                f"⚠️ *Segera merapat ke lokasi!*"
            )
            try: await context.bot.send_message(agency_data['group_id'], txt_agency, parse_mode='Markdown')
            except: pass

async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan Dashboard Statistik Utama."""
    if update.effective_user.id != ADMIN_ID: return
    msg = await update.message.reply_text("⏳ *Sedang menghitung data...*", parse_mode='Markdown')
    try:
        # Hitung Total Data (Exact Count)
        res_total = supabase.table('kendaraan').select("*", count="exact", head=True).execute()
        res_users = supabase.table('users').select("*", count="exact", head=True).execute()
        
        # Hitung Jumlah Leasing (Estimasi Cepat)
        # Kita ambil sample data finance untuk menghitung unique values
        raw_set = set()
        off = 0
        while True:
            # Ambil per batch kecil untuk cari nama leasing
            data = supabase.table('kendaraan').select("finance").range(off, off+999).execute().data
            if not data: break
            for d in data: 
                if d.get('finance'): raw_set.add(str(d.get('finance')).strip().upper())
            if len(data) < 1000: break # Sudah habis
            off += 1000
            
        await msg.edit_text(
            f"📊 **STATISTIK GLOBAL ONEASPAL**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📂 Total Data: `{res_total.count:,}` Unit\n"
            f"👥 Total User: `{res_users.count:,}` Mitra\n"
            f"🏦 Jumlah Leasing: `{len(raw_set)}` Perusahaan\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💡 _Gunakan perintah /leasing untuk melihat detail per perusahaan._", 
            parse_mode='Markdown'
        )
    except Exception as e:
        await msg.edit_text(f"❌ Error Stats: {e}")

async def get_leasing_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    NEW FEATURE v4.2: Audit Data Leasing.
    Menghitung jumlah unit per masing-masing leasing secara detail.
    """
    if update.effective_user.id != ADMIN_ID: return
    msg = await update.message.reply_text("⏳ *Sedang mengaudit seluruh data leasing... (Proses ini mungkin memakan waktu)*", parse_mode='Markdown')
    
    try:
        finance_counts = Counter()
        off = 0
        BATCH = 5000 # Batch besar untuk audit
        
        while True:
            res = supabase.table('kendaraan').select("finance").range(off, off + BATCH - 1).execute()
            data = res.data
            if not data: break
            
            # Kumpulkan nama finance
            batch_finances = []
            for d in data:
                f = d.get('finance')
                if f: 
                    batch_finances.append(str(f).strip().upper())
                else: 
                    batch_finances.append("UNKNOWN")
            
            finance_counts.update(batch_finances)
            
            if len(data) < BATCH: break
            off += BATCH
            
            # Update status ke admin biar tidak dikira hang
            if off % 20000 == 0: 
                try: await msg.edit_text(f"⏳ *Mengaudit... ({off} data terproses)*", parse_mode='Markdown')
                except: pass

        # Urutkan dari yang terbanyak
        sorted_leasing = finance_counts.most_common()
        
        # Buat Laporan
        report = "🏦 **LAPORAN AUDIT LEASING (v4.2)**\n━━━━━━━━━━━━━━━━━━\n"
        
        for name, count in sorted_leasing:
            if name not in ["UNKNOWN", "NONE", "NAN", "-", ""]:
                report += f"🔹 **{name}:** `{count:,}` unit\n"
        
        # Tampilkan yang UNKNOWN di bawah
        if finance_counts["UNKNOWN"] > 0:
            report += f"\n❓ **TANPA NAMA:** `{finance_counts['UNKNOWN']:,}` unit"

        # Potong text jika kepanjangan (Telegram max 4096 char)
        if len(report) > 4000:
            report = report[:4000] + "\n\n⚠️ _(Daftar terpotong, terlalu panjang)_"
            
        await msg.edit_text(report, parse_mode='Markdown')

    except Exception as e:
        await msg.edit_text(f"❌ Error Audit: {str(e)}")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan daftar user aktif."""
    if update.effective_user.id != ADMIN_ID: return
    try:
        res = supabase.table('users').select("*").execute()
        all_d = res.data
        act = [u for u in all_d if u.get('status')=='active']
        
        msg = f"📋 **DAFTAR MITRA AKTIF ({len(act)})**\n"
        for i, u in enumerate(act, 1): 
            msg += f"{i}. {u.get('nama_lengkap','-')} | {u.get('agency','-')} | `{u.get('user_id')}`\n"
        
        await update.message.reply_text(msg[:4000], parse_mode='Markdown')
    except Exception as e: 
        await update.message.reply_text("❌ Error ambil data user.")

async def admin_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Topup manual lewat command: /topup ID JUMLAH"""
    if update.effective_user.id != ADMIN_ID: return
    try:
        args = context.args
        if len(args) < 2: raise ValueError
        tid, amt = args[0], int(args[1])
        succ, bal = topup_quota(tid, amt)
        if succ: 
            await update.message.reply_text(f"✅ Topup Sukses ke `{tid}`.\nSaldo Baru: {bal}")
            await context.bot.send_message(tid, f"✅ **BONUS KUOTA!**\nAdmin telah menambahkan {amt} HIT ke akun Anda.")
        else: 
            await update.message.reply_text("❌ Gagal Topup (ID tidak ditemukan).")
    except: 
        await update.message.reply_text("⚠️ Format Salah. Gunakan: `/topup ID JUMLAH`")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban user: /ban ID"""
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        update_user_status(uid, 'rejected')
        await update.message.reply_text(f"⛔ User {uid} berhasil di-BAN.")
    except: pass

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unban user: /unban ID"""
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        update_user_status(uid, 'active')
        await update.message.reply_text(f"✅ User {uid} berhasil di-UNBAN (Aktif Kembali).")
    except: pass

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hapus user permanen: /delete ID"""
    if update.effective_user.id != ADMIN_ID: return
    try:
        supabase.table('users').delete().eq('user_id', context.args[0]).execute()
        await update.message.reply_text("🗑️ User dihapus permanen dari database.")
    except: pass

async def set_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set broadcast info di /start"""
    global GLOBAL_INFO
    if update.effective_user.id == ADMIN_ID: 
        GLOBAL_INFO = " ".join(context.args)
        await update.message.reply_text(f"✅ Info diupdate: {GLOBAL_INFO}")

async def del_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hapus broadcast info"""
    global GLOBAL_INFO
    if update.effective_user.id == ADMIN_ID: 
        GLOBAL_INFO = ""
        await update.message.reply_text("🗑️ Info dihapus.")

async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User mengirim pesan ke Admin"""
    u = get_user(update.effective_user.id)
    if not u: return
    
    if not context.args:
        await update.message.reply_text("⚠️ Tulis pesan Anda setelah perintah /admin.\nContoh: `/admin Mohon topup`", parse_mode='Markdown')
        return

    try: 
        msg_content = ' '.join(context.args)
        await context.bot.send_message(ADMIN_ID, f"📩 **PESAN DARI USER**\n👤 {u['nama_lengkap']}\n💬 {msg_content}")
        await update.message.reply_text("✅ Pesan terkirim ke Admin.")
    except: 
        await update.message.reply_text("❌ Gagal mengirim pesan.")

async def panduan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan panduan penggunaan."""
    txt = (
        "📖 **PANDUAN PENGGUNAAN**\n\n"
        "1️⃣ **Cari Data Kendaraan**\n"
        "   Cukup ketik Nopol atau Potongan Nopol.\n"
        "   Contoh: `B 1234 ABC` atau `1234`\n\n"
        "2️⃣ **Upload Data (Khusus Mitra)**\n"
        "   Kirim file Excel/CSV/ZIP ke bot ini.\n"
        "   Bot akan otomatis membaca isinya.\n\n"
        "3️⃣ **Lapor Unit Selesai**\n"
        "   Gunakan perintah /lapor untuk menghapus unit.\n\n"
        "4️⃣ **Cek Kuota**\n"
        "   Ketik /cekkuota untuk lihat sisa HIT."
    )
    await update.message.reply_text(txt, parse_mode='Markdown')

async def add_agency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menambah Agency Baru (B2B)."""
    if update.effective_user.id != ADMIN_ID: return
    try:
        args = update.message.text.split()[1:]
        adm_id = int(args[-1])
        grp_id = int(args[-2])
        name = " ".join(args[:-2])
        
        data = {"name": name, "group_id": grp_id, "admin_id": adm_id}
        supabase.table('agencies').insert(data).execute()
        
        await update.message.reply_text(f"✅ **AGENCY DITAMBAHKAN!**\n🏢 {name}\n📢 Group ID: `{grp_id}`", parse_mode='Markdown')
    except: 
        await update.message.reply_text("⚠️ Format Salah!\n`/addagency [NAMA] [GRUP_ID] [ADMIN_ID]`", parse_mode='Markdown')


# ==============================================================================
# BAGIAN 9: HANDLER CONVERSATION LAINNYA (REGISTER, TAMBAH, LAPOR)
# ==============================================================================

# --- LAPOR START ---
async def lapor_start(update, context): 
    if not get_user(update.effective_user.id): return
    await update.message.reply_text("🗑️ Masukkan Nopol yang ingin dilapor:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return L_NOPOL
async def lapor_check(update, context):
    n = update.message.text.upper().replace(" ", "")
    # Cek apakah data ada
    if not supabase.table('kendaraan').select("*").eq('nopol', n).execute().data: 
        await update.message.reply_text("❌ Data tidak ditemukan.")
        return ConversationHandler.END
    context.user_data['ln'] = n
    await update.message.reply_text(f"Yakin ingin melapor {n} sudah selesai?", reply_markup=ReplyKeyboardMarkup([["YA", "BATAL"]]))
    return L_CONFIRM
async def lapor_confirm(update, context):
    if update.message.text == "YA":
        n = context.user_data['ln']
        u = get_user(update.effective_user.id)
        await update.message.reply_text("✅ Laporan terkirim ke Admin.", reply_markup=ReplyKeyboardRemove())
        # Kirim tombol ACC/REJ ke Admin
        await context.bot.send_message(
            ADMIN_ID, 
            f"🗑️ **REQUEST HAPUS DATA**\nUnit: {n}\nPelapor: {u['nama_lengkap']}", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ACC HAPUS", callback_data=f"del_acc_{n}_{u['user_id']}"), InlineKeyboardButton("TOLAK", callback_data=f"del_rej_{u['user_id']}")]])
        )
    return ConversationHandler.END

# --- REGISTER START ---
async def register_start(update, context): 
    if get_user(update.effective_user.id): 
        return await update.message.reply_text("✅ Anda sudah terdaftar.")
    await update.message.reply_text("📝 **FORMULIR PENDAFTARAN**\n\nMasukkan Nama Lengkap:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return R_NAMA
async def register_nama(update, context): 
    context.user_data['r_nama'] = update.message.text
    await update.message.reply_text("📱 Masukkan Nomor HP (WA):")
    return R_HP
async def register_hp(update, context): 
    context.user_data['r_hp'] = update.message.text
    await update.message.reply_text("📧 Masukkan Email:")
    return R_EMAIL
async def register_email(update, context): 
    context.user_data['r_email'] = update.message.text
    await update.message.reply_text("📍 Masukkan Kota Domisili:")
    return R_KOTA
async def register_kota(update, context): 
    context.user_data['r_kota'] = update.message.text
    await update.message.reply_text("🏢 Masukkan Nama Agency/PT (Jika ada):")
    return R_AGENCY
async def register_agency(update, context): 
    context.user_data['r_agency'] = update.message.text
    await update.message.reply_text("✅ Data lengkap. Kirim pendaftaran?", reply_markup=ReplyKeyboardMarkup([["YA", "BATAL"]]))
    return R_CONFIRM
async def register_confirm(update, context):
    if update.message.text != "YA": return await cancel(update, context)
    
    d = {
        "user_id": update.effective_user.id, 
        "nama_lengkap": context.user_data['r_nama'], 
        "no_hp": context.user_data['r_hp'], 
        "email": context.user_data['r_email'], 
        "alamat": context.user_data['r_kota'], 
        "agency": context.user_data['r_agency'], 
        "quota": 50, # Bonus awal
        "status": "pending"
    }
    
    try:
        supabase.table('users').insert(d).execute()
        await update.message.reply_text("✅ Pendaftaran terkirim. Tunggu konfirmasi Admin.", reply_markup=ReplyKeyboardRemove())
        
        # Notif ke Admin
        msg = (
            f"🔔 **NEW USER REGISTRATION**\n"
            f"👤 {d['nama_lengkap']}\n"
            f"🏢 {d['agency']}\n"
            f"📍 {d['alamat']}\n"
            f"📱 {d['no_hp']}"
        )
        kb = [[InlineKeyboardButton("✅ ACC", callback_data=f"appu_{d['user_id']}"), InlineKeyboardButton("❌ REJ", callback_data=f"reju_{d['user_id']}")]]
        await context.bot.send_message(ADMIN_ID, text=msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text("❌ Gagal mendaftar. Mungkin Anda sudah terdaftar.")
    return ConversationHandler.END

# --- TAMBAH MANUAL START ---
async def add_start(update, context):
    if not get_user(update.effective_user.id): return
    await update.message.reply_text("➕ Masukkan Nopol:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return A_NOPOL
async def add_nopol(update, context): 
    context.user_data['a_nopol'] = update.message.text.upper()
    await update.message.reply_text("Masukkan Nama Unit (Tipe):")
    return A_TYPE
async def add_type(update, context): 
    context.user_data['a_type'] = update.message.text
    await update.message.reply_text("Masukkan Leasing:")
    return A_LEASING
async def add_leasing(update, context): 
    context.user_data['a_leasing'] = update.message.text
    await update.message.reply_text("Masukkan Keterangan (OVD/Sisa Hari):")
    return A_NOKIR
async def add_nokir(update, context): 
    context.user_data['a_nokir'] = update.message.text
    await update.message.reply_text("Simpan data ini?", reply_markup=ReplyKeyboardMarkup([["YA", "BATAL"]]))
    return A_CONFIRM
async def add_confirm(update, context):
    if update.message.text != "YA": return await cancel(update, context)
    n = context.user_data['a_nopol']
    
    # Simpan di memory bot data untuk di-ACC admin
    context.bot_data[f"prop_{n}"] = {
        "nopol": n, 
        "type": context.user_data['a_type'], 
        "finance": context.user_data['a_leasing'], 
        "ovd": context.user_data['a_nokir']
    }
    await update.message.reply_text("✅ Data dikirim ke Admin untuk verifikasi.", reply_markup=ReplyKeyboardRemove())
    await context.bot.send_message(
        ADMIN_ID, 
        f"📥 **MANUAL INPUT USER**\nNopol: {n}", 
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ACC", callback_data=f"v_acc_{n}_{update.effective_user.id}")]])
    )
    return ConversationHandler.END

# --- HAPUS MANUAL (ADMIN) ---
async def delete_start(update, context): 
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🗑️ Masukkan Nopol yang mau dihapus:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return D_NOPOL
async def delete_check(update, context): 
    context.user_data['dn'] = update.message.text.upper().replace(" ", "")
    await update.message.reply_text(f"Hapus {context.user_data['dn']} permanen?", reply_markup=ReplyKeyboardMarkup([["YA", "BATAL"]]))
    return D_CONFIRM
async def delete_confirm(update, context):
    if update.message.text == "YA": 
        supabase.table('kendaraan').delete().eq('nopol', context.user_data['dn']).execute()
        await update.message.reply_text("✅ Data Deleted.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ==============================================================================
# BAGIAN 10: MAIN HANDLER (PENCARIAN & CALLBACK)
# ==============================================================================

async def start(u, c): 
    await u.message.reply_text(f"{GLOBAL_INFO}\n🤖 **ONEASPAL V4.2 ENTERPRISE**\nSistem Siap. Silakan ketik Nopol.", parse_mode='Markdown')

async def handle_message(u, c):
    """
    Core Logic: Menerima pesan teks (Nopol) dan mencari di database.
    """
    user = get_user(u.effective_user.id)
    if not user or user['status'] != 'active': return
    
    # Cek Kuota
    if user.get('quota', 0) <= 0: 
        return await u.message.reply_text("⛔ **KUOTA HABIS**\nSilakan donasi & kirim bukti transfer di sini.", parse_mode='Markdown')
        
    kw = re.sub(r'[^a-zA-Z0-9]', '', u.message.text.upper())
    if len(kw) < 3: return await u.message.reply_text("⚠️ Ketik minimal 3 huruf/angka.")
    
    await c.bot.send_chat_action(u.effective_chat.id, constants.ChatAction.TYPING)
    try:
        # Search Query (Optimized)
        res = supabase.table('kendaraan').select("*").or_(f"nopol.ilike.%{kw}%,noka.eq.{kw},nosin.eq.{kw}").execute()
        
        if res.data:
            d = res.data[0]
            # Potong Kuota
            update_quota_usage(user['user_id'], user['quota'])
            
            txt = (
                f"✅ **UNIT DITEMUKAN**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🚙 Unit: {d.get('type')}\n"
                f"🔢 Nopol: `{d.get('nopol')}`\n"
                f"🗓️ OVD: {d.get('ovd')}\n"
                f"🏦 Leasing: {d.get('finance')}\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            await u.message.reply_text(txt, parse_mode='Markdown')
            
            # Log Activity
            await notify_hit(c, user, d)
        else: 
            await u.message.reply_text(f"❌ Tidak ditemukan: {kw}")
            
    except Exception as e: 
        logger.error(f"Search Error: {e}")
        await u.message.reply_text("❌ Terjadi kesalahan pada server.")

async def cancel(u, c): 
    await u.message.reply_text("🚫 Aksi Dibatalkan.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def callback_handler(u, c):
    """Handler untuk semua tombol Inline (Callback Query)."""
    q = u.callback_query
    await q.answer()
    d = q.data
    
    # 1. Topup Handling
    if d.startswith("topup_"):
        parts = d.split("_")
        uid = int(parts[1])
        action = parts[2]
        
        if action == "rej":
            await c.bot.send_message(uid, "❌ Topup Anda DITOLAK Admin.")
            await q.edit_message_caption("❌ Status: Topup DITOLAK.")
        else:
            amount = int(action)
            topup_quota(uid, amount)
            await c.bot.send_message(uid, f"✅ **TOPUP BERHASIL!**\n➕ {amount} HIT ditambahkan ke akun Anda.")
            await q.edit_message_caption(f"✅ Status: Sukses Topup {amount} ke User {uid}.")

    # 2. Register Approval
    elif d.startswith("appu_"): 
        uid = d.split("_")[1]
        update_user_status(uid, 'active')
        await c.bot.send_message(uid, "✅ **AKUN DIAKTIFKAN!**\nSelamat datang di OneAspal. Silakan bekerja.")
        await q.edit_message_text(f"✅ User {uid} telah DISETUJUI.")
    
    # Note: "reju_" (Reject User) sekarang ditangani oleh admin_reject_handler
    
    # 3. Manual Input Approval
    elif d.startswith("v_acc_"): 
        n = d.split("_")[2]
        item = c.bot_data.get(f"prop_{n}")
        if item:
            supabase.table('kendaraan').upsert(item).execute()
            await q.edit_message_text(f"✅ Data {n} berhasil DISIMPAN.")
            
    # 4. Delete Request Approval
    elif d.startswith("del_acc_"): 
        n = d.split("_")[2]
        supabase.table('kendaraan').delete().eq('nopol', n).execute()
        await q.edit_message_text(f"✅ Data {n} berhasil DIHAPUS.")


# ==============================================================================
# BAGIAN 11: SYSTEM RUNNER
# ==============================================================================

if __name__ == '__main__':
    print("🚀 ONEASPAL BOT v4.2 IS STARTING...")
    
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    
    # --- REGISTER HANDLERS ---
    
    # 1. Admin Reject Handler (Prioritas Tinggi)
    app.add_handler(admin_reject_handler)
    
    # 2. Upload Handler (Dokumen)
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Document.ALL, upload_start)], 
        states={
            U_LEASING_USER: [MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), upload_leasing_user)], 
            U_LEASING_ADMIN: [MessageHandler(filters.TEXT, upload_leasing_admin)], 
            U_CONFIRM_UPLOAD: [MessageHandler(filters.TEXT, upload_confirm_admin)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)],
        allow_reentry=True
    ))
    
    # 3. Registration Handler
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('register', register_start)], 
        states={
            R_NAMA:[MessageHandler(filters.TEXT, register_nama)], 
            R_HP:[MessageHandler(filters.TEXT, register_hp)], 
            R_EMAIL:[MessageHandler(filters.TEXT, register_email)], 
            R_KOTA:[MessageHandler(filters.TEXT, register_kota)], 
            R_AGENCY:[MessageHandler(filters.TEXT, register_agency)], 
            R_CONFIRM:[MessageHandler(filters.TEXT, register_confirm)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    
    # 4. Manual Add Handler
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('tambah', add_start)], 
        states={
            A_NOPOL:[MessageHandler(filters.TEXT, add_nopol)], 
            A_TYPE:[MessageHandler(filters.TEXT, add_type)], 
            A_LEASING:[MessageHandler(filters.TEXT, add_leasing)], 
            A_NOKIR:[MessageHandler(filters.TEXT, add_nokir)], 
            A_CONFIRM:[MessageHandler(filters.TEXT, add_confirm)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    
    # 5. Lapor/Delete Request Handler
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('lapor', lapor_start)], 
        states={
            L_NOPOL:[MessageHandler(filters.TEXT, lapor_check)], 
            L_CONFIRM:[MessageHandler(filters.TEXT, lapor_confirm)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    
    # 6. Admin Delete Handler
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('hapus', delete_start)], 
        states={
            D_NOPOL:[MessageHandler(filters.TEXT, delete_check)], 
            D_CONFIRM:[MessageHandler(filters.TEXT, delete_confirm)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    
    # 7. Command Handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('cekkuota', cek_kuota))
    app.add_handler(CommandHandler('topup', admin_topup))
    app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('leasing', get_leasing_list)) # v4.2 NEW
    app.add_handler(CommandHandler('users', list_users))
    app.add_handler(CommandHandler('ban', ban_user))
    app.add_handler(CommandHandler('unban', unban_user))
    app.add_handler(CommandHandler('delete', delete_user))
    app.add_handler(CommandHandler('setinfo', set_info))
    app.add_handler(CommandHandler('delinfo', del_info))
    app.add_handler(CommandHandler('admin', contact_admin))
    app.add_handler(CommandHandler('panduan', panduan))
    app.add_handler(CommandHandler('addagency', add_agency))
    
    # 8. Media & Text Handlers
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_topup)) # Auto Topup Proof
    app.add_handler(CallbackQueryHandler(callback_handler)) # Buttons
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)) # Search Engine
    
    print("✅ ONEASPAL BOT v4.2 IS ONLINE & READY!")
    app.run_polling()