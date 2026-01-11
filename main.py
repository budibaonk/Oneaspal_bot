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

# --- STATE CONVERSATION ---
R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_CONFIRM = range(6)
A_NOPOL, A_TYPE, A_LEASING, A_NOKIR, A_CONFIRM = range(6, 11)

# ==============================================================================
#                        AUTO MENU COMMAND
# ==============================================================================
async def post_init(application: Application):
    """Mengatur Tombol Menu secara Otomatis saat Bot Start"""
    await application.bot.set_my_commands([
        ("start", "🔄 Restart / Menu Utama"),
        ("register", "📝 Daftar Mitra Baru"),
        ("tambah", "➕ Tambah Unit Manual"),
        ("panduan", "📖 Petunjuk Penggunaan"),
        ("stats", "📊 Statistik (Admin Only)")
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

# ==============================================================================
#                 HANDLER UPLOAD FILE (SMART RETRY & CLEANING)
# ==============================================================================

async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    
    # Efek Uploading...
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.UPLOAD_DOCUMENT)

    if not user_data or user_data['status'] != 'active':
        if user_id != ADMIN_ID: 
            return await update.message.reply_text("⛔ **AKSES DITOLAK**\nAnda belum terdaftar aktif.")

    document = update.message.document
    file_name = document.file_name

    # USER BIASA -> TITIP FILE KE ADMIN
    if user_id != ADMIN_ID:
        await update.message.reply_text(
            "✅ **FILE DITERIMA**\nFile Excel telah dikirim ke Admin.\n⏳ *Menunggu verifikasi...*",
            parse_mode='Markdown'
        )
        try:
            caption_admin = (
                f"📥 **KONTRIBUSI FILE USER**\n"
                f"👤 {user_data.get('nama_lengkap')} ({user_data.get('agency')})\n"
                f"📄 `{file_name}`"
            )
            await context.bot.send_document(chat_id=ADMIN_ID, document=document.file_id, caption=caption_admin, parse_mode='Markdown')
        except: pass
        return 

    # ADMIN -> PROSES SMART UPLOAD
    status_msg = await update.message.reply_text("⏳ **Menganalisa & Membersihkan file...**")
    start_time = time.time()

    try:
        new_file = await document.get_file()
        file_content = await new_file.download_as_bytearray()
        
        # Baca File
        if file_name.lower().endswith('.csv'):
            try:
                df = pd.read_csv(io.BytesIO(file_content), sep=';', dtype=str)
                if len(df.columns) <= 1: df = pd.read_csv(io.BytesIO(file_content), sep=',', dtype=str)
            except: df = pd.read_csv(io.BytesIO(file_content), sep=None, engine='python', dtype=str)
        elif file_name.lower().endswith('.xlsx') or file_name.lower().endswith('.xls'):
            df = pd.read_excel(io.BytesIO(file_content), dtype=str)
        else:
            return await status_msg.edit_text("❌ Format salah. Gunakan .csv atau .xlsx")
        
        # Normalisasi
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        if 'nopol' not in df.columns:
            return await status_msg.edit_text("❌ Gagal: Tidak ada kolom 'nopol'.")

        # PEMBERSIHAN DATA (SMART CLEANING)
        df['nopol'] = df['nopol'].astype(str).str.replace(' ', '').str.upper()
        # Hapus Duplikat Internal (Ambil data paling bawah)
        df = df.drop_duplicates(subset=['nopol'], keep='last')
        df = df.replace({np.nan: None})
        
        valid_cols = df.columns.intersection(['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch'])
        final_data = df[valid_cols].to_dict(orient='records')
        
        total_rows = len(final_data)
        success_count = 0
        fail_count = 0

        await status_msg.edit_text(f"📥 **Memproses {total_rows} data bersih...**")

        # SMART BATCH UPLOAD (RETRY MECHANISM)
        BATCH_SIZE = 1000
        for i in range(0, total_rows, BATCH_SIZE):
            batch = final_data[i : i + BATCH_SIZE]
            try:
                # 1. Coba kirim 1000 sekaligus
                supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
                success_count += len(batch)
            except Exception:
                logging.error(f"Batch {i} failed, retrying smaller chunks...")
                # 2. Jika gagal, pecah jadi 100
                for j in range(0, len(batch), 100):
                    mini_batch = batch[j : j + 100]
                    try:
                        supabase.table('kendaraan').upsert(mini_batch, on_conflict='nopol').execute()
                        success_count += len(mini_batch)
                    except:
                        # 3. Jika masih gagal, kirim SATU PER SATU (Penyelamatan terakhir)
                        for item in mini_batch:
                            try:
                                supabase.table('kendaraan').upsert([item], on_conflict='nopol').execute()
                                success_count += 1
                            except:
                                fail_count += 1

        duration = round(time.time() - start_time, 2)
        report = (
            f"✅ **DATABASE DIPERBARUI**\n━━━━━━━━━━━━━━━━━━\n"
            f"📄 **File:** `{file_name}`\n📊 **Total Bersih:** {total_rows}\n"
            f"✅ **Sukses:** {success_count}\n❌ **Gagal:** {fail_count}\n"
            f"⏱ **Waktu:** {duration}s\n"
            f"ℹ️ _Smart Retry Active_"
        )
        await status_msg.edit_text(report, parse_mode='Markdown')

    except Exception as e:
        await status_msg.edit_text(f"❌ **ERROR:** {str(e)}")

# ==============================================================================
#                        ADMIN: MANAGEMENT & STATS (FIXED PAGINATION)
# ==============================================================================

async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
    msg_wait = await update.message.reply_text("⏳ *Sedang menghitung seluruh data (ini butuh waktu)...*", parse_mode='Markdown')

    try:
        # 1. Hitung Total Data & User (Pakai count='exact' dan head=True agar cepat)
        res_total = supabase.table('kendaraan').select("*", count="exact", head=True).execute()
        total_unit = res_total.count if res_total.count else 0

        res_users = supabase.table('users').select("*", count="exact", head=True).execute()
        total_user = res_users.count if res_users.count else 0

        # 2. Ambil Data Leasing (DENGAN LOOPING AGAR SEMUA DATA TERAMBIL)
        raw_set = set()
        offset = 0
        batch_size = 1000  # Supabase limit default
        
        while True:
            # Ambil per 1000 data
            res_batch = supabase.table('kendaraan').select("finance").range(offset, offset + batch_size - 1).execute()
            data = res_batch.data
            
            if not data:
                break # Berhenti jika data habis
            
            # Masukkan ke set (himpunan unik)
            for d in data:
                f = d.get('finance')
                if f:
                    clean_f = str(f).strip().upper()
                    if len(clean_f) > 1 and clean_f not in ["-", "NAN", "NONE", "NULL"]:
                        raw_set.add(clean_f)
            
            # Cek apakah data yang diterima kurang dari batch_size (artinya ini halaman terakhir)
            if len(data) < batch_size:
                break
            
            offset += batch_size

        # 3. Smart Grouping (BCA & BCA Finance = 1)
        sorted_names = sorted(list(raw_set), key=len)
        final_groups = []
        for name in sorted_names:
            is_duplicate = False
            for group in final_groups:
                if group in name: 
                    is_duplicate = True
                    break
            if not is_duplicate: final_groups.append(name)

        total_leasing = len(final_groups)

        # 4. Tampilkan Laporan
        msg = (
            f"📊 **STATISTIK ONEASPAL**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📂 **Total Data:** `{total_unit:,}` Unit\n"
            f"👥 **Total User:** `{total_user:,}` Mitra\n"
            f"🏦 **Jumlah Leasing:** `{total_leasing}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔍 _Metode: Pagination Loop & Smart Grouping_"
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

# ==============================================================================
#                        FITUR: PANDUAN LENGKAP
# ==============================================================================

async def panduan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text_panduan = (
        "📖 **PANDUAN PENGGUNAAN ONEASPAL**\n\n"
        "1️⃣ **PENCARIAN DATA**\n"
        "Cukup ketik data yang dicari langsung di chat ini (tanpa spasi).\n"
        "✅ Bisa cari: **Nopol**, **Noka**, atau **Nosin**\n"
        "🔍 *Contoh:* `B1234XYZ` atau `MH1JBB123...`\n\n"
        "2️⃣ **TAMBAH DATA (MANUAL)**\n"
        "Jika Anda menemukan unit baru di lapangan:\n"
        "👉 Ketik perintah: `/tambah`\n"
        "Ikuti instruksi bot untuk memasukkan Nopol, Type, Leasing, dll.\n\n"
        "3️⃣ **UPLOAD DATA (MASSAL)**\n"
        "Anda punya banyak data dalam format Excel/CSV?\n"
        "👉 **Kirim file Excel (.xlsx) langsung ke sini.**\n"
        "Bot akan meneruskan file Anda ke Admin untuk diverifikasi dan di-upload.\n\n"
        "💡 *Gunakan tombol Menu di kiri bawah untuk melihat perintah.*"
    )
    await update.message.reply_text(text_panduan, parse_mode='Markdown')

# ==============================================================================
#                        USER: REGISTRASI
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
    summary = (f"📋 **KONFIRMASI DATA**\nNama: {context.user_data['r_nama']}\n"
               f"HP: {context.user_data['r_hp']}\nKota: {context.user_data['r_kota']}\nAgency: {context.user_data['r_agency']}")
    await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ ULANGI"]], one_time_keyboard=True))
    return R_CONFIRM

async def register_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ ULANGI": 
        await update.message.reply_text("🔄 Silakan ketik /register untuk ulang.", reply_markup=ReplyKeyboardRemove())
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
        await update.message.reply_text("✅ **Data Terkirim!**\nMohon tunggu verifikasi Admin.", reply_markup=ReplyKeyboardRemove())
        
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
#                     USER: TAMBAH DATA (MANUAL)
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
        "nopol": n, "type": context.user_data['a_type'], 
        "finance": context.user_data['a_leasing'], "ovd": f"Kiriman: {context.user_data['a_nokir']}"
    }
    await update.message.reply_text("✅ Terkirim! Menunggu persetujuan Admin.", reply_markup=ReplyKeyboardRemove())
    kb = [[InlineKeyboardButton("✅ Terima Data", callback_data=f"v_acc_{n}_{update.effective_user.id}"), InlineKeyboardButton("❌ Tolak", callback_data="v_rej")]]
    await context.bot.send_message(ADMIN_ID, f"📥 **USULAN DATA BARU**\nNopol: {n}\nUnit: {context.user_data['a_type']}", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

# ==============================================================================
#                        HANDLER UTAMA
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
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
    
    # Efek Mengetik...
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
    await asyncio.sleep(0.5) 
    
    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.eq.{kw},noka.eq.{kw},nosin.eq.{kw}").execute()
        if res.data:
            d = res.data[0]
            update_quota_usage(u['user_id'], u['quota'])
            text = (
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
                f"⚠️ *CATATAN PENTING:*\n"
                f"Ini bukan alat yang SAH untuk penarikan atau menyita aset kendaraan, "
                f"Silahkan konfirmasi kepada PIC leasing terkait.\n"
                f"Terima kasih."
            )
            await update.message.reply_text(text, parse_mode='Markdown')
            await notify_hit_to_group(context, u, d)
        else:
            await update.message.reply_text(f"❌ **DATA TIDAK DITEMUKAN**\n`{kw}`\n\nKetik /tambah jika Anda ingin berkontribusi.", parse_mode='Markdown')
    except: await update.message.reply_text("❌ Terjadi kesalahan database.")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    data = q.data
    
    if data.startswith("appu_"):
        uid = data.split("_")[1]; update_user_status(uid, 'active')
        await q.edit_message_text(f"✅ User {uid} DISETUJUI.")
        await context.bot.send_message(uid, "🎉 **AKUN ANDA TELAH AKTIF!**\nSilakan mulai mencari data.")
    elif data.startswith("reju_"):
        uid = data.split("_")[1]; update_user_status(uid, 'rejected')
        await q.edit_message_text(f"⛔ User {uid} DITOLAK.")
        await context.bot.send_message(uid, "⛔ Pendaftaran Anda ditolak Admin.")
    elif data.startswith("v_acc_"):
        _, _, n, uid = data.split("_"); item = context.bot_data.get(f"prop_{n}")
        if item:
            supabase.table('kendaraan').upsert(item).execute()
            await q.edit_message_text(f"✅ Data {n} Masuk Database.")
            await context.bot.send_message(uid, f"🎊 Data `{n}` yang Anda kirim telah disetujui!")
    elif data == "v_rej":
        await q.edit_message_text("❌ Data Ditolak/Diabaikan.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Dibatalkan.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

if __name__ == '__main__':
    # post_init untuk Menu Command Otomatis
    app = ApplicationBuilder().token(token).post_init(post_init).build()
    
    # 1. REGISTRASI (Cancel Regex & Timeout)
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

    # 2. TAMBAH DATA (Cancel Regex & Timeout)
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

    # 3. COMMAND HANDLER UTAMA
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('stats', get_stats)) # FIX APPLIED HERE
    app.add_handler(CommandHandler('users', list_users))
    app.add_handler(CommandHandler('ban', ban_user))
    app.add_handler(CommandHandler('unban', unban_user))
    app.add_handler(CommandHandler('delete', delete_user))
    app.add_handler(CommandHandler('testgroup', test_group))
    app.add_handler(CommandHandler('panduan', panduan))

    # 4. UPLOAD & MESSAGE
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document_upload))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ ONEASPAL BOT ONLINE - FULL FEATURED v1.1")
    app.run_polling()