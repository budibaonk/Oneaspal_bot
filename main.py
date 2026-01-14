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
#                        1. KONFIGURASI SISTEM
# ==============================================================================

# Load environment variables
load_dotenv()

# Setup Logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# Load Credential dari .env
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
token: str = os.environ.get("TELEGRAM_TOKEN")

# Variable Global untuk Pengumuman Sticky
GLOBAL_INFO = ""

# Setup Admin ID
DEFAULT_ADMIN_ID = 7530512170
try:
    env_id = os.environ.get("ADMIN_ID")
    ADMIN_ID = int(env_id) if env_id else DEFAULT_ADMIN_ID
except ValueError:
    ADMIN_ID = DEFAULT_ADMIN_ID

print(f"✅ ADMIN ID TERDETEKSI: {ADMIN_ID}")

# ID Group Log
LOG_GROUP_ID = -1003627047676  

# Validasi Koneksi Database
if not url or not key or not token:
    print("❌ ERROR: Cek file .env Anda. Credential belum lengkap.")
    exit()

try:
    supabase: Client = create_client(url, key)
except Exception as e:
    print(f"❌ Gagal koneksi ke Supabase: {e}")
    exit()


# ==============================================================================
#                        2. KAMUS DATA & STATE
# ==============================================================================

# --- KAMUS ALIAS KOLOM (NORMALISASI AGRESIF v1.9.5) ---
# KUNCI UTAMA: Semua alias ditulis dalam HURUF KECIL TANPA SPASI/TITIK/SIMBOL
# Contoh: "No. Polisi" -> dinormalisasi jadi "nopolisi" -> cocok dengan alias di bawah
COLUMN_ALIASES = {
    'nopol': [
        'nopolisi', 'nomorpolisi', 'nopol', 'noplat', 'nomorplat', 
        'nomorkendaraan', 'nokendaraan', 'nomer', 'tnkb', 'licenseplate', 
        'plat', 'nopolisikendaraan'
    ],
    'type': [
        'type', 'tipe', 'unit', 'model', 'vehicle', 'jenis', 
        'deskripsiunit', 'merk', 'object', 'kendaraan', 'item', 'brand',
        'typedeskripsi', 'vehiclemodel'
    ],
    'tahun': [
        'tahun', 'year', 'thn', 'rakitan', 'th', 'yearofmanufacture', 'thnrakit'
    ],
    'warna': [
        'warna', 'color', 'colour', 'cat', 'kelir'
    ],
    'noka': [
        'noka', 'norangka', 'nomorrangka', 'chassis', 'chasis', 
        'vin', 'rangka', 'chassisno', 'norangka1'
    ],
    'nosin': [
        'nosin', 'nomesin', 'nomormesin', 'engine', 'mesin', 
        'engineno', 'nomesin1'
    ],
    'finance': [
        'finance', 'leasing', 'lising', 'multifinance', 'cabang', 
        'partner', 'mitra', 'principal', 'company', 'client', 'financecompany'
    ],
    'ovd': [
        'ovd', 'overdue', 'dpd', 'keterlambatan', 'hari', 
        'telat', 'aging', 'od', 'bucket', 'daysoverdue', 'overduedays'
    ],
    'branch': [
        'branch', 'area', 'kota', 'pos', 'cabang', 
        'lokasi', 'wilayah', 'region', 'areaname', 'branchname'
    ]
}

# --- DEFINISI STATE CONVERSATION (JANGAN DIUBAH) ---
# 1. Registrasi
R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_CONFIRM = range(6)
# 2. Tambah Data Manual
A_NOPOL, A_TYPE, A_LEASING, A_NOKIR, A_CONFIRM = range(6, 11)
# 3. Lapor Hapus
L_NOPOL, L_CONFIRM = range(11, 13) 
# 4. Hapus Manual (Admin)
D_NOPOL, D_CONFIRM = range(13, 15)
# 5. Smart Upload
U_LEASING_USER, U_LEASING_ADMIN, U_CONFIRM_UPLOAD = range(15, 18)


# ==============================================================================
#                        3. DATABASE & HELPER FUNCTIONS
# ==============================================================================

async def post_init(application: Application):
    """Mengatur Tombol Menu secara Otomatis saat Bot Start"""
    await application.bot.set_my_commands([
        ("start", "🔄 Restart / Menu Utama"),
        ("cekkuota", "💳 Cek Sisa Kuota"),
        ("tambah", "➕ Tambah Unit Manual"),
        ("lapor", "🗑️ Lapor Unit Selesai"),
        ("register", "📝 Daftar Mitra Baru"),
        ("admin", "📩 Hubungi Admin"),
        ("panduan", "📖 Petunjuk Penggunaan"),
    ])
    print("✅ Menu Perintah Telegram Berhasil Di-set!")

def get_user(user_id):
    """Mengambil data user dari database berdasarkan user_id Telegram"""
    try:
        response = supabase.table('users').select("*").eq('user_id', user_id).execute()
        return response.data[0] if response.data else None
    except: return None

def update_user_status(user_id, status):
    """Update status user (active/rejected/pending)"""
    try:
        supabase.table('users').update({'status': status}).eq('user_id', user_id).execute()
    except Exception as e: logging.error(f"Error update status: {e}")

def update_quota_usage(user_id, current_quota):
    """Mengurangi kuota user sebanyak 1 poin"""
    try:
        new_quota = current_quota - 1
        supabase.table('users').update({'quota': new_quota}).eq('user_id', user_id).execute()
    except: pass

def topup_quota(user_id, amount):
    """Fungsi Admin Topup Kuota"""
    try:
        user = get_user(user_id)
        if user:
            current = user.get('quota', 0)
            new_total = current + amount
            supabase.table('users').update({'quota': new_total}).eq('user_id', user_id).execute()
            return True, new_total
        return False, 0
    except: return False, 0

# --- FUNGSI BARU v1.9.5: AGGRESSIVE NORMALIZATION ---
def normalize_text(text):
    """
    Membersihkan teks dari spasi, titik, koma, underscore, dan simbol lain.
    Hanya menyisakan huruf dan angka (alfanumerik) lowercase.
    Contoh: 'No. Polisi' -> 'nopolisi'
    """
    if not isinstance(text, str): 
        return str(text).lower()
    # Hapus karakter non-alfanumerik
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()

def smart_rename_columns(df):
    """Fungsi pintar v1.9.5 untuk menstandarkan nama kolom"""
    new_cols = {}
    found_cols = []
    
    # Loop setiap kolom asli dari Excel
    for original_col in df.columns:
        # 1. Bersihkan nama kolom asli sagresif mungkin
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

    df.rename(columns=new_cols, inplace=True)
    return df, found_cols

def read_file_robust(file_content, file_name):
    """
    Mencoba berbagai strategi encoding untuk membaca file Excel/CSV yang bandel.
    Mendukung: UTF-8, Latin-1 (Windows), CP1252.
    Mendukung: Delimiter titik koma (;), koma (,), tab.
    """
    # Strategi 1: Jika Excel (.xlsx)
    if file_name.lower().endswith('.xlsx'):
        try:
            return pd.read_excel(io.BytesIO(file_content), dtype=str)
        except Exception as e:
            raise ValueError(f"Gagal baca Excel: {e}")

    # Strategi 2: Jika CSV, coba kombinasi encoding & separator
    encodings_to_try = ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']
    separators_to_try = [';', ',', '\t']
    
    for enc in encodings_to_try:
        for sep in separators_to_try:
            try:
                # Reset pointer file stream
                file_stream = io.BytesIO(file_content)
                df = pd.read_csv(file_stream, sep=sep, dtype=str, encoding=enc)
                
                # Validasi sederhana: Jika kolomnya > 1, kemungkinan berhasil baca
                if len(df.columns) > 1:
                    return df
            except:
                continue
    
    # Strategi 3: Last Resort (Python Engine Auto-detect)
    try:
        return pd.read_csv(io.BytesIO(file_content), sep=None, engine='python', dtype=str)
    except Exception as e:
        raise ValueError("File tidak terbaca dengan semua metode encoding.")


# ==============================================================================
#                 4. FITUR KUOTA & TOPUP (MANAJEMEN USER)
# ==============================================================================

async def cek_kuota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan sisa kuota dan informasi akun user"""
    u = get_user(update.effective_user.id)
    
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
        f"💡 _Kuota hanya berkurang jika data ditemukan (HIT)._"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def admin_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fitur Admin untuk menambah kuota user secara manual"""
    if update.effective_user.id != ADMIN_ID: return
    
    try:
        # Format perintah: /topup [User_ID] [Jumlah]
        args = context.args
        if len(args) < 2:
            return await update.message.reply_text("⚠️ Format: `/topup [User_ID] [Jumlah]`", parse_mode='Markdown')
        
        target_id = args[0]
        amount = int(args[1])
        
        success, new_balance = topup_quota(target_id, amount)
        
        if success:
            await update.message.reply_text(f"✅ **TOPUP SUKSES**\nTotal Baru: {new_balance}", parse_mode='Markdown')
            # Notifikasi ke User
            try:
                await context.bot.send_message(
                    chat_id=target_id, 
                    text=f"🎉 **KUOTA BERTAMBAH!**\nAdmin menambah +{amount} kuota.\nTotal: {new_balance}"
                )
            except: pass
        else:
            await update.message.reply_text("❌ Gagal. Pastikan ID User benar.")
            
    except ValueError:
        await update.message.reply_text("⚠️ Jumlah harus berupa angka.")


# ==============================================================================
#                 5. FITUR SMART UPLOAD (ROBUST VERSION)
# ==============================================================================

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler awal saat file dokumen diterima"""
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
    
    # Simpan info file sementara
    context.user_data['upload_file_id'] = document.file_id
    context.user_data['upload_file_name'] = file_name

    # --- ALUR 1: USER BIASA ---
    if user_id != ADMIN_ID:
        await update.message.reply_text(
            f"📄 File `{file_name}` diterima.\n\nSatu langkah lagi: **Ini data dari Leasing/Finance apa?**",
            parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)
        )
        return U_LEASING_USER

    # --- ALUR 2: ADMIN (SMART PROCESSING) ---
    else:
        msg = await update.message.reply_text("⏳ **Membaca file (Mode: Robust)...**")
        
        try:
            # Download file
            new_file = await document.get_file()
            file_content = await new_file.download_as_bytearray()
            
            # 1. BACA FILE DENGAN FUNGSI ROBUST (Anti-BOM & Anti-Encoding Error)
            df = read_file_robust(file_content, file_name)
            
            # 2. NORMALISASI HEADER (Anti-Spasi & Typo)
            df, found_cols = smart_rename_columns(df)
            
            # Simpan dataframe
            context.user_data['df_records'] = df.to_dict(orient='records')
            
            # 3. VALIDASI KOLOM NOPOL
            if 'nopol' not in df.columns:
                cols_detected = ", ".join(df.columns[:5])
                await msg.edit_text(
                    "❌ **GAGAL DETEKSI NOPOL**\n\n"
                    f"Kolom terbaca: {cols_detected}\n"
                    "👉 Pastikan ada kolom: 'No Polisi', 'Plat', 'TNKB' (Titik/Spasi tidak masalah)."
                )
                return ConversationHandler.END

            has_finance = 'finance' in df.columns
            
            report = (
                f"✅ **SMART SCAN SUKSES**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Kolom Dikenali:** {', '.join(found_cols)}\n"
                f"📁 **Total Baris:** {len(df)}\n"
                f"🏦 **Kolom Leasing:** {'✅ ADA' if has_finance else '⚠️ TIDAK ADA'}\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"👉 **MASUKKAN NAMA LEASING:**\n"
                f"_(Ketik 'SKIP' jika sudah ada di file)_"
            )
            await msg.edit_text(report, parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
            return U_LEASING_ADMIN

        except Exception as e:
            await msg.edit_text(f"❌ Gagal memproses file: {str(e)}")
            return ConversationHandler.END

async def upload_leasing_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User: Memasukkan nama leasing"""
    leasing_name = update.message.text
    if leasing_name == "❌ BATAL": 
        await update.message.reply_text("🚫 Upload dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    file_id = context.user_data.get('upload_file_id')
    file_name = context.user_data.get('upload_file_name')
    user = get_user(update.effective_user.id)

    caption_admin = (
        f"📥 **UPLOAD FILE USER**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Pengirim:** {user.get('nama_lengkap')}\n"
        f"🏦 **Leasing:** {leasing_name.upper()}\n"
        f"📄 **File:** `{file_name}`"
    )
    await context.bot.send_document(chat_id=ADMIN_ID, document=file_id, caption=caption_admin, parse_mode='Markdown')
    await update.message.reply_text("✅ Terkirim ke Admin.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def upload_leasing_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Inject Nama Leasing & Preview"""
    leasing_input = update.message.text
    
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
    df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
    
    # Hapus Duplikat
    df = df.drop_duplicates(subset=['nopol'], keep='last').replace({np.nan: None})
    
    # Filter Kolom DB
    valid_cols_db = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch']
    for col in valid_cols_db:
        if col not in df.columns: df[col] = None
    
    sample = df.iloc[0]
    context.user_data['final_data_records'] = df[valid_cols_db].to_dict(orient='records')
    context.user_data['final_leasing_name'] = final_leasing_name
    
    preview_msg = (
        f"🔎 **PREVIEW DATA**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏦 **Leasing:** {final_leasing_name}\n"
        f"📊 **Total:** {len(df)} Unit\n\n"
        f"📝 **SAMPEL BARIS 1:**\n"
        f"🔹 Nopol: `{sample['nopol']}`\n"
        f"🔹 Unit: {sample['type']}\n"
        f"🔹 OVD: {sample['ovd']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Klik **EKSEKUSI** jika data benar."
    )
    
    await update.message.reply_text(preview_msg, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["🚀 EKSEKUSI", "❌ BATAL"]], one_time_keyboard=True))
    return U_CONFIRM_UPLOAD

async def upload_confirm_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Eksekusi Upload ke Supabase"""
    choice = update.message.text
    if choice != "🚀 EKSEKUSI":
        await update.message.reply_text("🚫 Dibatalkan.", reply_markup=ReplyKeyboardRemove())
        context.user_data.pop('final_data_records', None)
        return ConversationHandler.END
    
    status_msg = await update.message.reply_text("⏳ **Sedang mengupload...**", reply_markup=ReplyKeyboardRemove())
    final_data = context.user_data.get('final_data_records')
    
    success_count = 0
    fail_count = 0
    BATCH_SIZE = 1000
    
    for i in range(0, len(final_data), BATCH_SIZE):
        batch = final_data[i : i + BATCH_SIZE]
        try:
            supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
            success_count += len(batch)
        except:
            # Retry satuan jika batch gagal
            for item in batch:
                try:
                    supabase.table('kendaraan').upsert([item], on_conflict='nopol').execute()
                    success_count += 1
                except: fail_count += 1

    await status_msg.edit_text(f"✅ **SELESAI!**\n✅ Sukses: {success_count}\n❌ Gagal: {fail_count}", parse_mode='Markdown')
    context.user_data.pop('final_data_records', None)
    return ConversationHandler.END


# ==============================================================================
#                 6. FITUR ADMIN: STATS & USER MANAGEMENT
# ==============================================================================
# (Fungsi Stats, List Users, Ban, Unban, dll tetap dipertahankan FULL)

async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg_wait = await update.message.reply_text("⏳ *Menghitung...*")
    try:
        res_total = supabase.table('kendaraan').select("*", count="exact", head=True).execute()
        res_users = supabase.table('users').select("*", count="exact", head=True).execute()
        await msg_wait.edit_text(f"📊 **STATS**\n📂 Data: `{res_total.count:,}`\n👥 User: `{res_users.count:,}`", parse_mode='Markdown')
    except: await msg_wait.edit_text("❌ Error.")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        res = supabase.table('users').select("*").order('created_at', desc=True).limit(20).execute()
        msg = "📋 **20 USER TERBARU**\n"
        for u in res.data:
            icon = "✅" if u['status'] == 'active' else "⏳"
            msg += f"{icon} `{u['user_id']}` | {u.get('nama_lengkap','-')}\n"
        await update.message.reply_text(msg, parse_mode='Markdown')
    except: await update.message.reply_text("Gagal.")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        update_user_status(uid, 'rejected')
        await update.message.reply_text(f"⛔ User `{uid}` BANNED.")
    except: await update.message.reply_text("⚠️ Format: `/ban ID`")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        update_user_status(uid, 'active')
        await update.message.reply_text(f"✅ User `{uid}` UNBANNED.")
    except: await update.message.reply_text("⚠️ Format: `/unban ID`")

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        supabase.table('users').delete().eq('user_id', uid).execute()
        await update.message.reply_text(f"🗑️ User `{uid}` DIHAPUS.")
    except: await update.message.reply_text("⚠️ Format: `/delete ID`")

# ==============================================================================
#                 7. FITUR INFO, KONTAK, & NOTIFIKASI
# ==============================================================================

async def set_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GLOBAL_INFO
    if update.effective_user.id != ADMIN_ID: return
    GLOBAL_INFO = " ".join(context.args)
    await update.message.reply_text(f"✅ Info: {GLOBAL_INFO}")

async def del_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GLOBAL_INFO
    if update.effective_user.id != ADMIN_ID: return
    GLOBAL_INFO = ""
    await update.message.reply_text("🗑️ Info dihapus.")

async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return
    msg = " ".join(context.args)
    if not msg: return await update.message.reply_text("⚠️ `/admin pesan`")
    try:
        await context.bot.send_message(ADMIN_ID, f"📩 **PESAN**\n👤 {u['nama_lengkap']}\n💬 {msg}")
        await update.message.reply_text("✅ Terkirim.")
    except: pass

async def notify_hit_to_group(context, user_data, vehicle_data):
    hp_raw = user_data.get('no_hp', '-')
    hp_wa = '62' + hp_raw[1:] if hp_raw.startswith('0') else hp_raw
    txt = (f"🚨 **HIT!**\n👤 {user_data.get('nama_lengkap')}\n🚙 {vehicle_data.get('type')}\n🔢 `{vehicle_data.get('nopol')}`\n🏦 {vehicle_data.get('finance')}")
    kb = [[InlineKeyboardButton("📞 WA", url=f"https://wa.me/{hp_wa}")]]
    try: await context.bot.send_message(LOG_GROUP_ID, txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    except: pass

async def panduan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ("📖 **PANDUAN**\n1️⃣ **CARI:** Ketik Nopol\n2️⃣ **UPLOAD:** Kirim Excel\n3️⃣ **TOPUP:** Hubungi Admin")
    await update.message.reply_text(text, parse_mode='Markdown')


# ==============================================================================
#                 8. HANDLER CONVERSATION LENGKAP (FULL RESTORED)
# ==============================================================================
# (Saya menyertakan seluruh handler dengan struktur lengkap agar tidak ada fitur hilang)

# --- REGISTRASI ---
async def register_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = get_user(u.effective_user.id)
    if user: return await u.message.reply_text("✅ Sudah terdaftar.")
    await u.message.reply_text("📝 **NAMA:**", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return R_NAMA
async def register_nama(u: Update, c: ContextTypes.DEFAULT_TYPE): c.user_data['r_nama'] = u.message.text; await u.message.reply_text("📱 **NO HP:**"); return R_HP
async def register_hp(u: Update, c: ContextTypes.DEFAULT_TYPE): c.user_data['r_hp'] = u.message.text; await u.message.reply_text("📧 **EMAIL:**"); return R_EMAIL
async def register_email(u: Update, c: ContextTypes.DEFAULT_TYPE): c.user_data['r_email'] = u.message.text; await u.message.reply_text("📍 **KOTA:**"); return R_KOTA
async def register_kota(u: Update, c: ContextTypes.DEFAULT_TYPE): c.user_data['r_kota'] = u.message.text; await u.message.reply_text("🏢 **AGENCY:**"); return R_AGENCY
async def register_agency(u: Update, c: ContextTypes.DEFAULT_TYPE):
    c.user_data['r_agency'] = u.message.text
    await u.message.reply_text("✅ Konfirmasi?", reply_markup=ReplyKeyboardMarkup([["✅ KIRIM SEKARANG", "❌ ULANGI"]], one_time_keyboard=True)); return R_CONFIRM
async def register_confirm(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.message.text == "❌ ULANGI": return await cancel(u, c)
    data = {"user_id": u.effective_user.id, "nama_lengkap": c.user_data['r_nama'], "no_hp": c.user_data['r_hp'], "email": c.user_data['r_email'], "alamat": c.user_data['r_kota'], "agency": c.user_data['r_agency'], "quota": 1000, "status": "pending"}
    try: 
        supabase.table('users').insert(data).execute()
        await u.message.reply_text("✅ Terkirim!", reply_markup=ReplyKeyboardRemove())
        kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"appu_{data['user_id']}"), InlineKeyboardButton("❌ Reject", callback_data=f"reju_{data['user_id']}")]]
        await c.bot.send_message(ADMIN_ID, f"🔔 **DAFTAR BARU**\n👤 {data['nama_lengkap']}", reply_markup=InlineKeyboardMarkup(kb))
    except: await u.message.reply_text("⚠️ Gagal.")
    return ConversationHandler.END

# --- TAMBAH DATA ---
async def add_start(u: Update, c: ContextTypes.DEFAULT_TYPE): await u.message.reply_text("➕ **NOPOL:**", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return A_NOPOL
async def add_nopol(u: Update, c: ContextTypes.DEFAULT_TYPE): c.user_data['a_nopol'] = u.message.text.upper(); await u.message.reply_text("🚙 **UNIT:**"); return A_TYPE
async def add_type(u: Update, c: ContextTypes.DEFAULT_TYPE): c.user_data['a_type'] = u.message.text; await u.message.reply_text("🏦 **LEASING:**"); return A_LEASING
async def add_leasing(u: Update, c: ContextTypes.DEFAULT_TYPE): c.user_data['a_leasing'] = u.message.text; await u.message.reply_text("📝 **KET:**"); return A_NOKIR
async def add_nokir(u: Update, c: ContextTypes.DEFAULT_TYPE): c.user_data['a_nokir'] = u.message.text; await u.message.reply_text("✅ Kirim?", reply_markup=ReplyKeyboardMarkup([["✅ YA", "❌ BATAL"]], one_time_keyboard=True)); return A_CONFIRM
async def add_confirm(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.message.text != "✅ YA": return await cancel(u, c)
    n = c.user_data['a_nopol']
    c.bot_data[f"prop_{n}"] = {"nopol": n, "type": c.user_data['a_type'], "finance": c.user_data['a_leasing'], "ovd": c.user_data['a_nokir']}
    await u.message.reply_text("✅ Terkirim ke Admin.", reply_markup=ReplyKeyboardRemove())
    kb = [[InlineKeyboardButton("✅ Terima", callback_data=f"v_acc_{n}_{u.effective_user.id}"), InlineKeyboardButton("❌ Tolak", callback_data="v_rej")]]
    await c.bot.send_message(ADMIN_ID, f"📥 **MANUAL**\n🔢 {n}", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

# --- LAPOR & HAPUS ---
async def lapor_start(u: Update, c: ContextTypes.DEFAULT_TYPE): await u.message.reply_text("🗑️ **NOPOL:**", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return L_NOPOL
async def lapor_check(u: Update, c: ContextTypes.DEFAULT_TYPE):
    n = u.message.text.upper().replace(" ", "")
    res = supabase.table('kendaraan').select("*").eq('nopol', n).execute()
    if not res.data: await u.message.reply_text("❌ Tidak ada."); return ConversationHandler.END
    c.user_data['ln'] = n; await u.message.reply_text(f"⚠️ Lapor {n}?", reply_markup=ReplyKeyboardMarkup([["✅ YA", "❌ BATAL"]], one_time_keyboard=True)); return L_CONFIRM
async def lapor_confirm(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.message.text == "✅ YA":
        n = c.user_data['ln']; uid = u.effective_user.id
        await u.message.reply_text("✅ Terkirim.", reply_markup=ReplyKeyboardRemove())
        kb = [[InlineKeyboardButton("✅ Hapus", callback_data=f"del_acc_{n}_{uid}"), InlineKeyboardButton("❌ Tolak", callback_data=f"del_rej_{uid}")]]
        await c.bot.send_message(ADMIN_ID, f"🗑️ **REQ HAPUS**\n🔢 {n}", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

async def delete_start(u: Update, c: ContextTypes.DEFAULT_TYPE): 
    if u.effective_user.id != ADMIN_ID: return
    await u.message.reply_text("🗑️ **NOPOL:**", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return D_NOPOL
async def delete_check(u: Update, c: ContextTypes.DEFAULT_TYPE):
    n = u.message.text.upper().replace(" ", "")
    c.user_data['dn'] = n; await u.message.reply_text(f"⚠️ Hapus {n}?", reply_markup=ReplyKeyboardMarkup([["✅ YA", "❌ BATAL"]], one_time_keyboard=True)); return D_CONFIRM
async def delete_confirm(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.message.text == "✅ YA":
        supabase.table('kendaraan').delete().eq('nopol', c.user_data['dn']).execute()
        await u.message.reply_text("✅ Dihapus.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def cancel(u: Update, c: ContextTypes.DEFAULT_TYPE): await u.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

# ==============================================================================
#                 9. MAIN & HANDLERS
# ==============================================================================

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE): await u.message.reply_text(f"{GLOBAL_INFO}\n🤖 **ONEASPAL**\nCari data via Nopol.", parse_mode='Markdown')

async def handle_message(u: Update, c: ContextTypes.DEFAULT_TYPE):
    user = get_user(u.effective_user.id)
    if not user or user['status'] != 'active': return
    if user.get('quota', 0) <= 0: return await u.message.reply_text("⛔ Kuota Habis.")
    
    # WILDCARD SEARCH (SUFFIX MATCHING)
    kw = re.sub(r'[^a-zA-Z0-9]', '', u.message.text.upper())
    if len(kw) < 3: return await u.message.reply_text("⚠️ Min 3 huruf.")
    
    await c.bot.send_chat_action(u.effective_chat.id, constants.ChatAction.TYPING)
    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.ilike.%{kw}%,noka.eq.{kw},nosin.eq.{kw}").execute()
        if res.data:
            d = res.data[0]; update_quota_usage(user['user_id'], user['quota'])
            txt = (f"✅ **DITEMUKAN**\nUnit: {d.get('type')}\nNopol: `{d.get('nopol')}`\nOVD: {d.get('ovd')}\nFinance: {d.get('finance')}")
            await u.message.reply_text(txt, parse_mode='Markdown')
            await notify_hit_to_group(c, user, d)
        else: await u.message.reply_text(f"❌ Tidak Ditemukan: {kw}")
    except: await u.message.reply_text("❌ Error DB.")

async def callback_handler(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); d = q.data
    if d.startswith("appu_"): update_user_status(d.split("_")[1], 'active'); await q.edit_message_text("✅ User Aktif.")
    elif d.startswith("reju_"): update_user_status(d.split("_")[1], 'rejected'); await q.edit_message_text("⛔ User Ditolak.")
    elif d.startswith("v_acc_"): 
        n = d.split("_")[2]; item = c.bot_data.get(f"prop_{n}")
        if item: supabase.table('kendaraan').upsert(item).execute()
        await q.edit_message_text("✅ Data Masuk.")
    elif d == "v_rej": await q.edit_message_text("❌ Ditolak.")
    elif d.startswith("del_acc_"): supabase.table('kendaraan').delete().eq('nopol', d.split("_")[2]).execute(); await q.edit_message_text("✅ Dihapus.")
    elif d.startswith("del_rej_"): await q.edit_message_text("❌ Ditolak.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(token).post_init(post_init).build()
    
    # Handlers Conversation
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('register', register_start)], states={R_NAMA:[MessageHandler(filters.TEXT, register_nama)], R_HP:[MessageHandler(filters.TEXT, register_hp)], R_EMAIL:[MessageHandler(filters.TEXT, register_email)], R_KOTA:[MessageHandler(filters.TEXT, register_kota)], R_AGENCY:[MessageHandler(filters.TEXT, register_agency)], R_CONFIRM:[MessageHandler(filters.TEXT, register_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('tambah', add_start)], states={A_NOPOL:[MessageHandler(filters.TEXT, add_nopol)], A_TYPE:[MessageHandler(filters.TEXT, add_type)], A_LEASING:[MessageHandler(filters.TEXT, add_leasing)], A_NOKIR:[MessageHandler(filters.TEXT, add_nokir)], A_CONFIRM:[MessageHandler(filters.TEXT, add_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('lapor', lapor_start)], states={L_NOPOL:[MessageHandler(filters.TEXT, lapor_check)], L_CONFIRM:[MessageHandler(filters.TEXT, lapor_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('hapus', delete_start)], states={D_NOPOL:[MessageHandler(filters.TEXT, delete_check)], D_CONFIRM:[MessageHandler(filters.TEXT, delete_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[MessageHandler(filters.Document.ALL, upload_start)], states={U_LEASING_USER: [MessageHandler(filters.TEXT, upload_leasing_user)], U_LEASING_ADMIN: [MessageHandler(filters.TEXT, upload_leasing_admin)], U_CONFIRM_UPLOAD: [MessageHandler(filters.TEXT, upload_confirm_admin)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    
    # Commands
    app.add_handler(CommandHandler('start', start)); app.add_handler(CommandHandler('cekkuota', cek_kuota))
    app.add_handler(CommandHandler('topup', admin_topup)); app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('users', list_users)); app.add_handler(CommandHandler('ban', ban_user))
    app.add_handler(CommandHandler('unban', unban_user)); app.add_handler(CommandHandler('delete', delete_user))
    app.add_handler(CommandHandler('setinfo', set_info)); app.add_handler(CommandHandler('delinfo', del_info))
    app.add_handler(CommandHandler('admin', contact_admin)); app.add_handler(CommandHandler('panduan', panduan))
    
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ ONEASPAL BOT ONLINE - V1.9.5 (COMPLETE & ROBUST)")
    app.run_polling()