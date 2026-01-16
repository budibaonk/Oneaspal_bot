"""
################################################################################
#                                                                              #
#                      PROJECT: ONEASPAL BOT (ASSET RECOVERY)                  #
#                      VERSION: 4.2 (ENTERPRISE MASTERPIECE)                   #
#                      ROLE:    MAIN APPLICATION CORE                          #
#                      AUTHOR:  CTO (GEMINI) & CEO (BAONK)                     #
#                                                                              #
################################################################################

DESKRIPSI SISTEM:
Bot Telegram High-Performance untuk manajemen data pencarian kendaraan (Matel).
Sistem ini dirancang untuk menangani jutaan data dengan fitur pencarian fuzzy.

FITUR UTAMA:
1.  **Turbo Search Engine:** Menggunakan Supabase Trigram Index untuk pencarian fuzzy (mirip).
2.  **Adaptive Polyglot Upload:** Mengenali file Excel, CSV, TXT, dan ZIP secara otomatis.
3.  **Monetization System (v4.0):** Manajemen Kuota, Topup Manual dengan Bukti Foto.
4.  **User Management (v4.1):** Register, Ban, Unban, dan Reject dengan Alasan (Reasoning).
5.  **Audit System (v4.2):** Statistik Global (/stats) dan Audit Leasing Detail (/leasing).
6.  **B2B Agency System:** Fitur Whitelabel untuk perusahaan/agency dengan notifikasi grup.

LOG PERUBAHAN (CHANGELOG v4.2):
- [FIX] Menambahkan fungsi set_info dan del_info yang sempat hilang.
- [NEW] Command /leasing untuk audit jumlah unit per leasing.
- [NEW] Admin Reject Reason: Memberikan alasan saat menolak pendaftaran user.
- [UPD] Kamus Data (Dictionary) diperluas untuk kompatibilitas file maksimal.
"""

# ==============================================================================
# BAGIAN 1: LIBRARY & DEPENDENCIES
# ==============================================================================
import os
import logging
import io
import time
import re
import asyncio 
import csv 
import zipfile 
import numpy as np
import pandas as pd

# Data Structures
from collections import Counter
from datetime import datetime

# Environment Variables Loader
from dotenv import load_dotenv

# Telegram Bot SDK
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

# Database Driver (Supabase)
from supabase import create_client, Client


# ==============================================================================
# BAGIAN 2: KONFIGURASI SYSTEM & LOGGING
# ==============================================================================

# 1. Load Environment Variables dari file .env
load_dotenv()

# 2. Konfigurasi Logging
# Ini penting agar Admin bisa melihat apa yang terjadi di terminal (Debug/Error)
logging.basicConfig(
    format='%(asctime)s - [%(levelname)s] - %(name)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 3. Ambil Credential
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# 4. Global Variables
GLOBAL_INFO = ""  # Untuk pesan broadcast di /start
LOG_GROUP_ID = -1003627047676  # ID Group untuk Log HIT

# 5. Setup Admin ID
DEFAULT_ADMIN_ID = 7530512170
try:
    env_id = os.environ.get("ADMIN_ID")
    ADMIN_ID = int(env_id) if env_id else DEFAULT_ADMIN_ID
except ValueError:
    ADMIN_ID = DEFAULT_ADMIN_ID

print(f"✅ [BOOT] SYSTEM STARTING... ADMIN ID TERDETEKSI: {ADMIN_ID}")

# 6. Validasi Credential
if not SUPABASE_URL or not SUPABASE_KEY or not TELEGRAM_TOKEN:
    print("❌ [CRITICAL ERROR] CREDENTIAL TIDAK LENGKAP! Cek file .env Anda.")
    exit()

# 7. Inisialisasi Koneksi Database
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ [BOOT] KONEKSI DATABASE SUPABASE BERHASIL!")
except Exception as e:
    print(f"❌ [CRITICAL] DATABASE ERROR: {e}")
    exit()


# ==============================================================================
# BAGIAN 3: KAMUS DATA (DICTIONARY) RAKSASA
# ==============================================================================
# Bagian ini adalah "Otak Bahasa" bot.
# Semakin banyak variasi di sini, semakin pintar bot membaca file Excel yang aneh-aneh.

COLUMN_ALIASES = {
    # 1. Variasi Kolom NOPOL (Plat Nomor)
    'nopol': [
        'nopolisi', 'nomorpolisi', 'nopol', 'noplat', 'nomorplat', 
        'nomorkendaraan', 'nokendaraan', 'nomer', 'tnkb', 'licenseplate', 
        'plat', 'nopolisikendaraan', 'nopil', 'polisi', 'platnomor', 
        'platkendaraan', 'nomerpolisi', 'no.polisi', 'nopol.', 'plat_nomor',
        'no_pol', 'no_polisi', 'police_no', 'vehicle_no', 'nomor_polisi'
    ],
    
    # 2. Variasi Kolom TIPE KENDARAAN
    'type': [
        'type', 'tipe', 'unit', 'model', 'vehicle', 'jenis', 
        'deskripsiunit', 'merk', 'object', 'kendaraan', 'item', 
        'brand', 'typedeskripsi', 'vehiclemodel', 'namaunit', 'kend', 
        'namakendaraan', 'merktype', 'objek', 'jenisobjek', 'item_description',
        'merk_type', 'tipe_kendaraan', 'model_kendaraan', 'description', 
        'vehicle_desc', 'nama_barang'
    ],
    
    # 3. Variasi Kolom TAHUN
    'tahun': [
        'tahun', 'year', 'thn', 'rakitan', 'th', 'yearofmanufacture', 
        'thnrakit', 'manufacturingyear', 'tahun_rakit', 'tahun_pembuatan',
        'th_rakit', 'th_pembuatan', 'model_year', 'th_pembuatan'
    ],
    
    # 4. Variasi Kolom WARNA
    'warna': [
        'warna', 'color', 'colour', 'cat', 'kelir', 'warnakendaraan', 
        'warna_unit', 'body_color', 'vehicle_color'
    ],
    
    # 5. Variasi Kolom NO RANGKA (Chassis)
    'noka': [
        'noka', 'norangka', 'nomorrangka', 'chassis', 'chasis', 'vin', 
        'rangka', 'chassisno', 'norangka1', 'chasisno', 'vinno', 'norang',
        'no_rangka', 'no.rangka', 'chassis_number', 'vin_number', 'serial_number'
    ],
    
    # 6. Variasi Kolom NO MESIN (Engine)
    'nosin': [
        'nosin', 'nomesin', 'nomormesin', 'engine', 'mesin', 'engineno', 
        'nomesin1', 'engineno', 'noengine', 'nomes', 'no_mesin',
        'no.mesin', 'engine_number', 'nomor_mesin'
    ],
    
    # 7. Variasi Kolom LEASING/FINANCE
    'finance': [
        'finance', 'leasing', 'lising', 'multifinance', 'cabang', 
        'partner', 'mitra', 'principal', 'company', 'client', 
        'financecompany', 'leasingname', 'keterangan', 'sumberdata', 
        'financetype', 'nama_leasing', 'nama_finance', 'client_name',
        'perusahaan', 'multifinance_name'
    ],
    
    # 8. Variasi Kolom OVD (Overdue/Terlambat)
    'ovd': [
        'ovd', 'overdue', 'dpd', 'keterlambatan', 'hari', 'telat', 
        'aging', 'od', 'bucket', 'daysoverdue', 'overduedays', 
        'kiriman', 'kolektibilitas', 'kol', 'kolek', 'jml_hari',
        'hari_keterlambatan', 'bucket_od', 'days_late', 'umur_tunggakan'
    ],
    
    # 9. Variasi Kolom CABANG/AREA
    'branch': [
        'branch', 'area', 'kota', 'pos', 'cabang', 'lokasi', 
        'wilayah', 'region', 'areaname', 'branchname', 'dealer',
        'nama_cabang', 'lokasi_unit', 'city', 'area_name', 'domisili'
    ]
}


# ==============================================================================
# BAGIAN 4: DEFINISI STATE (ALUR PERCAKAPAN)
# ==============================================================================
# Konstanta ini digunakan oleh ConversationHandler untuk melacak posisi user.

# State: Registrasi (/register)
R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_CONFIRM = range(6)

# State: Tambah Manual (/tambah)
A_NOPOL, A_TYPE, A_LEASING, A_NOKIR, A_CONFIRM = range(6, 11)

# State: Lapor Unit (/lapor)
L_NOPOL, L_CONFIRM = range(11, 13) 

# State: Hapus Manual Admin (/hapus)
D_NOPOL, D_CONFIRM = range(13, 15)

# State: Upload File Smart Upload
U_LEASING_USER, U_LEASING_ADMIN, U_CONFIRM_UPLOAD = range(15, 18)

# State: Admin Reject Reason (v4.1)
REJECT_REASON = 18


# ==============================================================================
# BAGIAN 5: FUNGSI HELPER & UTILITIES (LOGIC INTI)
# ==============================================================================

async def post_init(application: Application):
    """
    Fungsi yang dijalankan sekali saat bot baru menyala.
    Mengatur daftar menu perintah (command list) di tombol Menu Telegram.
    """
    await application.bot.set_my_commands([
        ("start", "🔄 Restart / Menu Utama"),
        ("cekkuota", "💳 Cek Sisa Kuota & Profil"),
        ("tambah", "➕ Input Data Manual (User)"),
        ("lapor", "🗑️ Lapor Unit Selesai"),
        ("register", "📝 Daftar Jadi Mitra"),
        ("stats", "📊 Statistik Global (Admin)"),
        ("leasing", "🏦 Audit Leasing (Admin)"),
        ("setinfo", "📢 Set Info Broadcast (Admin)"),
        ("delinfo", "🗑️ Hapus Info Broadcast (Admin)"),
        ("admin", "📩 Kirim Pesan ke Admin"),
        ("panduan", "📖 Buku Panduan"),
    ])
    print("✅ [INIT] Command List Updated Successfully!")

def get_user(user_id):
    """
    Mengambil profil user dari database Supabase berdasarkan ID Telegram.
    Return: Dictionary user data atau None jika tidak ditemukan.
    """
    try:
        response = supabase.table('users').select("*").eq('user_id', user_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Error get_user ({user_id}): {e}")
        return None

def get_agency_data(agency_name):
    """
    Mencari data Agency berdasarkan nama (Case Insensitive).
    Digunakan untuk fitur B2B Whitelabel.
    """
    try:
        # Menggunakan ilike untuk pencarian case-insensitive
        res = supabase.table('agencies').select("*").ilike('name', f"%{agency_name}%").execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"Error get_agency_data ({agency_name}): {e}")
        return None

def update_user_status(user_id, status):
    """
    Mengubah status user (active / pending / rejected).
    """
    try:
        supabase.table('users').update({'status': status}).eq('user_id', user_id).execute()
        logger.info(f"User {user_id} status updated to {status}")
        return True
    except Exception as e:
        logger.error(f"Error update_user_status: {e}")
        return False

def update_quota_usage(user_id, current_quota):
    """
    Mengurangi kuota user sebanyak 1 HIT setelah menemukan data.
    """
    try:
        new_quota = max(0, current_quota - 1)
        supabase.table('users').update({'quota': new_quota}).eq('user_id', user_id).execute()
    except Exception as e:
        logger.error(f"Error update_quota_usage: {e}")

def topup_quota(user_id, amount):
    """
    Menambah kuota user (Topup).
    Return: (Boolean Sukses/Gagal, Saldo Baru)
    """
    try:
        user = get_user(user_id)
        if user:
            new_total = user.get('quota', 0) + amount
            supabase.table('users').update({'quota': new_total}).eq('user_id', user_id).execute()
            logger.info(f"Topup {amount} to user {user_id}. New Balance: {new_total}")
            return True, new_total
        return False, 0
    except Exception as e:
        logger.error(f"Error topup_quota: {e}")
        return False, 0

# ------------------------------------------------------------------------------
# FILE PROCESSING ENGINE (Adaptive Polyglot v3.10)
# ------------------------------------------------------------------------------

def normalize_text(text):
    """Membersihkan teks menjadi lowercase alphanumeric only."""
    if not isinstance(text, str): return str(text).lower()
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()

def fix_header_position(df):
    """
    Algoritma pintar untuk mencari baris header yang 'tenggelam'
    karena format Excel yang tidak standar (ada logo/judul di baris atas).
    """
    target_aliases = COLUMN_ALIASES['nopol']
    
    # Scan 20 baris pertama
    for i in range(min(20, len(df))):
        # Ambil baris ke-i, normalkan teksnya
        row_values = [normalize_text(str(x)) for x in df.iloc[i].values]
        
        # Jika salah satu sel di baris ini mengandung kata kunci 'nopol', 'plat', dll
        if any(alias in row_values for alias in target_aliases):
            logger.info(f"Header ditemukan di baris ke-{i}")
            df.columns = df.iloc[i]         # Jadikan baris ini header
            df = df.iloc[i+1:].reset_index(drop=True) # Hapus baris di atasnya
            return df
            
    return df

def smart_rename_columns(df):
    """
    Mengubah nama kolom yang aneh-aneh menjadi nama standar database.
    Contoh: 'No. Polisi (Unit)' -> 'nopol'
    """
    new_cols = {}
    found = []
    
    for original_col in df.columns:
        clean = normalize_text(original_col)
        renamed = False
        
        # Loop dictionary untuk mencocokkan
        for std, aliases in COLUMN_ALIASES.items():
            if clean == std or clean in aliases:
                new_cols[original_col] = std
                found.append(std)
                renamed = True
                break
        
        # Jika tidak dikenali, biarkan nama aslinya
        if not renamed:
            new_cols[original_col] = original_col
            
    df.rename(columns=new_cols, inplace=True)
    return df, found

def read_file_robust(content, fname):
    """
    Fungsi pembaca file omnivora.
    Mendukung: ZIP, XLSX (OpenPyXL), XLS (Fake HTML/XML), CSV, TXT.
    """
    # 1. Handle File ZIP
    if fname.lower().endswith('.zip'):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                # Cari file valid di dalam zip (abaikan folder __MACOSX)
                valid = [f for f in z.namelist() if not f.startswith('__') and f.lower().endswith(('.csv','.xlsx','.xls','.txt'))]
                if not valid: 
                    raise ValueError("ZIP file kosong atau tidak berisi data Excel/CSV valid.")
                
                # Ambil file pertama yang valid
                target_file = valid[0]
                with z.open(target_file) as f: 
                    content = f.read()
                    fname = target_file # Update nama file
                    logger.info(f"Extracted from ZIP: {fname}")
        except Exception as e:
            raise ValueError(f"Gagal membaca ZIP: {str(e)}")

    # 2. Handle Excel (.xlsx, .xls)
    if fname.lower().endswith(('.xlsx', '.xls')):
        try:
            # Coba baca standard Excel
            return pd.read_excel(io.BytesIO(content), dtype=str)
        except: 
            try:
                # Coba engine openpyxl (untuk format xlsx modern)
                return pd.read_excel(io.BytesIO(content), dtype=str, engine='openpyxl')
            except: 
                pass # Jika gagal, lanjut ke Text Reader (Mungkin ini 'Fake Excel')

    # 3. Handle CSV / Text (Brute Force Mode)
    # Mencoba berbagai kombinasi Encoding dan Separator
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
                # Kriteria sukses: Minimal ada lebih dari 1 kolom
                if len(df.columns) > 1: 
                    logger.info(f"Read Success: Encoding={enc}, Sep={sep}")
                    return df
            except:
                continue
                
    # 4. Fallback Terakhir: Baca tanpa separator (Default Python Engine)
    return pd.read_csv(io.BytesIO(content), sep=None, engine='python', dtype=str)


# ==============================================================================
# BAGIAN 6: HANDLER: ADMIN REJECT REASONING (v4.1)
# ==============================================================================

async def reject_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Dipanggil saat Admin menekan tombol [❌ REJ].
    Memulai dialog untuk meminta alasan penolakan.
    """
    query = update.callback_query
    await query.answer()
    
    # Data callback format: "reju_USERID"
    target_uid = query.data.split("_")[1]
    
    # Simpan target user di memory context
    context.user_data['reject_target_uid'] = target_uid
    
    # Tanyakan alasan ke Admin
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"📝 **KONFIRMASI PENOLAKAN**\n\nTarget User ID: `{target_uid}`\n\nSilakan ketik **ALASAN PENOLAKAN** (Pesan ini akan dikirim ke User):",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
    )
    return REJECT_REASON

async def reject_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Dipanggil setelah Admin mengirimkan teks alasan.
    """
    reason = update.message.text
    
    if reason == "❌ BATAL":
        await update.message.reply_text("🚫 Proses Reject Dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    target_uid = context.user_data.get('reject_target_uid')
    
    # 1. Update status di database
    update_user_status(target_uid, 'rejected')
    
    # 2. Kirim notifikasi ke User
    msg_to_user = (
        f"⛔ **PENDAFTARAN DITOLAK**\n\n"
        f"Mohon maaf, data pendaftaran Anda belum dapat kami setujui.\n"
        f"📝 **Alasan:** {reason}\n\n"
        f"Silakan perbaiki data Anda dan lakukan pendaftaran ulang via /register."
    )
    
    try: 
        await context.bot.send_message(chat_id=target_uid, text=msg_to_user, parse_mode='Markdown')
    except Exception as e: 
        logger.warning(f"Gagal mengirim pesan reject ke user {target_uid}: {e}")
        
    # 3. Konfirmasi ke Admin
    await update.message.reply_text(
        f"✅ User {target_uid} telah DITOLAK.\nAlasan tercatat: \"{reason}\"", 
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


# ==============================================================================
# BAGIAN 7: HANDLER: FITUR USER (CEK KUOTA & TOPUP)
# ==============================================================================

async def cek_kuota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Menampilkan informasi profil dan sisa kuota user.
    """
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': 
        return await update.message.reply_text("⛔ Akun Anda belum aktif atau belum terdaftar. Silakan /register.")
    
    msg = (
        f"💳 **INFO KUOTA & PROFIL**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Nama: {u.get('nama_lengkap')}\n"
        f"🏢 Agency: {u.get('agency')}\n"
        f"📱 No HP: {u.get('no_hp')}\n"
        f"🔋 **SISA KUOTA:** `{u.get('quota', 0)}` HIT\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 **KUOTA HABIS?**\n"
        f"Kami menerapkan sistem donasi sukarela untuk biaya server.\n"
        f"Silakan transfer ke Admin, lalu **KIRIM FOTO BUKTI TRANSFER** langsung ke chat ini.\n"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def handle_photo_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler Cerdas: Mendeteksi jika user mengirim gambar di private chat.
    Gambar diasumsikan sebagai Bukti Transfer Topup.
    """
    if update.effective_chat.type != "private": return
    
    u = get_user(update.effective_user.id)
    if not u: return # Abaikan jika bukan user terdaftar
    
    # Ambil file foto ukuran terbesar
    photo_file = await update.message.photo[-1].get_file()
    caption = update.message.caption or "Topup Quota"
    
    # Beri respon cepat ke user
    await update.message.reply_text("✅ **Bukti diterima!**\nSedang diteruskan ke Admin untuk verifikasi...", quote=True)
    
    # Forward ke Admin dengan format rapi & tombol eksekusi
    msg_admin = (
        f"💰 **PERMINTAAN TOPUP BARU**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Nama: {u['nama_lengkap']}\n"
        f"🏢 Agency: {u['agency']}\n"
        f"🆔 User ID: `{u['user_id']}`\n"
        f"🔋 Saldo Saat Ini: {u.get('quota', 0)}\n"
        f"📝 Catatan: {caption}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👇 **PILIH NOMINAL TOPUP:**"
    )
    
    # Keyboard Tombol Topup Cepat
    keyboard = [
        [InlineKeyboardButton("✅ Isi 50", callback_data=f"topup_{u['user_id']}_50"), 
         InlineKeyboardButton("✅ Isi 120", callback_data=f"topup_{u['user_id']}_120")],
        [InlineKeyboardButton("✅ Isi 300", callback_data=f"topup_{u['user_id']}_300"), 
         InlineKeyboardButton("❌ TOLAK", callback_data=f"topup_{u['user_id']}_rej")]
    ]
    
    # Kirim ke Admin
    await context.bot.send_photo(
        chat_id=ADMIN_ID, 
        photo=photo_file.file_id, 
        caption=msg_admin, 
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode='Markdown'
    )


# ==============================================================================
# BAGIAN 8: HANDLER: SMART UPLOAD (CONVERSATION)
# ==============================================================================

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    [STEP 1] Menerima file dokumen dari user.
    """
    user_id = update.effective_user.id
    processing_msg = await update.message.reply_text("⏳ **Sedang menganalisa struktur file...**", parse_mode='Markdown')
    
    user_data = get_user(user_id)
    doc = update.message.document
    
    # Cek Izin Akses
    if not user_data or user_data['status'] != 'active':
        if user_id != ADMIN_ID: 
            await processing_msg.edit_text("⛔ **AKSES DITOLAK**\nAkun Anda belum aktif.")
            return ConversationHandler.END

    # Kirim status 'uploading' biar terlihat interaktif
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.UPLOAD_DOCUMENT)
    
    # Simpan metadata file
    context.user_data['upload_file_id'] = doc.file_id
    context.user_data['upload_file_name'] = doc.file_name

    # JIKA USER BIASA (BUKAN ADMIN)
    # File tidak diproses langsung, tapi diteruskan ke Admin.
    if user_id != ADMIN_ID:
        await processing_msg.delete()
        await update.message.reply_text(
            f"📄 File `{doc.file_name}` diterima.\nUntuk leasing/data apa file ini? (Contoh: BAF, OTO)", 
            parse_mode='Markdown', 
            reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)
        )
        return U_LEASING_USER

    # JIKA ADMIN
    # Langsung proses parsing data
    try:
        new_file = await doc.get_file()
        file_content = await new_file.download_as_bytearray()
        
        # Panggil Engine Polyglot
        df = read_file_robust(file_content, doc.file_name)
        df = fix_header_position(df) 
        df, found_cols = smart_rename_columns(df) 
        
        # Simpan DataFrame ke memory sementara
        context.user_data['df_records'] = df.to_dict(orient='records')
        
        # Validasi Kolom Kunci (Nopol)
        if 'nopol' not in df.columns:
            det = ", ".join(df.columns[:5])
            await processing_msg.edit_text(
                f"❌ **GAGAL DETEKSI NOPOL**\n"
                f"Bot tidak dapat menemukan kolom Nopol.\n"
                f"Kolom terbaca: {det}\n"
                f"Pastikan ada header: No Polisi, Nopol, atau Plat."
            )
            return ConversationHandler.END

        has_finance = 'finance' in df.columns
        report = (
            f"✅ **ANALISA FILE BERHASIL**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 **Kolom Dikenali:** {', '.join(found_cols)}\n"
            f"📁 **Total Baris:** {len(df)}\n"
            f"🏦 **Info Leasing:** {'✅ ADA' if has_finance else '⚠️ TIDAK ADA (Perlu Input Manual)'}\n\n"
            f"👉 **MASUKKAN NAMA LEASING UNTUK DATA INI:**\n"
            f"_(Klik SKIP jika leasing sudah ada di dalam file)_"
        )
        await processing_msg.delete()
        await update.message.reply_text(
            report, 
            parse_mode='Markdown', 
            reply_markup=ReplyKeyboardMarkup([["SKIP"], ["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
        )
        return U_LEASING_ADMIN

    except Exception as e:
        logger.error(f"Upload Error: {e}")
        await processing_msg.edit_text(f"❌ **ERROR MEMBACA FILE:**\n`{str(e)}`", parse_mode='Markdown')
        return ConversationHandler.END

async def upload_leasing_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    [STEP 2 USER] User mengirim nama leasing, Bot forward file ke Admin.
    """
    nm = update.message.text
    if nm == "❌ BATAL": return await cancel(update, context)
    
    fid = context.user_data['upload_file_id']
    fname = context.user_data['upload_file_name']
    u = get_user(update.effective_user.id)
    
    # Forward Document to Admin
    await context.bot.send_document(
        ADMIN_ID, 
        fid, 
        caption=f"📥 **UPLOAD DARI MITRA**\n👤 {u['nama_lengkap']}\n🏦 Leasing: {nm}\n📄 File: `{fname}`"
    )
    await update.message.reply_text("✅ File berhasil dikirim ke Admin untuk ditinjau.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def upload_leasing_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    [STEP 2 ADMIN] Admin menentukan nama leasing & Preview data.
    """
    nm = update.message.text.upper()
    df = pd.DataFrame(context.user_data['df_records'])
    
    # Logika Penentuan Finance
    if nm == 'SKIP':
        fin = "UNKNOWN" if 'finance' not in df.columns else "SESUAI FILE"
    else:
        fin = nm
        df['finance'] = fin # Override kolom finance
    
    # Jika kolom finance tidak ada dan tidak diisi admin
    if 'finance' not in df.columns: 
        df['finance'] = 'UNKNOWN'

    # CLEANING DATA
    # Hapus spasi dan simbol di Nopol
    df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
    
    # Hapus duplikat Nopol (Ambil data terbaru/terbawah)
    df = df.drop_duplicates(subset=['nopol'], keep='last')
    
    # Isi nilai NaN/Kosong dengan None agar diterima SQL
    df = df.replace({np.nan: None})
    
    # Standarisasi Struktur Kolom (Hanya ambil kolom yang relevan)
    valid_cols = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch']
    for c in valid_cols: 
        if c not in df.columns: df[c] = None
    
    # Simpan data final yang siap upload
    context.user_data['final_data_records'] = df[valid_cols].to_dict(orient='records')
    
    txt = (
        f"🔎 **PREVIEW DATA UPLOAD**\n"
        f"🏦 Leasing: {fin}\n"
        f"📊 Jumlah Data Bersih: {len(df)}\n"
        f"⚠️ Data siap dimasukkan ke Database.\n"
        f"Klik **EKSEKUSI** untuk melanjutkan."
    )
    await update.message.reply_text(
        txt, 
        parse_mode='Markdown', 
        reply_markup=ReplyKeyboardMarkup([["🚀 EKSEKUSI", "❌ BATAL"]], one_time_keyboard=True)
    )
    return U_CONFIRM_UPLOAD

async def upload_confirm_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    [STEP 3 ADMIN] Eksekusi Upsert ke Supabase.
    """
    if update.message.text != "🚀 EKSEKUSI": 
        await update.message.reply_text("🚫 Upload Dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    status_msg = await update.message.reply_text("⏳ **MEMULAI PROSES UPLOAD...**", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
    
    final_data = context.user_data.get('final_data_records')
    total = len(final_data)
    suc = 0
    fail = 0
    last_err = ""
    BATCH_SIZE = 1000 # Upload per 1000 baris untuk performa optimal
    start_time = time.time()
    
    # Looping Batch Upload
    for i in range(0, total, BATCH_SIZE):
        batch = final_data[i : i + BATCH_SIZE]
        try:
            # Upsert (Insert or Update)
            supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
            suc += len(batch)
        except Exception as e:
            last_err = str(e)
            # Jika batch gagal, coba fallback satu per satu
            # (Agar data yang bagus tetap masuk)
            for item in batch:
                try: 
                    supabase.table('kendaraan').upsert([item], on_conflict='nopol').execute()
                    suc += 1
                except Exception as ie: 
                    fail += 1
                    last_err = str(ie)
                    
        # Update progress bar setiap 5000 data
        if (i + BATCH_SIZE) % 5000 == 0: 
            await status_msg.edit_text(f"⏳ **MENGUPLOAD...**\n✅ {min(i+BATCH_SIZE, total)} / {total} data terproses...")
            await asyncio.sleep(0.5)

    duration = round(time.time() - start_time, 2)
    
    # Laporan Akhir
    if fail == 0:
        rpt = (
            f"✅ **UPLOAD SUKSES SEMPURNA!**\n"
            f"📊 Total Masuk: {suc}\n"
            f"⏱ Waktu: {duration} detik"
        ) 
    else:
        rpt = (
            f"❌ **UPLOAD SELESAI DENGAN ERROR**\n"
            f"✅ Sukses: {suc}\n"
            f"❌ Gagal: {fail}\n"
            f"🔍 Error Terakhir: `{last_err[:200]}`"
        )
        
    await status_msg.delete()
    await update.message.reply_text(rpt, parse_mode='Markdown')
    
    # Bersihkan memori
    context.user_data.pop('final_data_records', None)
    return ConversationHandler.END


# ==============================================================================
# BAGIAN 9: HANDLER: ADMIN FEATURES (STATS, AUDIT, LOGGING)
# ==============================================================================

async def notify_hit(context, user, data):
    """
    Mengirim notifikasi 'HIT' (Unit Ditemukan) ke berbagai channel.
    """
    # 1. Kirim ke Group Log Utama (Superadmin)
    txt_log = (
        f"🚨 **UNIT DITEMUKAN (HIT)!**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 User: {user['nama_lengkap']}\n"
        f"📍 Lokasi: {user.get('kota','-')}\n"
        f"🚙 Unit: {data['type']}\n"
        f"🔢 Nopol: `{data['nopol']}`\n"
        f"🏦 Leasing: {data['finance']}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    try: 
        await context.bot.send_message(LOG_GROUP_ID, txt_log, parse_mode='Markdown')
    except Exception as e:
        logger.warning(f"Gagal kirim log: {e}")

    # 2. Kirim ke Group Agency (Fitur B2B Whitelabel)
    # Jika user ini milik agency tertentu, kirim notif ke group agency tersebut
    user_agency = user.get('agency')
    if user_agency:
        agency_data = get_agency_data(user_agency)
        if agency_data and agency_data.get('group_id'):
            txt_agency = (
                f"🎯 **TEMUAN ANGGOTA (B2B)**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 Anggota: {user['nama_lengkap']}\n"
                f"🚙 Unit: {data['type']}\n"
                f"🔢 Nopol: `{data['nopol']}`\n"
                f"🏦 Leasing: {data['finance']}\n"
                f"⚠️ *Segera merapat ke lokasi!*"
            )
            try: 
                await context.bot.send_message(agency_data['group_id'], txt_agency, parse_mode='Markdown')
            except Exception as e:
                logger.warning(f"Gagal kirim notif B2B: {e}")

async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Command: /stats
    Menampilkan dashboard statistik keseluruhan.
    """
    if update.effective_user.id != ADMIN_ID: return
    
    msg = await update.message.reply_text("⏳ *Sedang menghitung statistik realtime...*", parse_mode='Markdown')
    try:
        # Hitung Total Data (Exact Count)
        res_total = supabase.table('kendaraan').select("*", count="exact", head=True).execute()
        
        # Hitung Total User
        res_users = supabase.table('users').select("*", count="exact", head=True).execute()
        
        # Hitung Estimasi Jumlah Leasing (Sampling)
        # Karena counting unique di tabel besar itu berat, kita sampling 2000 data awal
        raw_set = set()
        data = supabase.table('kendaraan').select("finance").limit(2000).execute().data
        for d in data: 
            if d.get('finance'): raw_set.add(str(d.get('finance')).strip().upper())
            
        await msg.edit_text(
            f"📊 **DASHBOARD STATISTIK GLOBAL**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📂 **Total Data:** `{res_total.count:,}` Unit\n"
            f"👥 **Total Mitra:** `{res_users.count:,}` Orang\n"
            f"🏦 **Est. Leasing:** `{len(raw_set)}+` Perusahaan\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💡 _Gunakan perintah /leasing untuk audit detail._", 
            parse_mode='Markdown'
        )
    except Exception as e:
        await msg.edit_text(f"❌ Error Stats: {e}")

async def get_leasing_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Command: /leasing
    Fitur Audit Detail: Menghitung jumlah unit per leasing.
    (Proses berat, menggunakan pagination).
    """
    if update.effective_user.id != ADMIN_ID: return
    
    msg = await update.message.reply_text("⏳ *Sedang mengaudit seluruh database... (Mohon tunggu)*", parse_mode='Markdown')
    
    try:
        finance_counts = Counter()
        off = 0
        BATCH = 5000 
        
        while True:
            # Fetch data pagination
            res = supabase.table('kendaraan').select("finance").range(off, off + BATCH - 1).execute()
            data = res.data
            if not data: break
            
            # Hitung frekuensi leasing di batch ini
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
            
            # Update status loading bar
            if off % 10000 == 0: 
                try: await msg.edit_text(f"⏳ *Mengaudit... ({off} data terproses)*", parse_mode='Markdown')
                except: pass

        # Sorting data terbanyak
        sorted_leasing = finance_counts.most_common()
        
        # Render Laporan
        report = "🏦 **LAPORAN AUDIT LEASING**\n━━━━━━━━━━━━━━━━━━\n"
        
        for name, count in sorted_leasing:
            # Filter nama kosong
            if name not in ["UNKNOWN", "NONE", "NAN", "-", ""]:
                report += f"🔹 **{name}:** `{count:,}` unit\n"
        
        # Tampilkan Unknown di paling bawah
        if finance_counts["UNKNOWN"] > 0:
            report += f"\n❓ **TANPA NAMA:** `{finance_counts['UNKNOWN']:,}` unit"

        # Potong jika melebihi batas karakter Telegram
        if len(report) > 4000:
            report = report[:4000] + "\n\n⚠️ _(Laporan terpotong, data terlalu banyak)_"
            
        await msg.edit_text(report, parse_mode='Markdown')

    except Exception as e:
        await msg.edit_text(f"❌ Error Audit: {str(e)}")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan daftar 50 user aktif pertama."""
    if update.effective_user.id != ADMIN_ID: return
    try:
        res = supabase.table('users').select("*").limit(50).execute()
        all_d = res.data
        act = [u for u in all_d if u.get('status')=='active']
        
        msg = f"📋 **DAFTAR MITRA AKTIF (Preview)**\n"
        for i, u in enumerate(act, 1): 
            msg += f"{i}. {u.get('nama_lengkap','-')} | {u.get('agency','-')} | `{u.get('user_id')}`\n"
        
        await update.message.reply_text(msg[:4000], parse_mode='Markdown')
    except Exception as e: 
        await update.message.reply_text("❌ Error ambil data user.")

async def admin_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Command: /topup ID JUMLAH
    Topup manual tanpa bukti foto.
    """
    if update.effective_user.id != ADMIN_ID: return
    try:
        args = context.args
        if len(args) < 2: raise ValueError
        tid, amt = args[0], int(args[1])
        
        succ, bal = topup_quota(tid, amt)
        if succ: 
            await update.message.reply_text(f"✅ Topup Sukses ke `{tid}`.\nSaldo Baru: {bal}")
            # Notif ke User
            await context.bot.send_message(tid, f"✅ **BONUS KUOTA!**\nAdmin telah menambahkan {amt} HIT ke akun Anda.")
        else: 
            await update.message.reply_text("❌ Gagal Topup (User ID tidak ditemukan).")
    except: 
        await update.message.reply_text("⚠️ Format Salah. Gunakan: `/topup ID JUMLAH`")

async def add_agency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Command: /addagency NAMA GROUP_ID ADMIN_ID
    Menambahkan Agency baru untuk B2B.
    """
    if update.effective_user.id != ADMIN_ID: return
    try:
        args = update.message.text.split()[1:] # Skip command
        if len(args) < 3: raise ValueError
        
        adm_id = int(args[-1])
        grp_id = int(args[-2])
        name = " ".join(args[:-2])
        
        data = {"name": name, "group_id": grp_id, "admin_id": adm_id}
        supabase.table('agencies').insert(data).execute()
        
        await update.message.reply_text(f"✅ **AGENCY DITAMBAHKAN!**\n🏢 {name}\n📢 Group ID: `{grp_id}`", parse_mode='Markdown')
    except: 
        await update.message.reply_text("⚠️ Format Salah!\n`/addagency [NAMA PT] [GROUP_ID] [ADMIN_ID]`", parse_mode='Markdown')

# --- USER MANAGEMENT SHORTCUTS ---

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        update_user_status(uid, 'rejected')
        await update.message.reply_text(f"⛔ User {uid} berhasil di-BAN.")
    except: pass

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        update_user_status(uid, 'active')
        await update.message.reply_text(f"✅ User {uid} berhasil di-UNBAN (Aktif Kembali).")
    except: pass

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        supabase.table('users').delete().eq('user_id', context.args[0]).execute()
        await update.message.reply_text("🗑️ User dihapus permanen dari database.")
    except: pass

async def set_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    FIX: Fungsi ini sebelumnya hilang.
    Admin bisa mengatur pesan info yang muncul saat user mengetik /start.
    """
    global GLOBAL_INFO
    if update.effective_user.id == ADMIN_ID: 
        GLOBAL_INFO = " ".join(context.args)
        await update.message.reply_text(f"✅ Info Update Berhasil:\n{GLOBAL_INFO}")

async def del_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    FIX: Fungsi ini sebelumnya hilang.
    Menghapus pesan info broadcast.
    """
    global GLOBAL_INFO
    if update.effective_user.id == ADMIN_ID: 
        GLOBAL_INFO = ""
        await update.message.reply_text("🗑️ Info Broadcast dihapus.")

async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u: return
    
    if not context.args:
        await update.message.reply_text("⚠️ Tulis pesan Anda setelah perintah /admin.\nContoh: `/admin Mohon cek topup saya`", parse_mode='Markdown')
        return

    try: 
        msg_content = ' '.join(context.args)
        await context.bot.send_message(ADMIN_ID, f"📩 **PESAN DARI USER**\n👤 {u['nama_lengkap']}\n💬 {msg_content}")
        await update.message.reply_text("✅ Pesan terkirim ke Admin.")
    except: 
        await update.message.reply_text("❌ Gagal mengirim pesan.")

async def panduan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "📖 **PANDUAN PENGGUNAAN ONEASPAL**\n\n"
        "1️⃣ **Cari Data Kendaraan**\n"
        "   - Ketik Nopol secara lengkap atau sebagian.\n"
        "   - Contoh: `B 1234 ABC` atau `1234`\n\n"
        "2️⃣ **Upload Data (Mitra)**\n"
        "   - Kirim file Excel/CSV/ZIP ke bot ini.\n"
        "   - Bot akan membaca otomatis.\n\n"
        "3️⃣ **Lapor Unit Selesai**\n"
        "   - Gunakan perintah /lapor jika unit sudah ditarik/selesai.\n\n"
        "4️⃣ **Cek Kuota**\n"
        "   - Ketik /cekkuota untuk melihat sisa HIT."
    )
    await update.message.reply_text(txt, parse_mode='Markdown')


# ==============================================================================
# BAGIAN 10: HANDLER: CONVERSATION UTILITIES (REG, ADD, LAPOR)
# ==============================================================================

# --- CONVERSATION: LAPOR (/lapor) ---
async def lapor_start(update, context): 
    if not get_user(update.effective_user.id): return
    await update.message.reply_text("🗑️ Masukkan Nopol yang ingin dilapor:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return L_NOPOL
async def lapor_check(update, context):
    n = update.message.text.upper().replace(" ", "")
    # Cek Database
    if not supabase.table('kendaraan').select("*").eq('nopol', n).execute().data: 
        await update.message.reply_text("❌ Data Nopol tidak ditemukan.")
        return ConversationHandler.END
    context.user_data['ln'] = n
    await update.message.reply_text(f"Yakin ingin melapor {n} sudah selesai?", reply_markup=ReplyKeyboardMarkup([["YA", "BATAL"]]))
    return L_CONFIRM
async def lapor_confirm(update, context):
    if update.message.text == "YA":
        n = context.user_data['ln']
        u = get_user(update.effective_user.id)
        await update.message.reply_text("✅ Laporan terkirim ke Admin.", reply_markup=ReplyKeyboardRemove())
        # Kirim Approval ke Admin
        await context.bot.send_message(
            ADMIN_ID, 
            f"🗑️ **REQUEST HAPUS DATA**\nUnit: {n}\nPelapor: {u['nama_lengkap']}", 
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ ACC HAPUS", callback_data=f"del_acc_{n}_{u['user_id']}"), 
                 InlineKeyboardButton("❌ TOLAK", callback_data=f"del_rej_{u['user_id']}")]
            ])
        )
    return ConversationHandler.END

# --- CONVERSATION: REGISTER (/register) ---
async def register_start(update, context): 
    if get_user(update.effective_user.id): 
        return await update.message.reply_text("✅ Anda sudah terdaftar sebagai Mitra.")
    await update.message.reply_text("📝 **FORMULIR PENDAFTARAN**\n\nMasukkan Nama Lengkap Anda:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return R_NAMA
async def register_nama(update, context): 
    context.user_data['r_nama'] = update.message.text
    await update.message.reply_text("📱 Masukkan Nomor HP (WhatsApp):")
    return R_HP
async def register_hp(update, context): 
    context.user_data['r_hp'] = update.message.text
    await update.message.reply_text("📧 Masukkan Alamat Email:")
    return R_EMAIL
async def register_email(update, context): 
    context.user_data['r_email'] = update.message.text
    await update.message.reply_text("📍 Masukkan Kota Domisili:")
    return R_KOTA
async def register_kota(update, context): 
    context.user_data['r_kota'] = update.message.text
    await update.message.reply_text("🏢 Masukkan Nama Agency/PT (Ketik '-' jika perorangan):")
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
        "quota": 50, # Bonus pendaftaran
        "status": "pending"
    }
    
    try:
        supabase.table('users').insert(d).execute()
        await update.message.reply_text("✅ Pendaftaran terkirim. Mohon tunggu konfirmasi Admin.", reply_markup=ReplyKeyboardRemove())
        
        msg = (
            f"🔔 **PENDAFTARAN MITRA BARU**\n"
            f"👤 {d['nama_lengkap']}\n"
            f"🏢 {d['agency']}\n"
            f"📍 {d['alamat']}\n"
            f"📱 {d['no_hp']}"
        )
        # Callback 'reju_' akan mentrigger reject_start (Reasoning)
        kb = [[InlineKeyboardButton("✅ TERIMA", callback_data=f"appu_{d['user_id']}"), InlineKeyboardButton("❌ TOLAK", callback_data=f"reju_{d['user_id']}")]]
        await context.bot.send_message(ADMIN_ID, text=msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text("❌ Gagal mendaftar. (Error: ID mungkin sudah ada)")
    return ConversationHandler.END

# --- CONVERSATION: TAMBAH MANUAL (/tambah) ---
async def add_start(update, context):
    if not get_user(update.effective_user.id): return
    await update.message.reply_text("➕ Masukkan Nopol Unit:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return A_NOPOL
async def add_nopol(update, context): 
    context.user_data['a_nopol'] = update.message.text.upper()
    await update.message.reply_text("Masukkan Nama Unit (Tipe):")
    return A_TYPE
async def add_type(update, context): 
    context.user_data['a_type'] = update.message.text
    await update.message.reply_text("Masukkan Nama Leasing:")
    return A_LEASING
async def add_leasing(update, context): 
    context.user_data['a_leasing'] = update.message.text
    await update.message.reply_text("Masukkan Keterangan OVD (Sisa Hari):")
    return A_NOKIR
async def add_nokir(update, context): 
    context.user_data['a_nokir'] = update.message.text
    await update.message.reply_text("Simpan data ini?", reply_markup=ReplyKeyboardMarkup([["YA", "BATAL"]]))
    return A_CONFIRM
async def add_confirm(update, context):
    if update.message.text != "YA": return await cancel(update, context)
    n = context.user_data['a_nopol']
    
    context.bot_data[f"prop_{n}"] = {
        "nopol": n, 
        "type": context.user_data['a_type'], 
        "finance": context.user_data['a_leasing'], 
        "ovd": context.user_data['a_nokir']
    }
    await update.message.reply_text("✅ Data dikirim ke Admin untuk verifikasi.", reply_markup=ReplyKeyboardRemove())
    await context.bot.send_message(
        ADMIN_ID, 
        f"📥 **MANUAL INPUT USER**\nNopol: {n}\nUser: {update.effective_user.first_name}", 
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ ACC SIMPAN", callback_data=f"v_acc_{n}_{update.effective_user.id}")]])
    )
    return ConversationHandler.END

# --- CONVERSATION: HAPUS MANUAL (/hapus) ---
async def delete_start(update, context): 
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🗑️ Masukkan Nopol yang mau dihapus permanen:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return D_NOPOL
async def delete_check(update, context): 
    context.user_data['dn'] = update.message.text.upper().replace(" ", "")
    await update.message.reply_text(f"Hapus {context.user_data['dn']} dari database?", reply_markup=ReplyKeyboardMarkup([["YA", "BATAL"]]))
    return D_CONFIRM
async def delete_confirm(update, context):
    if update.message.text == "YA": 
        supabase.table('kendaraan').delete().eq('nopol', context.user_data['dn']).execute()
        await update.message.reply_text("✅ Data Deleted Permanently.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ==============================================================================
# BAGIAN 11: MAIN ENGINE (SEARCH & CALLBACK)
# ==============================================================================

async def start(u, c): 
    """Pesan sambutan."""
    await u.message.reply_text(f"{GLOBAL_INFO}\n🤖 **ONEASPAL V4.2**\nSistem Online. Silakan ketik Nopol untuk mencari.", parse_mode='Markdown')

async def handle_message(u, c):
    """
    LOGIKA UTAMA PENCARIAN (SEARCH ENGINE).
    Menerima pesan teks -> Mencari di Database -> Memotong Kuota.
    """
    user = get_user(u.effective_user.id)
    if not user or user['status'] != 'active': return
    
    # Cek Kuota Guard
    if user.get('quota', 0) <= 0: 
        return await u.message.reply_text("⛔ **KUOTA HABIS**\nSilakan lakukan topup donasi.", parse_mode='Markdown')
        
    # Bersihkan Input User
    kw = re.sub(r'[^a-zA-Z0-9]', '', u.message.text.upper())
    if len(kw) < 3: return await u.message.reply_text("⚠️ Pencarian minimal 3 karakter.")
    
    # Indikator 'Typing'
    await c.bot.send_chat_action(u.effective_chat.id, constants.ChatAction.TYPING)
    
    try:
        # EXECUTE SEARCH (SUPABASE)
        # Mencari di Nopol, Noka, atau Nosin sekaligus
        res = supabase.table('kendaraan').select("*").or_(f"nopol.ilike.%{kw}%,noka.eq.{kw},nosin.eq.{kw}").execute()
        
        if res.data:
            # Jika ditemukan (HIT)
            d = res.data[0]
            
            # Potong Kuota
            update_quota_usage(user['user_id'], user['quota'])
            
            # Tampilkan Hasil
            txt = (
                f"✅ **UNIT DITEMUKAN!**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🚙 Unit: {d.get('type')}\n"
                f"🔢 Nopol: `{d.get('nopol')}`\n"
                f"🗓️ OVD: {d.get('ovd')}\n"
                f"🏦 Leasing: {d.get('finance')}\n"
                f"📍 Cabang: {d.get('branch')}\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            await u.message.reply_text(txt, parse_mode='Markdown')
            
            # Log Activity
            await notify_hit(c, user, d)
        else: 
            # Jika ZONK
            await u.message.reply_text(f"❌ Data tidak ditemukan: {kw}")
            
    except Exception as e: 
        logger.error(f"Search Error: {e}")
        await u.message.reply_text("❌ Terjadi kesalahan pada server database.")

async def cancel(u, c): 
    """Fungsi pembatalan umum."""
    await u.message.reply_text("🚫 Aksi Dibatalkan.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def callback_handler(u, c):
    """
    Pusat kendali tombol Inline (Approve, Reject, Topup).
    """
    q = u.callback_query
    await q.answer()
    d = q.data
    
    # --- HANDLING TOPUP ---
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

    # --- HANDLING USER REGISTER ---
    elif d.startswith("appu_"): 
        uid = d.split("_")[1]
        update_user_status(uid, 'active')
        await c.bot.send_message(uid, "✅ **AKUN DIAKTIFKAN!**\nSelamat datang di OneAspal. Silakan mulai bekerja.")
        await q.edit_message_text(f"✅ User {uid} telah DISETUJUI.")
    
    # --- HANDLING MANUAL DATA ---
    elif d.startswith("v_acc_"): 
        n = d.split("_")[2]
        item = c.bot_data.get(f"prop_{n}")
        if item:
            supabase.table('kendaraan').upsert(item).execute()
            await q.edit_message_text(f"✅ Data {n} berhasil DISIMPAN.")
            
    # --- HANDLING DELETE REQUEST ---
    elif d.startswith("del_acc_"): 
        n = d.split("_")[2]
        supabase.table('kendaraan').delete().eq('nopol', n).execute()
        await q.edit_message_text(f"✅ Data {n} berhasil DIHAPUS.")


# ==============================================================================
# 12. EXECUTOR (MAIN)
# ==============================================================================

if __name__ == '__main__':
    print("🚀 [BOOT] INITIALIZING ONEASPAL BOT v4.2...")
    
    # Build Application
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    # ---------------- REGISTER HANDLERS ----------------
    
    # 1. Admin Reject Handler (Harus prioritas tinggi)
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(reject_start, pattern='^reju_')],
        states={REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, reject_complete)]},
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]
    ))
    
    # 2. Upload Document Handler
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
    
    # 5. Lapor (Delete Request) Handler
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('lapor', lapor_start)], 
        states={
            L_NOPOL:[MessageHandler(filters.TEXT, lapor_check)], 
            L_CONFIRM:[MessageHandler(filters.TEXT, lapor_confirm)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    
    # 6. Admin Manual Delete Handler
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('hapus', delete_start)], 
        states={
            D_NOPOL:[MessageHandler(filters.TEXT, delete_check)], 
            D_CONFIRM:[MessageHandler(filters.TEXT, delete_confirm)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    
    # 7. Basic Commands
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('cekkuota', cek_kuota))
    app.add_handler(CommandHandler('topup', admin_topup))
    app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('leasing', get_leasing_list))
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
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_topup)) # Foto = Topup
    app.add_handler(CallbackQueryHandler(callback_handler)) # Klik Tombol
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)) # Search Nopol
    
    print("✅ [BOOT] ONEASPAL BOT v4.2 IS ONLINE AND READY TO SERVE!")
    app.run_polling()