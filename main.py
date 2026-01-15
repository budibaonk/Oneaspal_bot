import os
import logging
import pandas as pd
import io
import numpy as np
import time
import re
import asyncio 
import csv 
import zipfile # <--- SENJATA BARU: LIBRARY ZIP
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
# Membaca file .env untuk mengambil token dan kunci rahasia.
# Pastikan file .env ada di root folder proyek dan terisi dengan benar.
load_dotenv()

# ------------------------------------------------------------------------------
# 2. Konfigurasi Logging System
# ------------------------------------------------------------------------------
# Ini penting agar kita bisa melihat apa yang terjadi di terminal/log server.
# Level INFO akan menampilkan pesan status standar.
# Format waktu disertakan agar kita tahu kapan error terjadi.
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# ------------------------------------------------------------------------------
# 3. Ambil Credential dari Environment
# ------------------------------------------------------------------------------
# Pastikan nama variabel di .env atau Railway SESUAI dengan ini.
# Jika salah satu tidak ada, bot tidak akan bisa jalan.

# URL Database Supabase Project
url: str = os.environ.get("SUPABASE_URL")

# Service Role Key (Kunci Sakti untuk Admin Database)
key: str = os.environ.get("SUPABASE_KEY")

# Token Bot Telegram dari BotFather
token: str = os.environ.get("TELEGRAM_TOKEN")

# ------------------------------------------------------------------------------
# 4. Variable Global & Konstanta
# ------------------------------------------------------------------------------
# Variable ini digunakan untuk menyimpan pesan sticky info dari Admin.
# Default kosong, diisi lewat command /setinfo.
GLOBAL_INFO = ""

# ID Group Log untuk notifikasi jika ada unit ditemukan (HIT).
# Bot akan mengirim pesan ke sini jika ada user yang mencari Nopol dan hasilnya ADA.
# Pastikan bot sudah dimasukkan ke group ini dan dijadikan Admin.
LOG_GROUP_ID = -1003627047676  

# ------------------------------------------------------------------------------
# 5. Setup Admin ID
# ------------------------------------------------------------------------------
# Mengambil ID Admin dari .env, jika tidak ada gunakan default (ID Bapak).
# ID ini memiliki hak akses penuh (Superuser) untuk ACC user, Upload, dan Delete.
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
# Jika salah satu kunci kosong, matikan bot untuk mencegah error fatal.
if not url or not key or not token:
    print("❌ CRITICAL ERROR: Credential tidak lengkap!")
    print("👉 Pastikan file .env berisi: SUPABASE_URL, SUPABASE_KEY, TELEGRAM_TOKEN")
    exit()

# ------------------------------------------------------------------------------
# 7. Inisialisasi Koneksi Database Supabase
# ------------------------------------------------------------------------------
# Mencoba terhubung ke cloud database.
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
# Kamus ini berfungsi sebagai "Otak" bot untuk mengenali header Excel/CSV yang berantakan.
# Semua alias ditulis dalam HURUF KECIL TANPA SPASI/TITIK/SIMBOL.
# Ditulis memanjang ke bawah (Vertical) agar mudah dibaca dan diedit satu per satu.

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
        'platkendaraan',  # Support file data_base_dki_oto
        'nomerpolisi',
        'no.polisi',      # Support file dengan titik
        'nopol.'          # Support file dengan titik akhir
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
        'merktype',       # Support file gabungan merk+type
        'objek',
        'jenisobjek'
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
        'manufacturingyear'
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
        'vinno'
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
        'noengine'
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
        'financetype'
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
# Angka-angka ini adalah penanda "Posisi" user dalam percakapan.
# Jangan diubah urutannya kecuali Anda paham alurnya.

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
        ("admin", "📩 Hubungi Admin"),
        ("panduan", "📖 Petunjuk Penggunaan"),
    ])
    
    print("✅ System: Menu Perintah Berhasil Di-set!")

def get_user(user_id):
    """
    Mengambil data user dari tabel 'users' di Supabase.
    
    Parameter: 
        user_id (int): ID Telegram User
        
    Returns: 
        Dictionary data user ATAU None jika tidak ditemukan.
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
    Digunakan saat Admin menekan tombol Approve/Reject.
    """
    try:
        supabase.table('users').update({'status': status}).eq('user_id', user_id).execute()
        print(f"✅ User {user_id} status updated to {status}")
    except Exception as e: 
        logging.error(f"❌ Error update status: {e}")

def update_quota_usage(user_id, current_quota):
    """
    Mengurangi kuota user sebanyak 1 poin.
    Hanya dipanggil jika pencarian menghasilkan DATA DITEMUKAN (HIT).
    Jika hasil pencarian nihil (ZONK), kuota tidak berkurang.
    """
    try:
        new_quota = current_quota - 1
        supabase.table('users').update({'quota': new_quota}).eq('user_id', user_id).execute()
    except Exception as e:
        logging.error(f"❌ Error update quota: {e}")

def topup_quota(user_id, amount):
    """
    Fungsi khusus Admin untuk menambah kuota user secara manual.
    
    Parameter:
        user_id (int): ID Telegram User
        amount (int): Jumlah kuota yang ditambahkan
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
    Fungsi krusial untuk membersihkan nama kolom Excel.
    Menghapus spasi, titik, koma, underscore, dan karakter aneh.
    Hanya menyisakan huruf dan angka lowercase.
    
    Contoh: 'No. Polisi ' -> 'nopolisi'
    Contoh: 'Type_Kendaraan' -> 'typekendaraan'
    """
    if not isinstance(text, str): 
        return str(text).lower()
    # Regex: Ganti semua karakter NON-ALFANUMERIK dengan string kosong
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()

def fix_header_position(df):
    """
    FITUR SMART HEADER DETECTOR (v3.7)
    Fungsi ini akan mencari di mana sebenarnya baris header berada.
    Berguna untuk file Excel yang 3-5 baris pertamanya berisi "Judul Laporan".
    
    Cara kerja:
    1. Scan 20 baris pertama.
    2. Jika menemukan baris yang mengandung kata kunci NOPOL (misal: 'no polisi', 'plat'),
       maka baris itu dianggap sebagai HEADER.
    3. Hapus baris-baris di atasnya (Judul Laporan).
    """
    target_aliases = COLUMN_ALIASES['nopol']
    
    # Loop scanning 20 baris pertama
    for i in range(min(20, len(df))):
        # Ambil baris ke-i, konversi ke string, dan bersihkan teksnya
        row_values = [normalize_text(str(x)) for x in df.iloc[i].values]
        
        # Cek apakah ada satu pun kata kunci 'nopol' di baris ini
        if any(alias in row_values for alias in target_aliases):
            print(f"✅ SMART HEADER: Ditemukan di baris ke-{i}")
            
            # Jadikan baris ini sebagai nama kolom (Header)
            df.columns = df.iloc[i] 
            
            # Ambil data mulai dari baris setelahnya (i+1) sampai habis
            df = df.iloc[i+1:].reset_index(drop=True) 
            return df
            
    # Jika tidak ketemu apa-apa dalam 20 baris, kembalikan apa adanya (mungkin formatnya standar)
    return df

def smart_rename_columns(df):
    """
    Fungsi Cerdas untuk menstandarkan nama kolom DataFrame.
    Mencocokkan header file user yang aneh-aneh dengan KAMUS ALIAS internal bot.
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

    # Terapkan rename ke DataFrame
    df.rename(columns=new_cols, inplace=True)
    return df, found_cols

def read_file_robust(file_content, file_name):
    """
    Fungsi 'ZIP MASTER & OMNIVORA' (v3.9).
    Fungsi ini adalah inti dari kemampuan upload bot.
    
    KEMAMPUAN:
    1. ZIP EXTRACT: Membuka file .zip di memori server dan mengambil file data pertamanya.
    2. EXCEL READER: Membaca .xlsx / .xls menggunakan engine yang tersedia.
    3. TEXT READER: Membaca .csv / .txt dengan berbagai encoding (UTF-16, Latin1, CP1252)
       dan berbagai separator (Koma, Titik Koma, TAB).
    """
    
    # --------------------------------------------------------------------------
    # STEP 0: DETEKSI & EKSTRAK ZIP (New Feature v3.9)
    # --------------------------------------------------------------------------
    if file_name.lower().endswith('.zip'):
        try:
            print("📦 ZIP FILE DETECTED: Mencoba ekstrak...")
            with zipfile.ZipFile(io.BytesIO(file_content)) as z:
                # Cari file yang valid di dalam zip (Excel/CSV/TXT)
                # Filter file sistem MacOS (__MACOSX)
                valid_files = [
                    f for f in z.namelist() 
                    if not f.startswith('__MACOSX') and f.lower().endswith(('.csv', '.xlsx', '.xls', '.txt'))
                ]
                
                if not valid_files:
                    raise ValueError("ZIP Kosong atau tidak ada file data (CSV/Excel/TXT) di dalamnya.")
                
                target_file = valid_files[0] # Ambil file valid pertama
                print(f"📦 EXTRACTED: {target_file}")
                
                # Baca isi file tersebut menjadi bytes untuk diproses di langkah selanjutnya
                with z.open(target_file) as f:
                    file_content = f.read()
                    file_name = target_file # Ubah nama file agar sesuai dengan logic pembacaan di bawah
        except Exception as e:
            raise ValueError(f"Gagal membaca file ZIP: {str(e)}")

    # --------------------------------------------------------------------------
    # STEP 1: JIKA FORMAT EXCEL (.XLSX / .XLS)
    # --------------------------------------------------------------------------
    if file_name.lower().endswith(('.xlsx', '.xls')):
        try:
            return pd.read_excel(io.BytesIO(file_content), dtype=str)
        except Exception as e:
            # Fallback: Coba panggil engine openpyxl secara eksplisit
            try:
                return pd.read_excel(io.BytesIO(file_content), dtype=str, engine='openpyxl')
            except:
                raise ValueError(f"Gagal baca Excel: {e}")

    # --------------------------------------------------------------------------
    # STEP 2: JIKA FORMAT CSV ATAU TXT (Omnivora Logic)
    # --------------------------------------------------------------------------
    # Kita harus mencoba berbagai kombinasi Encoding dan Separator (Pemisah)
    
    # Daftar encoding yang sering dipakai di Indonesia/Corporate
    encodings_to_try = [
        'utf-8-sig',  # Modern CSV dengan BOM
        'utf-8',      # Standar Web
        'cp1252',     # Windows Default (Excel CSV)
        'latin1',     # Western Europe
        'utf-16',     # PENTING: Sering dipakai di file BAF / System Dump lama
        'utf-16le',   # UTF-16 Little Endian
        'utf-16be'    # UTF-16 Big Endian
    ]
    
    # Daftar pemisah (Separator)
    separators_to_try = [
        None, # Biarkan Python Auto-Detect (Sniffer)
        ';',  # Titik koma (Standard Excel Indonesia)
        ',',  # Koma (Standard International)
        '\t', # TAB (PENTING: File BAF menggunakan ini)
        '|'   # Pipa (Jarang tapi ada)
    ]
    
    # Loop percobaan membaca file
    for enc in encodings_to_try:
        for sep in separators_to_try:
            try:
                # Reset pointer file stream agar dibaca dari awal setiap loop
                file_stream = io.BytesIO(file_content)
                
                # Gunakan engine python agar lebih flexible
                df = pd.read_csv(
                    file_stream, 
                    sep=sep, 
                    dtype=str, 
                    encoding=enc, 
                    engine='python',
                    on_bad_lines='skip' # Lewati baris yang rusak/error
                )
                
                # Validasi Keberhasilan:
                # File dianggap terbaca jika memiliki lebih dari 1 kolom
                # Atau 1 kolom tapi namanya valid (kasus jarang)
                if len(df.columns) > 1:
                    print(f"✅ READ SUCCESS: Encoding={enc}, Separator={sep}")
                    return df
            except:
                continue
    
    # --------------------------------------------------------------------------
    # STEP 3: LAST RESORT (BACA APA ADANYA)
    # --------------------------------------------------------------------------
    try:
        return pd.read_csv(io.BytesIO(file_content), sep=None, engine='python', dtype=str)
    except Exception as e:
        raise ValueError("File tidak terbaca dengan semua metode encoding. Pastikan file tidak rusak atau terenkripsi.")


# ##############################################################################
# ##############################################################################
#
#                        BAGIAN 4: HANDLER FITUR USER
#
# ##############################################################################
# ##############################################################################

async def cek_kuota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler command /cekkuota.
    Menampilkan info user, agency, dan sisa kuota.
    """
    user_id = update.effective_user.id
    u = get_user(user_id)
    
    # Cek apakah user sudah terdaftar aktif
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
    Format: /topup [User_ID] [Jumlah]
    """
    if update.effective_user.id != ADMIN_ID: 
        return # Abaikan jika bukan admin
    
    try:
        # Cek argumen perintah
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
            await update.message.reply_text("❌ Gagal Topup. Pastikan ID User benar dan sudah terdaftar.")
            
    except ValueError:
        await update.message.reply_text("⚠️ Jumlah harus berupa angka.")


# ##############################################################################
# ##############################################################################
#
#                 BAGIAN 5: SMART UPLOAD (ZIP SUPPORT v3.9)
#
# ##############################################################################
# ##############################################################################

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler pemicu saat user mengirim file dokumen.
    Fitur Penting: Memberikan respon instan "File diterima" agar user tahu bot tidak mati.
    """
    user_id = update.effective_user.id
    
    # 1. RESPON INSTAN (Agar user tahu bot hidup & merespon)
    processing_msg = await update.message.reply_text(
        "⏳ **File diterima, sedang menganalisa format...**", 
        parse_mode='Markdown'
    )

    user_data = get_user(user_id)
    doc = update.message.document
    file_name = doc.file_name

    # 2. Cek Validitas User
    if not user_data or user_data['status'] != 'active':
        if user_id != ADMIN_ID: 
            await processing_msg.edit_text("⛔ **AKSES DITOLAK**\nAnda belum terdaftar aktif.")
            return ConversationHandler.END

    # Status Typing
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.UPLOAD_DOCUMENT)
    
    # Simpan info file sementara
    context.user_data['upload_file_id'] = doc.file_id
    context.user_data['upload_file_name'] = file_name

    # --- ALUR 1: USER BIASA (Forward ke Admin) ---
    if user_id != ADMIN_ID:
        # Hapus pesan processing, ganti dengan menu
        await processing_msg.delete()
        
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
        try:
            # Download file
            new_file = await doc.get_file()
            file_content = await new_file.download_as_bytearray()
            
            # 1. BACA FILE (ZIP/ROBUST MODE v3.9)
            # Menggunakan logika Zip Master + Omnivora
            df = read_file_robust(file_content, file_name)
            
            # 2. DETEKSI POSISI HEADER (Smart Detective v3.7)
            # Mencari baris header jika file memiliki judul laporan di baris atas
            df = fix_header_position(df)
            
            # 3. Normalisasi Nama Kolom
            df, found_cols = smart_rename_columns(df)
            
            # Simpan dataframe ke context
            context.user_data['df_records'] = df.to_dict(orient='records')
            
            # 4. Validasi Kolom Nopol (Wajib Ada)
            if 'nopol' not in df.columns:
                det = ", ".join(df.columns[:5])
                await processing_msg.edit_text(
                    f"❌ **GAGAL DETEKSI NOPOL**\n\n"
                    f"Kolom terbaca: {det}\n"
                    "👉 Pastikan ada kolom: 'No Polisi', 'Plat', atau 'TNKB'."
                )
                return ConversationHandler.END

            # Cek kolom finance
            has_finance = 'finance' in df.columns
            
            report = (
                f"✅ **SCAN SUKSES (v3.9 ZIP)**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Kolom Dikenali:** {', '.join(found_cols)}\n"
                f"📁 **Total Baris:** {len(df)}\n"
                f"🏦 **Kolom Leasing:** {'✅ ADA' if has_finance else '⚠️ TIDAK ADA'}\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"👉 **MASUKKAN NAMA LEASING UNTUK DATA INI:**\n"
                f"_(Ketik 'SKIP' jika ingin menggunakan kolom leasing dari file)_"
            )
            
            # Hapus pesan lama, kirim pesan baru (untuk menghindari error keyboard)
            await processing_msg.delete()
            
            await update.message.reply_text(
                report, 
                parse_mode='Markdown', 
                reply_markup=ReplyKeyboardMarkup([["SKIP"], ["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
            )
            return U_LEASING_ADMIN

        except Exception as e:
            # Handle Error "File too big"
            err_msg = str(e)
            if "File is too big" in err_msg:
                await processing_msg.edit_text(
                    "❌ **FILE TERLALU BESAR (>20MB)**\n\n"
                    "💡 **SOLUSI:**\n"
                    "Silakan **COMPRESS / ZIP** file tersebut di komputer/HP Anda, lalu upload file `.zip`-nya ke sini.\n"
                    "Bot v3.9 sudah bisa membaca ZIP otomatis! 🚀",
                    parse_mode='Markdown'
                )
            else:
                await processing_msg.edit_text(f"❌ **ERROR PEMBACAAN:**\n`{err_msg}`", parse_mode='Markdown')
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

    # Kirim Dokumen ke Admin
    caption_admin = (
        f"📥 **UPLOAD FILE DARI MITRA**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Pengirim:** {user.get('nama_lengkap')}\n"
        f"🏦 **Leasing:** {leasing_name.upper()}\n"
        f"📄 **File:** `{file_name}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👉 _Silakan download dan upload ulang file ini ke bot untuk memproses._"
    )
    await context.bot.send_document(chat_id=ADMIN_ID, document=file_id, caption=caption_admin, parse_mode='Markdown')
    
    await update.message.reply_text("✅ **TERKIRIM!**\nFile Anda telah dikirim ke Admin untuk diproses.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def upload_leasing_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler untuk Admin: Inject Nama Leasing & Preview Data.
    """
    leasing_input = update.message.text
    
    # Restore dataframe dari memory
    df = pd.DataFrame(context.user_data['df_records'])
    
    # Logic Penamaan Leasing
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
    
    # Hapus Duplikat Nopol (Ambil data paling bawah/terbaru)
    df = df.drop_duplicates(subset=['nopol'], keep='last').replace({np.nan: None})
    
    # Filter hanya kolom yang sesuai database Supabase
    valid_cols_db = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch']
    for col in valid_cols_db:
        if col not in df.columns: 
            df[col] = None
    
    # Ambil sampel baris pertama untuk preview
    sample = df.iloc[0]
    
    # Simpan data final yang siap upload
    context.user_data['final_data_records'] = df[valid_cols_db].to_dict(orient='records')
    context.user_data['final_leasing_name'] = final_leasing_name
    
    # Tampilkan Preview
    preview_msg = (
        f"🔎 **PREVIEW DATA (v3.9)**\n"
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
    Handler Admin: Eksekusi Upload ke Database.
    REVISI v3.6: Menambahkan update status per batch (Heartbeat) agar bot tidak dianggap mati oleh Telegram
    saat mengupload ribuan data, serta memastikan laporan akhir terkirim.
    """
    choice = update.message.text
    
    if choice != "🚀 EKSEKUSI":
        await update.message.reply_text("🚫 Proses upload dibatalkan.", reply_markup=ReplyKeyboardRemove())
        context.user_data.pop('final_data_records', None)
        return ConversationHandler.END
    
    # Kirim pesan awal progress
    status_msg = await update.message.reply_text(
        "⏳ **MEMULAI UPLOAD...**\n"
        "--------------------------------\n"
        "🚀 _Engine menyala..._\n"
        "☕ _Mohon tunggu, jangan kirim pesan lain dulu..._", 
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
    total_records = len(final_data)
    
    # Mulai Loop Batch Upload
    for i in range(0, total_records, BATCH_SIZE):
        batch = final_data[i : i + BATCH_SIZE]
        try:
            # Upsert: Insert baru atau Update jika nopol sudah ada
            supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
            success_count += len(batch)
        except Exception as e:
            last_error_msg = str(e) # Tangkap error level batch
            
            # Fallback: Jika batch gagal, coba satu per satu
            for item in batch:
                try:
                    supabase.table('kendaraan').upsert([item], on_conflict='nopol').execute()
                    success_count += 1
                except Exception as inner_e:
                    fail_count += 1
                    last_error_msg = str(inner_e) # Tangkap error spesifik per baris
        
        # --- FITUR BARU v3.6: HEARTBEAT UPDATE ---
        # Update status setiap 2000 data agar user tahu bot masih hidup
        # dan mencegah Telegram menutup koneksi (timeout)
        if (i + BATCH_SIZE) % 2000 == 0 or (i + BATCH_SIZE) >= total_records:
            current_progress = min(i + BATCH_SIZE, total_records)
            try:
                await status_msg.edit_text(
                    f"⏳ **SEDANG MENGUPLOAD...**\n"
                    f"✅ Terproses: `{current_progress}` / `{total_records}`\n"
                    f"⛔ Gagal: `{fail_count}`\n\n"
                    f"🚀 _Mohon bersabar, data sedang masuk..._"
                )
                # Jeda sejenak agar Telegram server tidak menolak request (Rate Limit)
                await asyncio.sleep(0.5) 
            except Exception:
                pass # Abaikan error edit message jika terjadi, lanjut upload

    duration = round(time.time() - start_time, 2)

    # Buat Laporan Akhir (PASTI DIKIRIM)
    if fail_count > 0:
        report = (
            f"❌ **SELESAI (DENGAN ERROR)**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✅ Sukses: {success_count}\n"
            f"❌ Gagal: {fail_count}\n"
            f"⏱ Waktu: {duration} detik\n\n"
            f"🔍 **LOG ERROR TERAKHIR:**\n"
            f"`{last_error_msg[:300]}...`"
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
    
    # Hapus pesan loading lama, kirim laporan baru agar notifikasi masuk
    await status_msg.delete()
    await update.message.reply_text(report, parse_mode='Markdown')
    
    # Bersihkan memori
    context.user_data.pop('final_data_records', None)
    return ConversationHandler.END


# ##############################################################################
# ##############################################################################
#
#                 BAGIAN 6: FITUR ADMIN EKSKLUSIF (STATS, USER MANAGEMENT)
#
# ##############################################################################
# ##############################################################################

async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Menampilkan statistik total data, user, dan JUMLAH LEASING UNIK.
    Menggunakan teknik Pagination Loop untuk menghitung leasing.
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
        raw_set = set()
        offset = 0
        batch_size = 1000
        
        while True:
            # Ambil data kolom 'finance' saja per batch
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
    Menampilkan daftar user secara lengkap dan terperinci.
    Dipisahkan antara User Aktif dan Statistik Non-Aktif.
    """
    if update.effective_user.id != ADMIN_ID: return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
    
    try:
        # Ambil semua user
        res = supabase.table('users').select("*").execute()
        if not res.data:
            return await update.message.reply_text("Belum ada user terdaftar.")

        all_data = res.data
        
        # Filter Data
        active_list = [u for u in all_data if u.get('status') == 'active']
        banned_count = len([u for u in all_data if u.get('status') == 'rejected'])
        pending_count = len([u for u in all_data if u.get('status') == 'pending'])

        # Susun Pesan: Daftar Aktif
        msg = f"📋 **DAFTAR MITRA AKTIF ({len(active_list)})**\n"
        msg += "━━━━━━━━━━━━━━━━━━\n"

        if active_list:
            for i, u in enumerate(active_list, 1):
                nama = u.get('nama_lengkap', '-')
                pt = u.get('agency', '-')
                uid = u.get('user_id', '-')
                msg += f"{i}. 👤 **{nama}**\n    🏢 {pt}\n    🆔 `{uid}`\n\n"
        else:
            msg += "_Tidak ada user aktif._\n\n"

        # Susun Pesan: Statistik Lainnya
        msg += "━━━━━━━━━━━━━━━━━━\n"
        msg += f"📊 **STATUS LAINNYA**\n"
        msg += f"⛔ Banned/Ditolak: `{banned_count}` User\n"
        msg += f"⏳ Pending/Menunggu: `{pending_count}` User"

        # Cek Panjang Pesan (Telegram Max 4096 char)
        if len(msg) > 4000:
            await update.message.reply_text(msg[:4000] + "\n\n⚠️ _(Daftar dipotong karena terlalu panjang)_", parse_mode='Markdown')
        else:
            await update.message.reply_text(msg, parse_mode='Markdown')

    except Exception as e:
        logging.error(f"List Users Error: {e}")
        await update.message.reply_text("❌ Gagal mengambil data user.")

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

async def set_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Set pesan info sticky di perintah /start.
    """
    global GLOBAL_INFO
    if update.effective_user.id != ADMIN_ID: return
    
    msg = " ".join(context.args)
    if not msg: 
        return await update.message.reply_text("⚠️ Contoh: `/setinfo 🔥 Bonus Hari Ini!`", parse_mode='Markdown')
    
    GLOBAL_INFO = msg
    await update.message.reply_text(f"✅ **Info Terpasang!**\n{GLOBAL_INFO}", parse_mode='Markdown')

async def del_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Menghapus pesan info sticky.
    """
    global GLOBAL_INFO
    if update.effective_user.id != ADMIN_ID: return
    
    GLOBAL_INFO = ""
    await update.message.reply_text("🗑️ Info dihapus.")

async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User mengirim pesan ke Admin.
    """
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
    """
    Mengirim notifikasi ke Group Log saat unit ditemukan (HIT).
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
    Mengetes apakah bot bisa mengirim pesan ke Group Log.
    """
    if update.effective_user.id != ADMIN_ID: return
    try:
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text="🔔 **TES NOTIFIKASI GROUP OK!**\nBot berfungsi dengan baik.")
        await update.message.reply_text("✅ Notifikasi terkirim ke Group Log.")
    except: await update.message.reply_text("❌ Gagal kirim ke Group Log. Cek ID Group & Pastikan Bot sudah jadi Admin di sana.")


# ##############################################################################
# ##############################################################################
#
#                 BAGIAN 8: HANDLER CONVERSATION (REGISTRASI & LAPOR)
#
# ##############################################################################
# ##############################################################################

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

# --- REGISTRASI (FULL STEP & LENGKAP v3.2) ---
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
        
        # NOTIFIKASI ADMIN LENGKAP (REVISI v3.2)
        # Menampilkan seluruh data user yang mendaftar agar Admin mudah memverifikasi
        msg_admin = (
            f"🔔 **PENDAFTARAN MITRA BARU**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 **Nama:** {data['nama_lengkap']}\n"
            f"🏢 **Agency:** {data['agency']}\n"
            f"📍 **Kota:** {data['alamat']}\n"
            f"📱 **HP:** {data['no_hp']}\n"
            f"📧 **Email:** {data['email']}\n"
            f"🆔 **ID:** `{data['user_id']}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👉 _Klik tombol di bawah untuk verifikasi._"
        )
        
        kb = [[InlineKeyboardButton("✅ Terima", callback_data=f"appu_{data['user_id']}"), InlineKeyboardButton("❌ Tolak", callback_data=f"reju_{data['user_id']}")]]
        
        await context.bot.send_message(chat_id=ADMIN_ID, text=msg_admin, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
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


# ##############################################################################
# ##############################################################################
#
#                 BAGIAN 9: HANDLER UTAMA (START, MESSAGE, CALLBACK)
#
# ##############################################################################
# ##############################################################################

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


# ##############################################################################
# ##############################################################################
#
#                        BAGIAN 10: MAIN PROGRAM ENTRY POINT
#
# ##############################################################################
# ##############################################################################

if __name__ == '__main__':
    # Build Application
    app = ApplicationBuilder().token(token).post_init(post_init).build()
    
    # --------------------------------------------------------------------------
    # REGISTRASI CONVERSATION HANDLERS (PRIORITAS UTAMA)
    # --------------------------------------------------------------------------
    
    # 1. SMART UPLOAD (Ditaruh paling atas agar tidak tertutup handler lain)
    # Fitur: allow_reentry=True agar bisa di-restart kapan saja jika error.
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

    # 2. Registrasi User
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

    # 3. Tambah Data Manual
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

    # 4. Lapor Hapus
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('lapor', lapor_delete_start)],
        states={
            L_NOPOL:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), lapor_delete_check)],
            L_CONFIRM:[MessageHandler(filters.TEXT, lapor_delete_confirm)]
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)],
        conversation_timeout=60
    ))

    # 5. Hapus Manual Admin
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('hapus', delete_unit_start)],
        states={
            D_NOPOL:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), delete_unit_check)],
            D_CONFIRM:[MessageHandler(filters.TEXT, delete_unit_confirm)]
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)],
        conversation_timeout=60
    ))

    # --------------------------------------------------------------------------
    # REGISTRASI COMMAND HANDLERS
    # --------------------------------------------------------------------------
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

    # --------------------------------------------------------------------------
    # REGISTRASI GENERIC HANDLERS
    # --------------------------------------------------------------------------
    app.add_handler(CallbackQueryHandler(callback_handler))
    # Handler pesan teks (harus paling akhir agar tidak memakan command lain)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ ONEASPAL BOT ONLINE - V3.9 (ZIP SUPPORT ENABLED)")
    app.run_polling()