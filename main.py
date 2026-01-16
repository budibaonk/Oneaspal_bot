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

# ##############################################################################
# ##############################################################################
#
#                        BAGIAN 1: KONFIGURASI SISTEM
#
# ##############################################################################
# ##############################################################################

# ------------------------------------------------------------------------------
# 1. Load Environment Variables
# ------------------------------------------------------------------------------
load_dotenv()

# ------------------------------------------------------------------------------
# 2. Konfigurasi Logging System
# ------------------------------------------------------------------------------
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# 3. Ambil Credential dari Environment
# ------------------------------------------------------------------------------
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
token: str = os.environ.get("TELEGRAM_TOKEN")

# ------------------------------------------------------------------------------
# 4. Variable Global & Konstanta
# ------------------------------------------------------------------------------
GLOBAL_INFO = ""
LOG_GROUP_ID = -1003627047676  

# ------------------------------------------------------------------------------
# 5. Setup Admin ID
# ------------------------------------------------------------------------------
DEFAULT_ADMIN_ID = 7530512170
try:
    env_id = os.environ.get("ADMIN_ID")
    if env_id:
        ADMIN_ID = int(env_id)
    else:
        ADMIN_ID = DEFAULT_ADMIN_ID
except ValueError:
    ADMIN_ID = DEFAULT_ADMIN_ID

print(f"✅ SYSTEM BOOT: ADMIN ID TERDETEKSI = {ADMIN_ID}")

# ------------------------------------------------------------------------------
# 6. Validasi Kelengkapan Credential
# ------------------------------------------------------------------------------
if not url or not key or not token:
    print("❌ CRITICAL ERROR: Credential tidak lengkap!")
    exit()

# ------------------------------------------------------------------------------
# 7. Inisialisasi Koneksi Database Supabase
# ------------------------------------------------------------------------------
try:
    supabase: Client = create_client(url, key)
    print("✅ DATABASE: Koneksi ke Supabase Berhasil!")
except Exception as e:
    print(f"❌ DATABASE ERROR: Gagal koneksi ke Supabase. Pesan: {e}")
    exit()


# ##############################################################################
# ##############################################################################
#
#                        BAGIAN 2: KAMUS DATA & STATE
#
# ##############################################################################
# ##############################################################################

# ------------------------------------------------------------------------------
# KAMUS ALIAS KOLOM (NORMALISASI AGRESIF - VERTIKAL MODE)
# ------------------------------------------------------------------------------
COLUMN_ALIASES = {
    # Alias untuk Kolom NOPOL (Nomor Polisi)
    'nopol': [
        'nopolisi', 
        'nomorpolisi', 
        'nopol', 
        'noplat', 
        'nomorplat', 
        'nomorkendaraan', 
        'nokendaraan', 
        'nomer', 
        'tnkb', 
        'licenseplate', 
        'plat', 
        'nopolisikendaraan', 
        'nopil', 
        'polisi', 
        'platnomor',
        'platkendaraan', 
        'nomerpolisi',
        'no.polisi', 
        'nopol.',
        'no_pol',
        'police_no'
    ],
    
    # Alias untuk Kolom UNIT / TYPE KENDARAAN
    'type': [
        'type', 
        'tipe', 
        'unit', 
        'model', 
        'vehicle', 
        'jenis', 
        'deskripsiunit', 
        'merk', 
        'object', 
        'kendaraan', 
        'item', 
        'brand', 
        'typedeskripsi', 
        'vehiclemodel', 
        'namaunit', 
        'kend', 
        'namakendaraan',
        'merktype', 
        'objek',
        'jenisobjek',
        'item_description'
    ],
    
    # Alias untuk Kolom TAHUN PERAKITAN
    'tahun': [
        'tahun', 
        'year', 
        'thn', 
        'rakitan', 
        'th', 
        'yearofmanufacture', 
        'thnrakit', 
        'manufacturingyear',
        'tahun_pembuatan'
    ],
    
    # Alias untuk Kolom WARNA
    'warna': [
        'warna', 
        'color', 
        'colour', 
        'cat', 
        'kelir', 
        'warnakendaraan'
    ],
    
    # Alias untuk Kolom NO RANGKA (Chassis)
    'noka': [
        'noka', 
        'norangka', 
        'nomorrangka', 
        'chassis', 
        'chasis', 
        'vin', 
        'rangka', 
        'chassisno', 
        'norangka1', 
        'chasisno', 
        'vinno',
        'norang',
        'no_rangka'
    ],
    
    # Alias untuk Kolom NO MESIN (Engine)
    'nosin': [
        'nosin', 
        'nomesin', 
        'nomormesin', 
        'engine', 
        'mesin', 
        'engineno', 
        'nomesin1', 
        'engineno', 
        'noengine',
        'nomes',
        'no_mesin'
    ],
    
    # Alias untuk Kolom LEASING / FINANCE
    'finance': [
        'finance', 
        'leasing', 
        'lising', 
        'multifinance', 
        'cabang', 
        'partner', 
        'mitra', 
        'principal', 
        'company', 
        'client', 
        'financecompany', 
        'leasingname', 
        'keterangan', 
        'sumberdata',
        'financetype',
        'nama_leasing'
    ],
    
    # Alias untuk Kolom OVERDUE / KETERLAMBATAN
    'ovd': [
        'ovd', 
        'overdue', 
        'dpd', 
        'keterlambatan', 
        'hari', 
        'telat', 
        'aging', 
        'od', 
        'bucket', 
        'daysoverdue', 
        'overduedays', 
        'kiriman', 
        'kolektibilitas', 
        'kol',
        'kolek'
    ],
    
    # Alias untuk Kolom CABANG / WILAYAH
    'branch': [
        'branch', 
        'area', 
        'kota', 
        'pos', 
        'cabang', 
        'lokasi', 
        'wilayah', 
        'region', 
        'areaname', 
        'branchname', 
        'dealer'
    ]
}

# ------------------------------------------------------------------------------
# DEFINISI STATE CONVERSATION HANDLER
# ------------------------------------------------------------------------------

# 1. State untuk Registrasi User Baru
R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_CONFIRM = range(6)

# 2. State untuk Tambah Data Manual
A_NOPOL, A_TYPE, A_LEASING, A_NOKIR, A_CONFIRM = range(6, 11)

# 3. State untuk Lapor Hapus Data (Oleh User)
L_NOPOL, L_CONFIRM = range(11, 13) 

# 4. State untuk Hapus Data Manual (Oleh Admin)
D_NOPOL, D_CONFIRM = range(13, 15)

# 5. State untuk Smart Upload Excel/CSV (Oleh Admin & User)
U_LEASING_USER, U_LEASING_ADMIN, U_CONFIRM_UPLOAD = range(15, 18)

# 6. State untuk Admin Reject Reason (FITUR BARU v4.4)
REJECT_REASON = 18


# ##############################################################################
# ##############################################################################
#
#                        BAGIAN 3: FUNGSI HELPER & DATABASE
#
# ##############################################################################
# ##############################################################################

async def post_init(application: Application):
    """
    Fungsi ini dipanggil otomatis SATU KALI saat bot pertama kali menyala.
    Tugasnya: Memasang tombol menu (Blue Menu Button) di samping kolom chat Telegram user.
    """
    print("⏳ System: Sedang meng-set menu perintah Telegram...")
    
    await application.bot.set_my_commands([
        ("start", "🔄 Restart / Menu Utama"),
        ("cekkuota", "💳 Cek Sisa Kuota"),
        ("tambah", "➕ Tambah Unit Manual"),
        ("lapor", "🗑️ Lapor Unit Selesai"),
        ("register", "📝 Daftar Mitra Baru"),
        ("stats", "📊 Statistik Global"),
        ("leasing", "🏦 Audit Leasing Detail"),
        ("setinfo", "📢 Set Info Broadcast"),
        ("delinfo", "🗑️ Hapus Info"),
        ("admin", "📩 Hubungi Admin"),
        ("panduan", "📖 Petunjuk Penggunaan"),
    ])
    
    print("✅ System: Menu Perintah Berhasil Di-set!")

def get_user(user_id):
    """
    Mengambil data user dari tabel 'users' di Supabase.
    """
    try:
        response = supabase.table('users').select("*").eq('user_id', user_id).execute()
        if response.data:
            return response.data[0]
        else:
            return None
    except Exception as e:
        logging.error(f"❌ DB Error (get_user): {e}")
        return None

def get_agency_data(agency_name):
    """
    Mencari data Agency (B2B).
    """
    try:
        res = supabase.table('agencies').select("*").ilike('name', f"%{agency_name}%").execute()
        return res.data[0] if res.data else None
    except Exception as e:
        return None

def update_user_status(user_id, status):
    """
    Mengupdate status user (active/rejected/pending).
    """
    try:
        supabase.table('users').update({'status': status}).eq('user_id', user_id).execute()
        print(f"✅ User {user_id} status updated to {status}")
    except Exception as e: 
        logging.error(f"❌ Error update status: {e}")

def update_quota_usage(user_id, current_quota):
    """
    Mengurangi kuota user sebanyak 1 poin.
    """
    try:
        new_quota = current_quota - 1
        supabase.table('users').update({'quota': new_quota}).eq('user_id', user_id).execute()
    except Exception as e:
        logging.error(f"❌ Error update quota: {e}")

def topup_quota(user_id, amount):
    """
    Fungsi khusus Admin untuk menambah kuota user secara manual.
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
        logging.error(f"❌ Error topup: {e}")
        return False, 0

# --- FUNGSI PEMBERSIH TEKS (NUCLEAR NORMALIZER) ---
def normalize_text(text):
    if not isinstance(text, str): 
        return str(text).lower()
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()

def fix_header_position(df):
    target_aliases = COLUMN_ALIASES['nopol']
    for i in range(min(20, len(df))):
        row_values = [normalize_text(str(x)) for x in df.iloc[i].values]
        if any(alias in row_values for alias in target_aliases):
            print(f"✅ SMART HEADER: Ditemukan di baris ke-{i}")
            df.columns = df.iloc[i] 
            df = df.iloc[i+1:].reset_index(drop=True) 
            return df
    return df

def smart_rename_columns(df):
    new_cols = {}
    found_cols = []
    
    for original_col in df.columns:
        clean_col = normalize_text(original_col)
        renamed = False
        
        for standard_name, aliases in COLUMN_ALIASES.items():
            if clean_col == standard_name or clean_col in aliases:
                new_cols[original_col] = standard_name
                found_cols.append(standard_name)
                renamed = True
                break
        
        if not renamed:
            new_cols[original_col] = original_col

    df.rename(columns=new_cols, inplace=True)
    return df, found_cols

def read_file_robust(file_content, file_name):
    """
    Fungsi 'ADAPTIVE POLYGLOT' (v3.10) - The Ultimate File Reader.
    """
    if file_name.lower().endswith('.zip'):
        try:
            print("📦 ZIP FILE DETECTED: Mencoba ekstrak...")
            with zipfile.ZipFile(io.BytesIO(file_content)) as z:
                valid_files = [
                    f for f in z.namelist() 
                    if not f.startswith('__MACOSX') and f.lower().endswith(('.csv', '.xlsx', '.xls', '.txt'))
                ]
                
                if not valid_files:
                    raise ValueError("ZIP Kosong atau tidak ada file data (CSV/Excel/TXT) di dalamnya.")
                
                target_file = valid_files[0]
                print(f"📦 EXTRACTED: {target_file}")
                
                with z.open(target_file) as f:
                    file_content = f.read()
                    file_name = target_file
        except Exception as e:
            raise ValueError(f"Gagal membaca file ZIP: {str(e)}")

    if file_name.lower().endswith(('.xlsx', '.xls')):
        try:
            return pd.read_excel(io.BytesIO(file_content), dtype=str)
        except Exception as e:
            try:
                return pd.read_excel(io.BytesIO(file_content), dtype=str, engine='openpyxl')
            except Exception:
                print(f"⚠️ Gagal baca Excel murni. Mencoba baca sebagai Text/CSV...")
                pass 

    encodings_to_try = ['utf-8-sig', 'utf-8', 'cp1252', 'latin1', 'utf-16', 'utf-16le', 'utf-16be']
    separators_to_try = [None, ';', ',', '\t', '|']
    
    for enc in encodings_to_try:
        for sep in separators_to_try:
            try:
                df = pd.read_csv(
                    io.BytesIO(file_content), 
                    sep=sep, 
                    dtype=str, 
                    encoding=enc, 
                    engine='python',
                    on_bad_lines='skip'
                )
                if len(df.columns) > 1:
                    print(f"✅ READ SUCCESS: Encoding={enc}, Separator={sep}")
                    return df
            except:
                continue
    
    try:
        return pd.read_csv(io.BytesIO(file_content), sep=None, engine='python', dtype=str)
    except Exception as e:
        raise ValueError("File tidak terbaca dengan semua metode encoding.")


# ##############################################################################
# ##############################################################################
#
#                        BAGIAN 4: HANDLER REJECT REASON (BARU v4.4)
#
# ##############################################################################
# ##############################################################################

async def reject_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin memulai proses penolakan dengan alasan.
    """
    query = update.callback_query
    await query.answer()
    
    # Ambil User ID
    context.user_data['reject_target_uid'] = query.data.split("_")[1]
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📝 **KONFIRMASI PENOLAKAN**\n\nSilakan ketik **ALASAN PENOLAKAN** (Pesan ini akan dikirim ke User):",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
    )
    return REJECT_REASON

async def reject_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin mengirim alasan penolakan.
    """
    reason = update.message.text
    
    if reason == "❌ BATAL":
        await update.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
        
    target_uid = context.user_data.get('reject_target_uid')
    update_user_status(target_uid, 'rejected')
    
    # Kirim Pesan Personal ke User
    try:
        msg_user = (
            f"⛔ **PENDAFTARAN DITOLAK**\n\n"
            f"Mohon maaf, pendaftaran Anda belum dapat kami setujui.\n"
            f"📝 **Alasan:** {reason}\n\n"
            f"Silakan perbaiki data dan daftar ulang via /register."
        )
        await context.bot.send_message(chat_id=target_uid, text=msg_user, parse_mode='Markdown')
    except: pass
    
    await update.message.reply_text(f"✅ User Ditolak.\nAlasan: {reason}", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ##############################################################################
# ##############################################################################
#
#                        BAGIAN 5: HANDLER FITUR USER
#
# ##############################################################################
# ##############################################################################

async def cek_kuota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler command /cekkuota.
    """
    user_id = update.effective_user.id
    u = get_user(user_id)
    
    if not u or u['status'] != 'active': 
        return await update.message.reply_text("⛔ **AKSES DITOLAK**\nAkun Anda belum terdaftar atau belum aktif.")
    
    msg = (
        f"💳 **INFO AKUN MITRA**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Nama:** {u.get('nama_lengkap')}\n"
        f"🏢 **Agency:** {u.get('agency')}\n"
        f"📱 **ID:** `{u.get('user_id')}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔋 **SISA KUOTA:** `{u.get('quota', 0)}` HIT\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 _Catatan: Kuota hanya berkurang jika data ditemukan (HIT). Pencarian ZONK tidak memotong kuota._"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def admin_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler command /topup (Khusus Admin).
    """
    if update.effective_user.id != ADMIN_ID: return 
    
    try:
        args = context.args
        if len(args) < 2:
            return await update.message.reply_text("⚠️ Gunakan: `/topup [User_ID] [Jumlah]`", parse_mode='Markdown')
        
        target_id = args[0]
        amount = int(args[1])
        
        success, new_balance = topup_quota(target_id, amount)
        
        if success:
            await update.message.reply_text(f"✅ **TOPUP SUKSES**\nUser ID: `{target_id}`\nTambah: +{amount}\nTotal Baru: {new_balance}", parse_mode='Markdown')
            try:
                await context.bot.send_message(
                    chat_id=target_id, 
                    text=f"🎉 **KUOTA BERTAMBAH!**\n\nAdmin telah menambahkan +{amount} kuota ke akun Anda.\nTotal Kuota: {new_balance}"
                )
            except: pass 
        else:
            await update.message.reply_text("❌ Gagal Topup. Pastikan ID User benar.")
            
    except ValueError:
        await update.message.reply_text("⚠️ Jumlah harus berupa angka.")

async def handle_photo_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler Otomatis untuk Bukti Transfer (Gambar).
    """
    if update.effective_chat.type != "private": return
    
    u = get_user(update.effective_user.id)
    if not u: return
    
    photo_file = await update.message.photo[-1].get_file()
    caption = update.message.caption or "Topup Quota"
    
    await update.message.reply_text("✅ **Bukti diterima!**\nSedang diteruskan ke Admin...", quote=True)
    
    msg_admin = (
        f"💰 **PERMINTAAN TOPUP**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Nama: {u['nama_lengkap']}\n"
        f"🆔 ID: `{u['user_id']}`\n"
        f"🔋 Saldo: {u.get('quota', 0)}\n"
        f"📝 Ket: {caption}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    
    kb = [
        [InlineKeyboardButton("✅ Isi 50", callback_data=f"topup_{u['user_id']}_50"), InlineKeyboardButton("✅ Isi 120", callback_data=f"topup_{u['user_id']}_120")],
        [InlineKeyboardButton("✅ Isi 300", callback_data=f"topup_{u['user_id']}_300"), InlineKeyboardButton("❌ TOLAK", callback_data=f"topup_{u['user_id']}_rej")]
    ]
    
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_file.file_id, caption=msg_admin, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')


# ##############################################################################
# ##############################################################################
#
#                 BAGIAN 6: SMART UPLOAD (ADAPTIVE POLYGLOT)
#
# ##############################################################################
# ##############################################################################

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    processing_msg = await update.message.reply_text("⏳ **File diterima, sedang menganalisa format...**", parse_mode='Markdown')

    user_data = get_user(user_id)
    doc = update.message.document
    file_name = doc.file_name

    if not user_data or user_data['status'] != 'active':
        if user_id != ADMIN_ID: 
            await processing_msg.edit_text("⛔ **AKSES DITOLAK**\nAnda belum terdaftar aktif.")
            return ConversationHandler.END

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.UPLOAD_DOCUMENT)
    
    context.user_data['upload_file_id'] = doc.file_id
    context.user_data['upload_file_name'] = file_name

    if user_id != ADMIN_ID:
        await processing_msg.delete()
        await update.message.reply_text(
            f"📄 File `{file_name}` diterima.\n\n"
            "Satu langkah lagi: **Ini data dari Leasing/Finance apa?**\n"
            "(Contoh: BCA, Mandiri, Adira)",
            parse_mode='Markdown', 
            reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)
        )
        return U_LEASING_USER

    else:
        try:
            new_file = await doc.get_file()
            file_content = await new_file.download_as_bytearray()
            
            df = read_file_robust(file_content, file_name)
            df = fix_header_position(df)
            df, found_cols = smart_rename_columns(df)
            
            context.user_data['df_records'] = df.to_dict(orient='records')
            
            if 'nopol' not in df.columns:
                await processing_msg.edit_text("❌ **GAGAL DETEKSI NOPOL**\nPastikan ada kolom: 'No Polisi', 'Plat', atau 'TNKB'.")
                return ConversationHandler.END

            has_finance = 'finance' in df.columns
            
            report = (
                f"✅ **SCAN SUKSES**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Kolom Dikenali:** {', '.join(found_cols)}\n"
                f"📁 **Total Baris:** {len(df)}\n"
                f"🏦 **Kolom Leasing:** {'✅ ADA' if has_finance else '⚠️ TIDAK ADA'}\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"👉 **MASUKKAN NAMA LEASING UNTUK DATA INI:**\n"
                f"_(Ketik 'SKIP' jika ingin menggunakan kolom leasing dari file)_"
            )
            
            await processing_msg.delete()
            await update.message.reply_text(
                report, 
                parse_mode='Markdown', 
                reply_markup=ReplyKeyboardMarkup([["SKIP"], ["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
            )
            return U_LEASING_ADMIN

        except Exception as e:
            await processing_msg.edit_text(f"❌ **ERROR PEMBACAAN:**\n`{str(e)}`", parse_mode='Markdown')
            return ConversationHandler.END

async def upload_leasing_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    leasing_name = update.message.text
    if leasing_name == "❌ BATAL": 
        await update.message.reply_text("🚫 Upload dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    file_id = context.user_data.get('upload_file_id')
    file_name = context.user_data.get('upload_file_name')
    user = get_user(update.effective_user.id)

    caption_admin = (
        f"📥 **UPLOAD FILE DARI MITRA**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Pengirim:** {user.get('nama_lengkap')}\n"
        f"🏦 **Leasing:** {leasing_name.upper()}\n"
        f"📄 **File:** `{file_name}`\n"
    )
    await context.bot.send_document(chat_id=ADMIN_ID, document=file_id, caption=caption_admin, parse_mode='Markdown')
    await update.message.reply_text("✅ **TERKIRIM!**\nFile Anda telah dikirim ke Admin.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def upload_leasing_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    leasing_input = update.message.text
    df = pd.DataFrame(context.user_data['df_records'])
    
    final_leasing_name = leasing_input.upper()
    if final_leasing_name != 'SKIP':
        df['finance'] = final_leasing_name
    elif 'finance' not in df.columns:
        final_leasing_name = "UNKNOWN (AUTO)"
        df['finance'] = 'UNKNOWN'
    else:
        final_leasing_name = "SESUAI FILE"

    df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
    df = df.drop_duplicates(subset=['nopol'], keep='last').replace({np.nan: None})
    
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
        f"📊 **Total Data:** {len(df)} Unit\n\n"
        f"📝 **CONTOH DATA:**\n"
        f"🔹 Nopol: `{sample['nopol']}`\n"
        f"🔹 Unit: {sample['type']}\n"
        f"🔹 OVD: {sample['ovd']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Klik **EKSEKUSI** untuk memulai upload."
    )
    
    await update.message.reply_text(
        preview_msg, 
        parse_mode='Markdown', 
        reply_markup=ReplyKeyboardMarkup([["🚀 EKSEKUSI", "❌ BATAL"]], one_time_keyboard=True)
    )
    return U_CONFIRM_UPLOAD

async def upload_confirm_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    if choice != "🚀 EKSEKUSI":
        await update.message.reply_text("🚫 Proses upload dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    status_msg = await update.message.reply_text("⏳ **MEMULAI UPLOAD...**", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
    
    final_data = context.user_data.get('final_data_records')
    success_count = 0
    fail_count = 0
    
    BATCH_SIZE = 1000 
    total_records = len(final_data)
    start_time = time.time()
    
    for i in range(0, total_records, BATCH_SIZE):
        batch = final_data[i : i + BATCH_SIZE]
        try:
            supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
            success_count += len(batch)
        except Exception as e:
            for item in batch:
                try:
                    supabase.table('kendaraan').upsert([item], on_conflict='nopol').execute()
                    success_count += 1
                except Exception as inner_e:
                    fail_count += 1
        
        if (i + BATCH_SIZE) % 5000 == 0:
            await status_msg.edit_text(f"⏳ **MENGUPLOAD...**\n✅ {min(i+BATCH_SIZE, total_records)} / {total_records} terproses...")
            await asyncio.sleep(0.5) 

    duration = round(time.time() - start_time, 2)
    
    report = (
        f"✅ **UPLOAD SUKSES 100%!**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 **Total:** {success_count}\n"
        f"❌ **Gagal:** {fail_count}\n"
        f"⏱ **Waktu:** {duration}s\n"
        f"🚀 **Status:** Database Updated!"
    )
    await status_msg.delete()
    await update.message.reply_text(report, parse_mode='Markdown')
    
    context.user_data.pop('final_data_records', None)
    return ConversationHandler.END


# ##############################################################################
# ##############################################################################
#
#                 BAGIAN 7: FITUR ADMIN (STATS & LEASING UPDATE)
#
# ##############################################################################
# ##############################################################################

async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
    msg_wait = await update.message.reply_text("⏳ *Sedang menghitung data...*", parse_mode='Markdown')

    try:
        res_total = supabase.table('kendaraan').select("*", count="exact", head=True).execute()
        res_users = supabase.table('users').select("*", count="exact", head=True).execute()
        
        msg = (
            f"📊 **STATISTIK ONEASPAL**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📂 **Total Data Kendaraan:** `{res_total.count:,}` Unit\n"
            f"👥 **Total Mitra Terdaftar:** `{res_users.count:,}` User\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💡 _Gunakan perintah /leasing untuk melihat detail per perusahaan._"
        )
        await msg_wait.edit_text(msg, parse_mode='Markdown')

    except Exception as e:
        await msg_wait.edit_text(f"❌ Error statistik: {e}")

async def get_leasing_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    FITUR BARU v4.4: Audit Leasing dengan Pagination 1000 (FIX BUG).
    Agar membaca seluruh 650rb data.
    """
    if update.effective_user.id != ADMIN_ID: return
    msg = await update.message.reply_text("⏳ *Sedang mengaudit seluruh data (Mohon tunggu)...*", parse_mode='Markdown')
    
    try:
        finance_counts = Counter()
        off = 0
        BATCH = 1000
        
        while True:
            res = supabase.table('kendaraan').select("finance").range(off, off + BATCH - 1).execute()
            data = res.data
            if not data: break
            
            batch_finances = [str(d.get('finance')).strip().upper() if d.get('finance') else "UNKNOWN" for d in data]
            finance_counts.update(batch_finances)
            
            if len(data) < BATCH: break
            off += BATCH
            
            if off % 50000 == 0: 
                try: await msg.edit_text(f"⏳ *Mengaudit... ({off:,} data terproses)*", parse_mode='Markdown')
                except: pass

        report = "🏦 **LAPORAN AUDIT LEASING**\n━━━━━━━━━━━━━━━━━━\n"
        for name, count in finance_counts.most_common():
             if name not in ["UNKNOWN", "NONE", "NAN", "-", ""]:
                 report += f"🔹 **{name}:** `{count:,}` unit\n"
        
        if finance_counts["UNKNOWN"] > 0:
            report += f"\n❓ **TANPA NAMA:** `{finance_counts['UNKNOWN']:,}` unit"

        if len(report) > 4000:
            report = report[:4000] + "\n\n⚠️ _(Laporan terpotong, data terlalu banyak)_"
            
        await msg.edit_text(report, parse_mode='Markdown')

    except Exception as e:
        await msg.edit_text(f"❌ Error Audit: {str(e)}")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
    try:
        res = supabase.table('users').select("*").execute()
        all_data = res.data
        active_list = [u for u in all_data if u.get('status') == 'active']
        
        msg = f"📋 **DAFTAR MITRA AKTIF ({len(active_list)})**\n━━━━━━━━━━━━━━━━━━\n"
        for i, u in enumerate(active_list, 1):
            msg += f"{i}. 👤 **{u.get('nama_lengkap')}**\n   🏢 {u.get('agency')}\n   🆔 `{u.get('user_id')}`\n\n"
        
        if len(msg) > 4000:
            await update.message.reply_text(msg[:4000], parse_mode='Markdown')
        else:
            await update.message.reply_text(msg, parse_mode='Markdown')
    except: await update.message.reply_text("❌ Gagal.")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        update_user_status(uid, 'rejected')
        await update.message.reply_text(f"⛔ User `{uid}` DI-BAN.")
    except: await update.message.reply_text("⚠️ Format: `/ban ID`")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        update_user_status(uid, 'active')
        await update.message.reply_text(f"✅ User `{uid}` DI-UNBAN.")
    except: await update.message.reply_text("⚠️ Format: `/unban ID`")

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        supabase.table('users').delete().eq('user_id', uid).execute()
        await update.message.reply_text(f"🗑️ User `{uid}` DIHAPUS PERMANEN.")
    except: await update.message.reply_text("⚠️ Format: `/delete ID`")

async def set_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GLOBAL_INFO
    if update.effective_user.id != ADMIN_ID: return
    msg = " ".join(context.args)
    GLOBAL_INFO = msg
    await update.message.reply_text(f"✅ **Info Terpasang!**\n{GLOBAL_INFO}", parse_mode='Markdown')

async def del_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GLOBAL_INFO
    if update.effective_user.id != ADMIN_ID: return
    GLOBAL_INFO = ""
    await update.message.reply_text("🗑️ Info dihapus.")

async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return
    msg_content = " ".join(context.args)
    if not msg_content: return await update.message.reply_text("⚠️ Contoh: `/admin Lapor...`", parse_mode='Markdown')
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"📩 **PESAN DARI MITRA**\n👤 {u.get('nama_lengkap')}\n💬 {msg_content}")
        await update.message.reply_text("✅ Terkirim ke Admin.")
    except: await update.message.reply_text("❌ Gagal.")

async def notify_hit_to_group(context: ContextTypes.DEFAULT_TYPE, user_data, vehicle_data):
    """
    NOTIFIKASI LENGKAP & PROFESIONAL
    """
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
    try: await context.bot.send_message(chat_id=LOG_GROUP_ID, text=report_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except: pass

async def panduan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text_panduan = "📖 **PANDUAN ONEASPAL**\n\n1️⃣ **CARI DATA**\nKetik Nopol/Noka/Nosin.\n✅ Contoh: `B1234ABC`\n\n2️⃣ **CEK KUOTA:** `/cekkuota`\n3️⃣ **TAMBAH DATA:** `/tambah`\n4️⃣ **LAPOR SELESAI:** `/lapor`\n5️⃣ **KONTAK ADMIN:** `/admin [pesan]`\n6️⃣ **UPLOAD:** Kirim file Excel."
    await update.message.reply_text(text_panduan, parse_mode='Markdown')

async def add_agency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        args = update.message.text.split()[1:]
        data = {"name": " ".join(args[:-2]), "group_id": int(args[-2]), "admin_id": int(args[-1])}
        supabase.table('agencies').insert(data).execute()
        await update.message.reply_text("✅ Agency Added.")
    except: await update.message.reply_text("⚠️ Format: `/addagency [NAMA] [GROUP] [ADMIN]`")

async def test_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID: 
        try: await context.bot.send_message(chat_id=LOG_GROUP_ID, text="🔔 **TES NOTIFIKASI OK!**"); await update.message.reply_text("✅ OK")
        except: await update.message.reply_text("❌ Gagal.")


# ##############################################################################
# ##############################################################################
#
#                        BAGIAN 8: HANDLER CONVERSATION
#
# ##############################################################################
# ##############################################################################

# --- LAPOR ---
async def lapor_delete_start(update, context): 
    if not get_user(update.effective_user.id): return
    await update.message.reply_text("🗑️ **LAPOR UNIT SELESAI**\nMasukkan Nopol:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return L_NOPOL
async def lapor_delete_check(update, context):
    n = update.message.text.upper().replace(" ", "")
    if not supabase.table('kendaraan').select("*").eq('nopol', n).execute().data: await update.message.reply_text("❌ Nopol tidak ditemukan."); return ConversationHandler.END
    context.user_data['lapor_nopol'] = n; await update.message.reply_text(f"⚠️ Lapor Hapus `{n}`?", reply_markup=ReplyKeyboardMarkup([["✅ KIRIM LAPORAN", "❌ BATAL"]])); return L_CONFIRM
async def lapor_delete_confirm(update, context):
    if update.message.text == "✅ KIRIM LAPORAN":
        n = context.user_data['lapor_nopol']; u = get_user(update.effective_user.id)
        await update.message.reply_text("✅ Laporan terkirim.", reply_markup=ReplyKeyboardRemove())
        kb = [[InlineKeyboardButton("✅ Setujui", callback_data=f"del_acc_{n}_{u['user_id']}"), InlineKeyboardButton("❌ Tolak", callback_data=f"del_rej_{u['user_id']}")]]
        await context.bot.send_message(ADMIN_ID, f"🗑️ **REQ HAPUS**\nNopol: `{n}`\nPelapor: {u['nama_lengkap']}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return ConversationHandler.END

# --- HAPUS MANUAL ---
async def delete_unit_start(update, context):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🗑️ **HAPUS MANUAL**\nNopol:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return D_NOPOL
async def delete_unit_check(update, context):
    n = update.message.text.upper().replace(" ", "")
    context.user_data['del_nopol'] = n; await update.message.reply_text(f"Hapus Permanen `{n}`?", reply_markup=ReplyKeyboardMarkup([["✅ YA, HAPUS", "❌ BATAL"]])); return D_CONFIRM
async def delete_unit_confirm(update, context):
    if update.message.text == "✅ YA, HAPUS": supabase.table('kendaraan').delete().eq('nopol', context.user_data['del_nopol']).execute(); await update.message.reply_text("✅ Terhapus.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- REGISTER ---
async def register_start(update, context): 
    if get_user(update.effective_user.id): return await update.message.reply_text("✅ Sudah terdaftar.")
    await update.message.reply_text("📝 **PENDAFTARAN MITRA**\n1️⃣ Nama Lengkap:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return R_NAMA
async def register_nama(update, context): context.user_data['r_nama'] = update.message.text; await update.message.reply_text("2️⃣ No HP (WA):"); return R_HP
async def register_hp(update, context): context.user_data['r_hp'] = update.message.text; await update.message.reply_text("3️⃣ Email:"); return R_EMAIL
async def register_email(update, context): context.user_data['r_email'] = update.message.text; await update.message.reply_text("4️⃣ Kota:"); return R_KOTA
async def register_kota(update, context): context.user_data['r_kota'] = update.message.text; await update.message.reply_text("5️⃣ Agency:"); return R_AGENCY
async def register_agency(update, context): context.user_data['r_agency'] = update.message.text; await update.message.reply_text("✅ Kirim Data?", reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ ULANGI"]])); return R_CONFIRM
async def register_confirm(update, context):
    if update.message.text != "✅ KIRIM": return await cancel(update, context)
    d = {"user_id": update.effective_user.id, "nama_lengkap": context.user_data['r_nama'], "no_hp": context.user_data['r_hp'], "email": context.user_data['r_email'], "alamat": context.user_data['r_kota'], "agency": context.user_data['r_agency'], "quota": 1000, "status": "pending"}
    try:
        supabase.table('users').insert(d).execute()
        await update.message.reply_text("✅ **PENDAFTARAN BERHASIL!**\nMohon tunggu verifikasi Admin.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
        kb = [[InlineKeyboardButton("✅ Terima", callback_data=f"appu_{d['user_id']}"), InlineKeyboardButton("❌ Tolak", callback_data=f"reju_{d['user_id']}")]]
        await context.bot.send_message(ADMIN_ID, f"🔔 **NEW USER**\n👤 {d['nama_lengkap']}\n🏢 {d['agency']}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    except: await update.message.reply_text("❌ Gagal Mendaftar.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- TAMBAH DATA ---
async def add_data_start(update, context):
    if not get_user(update.effective_user.id): return
    await update.message.reply_text("➕ **TAMBAH UNIT**\n1️⃣ Nopol:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return A_NOPOL
async def add_nopol(update, context): context.user_data['a_nopol'] = update.message.text.upper(); await update.message.reply_text("2️⃣ Type Mobil:"); return A_TYPE
async def add_type(update, context): context.user_data['a_type'] = update.message.text; await update.message.reply_text("3️⃣ Leasing:"); return A_LEASING
async def add_leasing(update, context): context.user_data['a_leasing'] = update.message.text; await update.message.reply_text("4️⃣ Ket (OVD):"); return A_NOKIR
async def add_nokir(update, context): context.user_data['a_nokir'] = update.message.text; await update.message.reply_text("✅ Kirim?", reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ BATAL"]])); return A_CONFIRM
async def add_confirm(update, context):
    if update.message.text != "✅ KIRIM": return await cancel(update, context)
    n = context.user_data['a_nopol']
    context.bot_data[f"prop_{n}"] = {"nopol": n, "type": context.user_data['a_type'], "finance": context.user_data['a_leasing'], "ovd": context.user_data['a_nokir']}
    await update.message.reply_text("✅ Terkirim ke Admin.", reply_markup=ReplyKeyboardRemove())
    kb = [[InlineKeyboardButton("✅ Terima", callback_data=f"v_acc_{n}_{update.effective_user.id}"), InlineKeyboardButton("❌ Tolak", callback_data="v_rej")]]
    await context.bot.send_message(ADMIN_ID, f"📥 **DATA BARU**\nNopol: `{n}`", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return ConversationHandler.END


# ##############################################################################
# ##############################################################################
#
#                        BAGIAN 9: MAIN HANDLER
#
# ##############################################################################
# ##############################################################################

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Global Info check
    global GLOBAL_INFO
    info_section = ""
    if GLOBAL_INFO:
        info_section = f"📢 <b>INFO:</b> {GLOBAL_INFO}\n━━━━━━━━━━━━━━━━━━\n\n"

    # Pesan Sesuai Request Bapak (Format HTML)
    welcome_msg = (
        f"{info_section}"
        f"🤖 <b>Selamat Datang di Oneaspalbot</b>\n\n"
        f"<b>Salam Satu Aspal!</b> 👋\n"
        f"Halo, Rekan Mitra Lapangan.\n\n"
        f"<b>Oneaspalbot</b> adalah asisten digital profesional untuk mempermudah pencarian data kendaraan secara real-time.\n\n"
        f"Cari data melalui:\n"
        f"✅ Nomor Polisi (Nopol)\n"
        f"✅ Nomor Rangka (Noka)\n"
        f"✅ Nomor Mesin (Nosin)\n\n"
        f"⚠️ <b>PENTING:</b> Akses bersifat PRIVATE. Anda wajib mendaftar dan menunggu verifikasi Admin.\n\n"
        f"--- 👉 Jalankan perintah /register untuk mendaftar."
    )
    
    # Kirim pesan dengan mode HTML
    await update.message.reply_text(welcome_msg, parse_mode=constants.ParseMode.HTML)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return
    if u.get('quota', 0) <= 0: return await update.message.reply_text("⛔ **KUOTA HABIS**\nSilakan hubungi Admin untuk Top Up.", parse_mode='Markdown')
    
    kw = re.sub(r'[^a-zA-Z0-9]', '', update.message.text.upper())
    if len(kw) < 3: return await update.message.reply_text("⚠️ Masukkan minimal 3 karakter.")
    
    await context.bot.send_chat_action(update.effective_chat.id, constants.ChatAction.TYPING)
    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.ilike.%{kw}%,noka.eq.{kw},nosin.eq.{kw}").execute()
        if res.data:
            d = res.data[0]; update_quota_usage(u['user_id'], u['quota'])
            info = f"📢 **INFO:** {GLOBAL_INFO}\n━━━━━━━━━━━━━━━━━━\n" if GLOBAL_INFO else ""
            txt = (
                f"{info}✅ **DATA DITEMUKAN**\n━━━━━━━━━━━━━━━━━━\n"
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
                f"Ini bukan alat yang SAH untuk penarikan. Konfirmasi ke PIC leasing."
            )
            await update.message.reply_text(txt, parse_mode='Markdown')
            await notify_hit_to_group(context, u, d)
        else:
            info = f"📢 **INFO:** {GLOBAL_INFO}\n\n" if GLOBAL_INFO else ""
            await update.message.reply_text(f"{info}❌ **DATA TIDAK DITEMUKAN**\n`{kw}`", parse_mode='Markdown')
    except Exception as e: 
        await update.message.reply_text("❌ Terjadi kesalahan database.")

async def cancel(update, context): await update.message.reply_text("🚫 Dibatalkan.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

async def callback_handler(update, context):
    q = update.callback_query; await q.answer(); d = q.data
    # Fitur Topup (v4.0)
    if d.startswith("topup_"):
        parts = d.split("_"); uid = int(parts[1])
        if parts[2] == "rej": await context.bot.send_message(uid, "❌ Topup DITOLAK."); await q.edit_message_caption("❌ Ditolak.")
        else: topup_quota(uid, int(parts[2])); await context.bot.send_message(uid, f"✅ Topup {parts[2]} Berhasil."); await q.edit_message_caption("✅ Sukses.")
    # Fitur Approve User
    elif d.startswith("appu_"): update_user_status(d.split("_")[1], 'active'); await q.edit_message_text("✅ User DISETUJUI."); await context.bot.send_message(d.split("_")[1], "🎉 **AKUN AKTIF!**")
    # Fitur Approve Data Manual
    elif d.startswith("v_acc_"): 
        n=d.split("_")[2]; item=context.bot_data.get(f"prop_{n}"); supabase.table('kendaraan').upsert(item).execute(); await q.edit_message_text("✅ Masuk DB."); await context.bot.send_message(d.split("_")[3], f"✅ Data `{n}` Disetujui.")
    elif d == "v_rej": await q.edit_message_text("❌ Ditolak.")
    # Fitur Approve Delete
    elif d.startswith("del_acc_"): supabase.table('kendaraan').delete().eq('nopol', d.split("_")[2]).execute(); await q.edit_message_text("✅ Dihapus."); await context.bot.send_message(d.split("_")[3], "✅ Laporan Disetujui.")
    elif d.startswith("del_rej_"): await q.edit_message_text("❌ Ditolak."); await context.bot.send_message(d.split("_")[2], "❌ Laporan Ditolak.")

if __name__ == '__main__':
    print("🚀 ONEASPAL BOT v4.5 (RESTORED & UPGRADED) STARTING...")
    app = ApplicationBuilder().token(token).post_init(post_init).build()
    
    # REJECT REASON HANDLER (NEW v4.4)
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(reject_start, pattern='^reju_')], states={REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, reject_complete)]}, fallbacks=[CommandHandler('cancel', cancel)]))

    app.add_handler(ConversationHandler(entry_points=[MessageHandler(filters.Document.ALL, upload_start)], states={U_LEASING_USER: [MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), upload_leasing_user)], U_LEASING_ADMIN: [MessageHandler(filters.TEXT, upload_leasing_admin)], U_CONFIRM_UPLOAD: [MessageHandler(filters.TEXT, upload_confirm_admin)]}, fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)], allow_reentry=True))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('register', register_start)], states={R_NAMA:[MessageHandler(filters.TEXT, register_nama)], R_HP:[MessageHandler(filters.TEXT, register_hp)], R_EMAIL:[MessageHandler(filters.TEXT, register_email)], R_KOTA:[MessageHandler(filters.TEXT, register_kota)], R_AGENCY:[MessageHandler(filters.TEXT, register_agency)], R_CONFIRM:[MessageHandler(filters.TEXT, register_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('tambah', add_data_start)], states={A_NOPOL:[MessageHandler(filters.TEXT, add_nopol)], A_TYPE:[MessageHandler(filters.TEXT, add_type)], A_LEASING:[MessageHandler(filters.TEXT, add_leasing)], A_NOKIR:[MessageHandler(filters.TEXT, add_nokir)], A_CONFIRM:[MessageHandler(filters.TEXT, add_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('lapor', lapor_delete_start)], states={L_NOPOL:[MessageHandler(filters.TEXT, lapor_delete_check)], L_CONFIRM:[MessageHandler(filters.TEXT, lapor_delete_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('hapus', delete_unit_start)], states={D_NOPOL:[MessageHandler(filters.TEXT, delete_unit_check)], D_CONFIRM:[MessageHandler(filters.TEXT, delete_unit_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('cekkuota', cek_kuota))
    app.add_handler(CommandHandler('topup', admin_topup))
    app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('leasing', get_leasing_list)) # NEW
    app.add_handler(CommandHandler('users', list_users))
    app.add_handler(CommandHandler('ban', ban_user))
    app.add_handler(CommandHandler('unban', unban_user))
    app.add_handler(CommandHandler('delete', delete_user))
    app.add_handler(CommandHandler('testgroup', test_group))
    app.add_handler(CommandHandler('panduan', panduan))
    app.add_handler(CommandHandler('setinfo', set_info)) # FIXED
    app.add_handler(CommandHandler('delinfo', del_info)) # FIXED
    app.add_handler(CommandHandler('admin', contact_admin))
    app.add_handler(CommandHandler('addagency', add_agency)) # NEW

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_topup))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ BOT ONLINE!")
    app.run_polling()