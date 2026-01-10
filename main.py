import os
import logging
import pandas as pd
import io
import numpy as np
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

# --- ⚠️ KONFIGURASI ID (Super Admin & Log Grup) ---
ADMIN_ID = 7530512170          
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
# Registrasi
R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_CONFIRM = range(6)
# Tambah Data User
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
    supabase.table('users').update({'status': status}).eq('user_id', user_id).execute()

def update_quota_usage(user_id, current_quota):
    new_quota = current_quota - 1
    supabase.table('users').update({'quota': new_quota}).eq('user_id', user_id).execute()

# ==============================================================================
#                        ADMIN: UPLOAD & STATS
# ==============================================================================

async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID: return

    document = update.message.document
    file_name = document.file_name.lower()
    if not (file_name.endswith('.csv') or file_name.endswith('.xlsx') or file_name.endswith('.xls')):
        await update.message.reply_text("❌ Format salah. Gunakan .csv atau .xlsx")
        return

    status_msg = await update.message.reply_text("⏳ **Menganalisa file...**")
    try:
        new_file = await document.get_file()
        file_content = await new_file.download_as_bytearray()
        
        if file_name.endswith('.csv'):
            try:
                df = pd.read_csv(io.BytesIO(file_content), sep=';', dtype=str)
                if len(df.columns) <= 1: df = pd.read_csv(io.BytesIO(file_content), sep=',', dtype=str)
            except: df = pd.read_csv(io.BytesIO(file_content), sep=None, engine='python', dtype=str)
        else:
            df = pd.read_excel(io.BytesIO(file_content), dtype=str)

        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        if 'nopol' not in df.columns:
            await status_msg.edit_text("❌ Kolom 'nopol' tidak ditemukan.")
            return

        df['nopol'] = df['nopol'].astype(str).str.replace(' ', '').str.upper()
        df = df.replace({np.nan: None})
        
        expected_cols = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch']
        valid_cols = df.columns.intersection(expected_cols)
        final_data = df[valid_cols].to_dict(orient='records')
        
        BATCH_SIZE = 1000
        success_count = 0
        for i in range(0, len(final_data), BATCH_SIZE):
            batch = final_data[i : i + BATCH_SIZE]
            supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
            success_count += len(batch)
            
        await context.bot.send_message(chat_id=user_id, text=f"✅ **UPLOAD BERHASIL!**\nTotal: {success_count} data masuk.")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")

async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hanya Admin yang bisa melihat total data"""
    if update.effective_user.id != ADMIN_ID:
        return # User biasa tidak mendapat respon apapun atau bisa diberi pesan 'Akses Ditolak'

    res_total = supabase.table('kendaraan').select("nopol", count="exact").execute()
    res_leasing = supabase.table('kendaraan').select("finance").execute()
    
    total_data = res_total.count if res_total.count else 0
    unique_leasing = len(set([d['finance'] for d in res_leasing.data if d['finance']]))
    
    await update.message.reply_text(
        f"📊 **STATISTIK ADMIN**\n━━━━━━━━━━━━━━━━━━\n"
        f"📂 Total Data Kendaraan: `{total_data}`\n"
        f"🏦 Total Leasing Terdaftar: `{unique_leasing}`\n"
        f"━━━━━━━━━━━━━━━━━━", parse_mode='Markdown'
    )

# ==============================================================================
#                        USER: REGISTRATION (REVISI)
# ==============================================================================

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_user(update.effective_user.id):
        return await update.message.reply_text("✅ Anda sudah terdaftar.")
    await update.message.reply_text("📝 **FORMULIR PENDAFTARAN**\n\n1️⃣ Masukkan **NAMA LENGKAP**:", parse_mode='Markdown')
    return R_NAMA

async def register_nama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['reg_nama'] = update.message.text
    await update.message.reply_text("2️⃣ Masukkan **NO HP AKTIF**:")
    return R_HP

async def register_hp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['reg_hp'] = update.message.text
    await update.message.reply_text("3️⃣ Masukkan **EMAIL**:")
    return R_EMAIL

async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['reg_email'] = update.message.text
    await update.message.reply_text("4️⃣ Masukkan **KOTA/KAB TEMPAT TINGGAL**:")
    return R_KOTA

async def register_kota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['reg_kota'] = update.message.text
    await update.message.reply_text("5️⃣ Masukkan **PT / AGENCY**:")
    return R_AGENCY

async def register_agency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['reg_agency'] = update.message.text
    summary = (f"📋 **KONFIRMASI PENDAFTARAN**\n\n"
               f"Nama: {context.user_data['reg_nama']}\nHP: {context.user_data['reg_hp']}\n"
               f"Email: {context.user_data['reg_email']}\nKota: {context.user_data['reg_kota']}\n"
               f"Agency: {context.user_data['reg_agency']}")
    kb = [["✅ KIRIM", "❌ ULANGI"]]
    await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return R_CONFIRM

async def register_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ ULANGI":
        await update.message.reply_text("🔄 Silakan ulangi /register")
        return ConversationHandler.END
    
    data = {
        "user_id": update.effective_user.id,
        "nama_lengkap": context.user_data['reg_nama'],
        "no_hp": context.user_data['reg_hp'],
        "email": context.user_data['reg_email'],
        "kota": context.user_data['reg_kota'],
        "agency": context.user_data['reg_agency'],
        "quota": 1000, "status": "pending"
    }
    supabase.table('users').insert(data).execute()
    await update.message.reply_text("✅ Terkirim! Mohon tunggu aktivasi dari Admin.", reply_markup=ReplyKeyboardRemove())
    
    kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"appu_{data['user_id']}"), 
           InlineKeyboardButton("❌ Reject", callback_data=f"reju_{data['user_id']}")]]
    await context.bot.send_message(ADMIN_ID, f"🔔 **PENDAFTAR BARU**\n{data['nama_lengkap']} ({data['agency']})", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

# ==============================================================================
#                     USER: TAMBAH DATA (CROWDSOURCING)
# ==============================================================================

async def add_data_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user or user['status'] != 'active': return await update.message.reply_text("⛔ Akun belum aktif.")
    await update.message.reply_text("➕ **KIRIM DATA UNIT**\n\n1️⃣ Masukkan **Nomor Polisi** (Contoh: B1234ABC):")
    return A_NOPOL

async def add_nopol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # AUTO FORMAT: Huruf besar & Tanpa Spasi
    context.user_data['add_nopol'] = update.message.text.upper().replace(" ", "")
    await update.message.reply_text("2️⃣ Masukkan **Type Mobil**:")
    return A_TYPE

async def add_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['add_type'] = update.message.text
    await update.message.reply_text("3️⃣ Masukkan **Nama Leasing**:")
    return A_LEASING

async def add_leasing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['add_leasing'] = update.message.text
    await update.message.reply_text("4️⃣ Masukkan **No Kiriman**:")
    return A_NOKIR

async def add_nokir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['add_nokir'] = update.message.text
    summary = (f"📋 **KONFIRMASI DATA BARU**\n\n"
               f"Nopol: {context.user_data['add_nopol']}\n"
               f"Type: {context.user_data['add_type']}\n"
               f"Leasing: {context.user_data['add_leasing']}\n"
               f"No Kiriman: {context.user_data['add_nokir']}")
    await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM KE ADMIN"]], one_time_keyboard=True, resize_keyboard=True))
    return A_CONFIRM

async def add_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nopol = context.user_data['add_nopol']
    uid = update.effective_user.id
    # Simpan ke memori bot untuk approval
    context.bot_data[f"prop_{nopol}"] = {
        "nopol": nopol, "type": context.user_data['add_type'], 
        "finance": context.user_data['add_leasing'], "ovd": f"Kiriman: {context.user_data['add_nokir']}"
    }
    
    await update.message.reply_text("✅ Berhasil! Data Anda sedang ditinjau Admin.", reply_markup=ReplyKeyboardRemove())
    
    kb = [[InlineKeyboardButton("✅ Terima Data", callback_data=f"v_acc_{nopol}_{uid}"), 
           InlineKeyboardButton("❌ Tolak", callback_data="v_rej")]]
    await context.bot.send_message(ADMIN_ID, f"📥 **USULAN DATA BARU**\nNopol: {nopol}\nUnit: {context.user_data['add_type']}\nOleh: {uid}", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

# ==============================================================================
#                        HANDLER UTAMA & PENCARIAN
# ==============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    if not user or user['status'] != 'active': return
    
    # AUTO FORMAT PENCARIAN
    kw = update.message.text.upper().replace(" ", "")
    
    await update.message.reply_text("⏳ *Mencari...*", parse_mode='Markdown')
    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.eq.{kw},noka.eq.{kw},nosin.eq.{kw}").execute()
        if res.data:
            d = res.data[0]
            update_quota_usage(uid, user['quota'])
            text = (f"✅ **DATA DITEMUKAN**\n━━━━━━━━━━━━━━━━━━\n"
                    f"🚙 **Unit:** {d.get('type','-')}\n🔢 **Nopol:** `{d.get('nopol','-')}`\n"
                    f"📅 **Tahun:** {d.get('tahun','-')}\n🎨 **Warna:** {d.get('warna','-')}\n"
                    f"----------------------------------\n🔧 **Noka:** `{d.get('noka','-')}`\n"
                    f"⚙️ **Nosin:** `{d.get('nosin','-')}`\n----------------------------------\n"
                    f"⚠️ **OVD:** {d.get('ovd', '-')}\n🏦 **Finance:** {d.get('finance', '-')}\n"
                    f"🏢 **Branch:** {d.get('branch', '-')}\n━━━━━━━━━━━━━━━━━━\n\n"
                    f"⚠️ *CATATAN PENTING:*\nIni bukan alat yang SAH untuk penarikan. Silakan konfirmasi ke PIC leasing terkait.\nTerima kasih.")
            await update.message.reply_text(text, parse_mode='Markdown')
            
            # Notif HIT ke Grup
            hp_wa = '62' + user['no_hp'][1:] if user['no_hp'].startswith('0') else user['no_hp']
            report = f"🚨 **HIT!**\n👤 {user['nama_lengkap']} ({user['agency']})\n🔢 `{d['nopol']}`\n🏦 {d['finance']}"
            kb = [[InlineKeyboardButton("📞 WhatsApp Penemu", url=f"https://wa.me/{hp_wa}")]]
            await context.bot.send_message(LOG_GROUP_ID, report, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ **DATA TIDAK ADA**\n`{kw}`\n\nIngin membantu? Ketik /tambah untuk kirim data ini.", parse_mode='Markdown')
    except: await update.message.reply_text("❌ Database Error")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    data = query.data
    
    if data.startswith("appu_"):
        uid = data.split("_")[1]
        update_user_status(uid, 'active')
        await query.edit_message_text(f"✅ User {uid} AKTIF")
        await context.bot.send_message(uid, "🎉 **AKUN AKTIF!**\nSilakan gunakan bot. Ketik /panduan")
        
    elif data.startswith("v_acc_"):
        _, _, nopol, uid = data.split("_")
        item = context.bot_data.get(f"prop_{nopol}")
        if item:
            supabase.table('kendaraan').upsert(item).execute()
            await query.edit_message_text(f"✅ Data {nopol} masuk database.")
            await context.bot.send_message(uid, f"🎊 Data `{nopol}` Anda telah disetujui Admin!")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Batal.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 **ONEASPAL BOT**\nKetik /register untuk mendaftar.")

async def manual_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ("📖 **PANDUAN PENGGUNA**\n\n"
            "• **Cari Data:** Ketik Nopol tanpa spasi (Contoh: B123ABC).\n"
            "• **Tambah Data:** Ketik /tambah jika menemukan unit baru.\n"
            "• **Batal:** Ketik /cancel jika ingin membatalkan formulir.")
    await update.message.reply_text(text, parse_mode='Markdown')

if __name__ == '__main__':
    app = ApplicationBuilder().token(token).build()
    
    # Conv Registrasi
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('register', register_start)],
        states={R_NAMA:[MessageHandler(filters.TEXT, register_nama)], R_HP:[MessageHandler(filters.TEXT, register_hp)],
                R_EMAIL:[MessageHandler(filters.TEXT, register_email)], R_KOTA:[MessageHandler(filters.TEXT, register_kota)],
                R_AGENCY:[MessageHandler(filters.TEXT, register_agency)], R_CONFIRM:[MessageHandler(filters.TEXT, register_confirm)]},
        fallbacks=[CommandHandler('cancel', cancel)]))

    # Conv Tambah Data User
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('tambah', add_data_start)],
        states={A_NOPOL:[MessageHandler(filters.TEXT, add_nopol)], A_TYPE:[MessageHandler(filters.TEXT, add_type)],
                A_LEASING:[MessageHandler(filters.TEXT, add_leasing)], A_NOKIR:[MessageHandler(filters.TEXT, add_nokir)],
                A_CONFIRM:[MessageHandler(filters.TEXT, add_confirm)]},
        fallbacks=[CommandHandler('cancel', cancel)]))

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('panduan', manual_book))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.Document.ALL & filters.Chat(ADMIN_ID), handle_document_upload))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ Oneaspal_bot Online...")
    app.run_polling()