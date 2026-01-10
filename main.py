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

# --- KONFIGURASI ---
load_dotenv()
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
token: str = os.environ.get("TELEGRAM_TOKEN")

# ⚠️ PASTIKAN ID INI BENAR
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

# --- STATE ---
NAMA, NO_HP, NIK, ALAMAT, EMAIL, AGENCY, CONFIRM = range(7)

# --- HELPER ---
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
    return new_quota

# --- FUNGSI UPLOAD DATABASE (AUTO DETECT SEMICOLON) ---
async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Access Denied.")
        return

    document = update.message.document
    file_name = document.file_name.lower()

    if not (file_name.endswith('.csv') or file_name.endswith('.xlsx') or file_name.endswith('.xls')):
        await update.message.reply_text("❌ Format harus .csv atau .xlsx")
        return

    status_msg = await update.message.reply_text("⏳ **Menganalisa File...**")

    try:
        new_file = await document.get_file()
        file_content = await new_file.download_as_bytearray()
        
        # 1. BACA FILE (Coba Titik Koma Dulu -> Lalu Koma)
        if file_name.endswith('.csv'):
            try:
                # Paksa baca semua sebagai string (dtype=str) agar NIK/HP tidak error
                df = pd.read_csv(io.BytesIO(file_content), sep=';', dtype=str)
                if len(df.columns) <= 1: 
                    df = pd.read_csv(io.BytesIO(file_content), sep=',', dtype=str)
            except:
                df = pd.read_csv(io.BytesIO(file_content), sep=None, engine='python', dtype=str)
        else:
            df = pd.read_excel(io.BytesIO(file_content), dtype=str)

        # 2. BERSIHKAN HEADER
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        
        # Kirim Laporan Kolom ke Admin (Untuk Debugging)
        await context.bot.send_message(chat_id=user_id, text=f"🔍 **Kolom Terbaca:**\n`{str(df.columns.tolist())}`", parse_mode='Markdown')

        if 'nopol' not in df.columns:
            # Coba cari alternatif
            possible = [c for c in df.columns if 'no' in c and 'pol' in c]
            if possible: df.rename(columns={possible[0]: 'nopol'}, inplace=True)
            else:
                await status_msg.edit_text(f"❌ **ERROR:** Kolom 'nopol' tidak ditemukan.")
                return

        # 3. BERSIHKAN DATA
        # Bersihkan Nopol (Hapus spasi, titik koma, jadikan uppercase)
        df['nopol'] = df['nopol'].astype(str).str.replace(' ', '').str.replace(';', '').str.upper()
        
        # Ubah NaN menjadi None (agar Supabase tidak menolak)
        df = df.replace({np.nan: None, 'nan': None, 'NaN': None})
        
        # Hapus baris sampah (Nopol terlalu pendek)
        df = df[df['nopol'].str.len() > 2] 

        # Filter hanya kolom yang sesuai database
        expected_cols = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch']
        valid_cols = df.columns.intersection(expected_cols)
        final_data = df[valid_cols].to_dict(orient='records')
        
        total_rows = len(final_data)
        if total_rows == 0:
            await status_msg.edit_text("❌ Data kosong setelah diproses.")
            return

        await status_msg.edit_text(f"📥 **Mengupload {total_rows} data...**")

        # 4. UPLOAD BATCH
        BATCH_SIZE = 1000
        success_count = 0
        first_error = None
        
        for i in range(0, total_rows, BATCH_SIZE):
            batch = final_data[i : i + BATCH_SIZE]
            try:
                # Upsert (Update jika ada, Insert jika baru)
                supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
                success_count += len(batch)
            except Exception as e:
                logging.error(f"Error batch {i}: {e}")
                if not first_error: first_error = str(e)
        
        if success_count == 0:
            err_text = f"❌ **GAGAL TOTAL**\nError: `{first_error}`\n\n👉 **SOLUSI:** Pastikan sudah menjalankan SQL 'ALTER TABLE...UNIQUE' di Supabase."
            await context.bot.send_message(chat_id=user_id, text=err_text, parse_mode='Markdown')
            await status_msg.delete()
        else:
            await context.bot.send_message(chat_id=user_id, text=f"✅ **SUKSES!**\nTotal Data Masuk: {success_count} dari {total_rows}", parse_mode='Markdown')
            await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ **SYSTEM ERROR:** {str(e)}")

# --- FUNGSI LAINNYA ---
async def test_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text="🔔 **TES NOTIFIKASI**", parse_mode='Markdown')
        await update.message.reply_text("✅ OK")
    except Exception as e: await update.message.reply_text(f"❌ {e}")

async def notify_hit_to_group(context: ContextTypes.DEFAULT_TYPE, user_data, vehicle_data):
    hp = user_data.get('no_hp', '-')
    hp_wa = '62' + hp[1:] if hp.startswith('0') else hp
    text = (f"🚨 **UNIT DITEMUKAN!**\n👤 {user_data.get('nama_lengkap')} ({user_data.get('agency')})\n🚙 {vehicle_data.get('type')}\n"
            f"🔢 `{vehicle_data.get('nopol')}`\n🏦 {vehicle_data.get('finance')}")
    kb = [[InlineKeyboardButton("📞 WA", url=f"https://wa.me/{hp_wa}")]]
    try: await context.bot.send_message(chat_id=LOG_GROUP_ID, text=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    except: pass

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    res = supabase.table('users').select("*").limit(20).execute()
    msg = "\n".join([f"`{u['user_id']}` {u.get('nama_lengkap')}" for u in res.data])
    await update.message.reply_text(f"📋 Users:\n{msg}" if msg else "Kosong", parse_mode='Markdown')

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    update_user_status(context.args[0], 'rejected')
    await update.message.reply_text("⛔ Banned")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    update_user_status(context.args[0], 'active')
    await update.message.reply_text("✅ Active")

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    supabase.table('users').delete().eq('user_id', context.args[0]).execute()
    await update.message.reply_text("🗑️ Deleted")

# --- REGISTER ---
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_user(update.effective_user.id): return await update.message.reply_text("Sudah terdaftar.")
    await update.message.reply_text("1️⃣ **NAMA LENGKAP**:", parse_mode='Markdown')
    return NAMA

async def register_nama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nama'] = update.message.text
    await update.message.reply_text("2️⃣ **NO HP**:")
    return NO_HP

async def register_hp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['no_hp'] = update.message.text
    await update.message.reply_text("3️⃣ **NIK**:")
    return NIK

async def register_nik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nik'] = update.message.text
    await update.message.reply_text("4️⃣ **ALAMAT**:")
    return ALAMAT

async def register_alamat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['alamat'] = update.message.text
    await update.message.reply_text("5️⃣ **EMAIL**:")
    return EMAIL

async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['email'] = update.message.text
    await update.message.reply_text("6️⃣ **AGENCY**:")
    return AGENCY

async def register_agency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['agency'] = update.message.text
    await update.message.reply_text("Ketik **OK** untuk kirim.", reply_markup=ReplyKeyboardMarkup([["OK"]], one_time_keyboard=True))
    return CONFIRM

async def register_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = {
        "user_id": update.effective_user.id,
        "nama_lengkap": context.user_data['nama'],
        "no_hp": context.user_data['no_hp'],
        "nik": context.user_data['nik'],
        "alamat": context.user_data['alamat'],
        "email": context.user_data['email'],
        "agency": context.user_data['agency'],
        "quota": 1000, "status": "pending"
    }
    supabase.table('users').insert(data).execute()
    await update.message.reply_text("✅ Terkirim. Tunggu Admin.", reply_markup=ReplyKeyboardRemove())
    kb = [[InlineKeyboardButton("✅", callback_data=f"approve_{data['user_id']}"), InlineKeyboardButton("❌", callback_data=f"reject_{data['user_id']}")]]
    await context.bot.send_message(ADMIN_ID, f"🔔 NEW: {data['nama_lengkap']}", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Batal", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if update.effective_user.id != ADMIN_ID: return
    act, uid = query.data.split("_")
    update_user_status(uid, 'active' if act == "approve" else 'rejected')
    await query.edit_message_text(f"{act.upper()} {uid}")
    try: await context.bot.send_message(uid, "✅ AKUN AKTIF" if act == "approve" else "⛔ DITOLAK")
    except: pass

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    if not user or user['status'] != 'active': return await update.message.reply_text("⛔ Akses Ditolak")
    if user['quota'] <= 0: return await update.message.reply_text("⚠️ Kuota Habis")

    await update.message.reply_text("⏳ ...")
    kw = update.message.text.replace(" ", "").upper()
    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.eq.{kw},noka.eq.{kw},nosin.eq.{kw}").execute()
        if res.data:
            d = res.data[0]
            update_quota_usage(uid, user['quota'])
            msg = f"✅ **DITEMUKAN**\n🚙 {d.get('type')}\n🔢 `{d.get('nopol')}`\n🏦 {d.get('finance')}\n⚠️ {d.get('ovd')}"
            await update.message.reply_text(msg, parse_mode='Markdown')
            await notify_hit_to_group(context, user, d)
        else:
            await update.message.reply_text("❌ Tidak Ditemukan")
    except: await update.message.reply_text("❌ Database Error")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Matel Bot")

if __name__ == '__main__':
    app = ApplicationBuilder().token(token).build()
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('register', register_start)],
        states={NAMA:[MessageHandler(filters.TEXT, register_nama)], NO_HP:[MessageHandler(filters.TEXT, register_hp)],
                NIK:[MessageHandler(filters.TEXT, register_nik)], ALAMAT:[MessageHandler(filters.TEXT, register_alamat)],
                EMAIL:[MessageHandler(filters.TEXT, register_email)], AGENCY:[MessageHandler(filters.TEXT, register_agency)],
                CONFIRM:[MessageHandler(filters.TEXT, register_confirm)]},
        fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('users', list_users))
    app.add_handler(CommandHandler('ban', ban_user))
    app.add_handler(CommandHandler('unban', unban_user))
    app.add_handler(CommandHandler('delete', delete_user))
    app.add_handler(CommandHandler('testgroup', test_group))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL & filters.Chat(ADMIN_ID), handle_document_upload))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print(f"✅ Bot Ready. Admin: {ADMIN_ID}")
    app.run_polling()