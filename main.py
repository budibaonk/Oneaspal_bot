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
#                        BAGIAN 1: KONFIGURASI SISTEM
# ==============================================================================

# 1. Load Environment Variables
# Membaca file .env untuk mengambil token dan kunci rahasia
load_dotenv()

# 2. Konfigurasi Logging System
# Ini penting agar kita bisa melihat apa yang terjadi di terminal/log server
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# 3. Ambil Credential dari Environment
# Pastikan nama variabel di .env atau Railway SESUAI dengan ini
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
token: str = os.environ.get("TELEGRAM_TOKEN")

# 4. Variable Global & Konstanta
# Variable ini digunakan untuk menyimpan pesan sticky info dari Admin
GLOBAL_INFO = ""

# ID Group Log untuk notifikasi jika ada unit ditemukan (HIT)
# Pastikan bot sudah dimasukkan ke group ini dan dijadikan Admin
LOG_GROUP_ID = -1003627047676  

# 5. Setup Admin ID
# Mengambil ID Admin dari .env, jika tidak ada gunakan default (ID Bapak)
DEFAULT_ADMIN_ID = 7530512170
try:
    env_id = os.environ.get("ADMIN_ID")
    ADMIN_ID = int(env_id) if env_id else DEFAULT_ADMIN_ID
except ValueError:
    ADMIN_ID = DEFAULT_ADMIN_ID

print(f"✅ SYSTEM BOOT: ADMIN ID TERDETEKSI = {ADMIN_ID}")

# 6. Validasi Kelengkapan Credential
# Jika salah satu kunci kosong, bot akan membatalkan start agar tidak error di tengah jalan
if not url or not key or not token:
    print("❌ CRITICAL ERROR: Credential tidak lengkap!")
    print("👉 Pastikan file .env berisi: SUPABASE_URL, SUPABASE_KEY, TELEGRAM_TOKEN")
    exit()

# 7. Inisialisasi Koneksi Database Supabase
try:
    supabase: Client = create_client(url, key)
    print("✅ DATABASE: Koneksi ke Supabase Berhasil!")
except Exception as e:
    print(f"❌ DATABASE ERROR: Gagal koneksi ke Supabase. Pesan: {e}")
    exit()


# ==============================================================================
#                        BAGIAN 2: KAMUS DATA & STATE
# ==============================================================================

# --- KAMUS ALIAS KOLOM (NORMALISASI AGRESIF) ---
# Kamus ini berfungsi sebagai "Otak" bot untuk mengenali header Excel yang berantakan.
# Semua alias ditulis dalam HURUF KECIL TANPA SPASI/TITIK/SIMBOL.

COLUMN_ALIASES = {
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
        'platnomor'
    ],
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
        'namakendaraan'
    ],
    'tahun': [
        'tahun', 
        'year', 
        'thn', 
        'rakitan', 
        'th', 
        'yearofmanufacture', 
        'thnrakit', 
        'manufacturingyear'
    ],
    'warna': [
        'warna', 
        'color', 
        'colour', 
        'cat', 
        'kelir', 
        'warnakendaraan'
    ],
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
        'vinno'
    ],
    'nosin': [
        'nosin', 
        'nomesin', 
        'nomormesin', 
        'engine', 
        'mesin', 
        'engineno', 
        'nomesin1', 
        'engineno', 
        'noengine'
    ],
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
        'sumberdata'
    ],
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
        'kol'
    ],
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

# --- DEFINISI STATE CONVERSATION HANDLER ---
# Angka-angka ini adalah penanda "Posisi" user dalam percakapan.

# 1. Registrasi User
R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_CONFIRM = range(6)

# 2. Tambah Data Manual
A_NOPOL, A_TYPE, A_LEASING, A_NOKIR, A_CONFIRM = range(6, 11)

# 3. Lapor Hapus Data (User)
L_NOPOL, L_CONFIRM = range(11, 13) 

# 4. Hapus Data Manual (Admin)
D_NOPOL, D_CONFIRM = range(13, 15)

# 5. Smart Upload Excel/CSV
U_LEASING_USER, U_LEASING_ADMIN, U_CONFIRM_UPLOAD = range(15, 18)


# ==============================================================================
#                        BAGIAN 3: FUNGSI HELPER & DATABASE
# ==============================================================================

async def post_init(application: Application):
    """
    Fungsi ini dipanggil otomatis SATU KALI saat bot pertama kali menyala.
    Tugasnya: Memasang tombol menu di samping kolom chat Telegram user.
    """
    print("⏳ Sedang meng-set menu perintah Telegram...")
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
    Mengambil data user dari tabel 'users' di Supabase.
    Return: Dictionary data user ATAU None jika tidak ditemukan.
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
    Hanya dipanggil jika pencarian menghasilkan HIT.
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
    """
    Membersihkan teks dari spasi, titik, koma, underscore, dan simbol lain.
    Hanya menyisakan huruf dan angka (alfanumerik) lowercase.
    """
    if not isinstance(text, str): 
        return str(text).lower()
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()

def smart_rename_columns(df):
    """
    Fungsi Cerdas untuk menstandarkan nama kolom DataFrame.
    Mencocokkan header file user dengan KAMUS ALIAS.
    """
    new_cols = {}
    found_cols = []
    
    # Loop setiap kolom asli dari file Excel
    for original_col in df.columns:
        # Bersihkan nama kolom asli
        clean_col = normalize_text(original_col)
        renamed = False
        
        # Cek kecocokan di kamus alias
        for standard_name, aliases in COLUMN_ALIASES.items():
            if clean_col == standard_name or clean_col in aliases:
                new_cols[original_col] = standard_name
                found_cols.append(standard_name)
                renamed = True
                break
        
        # Jika tidak ada di kamus, biarkan nama aslinya
        if not renamed:
            new_cols[original_col] = original_col

    df.rename(columns=new_cols, inplace=True)
    return df, found_cols

def read_file_robust(file_content, file_name):
    """
    Fungsi 'Tank Baja' untuk membaca file Excel/CSV apapun kondisinya.
    Mencoba berbagai encoding (UTF-8, Latin1, CP1252) dan delimiter.
    """
    # Strategi 1: Jika file Excel (.xlsx / .xls)
    if file_name.lower().endswith(('.xlsx', '.xls')):
        try:
            return pd.read_excel(io.BytesIO(file_content), dtype=str)
        except Exception as e:
            raise ValueError(f"Gagal baca Excel: {e}")

    # Strategi 2: Jika CSV, coba kombinasi encoding & separator
    encodings_to_try = ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']
    separators_to_try = [';', ',', '\t', '|']
    
    for enc in encodings_to_try:
        for sep in separators_to_try:
            try:
                # Reset pointer file stream
                file_stream = io.BytesIO(file_content)
                df = pd.read_csv(file_stream, sep=sep, dtype=str, encoding=enc)
                
                if len(df.columns) > 1:
                    print(f"✅ DEBUG: File terbaca dengan encoding: {enc} dan separator: {sep}")
                    return df
            except:
                continue
    
    # Strategi 3: Last Resort (Python Engine Auto-detect)
    try:
        return pd.read_csv(io.BytesIO(file_content), sep=None, engine='python', dtype=str)
    except Exception as e:
        raise ValueError("File tidak terbaca dengan semua metode encoding yang tersedia.")


# ==============================================================================
#                        BAGIAN 4: HANDLER FITUR USER
# ==============================================================================

async def cek_kuota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler command /cekkuota.
    Menampilkan info user, agency, dan sisa kuota.
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
        f"💡 _Catatan: Kuota hanya berkurang jika data ditemukan (HIT)._"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def admin_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler command /topup (Khusus Admin).
    """
    if update.effective_user.id != ADMIN_ID: 
        return # Abaikan jika bukan admin
    
    try:
        args = context.args
        if len(args) < 2:
            return await update.message.reply_text(
                "⚠️ **Format Salah!**\nGunakan: `/topup [User_ID] [Jumlah]`", 
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
            # Notifikasi ke User
            try:
                await context.bot.send_message(
                    chat_id=target_id, 
                    text=f"🎉 **KUOTA BERTAMBAH!**\nAdmin menambah +{amount} kuota.\nTotal: {new_balance}"
                )
            except: 
                pass
        else:
            await update.message.reply_text("❌ Gagal. Pastikan ID User benar.")
            
    except ValueError:
        await update.message.reply_text("⚠️ Jumlah harus berupa angka.")


# ==============================================================================
#                 BAGIAN 5: SMART UPLOAD (STABLE MODE)
# ==============================================================================

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler pemicu saat user mengirim file dokumen.
    """
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    doc = update.message.document
    file_name = doc.file_name

    # Cek Validitas User
    if not user_data or user_data['status'] != 'active':
        if user_id != ADMIN_ID: 
            return await update.message.reply_text("⛔ **AKSES DITOLAK**\nAnda belum terdaftar aktif.")

    # Status Typing
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.UPLOAD_DOCUMENT)
    
    # Simpan info file
    context.user_data['upload_file_id'] = doc.file_id
    context.user_data['upload_file_name'] = file_name

    # ALUR 1: USER BIASA (Forward ke Admin)
    if user_id != ADMIN_ID:
        await update.message.reply_text(
            f"📄 File `{file_name}` diterima.\n\nSatu langkah lagi: **Ini data dari Leasing/Finance apa?**",
            parse_mode='Markdown', 
            reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)
        )
        return U_LEASING_USER

    # ALUR 2: ADMIN (SMART PROCESSING)
    else:
        msg = await update.message.reply_text("⏳ **Membaca file (Mode: Robust)...**")
        
        try:
            # Download file
            new_file = await doc.get_file()
            file_content = await new_file.download_as_bytearray()
            
            # Baca & Normalisasi
            df = read_file_robust(file_content, file_name)
            df, found_cols = smart_rename_columns(df)
            context.user_data['df_records'] = df.to_dict(orient='records')
            
            # Validasi Kolom Nopol
            if 'nopol' not in df.columns:
                det = ", ".join(df.columns[:5])
                
                # Hapus pesan loading
                await msg.delete()
                
                await update.message.reply_text(
                    f"❌ **GAGAL DETEKSI NOPOL**\nKolom terbaca: {det}\nPastikan ada kolom: 'No Polisi', 'Plat', atau 'TNKB'."
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
                f"👉 **MASUKKAN NAMA LEASING:**\n"
                f"_(Ketik 'SKIP' jika ingin menggunakan kolom dari file)_"
            )
            
            # Hapus pesan lama, kirim pesan baru (untuk menghindari error keyboard)
            await msg.delete()
            
            await update.message.reply_text(
                report, 
                parse_mode='Markdown', 
                reply_markup=ReplyKeyboardMarkup([["SKIP"], ["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
            )
            return U_LEASING_ADMIN

        except Exception as e:
            await msg.edit_text(f"❌ Gagal memproses file: {str(e)}")
            return ConversationHandler.END

async def upload_leasing_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler User: Input nama leasing -> Forward ke Admin.
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
        f"👉 _Silakan download dan upload ulang file ini._"
    )
    await context.bot.send_document(chat_id=ADMIN_ID, document=file_id, caption=caption_admin, parse_mode='Markdown')
    
    await update.message.reply_text("✅ **TERKIRIM!**\nFile Anda telah dikirim ke Admin.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def upload_leasing_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler Admin: Input nama leasing -> Preview Data.
    """
    leasing_input = update.message.text
    
    # Ambil dataframe dari memory
    df = pd.DataFrame(context.user_data['df_records'])
    
    # Tentukan nama leasing
    final_leasing_name = leasing_input.upper()
    
    if final_leasing_name != 'SKIP':
        df['finance'] = final_leasing_name
    elif 'finance' not in df.columns:
        final_leasing_name = "UNKNOWN (AUTO)"
        df['finance'] = 'UNKNOWN'
    else:
        final_leasing_name = "SESUAI FILE"

    # Bersihkan Data Nopol (Hapus spasi, titik, dll)
    df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
    
    # Hapus Duplikat Nopol (Prioritaskan data terbaru/paling bawah)
    df = df.drop_duplicates(subset=['nopol'], keep='last').replace({np.nan: None})
    
    # Filter Kolom yang akan masuk DB
    valid_cols_db = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch']
    for col in valid_cols_db:
        if col not in df.columns: 
            df[col] = None
    
    # Ambil sample untuk preview
    sample = df.iloc[0]
    
    # Simpan final data
    context.user_data['final_data_records'] = df[valid_cols_db].to_dict(orient='records')
    context.user_data['final_leasing_name'] = final_leasing_name
    
    # Tampilkan Preview
    preview_msg = (
        f"🔎 **PREVIEW DATA (SAFEGUARD)**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏦 **Leasing:** {final_leasing_name}\n"
        f"📊 **Total Data:** {len(df)} Unit\n\n"
        f"📝 **CONTOH DATA BARIS PERTAMA:**\n"
        f"🔹 Nopol: `{sample['nopol']}`\n"
        f"🔹 Unit: {sample['type']}\n"
        f"🔹 Noka: {sample['noka']}\n"
        f"🔹 OVD: {sample['ovd']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Klik **EKSEKUSI** untuk memulai upload.\n"
        f"⚠️ Klik **BATAL** jika ada yang salah."
    )
    
    await update.message.reply_text(
        preview_msg, 
        parse_mode='Markdown', 
        reply_markup=ReplyKeyboardMarkup([["🚀 EKSEKUSI", "❌ BATAL"]], one_time_keyboard=True)
    )
    return U_CONFIRM_UPLOAD

async def upload_confirm_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler Eksekusi Upload - STABLE MODE (Tanpa Update Live Bar).
    Ini untuk mencegah error 'Rate Limit' dari Telegram saat upload banyak data.
    """
    choice = update.message.text
    
    if choice != "🚀 EKSEKUSI":
        await update.message.reply_text("🚫 Proses upload dibatalkan.", reply_markup=ReplyKeyboardRemove())
        context.user_data.pop('final_data_records', None)
        return ConversationHandler.END
    
    # 1. Info Awal (Satu kali saja)
    status_msg = await update.message.reply_text(
        "⏳ **SEDANG MENGUPLOAD DATA...**\n"
        "--------------------------------\n"
        "⚠️ _Bot akan bekerja di latar belakang._\n"
        "⚠️ _Status tidak akan update per detik agar lebih cepat & stabil._\n\n"
        "☕ _Silakan tunggu, bot akan melapor jika sudah selesai._", 
        reply_markup=ReplyKeyboardRemove(), 
        parse_mode='Markdown'
    )
    
    final_data = context.user_data.get('final_data_records')
    
    success_count = 0
    fail_count = 0
    last_error_msg = "" 
    
    # Batasan Upload per Batch (Supabase limit)
    BATCH_SIZE = 1000 
    
    start_time = time.time()
    
    # 2. Proses Upload (Looping)
    for i in range(0, len(final_data), BATCH_SIZE):
        batch = final_data[i : i + BATCH_SIZE]
        try:
            # Upsert: Insert baru atau Update jika nopol sudah ada
            supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
            success_count += len(batch)
        except Exception as e:
            last_error_msg = str(e) # Tangkap error umum
            
            # Fallback: Jika batch gagal, coba satu per satu
            for item in batch:
                try:
                    supabase.table('kendaraan').upsert([item], on_conflict='nopol').execute()
                    success_count += 1
                except Exception as inner_e:
                    fail_count += 1
                    last_error_msg = str(inner_e) # Tangkap error spesifik

    duration = round(time.time() - start_time, 2)

    # 3. Laporan Akhir (Satu kali di akhir)
    if fail > 0:
        report = (
            f"❌ **SELESAI DENGAN ERROR**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✅ Berhasil: {success_count}\n"
            f"❌ Gagal: {fail_count}\n"
            f"⏱ Waktu: {duration} detik\n\n"
            f"🔍 **LOG ERROR:**\n"
            f"`{last_error_msg[:300]}...`\n\n"
            f"💡 _Saran: Cek apakah format data di Excel sudah benar._"
        )
    else:
        report = (
            f"✅ **UPLOAD SUKSES 100%!**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 **Total Data:** {success_count}\n"
            f"❌ **Gagal:** 0\n"
            f"⏱ **Waktu:** {duration} detik\n"
            f"🚀 **Status:** Database Updated Successfully!"
        )
        
    await status_msg.edit_text(report, parse_mode='Markdown')
    
    # Bersihkan Memori Server
    context.user_data.pop('final_data_records', None)
    return ConversationHandler.END


# ==============================================================================
#                 BAGIAN 6: FITUR ADMIN (STATS, USER, BROADCAST)
# ==============================================================================

async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Menampilkan statistik total data, user, dan JUMLAH LEASING UNIK.
    """
    if update.effective_user.id != ADMIN_ID: return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
    msg_wait = await update.message.reply_text("⏳ *Sedang menghitung seluruh data... (Mohon tunggu)*", parse_mode='Markdown')

    try:
        # 1. Hitung Total Unit (Cepat)
        res_total = supabase.table('kendaraan').select("*", count="exact", head=True).execute()
        total_unit = res_total.count if res_total.count else 0

        # 2. Hitung Total User (Cepat)
        res_users = supabase.table('users').select("*", count="exact", head=True).execute()
        total_user = res_users.count if res_users.count else 0

        # 3. Hitung Jumlah Leasing Unik (Pagination Loop)
        # Mengambil seluruh data finance secara bertahap untuk dihitung uniknya
        raw_set = set()
        offset = 0
        batch_size = 1000
        
        while True:
            # Ambil data kolom 'finance' saja
            res_batch = supabase.table('kendaraan').select("finance").range(offset, offset + batch_size - 1).execute()
            data = res_batch.data
            
            if not data: 
                break
            
            for d in data:
                f = d.get('finance')
                if f:
                    # Bersihkan nama leasing (uppercase & trim)
                    clean_f = str(f).strip().upper()
                    # Filter data sampah
                    if len(clean_f) > 1 and clean_f not in ["-", "NAN", "NONE", "NULL", "UNKNOWN"]:
                        raw_set.add(clean_f)
            
            if len(data) < batch_size: 
                break
            
            offset += batch_size

        total_leasing = len(raw_set)

        msg = (
            f"📊 **STATISTIK ONEASPAL**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📂 **Total Data Kendaraan:** `{total_unit:,}` Unit\n"
            f"👥 **Total Mitra Terdaftar:** `{total_user:,}` User\n"
            f"🏦 **Jumlah Leasing:** `{total_leasing}` Perusahaan\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        await msg_wait.edit_text(msg, parse_mode='Markdown')

    except Exception as e:
        logging.error(f"Stats Error: {e}")
        await msg_wait.edit_text(f"❌ Error mengambil statistik: {e}")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Menampilkan 20 user terbaru.
    """
    if update.effective_user.id != ADMIN_ID: return
    try:
        res = supabase.table('users').select("*").order('created_at', desc=True).limit(20).execute()
        
        msg = "📋 **DAFTAR 20 USER TERBARU**\n\n"
        for u in res.data:
            icon = "✅" if u['status'] == 'active' else "⏳"
            if u['status'] == 'rejected': icon = "⛔"
            
            msg += f"{icon} `{u['user_id']}` | {u.get('nama_lengkap','-')}\n"
            
        await update.message.reply_text(msg, parse_mode='Markdown')
    except: await update.message.reply_text("Gagal mengambil data user.")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Blokir user akses.
    """
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        update_user_status(uid, 'rejected')
        await update.message.reply_text(f"⛔ User `{uid}` BERHASIL DI-BAN.")
    except: await update.message.reply_text("⚠️ Format: `/ban ID`")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Buka blokir user.
    """
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        update_user_status(uid, 'active')
        await update.message.reply_text(f"✅ User `{uid}` BERHASIL DI-UNBAN.")
    except: await update.message.reply_text("⚠️ Format: `/unban ID`")

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Hapus user permanen.
    """
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        supabase.table('users').delete().eq('user_id', uid).execute()
        await update.message.reply_text(f"🗑️ User `{uid}` DIHAPUS PERMANEN.")
    except: await update.message.reply_text("⚠️ Format: `/delete ID`")

async def set_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Set pesan info sticky.
    """
    global GLOBAL_INFO
    if update.effective_user.id != ADMIN_ID: return
    
    msg = " ".join(context.args)
    GLOBAL_INFO = msg
    await update.message.reply_text(f"✅ **Info Terpasang!**\n{GLOBAL_INFO}", parse_mode='Markdown')

async def del_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Hapus pesan info.
    """
    global GLOBAL_INFO
    if update.effective_user.id != ADMIN_ID: return
    
    GLOBAL_INFO = ""
    await update.message.reply_text("🗑️ Info dihapus.")

async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User kirim pesan ke admin.
    """
    u = get_user(update.effective_user.id)
    if not u: return
    
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
    """
    Kirim notifikasi ke Group Log jika data ditemukan.
    """
    hp_raw = user_data.get('no_hp', '-')
    hp_wa = '62' + hp_raw[1:] if hp_raw.startswith('0') else hp_raw
    
    report_text = (
        f"🚨 **UNIT DITEMUKAN! (HIT)**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Penemu:** {user_data.get('nama_lengkap')} ({user_data.get('agency')})\n"
        f"📍 **Kota:** {user_data.get('kota', '-')}\n\n"
        f"🚙 **Unit:** {vehicle_data.get('type')}\n"
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
    """
    Menampilkan panduan penggunaan.
    """
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

async def test_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Test kirim pesan ke group log.
    """
    if update.effective_user.id != ADMIN_ID: return
    try:
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text="🔔 **TES NOTIFIKASI GROUP OK!**")
        await update.message.reply_text("✅ Notifikasi terkirim ke Group Log.")
    except: await update.message.reply_text("❌ Gagal kirim ke Group Log.")


# ==============================================================================
#                 BAGIAN 8: HANDLER CONVERSATION (INTERAKSI USER)
# ==============================================================================

# --- LAPOR HAPUS ---
async def lapor_delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return await update.message.reply_text("⛔ Akses ditolak.")
    
    await update.message.reply_text(
        "🗑️ **LAPOR UNIT SELESAI**\nMasukkan Nopol:",
        reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)
    )
    return L_NOPOL

async def lapor_delete_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nopol_input = update.message.text.upper().replace(" ", "")
    try:
        res = supabase.table('kendaraan').select("*").eq('nopol', nopol_input).execute()
        if not res.data: 
            await update.message.reply_text("❌ Data tidak ditemukan.")
            return ConversationHandler.END
        
        context.user_data['ln'] = nopol_input
        await update.message.reply_text(f"⚠️ Lapor Hapus `{nopol_input}`?", reply_markup=ReplyKeyboardMarkup([["✅ YA", "❌ BATAL"]], one_time_keyboard=True), parse_mode='Markdown')
        return L_CONFIRM
    except: return ConversationHandler.END

async def lapor_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "✅ YA":
        n = context.user_data['ln']
        user = get_user(update.effective_user.id)
        
        await update.message.reply_text("✅ Laporan terkirim ke Admin.", reply_markup=ReplyKeyboardRemove())
        
        kb = [[InlineKeyboardButton("✅ Setujui", callback_data=f"del_acc_{n}_{update.effective_user.id}"), InlineKeyboardButton("❌ Tolak", callback_data=f"del_rej_{update.effective_user.id}")]]
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🗑️ **REQ HAPUS:** `{n}`\n👤 {user['nama_lengkap']}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    
    return ConversationHandler.END

# --- HAPUS MANUAL (ADMIN) ---
async def delete_unit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🗑️ **HAPUS MANUAL**\nMasukkan Nopol:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return D_NOPOL

async def delete_unit_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['dn'] = update.message.text.upper().replace(" ", "")
    await update.message.reply_text(f"⚠️ Hapus Permanen `{context.user_data['dn']}`?", reply_markup=ReplyKeyboardMarkup([["✅ YA", "❌ BATAL"]], one_time_keyboard=True), parse_mode='Markdown')
    return D_CONFIRM

async def delete_unit_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "✅ YA":
        supabase.table('kendaraan').delete().eq('nopol', context.user_data['dn']).execute()
        await update.message.reply_text("✅ Data Dihapus.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- REGISTRASI ---
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_user(update.effective_user.id): return await update.message.reply_text("✅ Sudah terdaftar.")
    await update.message.reply_text("📝 **NAMA LENGKAP:**", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return R_NAMA

async def register_nama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['r_nama'] = update.message.text
    await update.message.reply_text("📱 **NO HP:**")
    return R_HP

async def register_hp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['r_hp'] = update.message.text
    await update.message.reply_text("📧 **EMAIL:**")
    return R_EMAIL

async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['r_email'] = update.message.text
    await update.message.reply_text("📍 **KOTA DOMISILI:**")
    return R_KOTA

async def register_kota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['r_kota'] = update.message.text
    await update.message.reply_text("🏢 **AGENCY:**")
    return R_AGENCY

async def register_agency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['r_agency'] = update.message.text
    await update.message.reply_text("✅ **KIRIM DATA?**", reply_markup=ReplyKeyboardMarkup([["✅ YA", "❌ BATAL"]], one_time_keyboard=True))
    return R_CONFIRM

async def register_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "✅ YA":
        d = {"user_id": update.effective_user.id, "nama_lengkap": context.user_data['r_nama'], "no_hp": context.user_data['r_hp'], "email": context.user_data['r_email'], "alamat": context.user_data['r_kota'], "agency": context.user_data['r_agency'], "quota": 1000, "status": "pending"}
        try:
            supabase.table('users').insert(d).execute()
            await update.message.reply_text("✅ Pendaftaran Terkirim. Tunggu verifikasi Admin.", reply_markup=ReplyKeyboardRemove())
            
            kb = [[InlineKeyboardButton("✅ Acc", callback_data=f"appu_{d['user_id']}"), InlineKeyboardButton("❌ Rej", callback_data=f"reju_{d['user_id']}")]]
            await context.bot.send_message(ADMIN_ID, f"🔔 **NEW USER**\n👤 {d['nama_lengkap']}", reply_markup=InlineKeyboardMarkup(kb))
        except: await update.message.reply_text("❌ Gagal/Sudah Terdaftar.")
    return ConversationHandler.END

# --- TAMBAH MANUAL ---
async def add_data_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not get_user(update.effective_user.id): return
    await update.message.reply_text("➕ **NOPOL:**", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
    return A_NOPOL

async def add_nopol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['a_nopol'] = update.message.text.upper()
    await update.message.reply_text("🚙 **UNIT:**")
    return A_TYPE

async def add_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['a_type'] = update.message.text
    await update.message.reply_text("🏦 **LEASING:**")
    return A_LEASING

async def add_leasing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['a_leasing'] = update.message.text
    await update.message.reply_text("📝 **KETERANGAN:**")
    return A_NOKIR

async def add_nokir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['a_nokir'] = update.message.text
    await update.message.reply_text("✅ Kirim ke Admin?", reply_markup=ReplyKeyboardMarkup([["✅ YA", "❌ BATAL"]], one_time_keyboard=True))
    return A_CONFIRM

async def add_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "✅ YA":
        n = context.user_data['a_nopol']
        context.bot_data[f"prop_{n}"] = {"nopol": n, "type": context.user_data['a_type'], "finance": context.user_data['a_leasing'], "ovd": context.user_data['a_nokir']}
        await update.message.reply_text("✅ Terkirim.", reply_markup=ReplyKeyboardRemove())
        
        kb = [[InlineKeyboardButton("✅ Acc", callback_data=f"v_acc_{n}_{update.effective_user.id}")]]
        await context.bot.send_message(ADMIN_ID, f"📥 **DATA BARU**\n🔢 {n}", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END


# ==============================================================================
#                 BAGIAN 9: HANDLER UTAMA (START, MESSAGE, CALLBACK)
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info_text = f"\n📢 **INFO:** {GLOBAL_INFO}\n━━━━━━━━━━━━━━━━━━\n" if GLOBAL_INFO else ""
    text = (
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
    await update.message.reply_text(text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return
    
    if u.get('quota', 0) <= 0:
        return await update.message.reply_text("⛔ **KUOTA HABIS!**\nSilakan hubungi Admin.")

    kw = re.sub(r'[^a-zA-Z0-9]', '', update.message.text.upper())
    if len(kw) < 3: return await update.message.reply_text("⚠️ Masukkan minimal 3 karakter.")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
    await asyncio.sleep(0.5) 
    
    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.ilike.%{kw}%,noka.eq.{kw},nosin.eq.{kw}").execute()
        
        if res.data:
            d = res.data[0]
            update_quota_usage(u['user_id'], u['quota'])
            
            txt = (
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
                f"Ini bukan alat yang SAH untuk penarikan."
            )
            await update.message.reply_text(txt, parse_mode='Markdown')
            await notify_hit_to_group(context, u, d)
        else:
            await update.message.reply_text(f"❌ **DATA TIDAK DITEMUKAN**\n`{kw}`", parse_mode='Markdown')
            
    except Exception as e:
        await update.message.reply_text("❌ Terjadi kesalahan database.")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    
    if data.startswith("appu_"):
        uid = data.split("_")[1]
        update_user_status(uid, 'active')
        await q.edit_message_text(f"✅ User {uid} DISETUJUI.")
        await context.bot.send_message(uid, "🎉 **AKUN ANDA TELAH AKTIF!**")
        
    elif data.startswith("reju_"):
        uid = data.split("_")[1]
        update_user_status(uid, 'rejected')
        await q.edit_message_text(f"⛔ User {uid} DITOLAK.")
        
    elif data.startswith("v_acc_"):
        n = data.split("_")[2]
        item = context.bot_data.get(f"prop_{n}")
        if item: supabase.table('kendaraan').upsert(item).execute()
        await q.edit_message_text(f"✅ Data {n} Masuk Database.")
        
    elif data.startswith("del_acc_"):
        n = data.split("_")[2]
        supabase.table('kendaraan').delete().eq('nopol', n).execute()
        await q.edit_message_text(f"✅ `{n}` DIHAPUS.", parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Dibatalkan.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ==============================================================================
#                        BAGIAN 10: MAIN PROGRAM
# ==============================================================================

if __name__ == '__main__':
    # Build Application
    app = ApplicationBuilder().token(token).post_init(post_init).build()
    
    # --- REGISTRASI HANDLERS ---
    
    # 1. Registrasi
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

    # 2. Tambah Data
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

    # 4. Hapus Manual
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('hapus', delete_unit_start)],
        states={
            D_NOPOL:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), delete_unit_check)],
            D_CONFIRM:[MessageHandler(filters.TEXT, delete_unit_confirm)]
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)],
        conversation_timeout=60
    ))

    # 5. Smart Upload (STABLE MODE)
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

    # --- COMMAND HANDLERS ---
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

    # --- GENERIC HANDLERS ---
    app.add_handler(CallbackQueryHandler(callback_handler))
    # Handle message text harus paling bawah agar tidak memakan command lain
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ ONEASPAL BOT ONLINE - V2.9 (TITAN EDITION - FULL STATS & STABLE UPLOAD)")
    app.run_polling()