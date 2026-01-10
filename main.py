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
    print("❌ ERROR: Cek file .env Anda. Pastikan Token & Key sudah benar.")
    exit()

try:
    supabase: Client = create_client(url, key)
except Exception as e:
    print(f"❌ Gagal koneksi Supabase: {e}")
    exit()

# --- STATE FORMULIR REGISTRASI ---
NAMA, NO_HP, NIK, ALAMAT, EMAIL, AGENCY, CONFIRM = range(7)

# ==============================================================================
#                             DATABASE HELPERS
# ==============================================================================

def get_user(user_id):
    try:
        response = supabase.table('users').select("*").eq('user_id', user_id).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logging.error(f"Error get_user: {e}")
        return None

def update_user_status(user_id, status):
    try:
        supabase.table('users').update({'status': status}).eq('user_id', user_id).execute()
    except Exception as e:
        logging.error(f"Error update_status: {e}")

def update_quota_usage(user_id, current_quota):
    try:
        new_quota = current_quota - 1
        supabase.table('users').update({'quota': new_quota}).eq('user_id', user_id).execute()
        return new_quota
    except Exception as e:
        logging.error(f"Error update_quota: {e}")
        return current_quota

# ==============================================================================
#                        ADMIN FEATURE: UPLOAD CSV/EXCEL
# ==============================================================================

async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Anda tidak memiliki izin untuk akses ini.")
        return

    document = update.message.document
    file_name = document.file_name.lower()

    if not (file_name.endswith('.csv') or file_name.endswith('.xlsx') or file_name.endswith('.xls')):
        await update.message.reply_text("❌ Format salah. Harap upload .csv atau .xlsx")
        return

    status_msg = await update.message.reply_text("⏳ **Sedang menganalisa file...**")

    try:
        new_file = await document.get_file()
        file_content = await new_file.download_as_bytearray()
        
        # 1. BACA FILE (Auto-detect separator ; atau ,)
        if file_name.endswith('.csv'):
            try:
                df = pd.read_csv(io.BytesIO(file_content), sep=';', dtype=str)
                if len(df.columns) <= 1:
                    df = pd.read_csv(io.BytesIO(file_content), sep=',', dtype=str)
            except:
                df = pd.read_csv(io.BytesIO(file_content), sep=None, engine='python', dtype=str)
        else:
            df = pd.read_excel(io.BytesIO(file_content), dtype=str)

        # 2. NORMALISASI HEADER
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        
        # Cek kolom Nopol
        if 'nopol' not in df.columns:
            possible = [c for c in df.columns if 'no' in c and 'pol' in c]
            if possible:
                df.rename(columns={possible[0]: 'nopol'}, inplace=True)
            else:
                await status_msg.edit_text(f"❌ Kolom 'nopol' tidak ditemukan.\nHeader terbaca: `{str(df.columns.tolist())}`")
                return

        # 3. CLEANING DATA
        df['nopol'] = df['nopol'].astype(str).str.replace(' ', '').str.replace(';', '').str.upper()
        df = df.replace({np.nan: None, 'nan': None, 'NaN': None})
        df = df[df['nopol'].str.len() > 2] 

        # Filter kolom agar sesuai database
        expected_cols = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch']
        valid_cols = df.columns.intersection(expected_cols)
        final_data = df[valid_cols].to_dict(orient='records')
        
        total_rows = len(final_data)
        if total_rows == 0:
            await status_msg.edit_text("❌ Data terbaca kosong.")
            return

        await status_msg.edit_text(f"📥 **Mengupload {total_rows} data...**")

        # 4. UPSERT KE DATABASE
        BATCH_SIZE = 1000
        success_count = 0
        first_error = None
        
        for i in range(0, total_rows, BATCH_SIZE):
            batch = final_data[i : i + BATCH_SIZE]
            try:
                supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
                success_count += len(batch)
            except Exception as e:
                logging.error(f"Batch {i} Error: {e}")
                if not first_error: first_error = str(e)
        
        if success_count == 0:
            await context.bot.send_message(chat_id=user_id, text=f"❌ **UPLOAD GAGAL TOTAL**\nError: `{first_error}`")
            await status_msg.delete()
        else:
            await context.bot.send_message(chat_id=user_id, text=f"✅ **UPLOAD BERHASIL!**\n\nTotal: {success_count} / {total_rows} data masuk.")
            await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ **SYSTEM ERROR:** {str(e)}")

# ==============================================================================
#                        ADMIN TOOLS & NOTIFICATIONS
# ==============================================================================

async def test_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text="🔔 **TES NOTIFIKASI SUKSES!**", parse_mode='Markdown')
        await update.message.reply_text(f"✅ Pesan dikirim ke ID: `{LOG_GROUP_ID}`")
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal: {e}")

async def notify_hit_to_group(context: ContextTypes.DEFAULT_TYPE, user_data, vehicle_data):
    hp_raw = user_data.get('no_hp', '-')
    hp_wa = '62' + hp_raw[1:] if hp_raw.startswith('0') else hp_raw
    
    report_text = (
        f"🚨 **UNIT DITEMUKAN! (HIT)**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Penemu:** {user_data.get('nama_lengkap')} ({user_data.get('agency')})\n\n"
        f"🚙 **Unit:** {vehicle_data.get('type', '-')}\n"
        f"🔢 **Nopol:** `{vehicle_data.get('nopol', '-')}`\n"
        f"🏦 **Finance:** {vehicle_data.get('finance', '-')}\n"
        f"⚠️ **OVD:** {vehicle_data.get('ovd', '-')}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    keyboard = [[InlineKeyboardButton("📞 Hubungi via WhatsApp", url=f"https://wa.me/{hp_wa}")]]
    try:
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text=report_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except: pass

async def help_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text(
        "🛠 **MENU ADMIN**\n\n"
        "1. Upload File (.xlsx/.csv) untuk update data.\n"
        "2. /users - Lihat daftar user\n"
        "3. /ban <id> - Blokir\n"
        "4. /unban <id> - Aktifkan\n"
        "5. /delete <id> - Hapus Permanen"
    )

# ==============================================================================
#                        USER REGISTRATION FLOW
# ==============================================================================

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_user(update.effective_user.id):
        return await update.message.reply_text("✅ Anda sudah terdaftar.")
    await update.message.reply_text("📝 **FORMULIR PENDAFTARAN**\n\n1️⃣ Masukkan **NAMA LENGKAP**:", parse_mode='Markdown')
    return NAMA

async def register_nama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nama'] = update.message.text
    await update.message.reply_text("2️⃣ Masukkan **NO WA (08...)**:")
    return NO_HP

async def register_hp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['no_hp'] = update.message.text
    await update.message.reply_text("3️⃣ Masukkan **NIK**:")
    return NIK

async def register_nik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nik'] = update.message.text
    await update.message.reply_text("4️⃣ Masukkan **ALAMAT**:")
    return ALAMAT

async def register_alamat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['alamat'] = update.message.text
    await update.message.reply_text("5️⃣ Masukkan **EMAIL**:")
    return EMAIL

async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['email'] = update.message.text
    await update.message.reply_text("6️⃣ Masukkan **AGENCY / PT**:")
    return AGENCY

async def register_agency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['agency'] = update.message.text
    summary = (f"📋 **KONFIRMASI**\nNama: {context.user_data['nama']}\nHP: {context.user_data['no_hp']}\n"
               f"Agency: {context.user_data['agency']}")
    kb = [["✅ KIRIM", "❌ ULANGI"]]
    await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
    return CONFIRM

async def register_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ ULANGI":
        await update.message.reply_text("🔄 Ulangi dengan /register", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
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
    try:
        supabase.table('users').insert(data).execute()
        await update.message.reply_text("✅ Terkirim! Mohon tunggu persetujuan Admin.", reply_markup=ReplyKeyboardRemove())
        
        # Notif Admin Pribadi
        kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{data['user_id']}"), 
               InlineKeyboardButton("❌ Reject", callback_data=f"reject_{data['user_id']}")]]
        await context.bot.send_message(ADMIN_ID, f"🔔 **NEW REGISTER**\n{data['nama_lengkap']} - {data['agency']}", reply_markup=InlineKeyboardMarkup(kb))
    except:
        await update.message.reply_text("❌ Gagal menyimpan data.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ==============================================================================
#                        HANDLER UTAMA & PENCARIAN
# ==============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_input = update.message.text
    
    user = get_user(uid)
    if not user or user['status'] != 'active':
        return await update.message.reply_text("⛔ Akun tidak aktif atau belum terdaftar.")
    if user['quota'] <= 0:
        return await update.message.reply_text("⚠️ Kuota Anda habis.")

    await update.message.reply_text("⏳ *Mencari data...*", parse_mode='Markdown')
    kw = user_input.replace(" ", "").upper()
    
    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.eq.{kw},noka.eq.{kw},nosin.eq.{kw}").execute()
        
        if res.data:
            d = res.data[0]
            update_quota_usage(uid, user['quota'])
            
            # FORMAT TAMPILAN PREMIUM (FULL DATA)
            reply_text = (
                f"✅ **DATA DITEMUKAN**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🚙 **Unit:** {d.get('type', '-')}\n"
                f"🔢 **Nopol:** `{d.get('nopol', '-')}`\n"
                f"📅 **Tahun:** {d.get('tahun', '-')}\n"
                f"🎨 **Warna:** {d.get('warna', '-')}\n"
                f"----------------------------------\n"
                f"🔧 **Noka:** `{d.get('noka', '-')}`\n"
                f"⚙️ **Nosin:** `{d.get('nosin', '-')}`\n"
                f"----------------------------------\n"
                f"⚠️ **OVD:** {d.get('ovd', '-')}\n"
                f"🏦 **Finance:** {d.get('finance', '-')}\n"
                f"🏢 **Branch:** {d.get('branch', '-')}\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"⚠️ *CATATAN PENTING:*\n"
                f"Ini bukan alat yang SAH untuk melakukan penarikan atau menyita aset kendaraan, Silahkan konfirmasi kepada PIC leasing terkait.\n"
                f"Terima kasih."
            )
            await update.message.reply_text(reply_text, parse_mode='Markdown')
            await notify_hit_to_group(context, user, d)
        else:
            await update.message.reply_text(f"❌ **DATA TIDAK DITEMUKAN**\n`{user_input}`", parse_mode='Markdown')
    except:
        await update.message.reply_text("❌ Database Error")

# ==============================================================================
#                               BOT INITIALIZATION
# ==============================================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if update.effective_user.id != ADMIN_ID: return
    act, uid = query.data.split("_")
    update_user_status(uid, 'active' if act == "approve" else 'rejected')
    await query.edit_message_text(f"Hasil: {act.upper()} pada user {uid}")
    try: await context.bot.send_message(uid, "✅ AKUN ANDA TELAH AKTIF!" if act == "approve" else "⛔ REGISTRASI DITOLAK.")
    except: pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 **MATEL SYSTEM ONLINE**\nKetik /register untuk mendaftar.", parse_mode='Markdown')

if __name__ == '__main__':
    app = ApplicationBuilder().token(token).build()
    
    # Registration Handler
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('register', register_start)],
        states={NAMA:[MessageHandler(filters.TEXT, register_nama)], NO_HP:[MessageHandler(filters.TEXT, register_hp)],
                NIK:[MessageHandler(filters.TEXT, register_nik)], ALAMAT:[MessageHandler(filters.TEXT, register_alamat)],
                EMAIL:[MessageHandler(filters.TEXT, register_email)], AGENCY:[MessageHandler(filters.TEXT, register_agency)],
                CONFIRM:[MessageHandler(filters.TEXT, register_confirm)]},
        fallbacks=[CommandHandler('cancel', cancel)]))
    
    # Other Handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('admin', help_admin))
    app.add_handler(CommandHandler('testgroup', test_group))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL & filters.Chat(ADMIN_ID), handle_document_upload))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print(f"✅ Bot Berjalan. Admin: {ADMIN_ID}")
    app.run_polling()