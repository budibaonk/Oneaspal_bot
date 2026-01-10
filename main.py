import os
import logging
import pandas as pd
import io
import numpy as np
import time
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
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

# --- ⚠️ KONFIGURASI ID ---
ADMIN_ID = 7530512170          
LOG_GROUP_ID = -1003627047676  

# Cek Koneksi
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
#                        ADMIN: UPLOAD FILE (DETAIL)
# ==============================================================================

async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID: return
    
    document = update.message.document
    file_name = document.file_name
    
    status_msg = await update.message.reply_text("⏳ **Menganalisa file...**")
    start_time = time.time()

    try:
        new_file = await document.get_file()
        file_content = await new_file.download_as_bytearray()
        
        # Deteksi Format CSV/Excel
        if file_name.lower().endswith('.csv'):
            try:
                df = pd.read_csv(io.BytesIO(file_content), sep=';', dtype=str)
                if len(df.columns) <= 1: df = pd.read_csv(io.BytesIO(file_content), sep=',', dtype=str)
            except: df = pd.read_csv(io.BytesIO(file_content), sep=None, engine='python', dtype=str)
        else:
            df = pd.read_excel(io.BytesIO(file_content), dtype=str)
        
        # Normalisasi Header & Data
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        df['nopol'] = df['nopol'].astype(str).str.replace(' ', '').str.upper()
        df = df.replace({np.nan: None})
        
        # Filter Kolom Valid
        valid_cols = df.columns.intersection(['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch'])
        final_data = df[valid_cols].to_dict(orient='records')
        
        total_rows = len(final_data)
        success_count = 0
        fail_count = 0

        await status_msg.edit_text(f"📥 **Sedang memproses {total_rows} data...**")

        # Batch Upload (Supabase Limit)
        BATCH_SIZE = 1000
        for i in range(0, total_rows, BATCH_SIZE):
            batch = final_data[i : i + BATCH_SIZE]
            try:
                supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
                success_count += len(batch)
            except Exception as e:
                logging.error(f"Batch Error: {e}")
                fail_count += len(batch)

        duration = round(time.time() - start_time, 2)
        
        # Laporan Detail
        report = (
            f"✅ **DATABASE BERHASIL DIPERBARUI**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📄 **File:** `{file_name}`\n"
            f"📊 **Total:** {total_rows}\n"
            f"✅ **Sukses:** {success_count}\n"
            f"❌ **Gagal:** {fail_count}\n"
            f"⏱ **Waktu:** {duration} detik\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📅 _Update: {datetime.now().strftime('%d/%m/%Y %H:%M')}_"
        )
        await status_msg.edit_text(report, parse_mode='Markdown')

    except Exception as e:
        await status_msg.edit_text(f"❌ **UPLOAD GAGAL:** {str(e)}")

# ==============================================================================
#                        ADMIN: MANAJEMEN USER & STATS
# ==============================================================================

async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        res_total = supabase.table('kendaraan').select("nopol", count="exact").execute()
        res_leasing = supabase.table('kendaraan').select("finance").execute()
        total = res_total.count if res_total.count else 0
        leasings = len(set([d['finance'] for d in res_leasing.data if d['finance']]))
        await update.message.reply_text(f"📊 **STATISTIK ADMIN**\n📂 Total Data: `{total}`\n🏦 Leasing: `{leasings}`", parse_mode='Markdown')
    except Exception as e: await update.message.reply_text(f"Error: {e}")

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
    except: await update.message.reply_text("Gagal mengambil data.")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        update_user_status(uid, 'rejected')
        await update.message.reply_text(f"⛔ User `{uid}` berhasil di-BANNED.")
    except: await update.message.reply_text("⚠️ Format salah. Gunakan: `/ban ID_USER`")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        update_user_status(uid, 'active')
        await update.message.reply_text(f"✅ User `{uid}` berhasil di-UNBAN.")
    except: await update.message.reply_text("⚠️ Format salah. Gunakan: `/unban ID_USER`")

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        supabase.table('users').delete().eq('user_id', uid).execute()
        await update.message.reply_text(f"🗑️ User `{uid}` DIHAPUS PERMANEN.")
    except: await update.message.reply_text("⚠️ Format salah. Gunakan: `/delete ID_USER`")

async def test_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text="🔔 **TES NOTIFIKASI SUKSES!**", parse_mode='Markdown')
        await update.message.reply_text("✅ Pesan terkirim ke Group Log.")
    except: await update.message.reply_text("❌ Gagal kirim ke grup. Cek ID Group.")

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
#                        USER: REGISTRASI (FORMULIR LENGKAP)
# ==============================================================================

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_user(update.effective_user.id): return await update.message.reply_text("✅ Anda sudah terdaftar.")
    await update.message.reply_text("📝 **PENDAFTARAN MITRA**\n\n1️⃣ Masukkan **NAMA LENGKAP**:")
    return R_NAMA

async def register_nama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['r_nama'] = update.message.text
    await update.message.reply_text("2️⃣ Masukkan **NO HP (WA)**:")
    return R_HP

async def register_hp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['r_hp'] = update.message.text
    await update.message.reply_text("3️⃣ Masukkan **EMAIL**:")
    return R_EMAIL

async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['r_email'] = update.message.text
    await update.message.reply_text("4️⃣ Masukkan **KOTA DOMISILI**:")
    return R_KOTA

async def register_kota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['r_kota'] = update.message.text
    await update.message.reply_text("5️⃣ Masukkan **PT / AGENCY**:")
    return R_AGENCY

async def register_agency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['r_agency'] = update.message.text
    summary = (f"📋 **KONFIRMASI DATA**\nNama: {context.user_data['r_nama']}\n"
               f"HP: {context.user_data['r_hp']}\nKota: {context.user_data['r_kota']}\nAgency: {context.user_data['r_agency']}")
    await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ ULANGI"]], one_time_keyboard=True))
    return R_CONFIRM

async def register_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ ULANGI": return ConversationHandler.END
    data = {
        "user_id": update.effective_user.id,
        "nama_lengkap": context.user_data['r_nama'],
        "no_hp": context.user_data['r_hp'],
        "email": context.user_data['r_email'],
        "kota": context.user_data['r_kota'],
        "agency": context.user_data['r_agency'],
        "quota": 1000, "status": "pending"
    }
    supabase.table('users').insert(data).execute()
    await update.message.reply_text("✅ Data Terkirim! Mohon tunggu verifikasi Admin.", reply_markup=ReplyKeyboardRemove())
    
    # Notif ke Admin
    kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"appu_{data['user_id']}"), InlineKeyboardButton("❌ Reject", callback_data=f"reju_{data['user_id']}")]]
    await context.bot.send_message(ADMIN_ID, f"🔔 **PENDAFTAR BARU**\n{data['nama_lengkap']} ({data['agency']})", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

# ==============================================================================
#                     USER: TAMBAH DATA (CROWDSOURCING)
# ==============================================================================

async def add_data_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return await update.message.reply_text("⛔ Akses ditolak.")
    await update.message.reply_text("➕ **TAMBAH UNIT BARU**\n\n1️⃣ Masukkan **Nopol**:")
    return A_NOPOL

async def add_nopol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['a_nopol'] = update.message.text.upper().replace(" ", "")
    await update.message.reply_text("2️⃣ Masukkan **Type Mobil**:")
    return A_TYPE

async def add_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['a_type'] = update.message.text
    await update.message.reply_text("3️⃣ Masukkan **Leasing**:")
    return A_LEASING

async def add_leasing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['a_leasing'] = update.message.text
    await update.message.reply_text("4️⃣ Masukkan **No Kiriman**:")
    return A_NOKIR

async def add_nokir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['a_nokir'] = update.message.text
    summary = f"📋 **KONFIRMASI UNIT**\nNopol: {context.user_data['a_nopol']}\nUnit: {context.user_data['a_type']}"
    await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM KE ADMIN"]], one_time_keyboard=True))
    return A_CONFIRM

async def add_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    n = context.user_data['a_nopol']
    context.bot_data[f"prop_{n}"] = {
        "nopol": n, "type": context.user_data['a_type'], 
        "finance": context.user_data['a_leasing'], "ovd": f"Kiriman: {context.user_data['a_nokir']}"
    }
    await update.message.reply_text("✅ Terkirim! Menunggu persetujuan Admin.", reply_markup=ReplyKeyboardRemove())
    
    # Notif ke Admin
    kb = [[InlineKeyboardButton("✅ Terima Data", callback_data=f"v_acc_{n}_{update.effective_user.id}"), InlineKeyboardButton("❌ Tolak", callback_data="v_rej")]]
    await context.bot.send_message(ADMIN_ID, f"📥 **USULAN DATA BARU**\nNopol: {n}\nUnit: {context.user_data['a_type']}", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

# ==============================================================================
#                        HANDLER UTAMA & START MESSAGE
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
    await update.message.reply_text("⏳ *Mencari data...*", parse_mode='Markdown')
    
    # SEARCH MULTI-FIELD (NOPOL, NOKA, NOSIN)
    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.eq.{kw},noka.eq.{kw},nosin.eq.{kw}").execute()
        if res.data:
            d = res.data[0]
            update_quota_usage(u['user_id'], u['quota'])
            
            # FORMAT TAMPILAN PREMIUM
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
    except Exception as e:
        await update.message.reply_text("❌ Terjadi kesalahan database.")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    data = q.data
    
    # APPROVE USER
    if data.startswith("appu_"):
        uid = data.split("_")[1]; update_user_status(uid, 'active')
        await q.edit_message_text(f"✅ User {uid} DISETUJUI.")
        await context.bot.send_message(uid, "🎉 **AKUN ANDA TELAH AKTIF!**\nSilakan mulai mencari data.")
    
    # REJECT USER
    elif data.startswith("reju_"):
        uid = data.split("_")[1]; update_user_status(uid, 'rejected')
        await q.edit_message_text(f"⛔ User {uid} DITOLAK.")
        await context.bot.send_message(uid, "⛔ Pendaftaran Anda ditolak Admin.")

    # APPROVE DATA
    elif data.startswith("v_acc_"):
        _, _, n, uid = data.split("_"); item = context.bot_data.get(f"prop_{n}")
        if item:
            supabase.table('kendaraan').upsert(item).execute()
            await q.edit_message_text(f"✅ Data {n} Masuk Database.")
            await context.bot.send_message(uid, f"🎊 Data `{n}` yang Anda kirim telah disetujui!")
    
    # REJECT DATA
    elif data == "v_rej":
        await q.edit_message_text("❌ Data Ditolak/Diabaikan.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Dibatalkan.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

if __name__ == '__main__':
    app = ApplicationBuilder().token(token).build()
    
    # 1. HANDLER REGISTRASI
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

    # 2. HANDLER TAMBAH DATA
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('tambah', add_data_start)],
        states={
            A_NOPOL:[MessageHandler(filters.TEXT, add_nopol)],
            A_TYPE:[MessageHandler(filters.TEXT, add_type)],
            A_LEASING:[MessageHandler(filters.TEXT, add_leasing)],
            A_NOKIR:[MessageHandler(filters.TEXT, add_nokir)],
            A_CONFIRM:[MessageHandler(filters.TEXT, add_confirm)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    ))

    # 3. COMMAND HANDLERS
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('users', list_users)) # Telah dikembalikan
    app.add_handler(CommandHandler('ban', ban_user))     # Telah dikembalikan
    app.add_handler(CommandHandler('unban', unban_user)) # Telah dikembalikan
    app.add_handler(CommandHandler('delete', delete_user)) # Telah dikembalikan
    app.add_handler(CommandHandler('testgroup', test_group))
    app.add_handler(CommandHandler('panduan', lambda u,c: u.message.reply_text("📖 Ketik Nopol tanpa spasi.")))

    # 4. MESSAGE & CALLBACK
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.Document.ALL & filters.Chat(ADMIN_ID), handle_document_upload))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ ONEASPAL BOT ONLINE - FULL FEATURED")
    app.run_polling()