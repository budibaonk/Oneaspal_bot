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

# --- ⚠️ KONFIGURASI ID ---
ADMIN_ID = 7530512170          
LOG_GROUP_ID = -1003627047676  

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
    supabase.table('users').update({'status': status}).eq('user_id', user_id).execute()

def update_quota_usage(user_id, current_quota):
    new_quota = current_quota - 1
    supabase.table('users').update({'quota': new_quota}).eq('user_id', user_id).execute()

# ==============================================================================
#                        ADMIN: NOTIFIKASI GRUP RAPI
# ==============================================================================

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
    keyboard = [[InlineKeyboardButton("📞 Hubungi Penemu via WA", url=f"https://wa.me/{hp_wa}")]]
    try:
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text=report_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except: pass

# ==============================================================================
#                        ADMIN: UPLOAD & STATS (PRIVAT)
# ==============================================================================

async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID: return
    document = update.message.document
    file_name = document.file_name.lower()
    if not (file_name.endswith('.csv') or file_name.endswith('.xlsx') or file_name.endswith('.xls')):
        await update.message.reply_text("❌ Gunakan .csv atau .xlsx")
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
        df['nopol'] = df['nopol'].astype(str).str.replace(' ', '').str.upper()
        df = df.replace({np.nan: None})
        
        expected_cols = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch']
        valid_cols = df.columns.intersection(expected_cols)
        final_data = df[valid_cols].to_dict(orient='records')
        
        for i in range(0, len(final_data), 1000):
            batch = final_data[i : i + 1000]
            supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
        
        await context.bot.send_message(chat_id=user_id, text=f"✅ **UPLOAD BERHASIL!**\nData masuk ke database.")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")

async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return # Kunci Hanya Admin
    res_total = supabase.table('kendaraan').select("nopol", count="exact").execute()
    res_leasing = supabase.table('kendaraan').select("finance").execute()
    total_data = res_total.count if res_total.count else 0
    unique_leasing = len(set([d['finance'] for d in res_leasing.data if d['finance']]))
    await update.message.reply_text(f"📊 **STATISTIK ADMIN**\n📂 Total Data: `{total_data}`\n🏦 Total Leasing: `{unique_leasing}`", parse_mode='Markdown')

# ==============================================================================
#                        USER: REGISTRATION (REVISI FORM)
# ==============================================================================

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_user(update.effective_user.id): return await update.message.reply_text("✅ Terdaftar.")
    await update.message.reply_text("📝 **DAFTAR MITRA**\n1️⃣ **NAMA LENGKAP**:", parse_mode='Markdown')
    return R_NAMA

async def register_nama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['reg_nama'] = update.message.text
    await update.message.reply_text("2️⃣ **NO HP AKTIF**:")
    return R_HP

async def register_hp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['reg_hp'] = update.message.text
    await update.message.reply_text("3️⃣ **EMAIL**:")
    return R_EMAIL

async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['reg_email'] = update.message.text
    await update.message.reply_text("4️⃣ **KOTA/KAB TEMPAT TINGGAL**:")
    return R_KOTA

async def register_kota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['reg_kota'] = update.message.text
    await update.message.reply_text("5️⃣ **PT / AGENCY**:")
    return R_AGENCY

async def register_agency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['reg_agency'] = update.message.text
    summary = f"📋 **KONFIRMASI**\nNama: {context.user_data['reg_nama']}\nKota: {context.user_data['reg_kota']}\nAgency: {context.user_data['reg_agency']}"
    await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ ULANGI"]], one_time_keyboard=True, resize_keyboard=True))
    return R_CONFIRM

async def register_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ ULANGI": return ConversationHandler.END
    data = {"user_id": update.effective_user.id, "nama_lengkap": context.user_data['reg_nama'], "no_hp": context.user_data['reg_hp'], "email": context.user_data['reg_email'], "kota": context.user_data['reg_kota'], "agency": context.user_data['reg_agency'], "quota": 1000, "status": "pending"}
    supabase.table('users').insert(data).execute()
    await update.message.reply_text("✅ Terkirim! Menunggu aktivasi Admin.", reply_markup=ReplyKeyboardRemove())
    kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"appu_{data['user_id']}"), InlineKeyboardButton("❌ Reject", callback_data=f"reju_{data['user_id']}")]]
    await context.bot.send_message(ADMIN_ID, f"🔔 **PENDAFTAR BARU**\n{data['nama_lengkap']}", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

# ==============================================================================
#                     USER: TAMBAH DATA (FORMAT NOKIR)
# ==============================================================================

async def add_data_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user or user['status'] != 'active': return await update.message.reply_text("⛔ Tidak aktif.")
    await update.message.reply_text("➕ **KIRIM DATA UNIT**\n1️⃣ **Nopol** (Contoh: B123ABC):")
    return A_NOPOL

async def add_nopol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['add_nopol'] = update.message.text.upper().replace(" ", "")
    await update.message.reply_text("2️⃣ **Type Mobil**:")
    return A_TYPE

async def add_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['add_type'] = update.message.text
    await update.message.reply_text("3️⃣ **Leasing**:")
    return A_LEASING

async def add_leasing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['add_leasing'] = update.message.text
    await update.message.reply_text("4️⃣ **No Kiriman**:")
    return A_LEASING # Reuse state leasing for simplicity in logic

async def add_nokir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['add_nokir'] = update.message.text
    summary = f"📋 **DATA BARU**\nNopol: {context.user_data['add_nopol']}\nUnit: {context.user_data['add_type']}"
    await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM"]], one_time_keyboard=True))
    return A_CONFIRM

# ==============================================================================
#                        PENCARIAN (AUTO-FORMAT)
# ==============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    if not user or user['status'] != 'active': return
    
    kw = update.message.text.upper().replace(" ", "")
    await update.message.reply_text("⏳ *Mencari...*", parse_mode='Markdown')
    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.eq.{kw},noka.eq.{kw},nosin.eq.{kw}").execute()
        if res.data:
            d = res.data[0]
            update_quota_usage(uid, user['quota'])
            text = (f"✅ **DATA DITEMUKAN**\n━━━━━━━━━━━━━━━━━━\n🚙 **Unit:** {d.get('type','-')}\n🔢 **Nopol:** `{d.get('nopol','-')}`\n📅 **Tahun:** {d.get('tahun','-')}\n🎨 **Warna:** {d.get('warna','-')}\n----------------------------------\n🔧 **Noka:** `{d.get('noka','-')}`\n⚙️ **Nosin:** `{d.get('nosin','-')}`\n----------------------------------\n⚠️ **OVD:** {d.get('ovd', '-')}\n🏦 **Finance:** {d.get('finance', '-')}\n🏢 **Branch:** {d.get('branch', '-')}\n━━━━━━━━━━━━━━━━━━\n\n⚠️ *CATATAN PENTING:*\nIni bukan alat yang SAH untuk penarikan atau menyita aset kendaraan, Silahkan konfirmasi kepada PIC leasing terkait.\nTerima kasih.")
            await update.message.reply_text(text, parse_mode='Markdown')
            await notify_hit_to_group(context, user, d)
        else:
            await update.message.reply_text(f"❌ **DATA TIDAK ADA**\n`{kw}`\n\nKetik /tambah untuk kirim data ini.", parse_mode='Markdown')
    except: await update.message.reply_text("❌ Database Error")

# ==============================================================================
#                        CALLBACK & CORE HANDLERS
# ==============================================================================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    data = query.data
    if data.startswith("appu_"):
        uid = data.split("_")[1]; update_user_status(uid, 'active')
        await query.edit_message_text(f"✅ User {uid} AKTIF")
        await context.bot.send_message(uid, "🎉 **AKUN AKTIF!**")
    elif data.startswith("v_acc_"):
        _, _, nopol, uid = data.split("_"); item = context.bot_data.get(f"prop_{nopol}")
        if item:
            supabase.table('kendaraan').upsert(item).execute()
            await query.edit_message_text(f"✅ Data {nopol} Masuk.")
            await context.bot.send_message(uid, f"🎊 Data `{nopol}` disetujui Admin!")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

if __name__ == '__main__':
    app = ApplicationBuilder().token(token).build()
    
    # Conv Registrasi
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('register', register_start)], states={R_NAMA:[MessageHandler(filters.TEXT, register_nama)], R_HP:[MessageHandler(filters.TEXT, register_hp)], R_EMAIL:[MessageHandler(filters.TEXT, register_email)], R_KOTA:[MessageHandler(filters.TEXT, register_kota)], R_AGENCY:[MessageHandler(filters.TEXT, register_agency)], R_CONFIRM:[MessageHandler(filters.TEXT, register_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    
    # Conv Tambah Data User
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('tambah', add_data_start)], states={A_NOPOL:[MessageHandler(filters.TEXT, add_nopol)], A_TYPE:[MessageHandler(filters.TEXT, add_type)], A_LEASING:[MessageHandler(filters.TEXT, add_leasing)], A_NOKIR:[MessageHandler(filters.TEXT, add_nokir)], A_CONFIRM:[MessageHandler(filters.TEXT, add_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))

    app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('panduan', lambda u, c: u.message.reply_text("📖 Ketik Nopol tanpa spasi atau /tambah data.")))
    app.add_handler(CommandHandler('testgroup', lambda u, c: u.message.reply_text("✅ OK") if u.effective_user.id == ADMIN_ID else None))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.Document.ALL & filters.Chat(ADMIN_ID), handle_document_upload))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ ONEASPAL BOT ONLINE...")
    app.run_polling()