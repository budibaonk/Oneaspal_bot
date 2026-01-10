import os
import logging
import pandas as pd
import io
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

# --- ⚠️ KONFIGURASI ID ---
ADMIN_ID = 7530512170          # ID Super Admin (Anda)
LOG_GROUP_ID = -1003627047676  # ID Grup Notifikasi

if not url or not key or not token:
    print("❌ ERROR: Cek file .env Anda.")
    exit()

try:
    supabase: Client = create_client(url, key)
except Exception as e:
    print(f"❌ Gagal koneksi Supabase: {e}")
    exit()

# --- STATE FORMULIR ---
NAMA, NO_HP, NIK, ALAMAT, EMAIL, AGENCY, CONFIRM = range(7)

# --- FUNGSI HELPER DATABASE ---
def get_user(user_id):
    response = supabase.table('users').select("*").eq('user_id', user_id).execute()
    if response.data: return response.data[0]
    return None

def update_user_status(user_id, status):
    supabase.table('users').update({'status': status}).eq('user_id', user_id).execute()

def update_quota_usage(user_id, current_quota):
    new_quota = current_quota - 1
    supabase.table('users').update({'quota': new_quota}).eq('user_id', user_id).execute()
    return new_quota

# --- FUNGSI UPLOAD DATABASE (UPDATED: AUTO-DETECT PEMISAH) ---
async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani upload file CSV/Excel dari Admin dengan deteksi otomatis"""
    user_id = update.effective_user.id
    
    # 1. Proteksi: Hanya Admin yang boleh upload
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Anda tidak memiliki izin untuk mengupload database.")
        return

    document = update.message.document
    file_name = document.file_name.lower()

    # 2. Cek Format File
    if not (file_name.endswith('.csv') or file_name.endswith('.xlsx') or file_name.endswith('.xls')):
        await update.message.reply_text("❌ Format salah. Harap upload file **.csv** atau **.xlsx** (Excel).", parse_mode='Markdown')
        return

    status_msg = await update.message.reply_text("⏳ **Sedang memproses file...**\nMohon tunggu, jangan kirim pesan lain.")

    try:
        # 3. Download File ke Memory
        new_file = await document.get_file()
        file_content = await new_file.download_as_bytearray()
        
        # 4. Baca File (Logic Baru: Support Titik Koma)
        if file_name.endswith('.csv'):
            try:
                # Coba baca dengan engine python (auto-detect separator)
                df = pd.read_csv(io.BytesIO(file_content), sep=None, engine='python')
            except:
                # Jika gagal, paksa pakai titik koma (format umum Indonesia)
                df = pd.read_csv(io.BytesIO(file_content), sep=';')
        else:
            df = pd.read_excel(io.BytesIO(file_content))

        # 5. Normalisasi Header (Lower case & ganti spasi dengan _)
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        
        # Cek Header
        if 'nopol' not in df.columns:
            # Coba cari kolom alternatif jika user salah ketik header
            possible = [c for c in df.columns if 'no' in c and 'pol' in c] # cari yang mengandung 'no' dan 'pol'
            if possible:
                df.rename(columns={possible[0]: 'nopol'}, inplace=True)
            else:
                await status_msg.edit_text(f"❌ **ERROR HEADER:** Tidak ditemukan kolom 'nopol'.\nKolom terbaca: {df.columns.tolist()}")
                return

        # 6. Bersihkan Data
        # Hapus spasi, titik koma, dan jadikan huruf besar semua
        df['nopol'] = df['nopol'].astype(str).str.replace(' ', '').str.replace(';', '').str.upper()
        df = df.fillna('')
        
        # Filter kolom yang akan diupload
        expected_cols = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch']
        valid_cols = df.columns.intersection(expected_cols)
        
        final_data = df[valid_cols].to_dict(orient='records')
        total_rows = len(final_data)
        
        if total_rows == 0:
            await status_msg.edit_text("❌ File kosong atau tidak ada data yang terbaca.")
            return

        await status_msg.edit_text(f"📥 **Mulai Upload {total_rows} data...**\nProses ini berjalan di background.")

        # 7. Upload per Batch (Agar server stabil)
        BATCH_SIZE = 1000
        success_count = 0
        
        for i in range(0, total_rows, BATCH_SIZE):
            batch = final_data[i : i + BATCH_SIZE]
            try:
                # Upsert: Update jika ada, Insert jika baru
                supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
                success_count += len(batch)
            except Exception as e:
                logging.error(f"Error batch {i}: {e}")
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ **UPLOAD SUKSES!**\n\nTotal Data Masuk: {success_count} dari {total_rows}.\nDatabase telah diperbarui.",
            parse_mode='Markdown'
        )

    except Exception as e:
        logging.error(f"Error Upload: {e}")
        await status_msg.edit_text(f"❌ **GAGAL:** Terjadi kesalahan sistem.\nError: {str(e)}")

# --- FUNGSI TEST & NOTIFIKASI ---
async def test_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text="🔔 **TES NOTIFIKASI SUKSES!**", parse_mode='Markdown')
        await update.message.reply_text(f"✅ Pesan terkirim ke ID: `{LOG_GROUP_ID}`")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def notify_hit_to_group(context: ContextTypes.DEFAULT_TYPE, user_data, vehicle_data):
    hp_raw = user_data.get('no_hp', '-')
    hp_wa = '62' + hp_raw[1:] if hp_raw.startswith('0') else hp_raw
    
    report_text = (
        f"🚨 **UNIT DITEMUKAN! (HIT)**\n━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Penemu:** {user_data.get('nama_lengkap')} ({user_data.get('agency')})\n"
        f"📍 **Lokasi User:** (Tracking via Chat)\n\n"
        f"🚙 **Unit:** {vehicle_data.get('type')}\n"
        f"🔢 **Nopol:** `{vehicle_data.get('nopol')}`\n"
        f"🏦 **Finance:** {vehicle_data.get('finance')}\n"
        f"⚠️ **OVD:** {vehicle_data.get('ovd')}\n"
        f"━━━━━━━━━━━━━━━━━━\nSegera hubungi tim lapangan!"
    )
    keyboard = [[InlineKeyboardButton("📞 Hubungi via WhatsApp", url=f"https://wa.me/{hp_wa}")]]
    try:
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text=report_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Gagal kirim notif: {e}")

# --- ADMIN COMMANDS ---
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        response = supabase.table('users').select("*").order('created_at', desc=True).limit(20).execute()
        users = response.data
        if not users:
            await update.message.reply_text("Belum ada user.")
            return
        message = "📋 **DAFTAR USER TERBARU**\n\n"
        for u in users:
            icon = "✅" if u['status'] == 'active' else "⏳" if u['status'] == 'pending' else "⛔"
            message += f"{icon} `{u['user_id']}` | {u.get('nama_lengkap', '-')}\n"
        await update.message.reply_text(message + "\nℹ️ Use /ban, /unban, /delete", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        update_user_status(context.args[0], 'rejected')
        await update.message.reply_text(f"⛔ User `{context.args[0]}` BANNED.", parse_mode='Markdown')
    except: await update.message.reply_text("⚠️ Format: `/ban <id>`")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        update_user_status(context.args[0], 'active')
        await update.message.reply_text(f"✅ User `{context.args[0]}` ACTIVE.", parse_mode='Markdown')
    except: await update.message.reply_text("⚠️ Format: `/unban <id>`")

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        supabase.table('users').delete().eq('user_id', context.args[0]).execute()
        await update.message.reply_text(f"🗑️ User `{context.args[0]}` DELETED.", parse_mode='Markdown')
    except: await update.message.reply_text("⚠️ Format: `/delete <id>`")

# --- REGISTRATION FLOW ---
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    if user:
        await update.message.reply_text(f"Status Anda: {user.get('status', 'Unknown')}")
        return ConversationHandler.END
    await update.message.reply_text("📝 **FORMULIR REGISTRASI**\n\n1️⃣ **NAMA LENGKAP**:", parse_mode='Markdown')
    return NAMA

async def register_nama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nama'] = update.message.text
    await update.message.reply_text("2️⃣ **NO HP / WA**:")
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
    await update.message.reply_text("6️⃣ **AGENCY / PT**:")
    return AGENCY

async def register_agency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['agency'] = update.message.text
    summary = (f"📋 **KONFIRMASI**\nNama: {context.user_data['nama']}\nHP: {context.user_data['no_hp']}\n"
               f"Agency: {context.user_data['agency']}\n\nCek data sebelum kirim.")
    await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ ULANGI"]], one_time_keyboard=True, resize_keyboard=True))
    return CONFIRM

async def register_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ ULANGI":
        await update.message.reply_text("🔄 Ulangi /register", reply_markup=ReplyKeyboardRemove())
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
        await update.message.reply_text("✅ DATA TERKIRIM. Tunggu verifikasi Admin.", reply_markup=ReplyKeyboardRemove())
        
        kb = [[InlineKeyboardButton("✅", callback_data=f"approve_{data['user_id']}"), InlineKeyboardButton("❌", callback_data=f"reject_{data['user_id']}")]]
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 **NEW REGISTER**\nUser: {data['nama_lengkap']}\nAgency: {data['agency']}", reply_markup=InlineKeyboardMarkup(kb))
    except: await update.message.reply_text("❌ Error / Sudah terdaftar.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- HANDLER UTAMA ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID: return
    action, uid = query.data.split("_")
    
    if action == "approve":
        update_user_status(uid, 'active')
        await query.edit_message_text(f"✅ User `{uid}` APPROVED.")
        try: await context.bot.send_message(uid, "🎉 **AKUN AKTIF!**")
        except: pass
    elif action == "reject":
        update_user_status(uid, 'rejected')
        await query.edit_message_text(f"❌ User `{uid}` REJECTED.")
        try: await context.bot.send_message(uid, "⛔ **DITOLAK**")
        except: pass

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    if not user: return await update.message.reply_text("⛔ Belum terdaftar. Ketik /register")
    if user['status'] != 'active': return await update.message.reply_text(f"⛔ Status Akun: {user['status']}")
    if user['quota'] <= 0: return await update.message.reply_text("⚠️ Kuota habis.")

    await update.message.reply_text("⏳ *Mencari data...*", parse_mode='Markdown')
    kw = update.message.text.replace(" ", "").upper()
    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.eq.{kw},noka.eq.{kw},nosin.eq.{kw}").execute()
        if res.data:
            data = res.data[0]
            update_quota_usage(uid, user['quota'])
            msg = (f"✅ **DATA DITEMUKAN**\n━━━━━━━━━━━━━━━━━━\n🚙 {data.get('type','-')}\n🔢 `{data.get('nopol','-')}`\n"
                   f"🏦 {data.get('finance','-')}\n⚠️ {data.get('ovd','-')}\n━━━━━━━━━━━━━━━━━━\nCek fisik sebelum eksekusi.")
            await update.message.reply_text(msg, parse_mode='Markdown')
            await notify_hit_to_group(context, user, data)
        else:
            await update.message.reply_text(f"❌ **DATA TIDAK DITEMUKAN**\n`{update.message.text}`", parse_mode='Markdown')
    except: await update.message.reply_text("❌ Database Error")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 **MATEL BOT**\nKetik /register untuk daftar.", parse_mode='Markdown')

async def help_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🛠 **ADMIN**\nUpload file CSV/Excel langsung kesini untuk update data.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(token).build()
    
    # Conversations
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('register', register_start)],
        states={NAMA:[MessageHandler(filters.TEXT, register_nama)], NO_HP:[MessageHandler(filters.TEXT, register_hp)],
                NIK:[MessageHandler(filters.TEXT, register_nik)], ALAMAT:[MessageHandler(filters.TEXT, register_alamat)],
                EMAIL:[MessageHandler(filters.TEXT, register_email)], AGENCY:[MessageHandler(filters.TEXT, register_agency)],
                CONFIRM:[MessageHandler(filters.TEXT, register_confirm)]},
        fallbacks=[CommandHandler('cancel', cancel)]))
    
    # Commands
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('users', list_users))
    app.add_handler(CommandHandler('ban', ban_user))
    app.add_handler(CommandHandler('unban', unban_user))
    app.add_handler(CommandHandler('delete', delete_user))
    app.add_handler(CommandHandler('admin', help_admin))
    app.add_handler(CommandHandler('testgroup', test_group))
    
    # Callback & Document Upload
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL & filters.Chat(ADMIN_ID), handle_document_upload))
    
    # Text Message (Search)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print(f"✅ Bot Online. Admin: {ADMIN_ID}")
    app.run_polling()