import os
import logging
import pandas as pd
import io
import numpy as np
import time
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

# --- KONFIGURASI LOGGING ---
load_dotenv()
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- LOAD KONFIGURASI ---
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
token: str = os.environ.get("TELEGRAM_TOKEN")

# --- VARIABLE GLOBAL PENGUMUMAN ---
GLOBAL_INFO = ""

# --- SETUP ADMIN ID ---
DEFAULT_ADMIN_ID = 7530512170
try:
    env_id = os.environ.get("ADMIN_ID")
    ADMIN_ID = int(env_id) if env_id else DEFAULT_ADMIN_ID
except ValueError:
    ADMIN_ID = DEFAULT_ADMIN_ID

print(f"✅ ADMIN ID: {ADMIN_ID}")

LOG_GROUP_ID = -1003627047676  

if not url or not key or not token:
    print("❌ ERROR: Cek file .env Anda.")
    exit()

try:
    supabase: Client = create_client(url, key)
except Exception as e:
    print(f"❌ Gagal koneksi Supabase: {e}")
    exit()

# --- KAMUS ALIAS KOLOM (SMART MAPPING) ---
# Ini adalah "Otak Detektif" untuk mengenali berbagai istilah kolom
COLUMN_ALIASES = {
    'nopol': [
        'no polisi', 'nomor polisi', 'no_polisi', 'no.polisi', 
        'plat', 'no plat', 'nomor plat', 'nopol', 
        'nomor kendaraan', 'no. kendaraan', 'nomer', 'tnkb', 'license plate'
    ],
    'type': [
        'type', 'tipe', 'unit', 'model', 'vehicle', 'jenis', 
        'deskripsi unit', 'merk', 'object', 'kendaraan', 'item', 'brand'
    ],
    'tahun': ['tahun', 'year', 'thn', 'rakitan', 'th'],
    'warna': ['warna', 'color', 'colour', 'cat', 'kelir'],
    'noka': [
        'noka', 'no rangka', 'nomor rangka', 'chassis', 'chasis', 
        'vin', 'rangka', 'no.rangka'
    ],
    'nosin': [
        'nosin', 'no mesin', 'nomor mesin', 'engine', 'mesin', 
        'no.mesin'
    ],
    'finance': [
        'finance', 'leasing', 'lising', 'multifinance', 'cabang', 
        'partner', 'mitra', 'principal', 'company'
    ],
    'ovd': [
        'ovd', 'overdue', 'dpd', 'keterlambatan', 'hari', 
        'telat', 'aging', 'od', 'bucket'
    ],
    'branch': [
        'branch', 'area', 'kota', 'pos', 'cabang', 
        'lokasi', 'wilayah', 'region', 'area_name'
    ]
}

# --- STATE CONVERSATION ---
R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_CONFIRM = range(6)
A_NOPOL, A_TYPE, A_LEASING, A_NOKIR, A_CONFIRM = range(6, 11)
L_NOPOL, L_CONFIRM = range(11, 13) 
D_NOPOL, D_CONFIRM = range(13, 15)
# UPLOAD SMART STATES (Updated v1.9)
U_LEASING_USER, U_LEASING_ADMIN, U_CONFIRM_UPLOAD = range(15, 18)

# ==============================================================================
#                        AUTO MENU COMMAND
# ==============================================================================
async def post_init(application: Application):
    """Mengatur Tombol Menu secara Otomatis saat Bot Start"""
    await application.bot.set_my_commands([
        ("start", "🔄 Restart / Menu Utama"),
        ("register", "📝 Daftar Mitra Baru"),
        ("tambah", "➕ Tambah Unit Manual"),
        ("lapor", "🗑️ Lapor Unit Selesai"),
        ("admin", "📩 Hubungi Admin"),
        ("panduan", "📖 Petunjuk Penggunaan"),
    ])
    print("✅ Menu Perintah Berhasil Di-set!")

# ==============================================================================
#                             DATABASE HELPERS
# ==============================================================================

def get_user(user_id):
    try:
        response = supabase.table('users').select("*").eq('user_id', user_id).execute()
        return response.data[0] if response.data else None
    except: return None

def update_user_status(user_id, status):
    try:
        supabase.table('users').update({'status': status}).eq('user_id', user_id).execute()
    except Exception as e: logging.error(f"Error update status: {e}")

def update_quota_usage(user_id, current_quota):
    try:
        new_quota = current_quota - 1
        supabase.table('users').update({'quota': new_quota}).eq('user_id', user_id).execute()
    except: pass

def smart_rename_columns(df):
    """Fungsi pintar untuk menstandarkan nama kolom berdasarkan Kamus"""
    # Bersihkan nama kolom asli (lowercase, strip, replace spasi/titik dengan _)
    df.columns = df.columns.str.strip().str.lower().str.replace('.', ' ', regex=False)
    
    new_cols = {}
    found_cols = []
    
    for col in df.columns:
        renamed = False
        # Cek di kamus alias
        for standard_name, aliases in COLUMN_ALIASES.items():
            # Cek apakah nama kolom ada di dalam list alias
            if col == standard_name or col in aliases:
                new_cols[col] = standard_name
                found_cols.append(standard_name)
                renamed = True
                break
        
        # Jika tidak ada di alias, biarkan nama aslinya
        if not renamed:
            new_cols[col] = col

    df.rename(columns=new_cols, inplace=True)
    return df, found_cols

# ==============================================================================
#                 HANDLER UPLOAD FILE (SMART CONVERSATION) - V1.9
# ==============================================================================

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    document = update.message.document
    file_name = document.file_name

    # Cek Validitas User
    if not user_data or user_data['status'] != 'active':
        if user_id != ADMIN_ID: 
            return await update.message.reply_text("⛔ **AKSES DITOLAK**\nAnda belum terdaftar aktif.")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.UPLOAD_DOCUMENT)
    
    # Simpan file sementara di memory context
    context.user_data['upload_file_id'] = document.file_id
    context.user_data['upload_file_name'] = file_name

    # ALUR 1: USER BIASA -> Minta Nama Leasing -> Forward ke Admin
    if user_id != ADMIN_ID:
        await update.message.reply_text(
            f"📄 File `{file_name}` diterima.\n\n"
            "Satu langkah lagi: **Ini data dari Leasing/Finance apa?**\n"
            "(Contoh: BCA, Mandiri, Adira, Balimor)",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)
        )
        return U_LEASING_USER

    # ALUR 2: ADMIN -> Smart Process -> Konfirmasi Leasing
    else:
        msg = await update.message.reply_text("⏳ **Menganalisa struktur file...**")
        
        try:
            # Download file
            new_file = await document.get_file()
            file_content = await new_file.download_as_bytearray()
            
            # Baca Excel/CSV
            if file_name.lower().endswith('.csv'):
                try: df = pd.read_csv(io.BytesIO(file_content), sep=';', dtype=str)
                except: df = pd.read_csv(io.BytesIO(file_content), sep=None, engine='python', dtype=str)
            else:
                df = pd.read_excel(io.BytesIO(file_content), dtype=str)
            
            # --- THE BRAIN: SMART RENAME ---
            df, found_cols = smart_rename_columns(df)
            
            # Simpan dataframe di context
            context.user_data['df_records'] = df.to_dict(orient='records')
            
            # Cek apakah kolom Nopol ketemu
            if 'nopol' not in df.columns:
                await msg.edit_text(
                    "❌ **ERROR SMART DETECT**\n"
                    "Sistem tidak menemukan kolom yang mirip dengan **'Nopol'**.\n"
                    f"Kolom terbaca: {', '.join(df.columns[:5])}...\n"
                    "Mohon cek file Anda."
                )
                return ConversationHandler.END

            # Cek keberadaan Leasing
            has_finance = 'finance' in df.columns
            
            report = (
                f"✅ **SMART SCAN SELESAI**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Kolom Terdeteksi:** {', '.join(found_cols)}\n"
                f"📁 **Total Baris:** {len(df)}\n"
                f"🏦 **Kolom Leasing:** {'✅ ADA' if has_finance else '⚠️ TIDAK ADA'}\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"👉 **MASUKKAN NAMA LEASING UNTUK DATA INI:**\n"
                f"_(Ketik 'SKIP' jika ingin menggunakan kolom leasing yang ada di file)_"
            )
            await msg.edit_text(report, parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
            return U_LEASING_ADMIN

        except Exception as e:
            await msg.edit_text(f"❌ Gagal baca file: {str(e)}")
            return ConversationHandler.END

async def upload_leasing_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # User memasukkan nama leasing
    leasing_name = update.message.text
    if leasing_name == "❌ BATAL": 
        await update.message.reply_text("🚫 Upload dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    file_id = context.user_data.get('upload_file_id')
    file_name = context.user_data.get('upload_file_name')
    user = get_user(update.effective_user.id)

    # Forward ke Admin dengan Keterangan Leasing
    caption_admin = (
        f"📥 **FILE DARI MITRA (SMART UPLOAD)**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Pengirim:** {user.get('nama_lengkap')} ({user.get('agency')})\n"
        f"🏦 **Leasing:** {leasing_name.upper()}\n"
        f"📄 **File:** `{file_name}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👉 _Silakan download dan upload ulang untuk memproses._"
    )
    await context.bot.send_document(chat_id=ADMIN_ID, document=file_id, caption=caption_admin, parse_mode='Markdown')
    
    await update.message.reply_text(
        "✅ **TERIMA KASIH!**\n"
        "File dan info leasing telah dikirim ke Admin untuk diproses.\n"
        "Salam Satu Aspal! 👋",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def upload_leasing_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Admin memasukkan nama leasing override
    leasing_input = update.message.text
    
    # Restore Dataframe
    df = pd.DataFrame(context.user_data['df_records'])
    
    # INJECT LEASING NAME
    final_leasing_name = leasing_input.upper()
    if final_leasing_name != 'SKIP':
        df['finance'] = final_leasing_name
    elif 'finance' in df.columns:
        final_leasing_name = "SESUAI FILE (AUTO)"
    else:
        final_leasing_name = "UNKNOWN"
        df['finance'] = 'UNKNOWN'

    # Standardize Nopol
    df['nopol'] = df['nopol'].astype(str).str.replace(' ', '').str.upper()
    df = df.drop_duplicates(subset=['nopol'], keep='last')
    df = df.replace({np.nan: None})
    
    # Filter kolom yang valid untuk DB
    valid_cols_db = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch']
    for col in valid_cols_db:
        if col not in df.columns:
            df[col] = None
    
    # Ambil sampel baris pertama untuk preview
    sample = df.iloc[0]
    
    # Simpan data final yang siap upload ke context
    context.user_data['final_data_records'] = df[valid_cols_db].to_dict(orient='records')
    context.user_data['final_leasing_name'] = final_leasing_name
    
    # Tampilkan Preview & Minta Konfirmasi (SAFEGUARD)
    preview_msg = (
        f"🔎 **PREVIEW SMART DETECTIVE**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏦 **Leasing Set:** {final_leasing_name}\n"
        f"📊 **Total Data:** {len(df)}\n\n"
        f"📝 **CONTOH DATA BARIS PERTAMA:**\n"
        f"🔹 **Nopol:** `{sample['nopol']}`\n"
        f"🔹 **Unit:** {sample['type']}\n"
        f"🔹 **Noka:** {sample['noka']}\n"
        f"🔹 **Nosin:** {sample['nosin']}\n"
        f"🔹 **Warna:** {sample['warna']}\n"
        f"🔹 **OVD:** {sample['ovd']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ **Pastikan data di atas sudah benar.**\n"
        f"Klik **EKSEKUSI UPLOAD** untuk memasukkan ke database."
    )
    
    await update.message.reply_text(
        preview_msg, 
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup([["🚀 EKSEKUSI UPLOAD", "❌ BATAL"]], one_time_keyboard=True)
    )
    return U_CONFIRM_UPLOAD

async def upload_confirm_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    
    if choice == "❌ BATAL":
        await update.message.reply_text("🚫 Proses upload dibatalkan. Data tidak disimpan.", reply_markup=ReplyKeyboardRemove())
        context.user_data.pop('final_data_records', None)
        return ConversationHandler.END
    
    if choice == "🚀 EKSEKUSI UPLOAD":
        status_msg = await update.message.reply_text("⏳ **Sedang mengupload data ke database...**", reply_markup=ReplyKeyboardRemove())
        start_time = time.time()
        
        final_data = context.user_data.get('final_data_records')
        leasing_name = context.user_data.get('final_leasing_name')
        file_name = context.user_data.get('upload_file_name')
        
        # BATCH UPLOAD PROCESS
        total_rows = len(final_data)
        success_count = 0
        fail_count = 0
        BATCH_SIZE = 1000
        
        for i in range(0, total_rows, BATCH_SIZE):
            batch = final_data[i : i + BATCH_SIZE]
            try:
                supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
                success_count += len(batch)
            except Exception:
                # Retry Logic
                for j in range(0, len(batch), 100):
                    mini = batch[j : j + 100]
                    try:
                        supabase.table('kendaraan').upsert(mini, on_conflict='nopol').execute()
                        success_count += len(mini)
                    except:
                        for item in mini:
                            try:
                                supabase.table('kendaraan').upsert([item], on_conflict='nopol').execute()
                                success_count += 1
                            except: fail_count += 1

        duration = round(time.time() - start_time, 2)
        report = (
            f"✅ **UPLOAD SUKSES!**\n━━━━━━━━━━━━━━━━━━\n"
            f"📄 **File:** `{file_name}`\n"
            f"🏦 **Leasing:** {leasing_name}\n"
            f"📊 **Total Upload:** {total_rows}\n"
            f"✅ **Berhasil:** {success_count}\n❌ **Gagal:** {fail_count}\n"
            f"⏱ **Waktu:** {duration}s"
        )
        await status_msg.edit_text(report, parse_mode='Markdown')
        
        # Bersihkan memory
        context.user_data.pop('final_data_records', None)
        return ConversationHandler.END

# ==============================================================================
#                        ADMIN: MANAGEMENT & STATS
# ==============================================================================

async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
    msg_wait = await update.message.reply_text("⏳ *Sedang menghitung seluruh data (ini butuh waktu)...*", parse_mode='Markdown')

    try:
        res_total = supabase.table('kendaraan').select("*", count="exact", head=True).execute()
        total_unit = res_total.count if res_total.count else 0

        res_users = supabase.table('users').select("*", count="exact", head=True).execute()
        total_user = res_users.count if res_users.count else 0

        raw_set = set()
        offset = 0
        batch_size = 1000
        while True:
            res_batch = supabase.table('kendaraan').select("finance").range(offset, offset + batch_size - 1).execute()
            data = res_batch.data
            if not data: break
            for d in data:
                f = d.get('finance')
                if f:
                    clean_f = str(f).strip().upper()
                    if len(clean_f) > 1 and clean_f not in ["-", "NAN", "NONE", "NULL"]:
                        raw_set.add(clean_f)
            if len(data) < batch_size: break
            offset += batch_size

        sorted_names = sorted(list(raw_set), key=len)
        final_groups = []
        for name in sorted_names:
            is_duplicate = False
            for group in final_groups:
                if group in name: is_duplicate = True; break
            if not is_duplicate: final_groups.append(name)

        total_leasing = len(final_groups)

        msg = (
            f"📊 **STATISTIK ONEASPAL**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📂 **Total Data:** `{total_unit:,}` Unit\n"
            f"👥 **Total User:** `{total_user:,}` Mitra\n"
            f"🏦 **Jumlah Leasing:** `{total_leasing}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔍 _Metode: Pagination Loop_"
        )
        await msg_wait.edit_text(msg, parse_mode='Markdown')

    except Exception as e:
        logging.error(f"Stats Error: {e}")
        await msg_wait.edit_text(f"❌ Error: {e}")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        res = supabase.table('users').select("*").order('created_at', desc=True).limit(20).execute()
        if not res.data: return await update.message.reply_text("Belum ada user.")
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

async def test_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text="🔔 **TES NOTIFIKASI OK!**")
        await update.message.reply_text("✅ Terkirim.")
    except: await update.message.reply_text("❌ Gagal.")

# ==============================================================================
#                 FITUR: INFO/PENGUMUMAN & CONTACT ADMIN
# ==============================================================================

async def set_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return
    
    msg_content = " ".join(context.args)
    if not msg_content: 
        return await update.message.reply_text("⚠️ Contoh: `/admin Lapor error...`", parse_mode='Markdown')
    
    try:
        report = (f"📩 **PESAN MITRA**\n👤 {u.get('nama_lengkap')}\n💬 {msg_content}")
        await context.bot.send_message(chat_id=ADMIN_ID, text=report)
        await update.message.reply_text("✅ Terkirim.")
    except: 
        await update.message.reply_text("❌ Gagal.")

async def notify_hit_to_group(context: ContextTypes.DEFAULT_TYPE, user_data, vehicle_data):
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
    text_panduan = (
        "📖 **PANDUAN ONEASPAL**\n\n"
        "1️⃣ **CARI DATA**\n"
        "Ketik Nopol/Noka/Nosin tanpa spasi.\n"
        "✅ Contoh: `1234ABC` (Tanpa huruf depan)\n"
        "✅ Contoh: `B1234ABC` (Lengkap)\n\n"
        "2️⃣ **TAMBAH DATA:** `/tambah`\n"
        "3️⃣ **LAPOR SELESAI:** `/lapor`\n"
        "4️⃣ **KONTAK ADMIN:** `/admin [pesan]`\n"
        "5️⃣ **UPLOAD:** Kirim file Excel ke chat bot langsung, klik icon CLIP kirim file yang ada dikanan bawah."
    )
    await update.message.reply_text(text_panduan, parse_mode='Markdown')

# ==============================================================================
#                 FITUR: LAPOR HAPUS UNIT (USER REQUEST -> ADMIN APPROVE)
# ==============================================================================

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
            f"📱 **No HP:** `{user.get('no_hp')}`\n"
            f"📧 **Email:** `{user.get('email')}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔢 **Nopol:** `{nopol}`\n"
            f"📝 **Status:** Laporan Selesai/Aman\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👉 Klik **Setujui** untuk menghapus data ini dari database PERMANEN."
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    
    return ConversationHandler.END

# ==============================================================================
#                 FITUR: HAPUS UNIT (ADMIN MANUAL)
# ==============================================================================

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

# ==============================================================================
#                        USER: REGISTRASI (EXPANDED)
# ==============================================================================

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
    
    # PERBAIKAN UX: Tampilan lebih rapi & Instruksi lebih tegas
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
        if "duplicate key" in str(e).lower():
            await update.message.reply_text("⚠️ Anda sudah terdaftar sebelumnya.", reply_markup=ReplyKeyboardRemove())
        else:
            await update.message.reply_text(f"⚠️ Gagal menyimpan data.", reply_markup=ReplyKeyboardRemove())
        
    return ConversationHandler.END

# ==============================================================================
#                     USER: TAMBAH DATA (MANUAL - EXPANDED)
# ==============================================================================

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
#                        HANDLER UTAMA (START & MESSAGE)
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info_text = ""
    if GLOBAL_INFO:
        info_text = f"\n📢 **INFO:** {GLOBAL_INFO}\n━━━━━━━━━━━━━━━━━━\n"

    # TEKS LENGKAP PROFESIONAL (RESTORED)
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
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return
    
    kw = update.message.text.upper().replace(" ", "")
    
    if len(kw) < 3:
        return await update.message.reply_text("⚠️ Masukkan minimal 3 karakter.")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
    await asyncio.sleep(0.5) 
    
    try:
        # WILDCARD SEARCH ENABLED
        res = supabase.table('kendaraan').select("*").or_(f"nopol.ilike.%{kw},noka.eq.{kw},nosin.eq.{kw}").execute()
        if res.data:
            d = res.data[0]
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
            await notify_hit_to_group(context, u, d)
        else:
            header_info = f"📢 **INFO:** {GLOBAL_INFO}\n\n" if GLOBAL_INFO else ""
            await update.message.reply_text(f"{header_info}❌ **DATA TIDAK DITEMUKAN**\n`{kw}`", parse_mode='Markdown')
    except: await update.message.reply_text("❌ Terjadi kesalahan database.")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
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
        await context.bot.send_message(uid, "⛔ Pendaftaran Anda ditolak Admin.")
        
    elif data.startswith("v_acc_"):
        _, _, n, uid = data.split("_")
        item = context.bot_data.get(f"prop_{n}")
        if item: 
            supabase.table('kendaraan').upsert(item).execute()
            await q.edit_message_text(f"✅ Data {n} Masuk Database.")
            await context.bot.send_message(uid, f"🎊 Data `{n}` yang Anda kirim telah disetujui!")
            
    elif data == "v_rej":
        await q.edit_message_text("❌ Data Ditolak.")
        
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
            
    elif data.startswith("del_rej_"):
        uid_lapor = data.split("_")[2]
        await q.edit_message_text("❌ Ditolak.")
        await context.bot.send_message(uid_lapor, "❌ Laporan Hapus DITOLAK.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Dibatalkan.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

if __name__ == '__main__':
    app = ApplicationBuilder().token(token).post_init(post_init).build()
    
    # 1. REGISTRASI
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

    # 2. TAMBAH DATA (USER)
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

    # 3. LAPOR HAPUS DATA (USER)
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('lapor', lapor_delete_start)],
        states={
            L_NOPOL:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), lapor_delete_check)],
            L_CONFIRM:[MessageHandler(filters.TEXT, lapor_delete_confirm)]
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)],
        conversation_timeout=60
    ))

    # 4. HAPUS MANUAL (ADMIN)
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('hapus', delete_unit_start)],
        states={
            D_NOPOL:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), delete_unit_check)],
            D_CONFIRM:[MessageHandler(filters.TEXT, delete_unit_confirm)]
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)],
        conversation_timeout=60
    ))

    # 5. UPLOAD FILE SMART (USER & ADMIN) - V1.9 (With Admin Confirmation)
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Document.ALL, upload_start)],
        states={
            U_LEASING_USER: [MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), upload_leasing_user)],
            U_LEASING_ADMIN: [MessageHandler(filters.TEXT, upload_leasing_admin)],
            U_CONFIRM_UPLOAD: [MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), upload_confirm_admin)]
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)],
        conversation_timeout=120
    ))

    # HANDLERS UMUM
    app.add_handler(CommandHandler('start', start))
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

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ ONEASPAL BOT ONLINE - V1.9 (SMART UPLOAD + ADMIN CONFIRMATION)")
    app.run_polling()