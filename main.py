import os
import logging
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
ADMIN_ID = 7530512170        # ID Super Admin (Anda)
LOG_GROUP_ID = -3627047676   # ID Grup Notifikasi

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

# --- FUNGSI DATABASE HELPER ---
def get_user(user_id):
    response = supabase.table('users').select("*").eq('user_id', user_id).execute()
    if response.data:
        return response.data[0]
    return None

def update_user_status(user_id, status):
    supabase.table('users').update({'status': status}).eq('user_id', user_id).execute()

def update_quota_usage(user_id, current_quota):
    new_quota = current_quota - 1
    supabase.table('users').update({'quota': new_quota}).eq('user_id', user_id).execute()
    return new_quota

# --- FUNGSI NOTIFIKASI GRUP ---
async def notify_hit_to_group(context: ContextTypes.DEFAULT_TYPE, user_data, vehicle_data):
    """Mengirim laporan penemuan unit ke Grup Admin"""
    
    # Format No HP untuk link WhatsApp (ganti 08 jadi 628)
    hp_raw = user_data.get('no_hp', '-')
    if hp_raw.startswith('0'):
        hp_wa = '62' + hp_raw[1:]
    else:
        hp_wa = hp_raw
    
    # Pesan Laporan
    report_text = (
        f"🚨 **UNIT DITEMUKAN! (HIT)**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Penemu:** {user_data.get('nama_lengkap')} ({user_data.get('agency')})\n"
        f"📍 **Lokasi User:** (Tracking via Chat)\n\n"
        f"🚙 **Unit:** {vehicle_data.get('type')}\n"
        f"🔢 **Nopol:** `{vehicle_data.get('nopol')}`\n"
        f"🏦 **Finance:** {vehicle_data.get('finance')}\n"
        f"⚠️ **OVD:** {vehicle_data.get('ovd')}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Segera hubungi tim lapangan!"
    )

    # Tombol Link WhatsApp
    keyboard = [[InlineKeyboardButton("📞 Hubungi via WhatsApp", url=f"https://wa.me/{hp_wa}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.send_message(
            chat_id=LOG_GROUP_ID, 
            text=report_text, 
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Gagal kirim notif ke grup: {e}")

# --- ADMIN COMMANDS ---

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        response = supabase.table('users').select("*").order('created_at', desc=True).limit(20).execute()
        users = response.data
        if not users:
            await update.message.reply_text("Belum ada user terdaftar.")
            return
        message = "📋 **DAFTAR USER TERBARU**\n\n"
        for u in users:
            status_icon = "✅" if u['status'] == 'active' else "⏳" if u['status'] == 'pending' else "⛔"
            nama = u.get('nama_lengkap', 'Tanpa Nama')
            message += f"{status_icon} `{u['user_id']}` | {nama}\n"
        message += "\nℹ️ *Gunakan ID diatas untuk command /ban atau /delete*"
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id = context.args[0]
        update_user_status(target_id, 'rejected')
        await update.message.reply_text(f"⛔ User `{target_id}` berhasil di-NONAKTIFKAN.", parse_mode='Markdown')
    except IndexError:
        await update.message.reply_text("⚠️ Format: `/ban <user_id>`", parse_mode='Markdown')

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id = context.args[0]
        update_user_status(target_id, 'active')
        await update.message.reply_text(f"✅ User `{target_id}` berhasil di-AKTIFKAN.", parse_mode='Markdown')
    except IndexError:
        await update.message.reply_text("⚠️ Format: `/unban <user_id>`", parse_mode='Markdown')

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id = context.args[0]
        supabase.table('users').delete().eq('user_id', target_id).execute()
        await update.message.reply_text(f"🗑️ User `{target_id}` DIHAPUS PERMANEN.", parse_mode='Markdown')
    except IndexError:
        await update.message.reply_text("⚠️ Format: `/delete <user_id>`", parse_mode='Markdown')

# --- ALUR PENDAFTARAN (REGISTRASI) ---

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    existing_user = get_user(user_id)
    
    if existing_user:
        status = existing_user.get('status')
        if status == 'active':
            await update.message.reply_text("✅ Akun Anda sudah AKTIF.")
        elif status == 'pending':
            await update.message.reply_text("⏳ Akun Anda sedang menunggu persetujuan Admin.")
        else:
            await update.message.reply_text("⛔ Pendaftaran Anda ditolak/diblokir Admin.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📝 **FORMULIR REGISTRASI MITRA**\n\n1️⃣ Silakan ketik **NAMA LENGKAP** Anda:",
        parse_mode='Markdown'
    )
    return NAMA

async def register_nama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nama'] = update.message.text
    await update.message.reply_text("2️⃣ Masukkan **NO HP / WA** (Wajib Aktif):")
    return NO_HP

async def register_hp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['no_hp'] = update.message.text
    await update.message.reply_text("3️⃣ Masukkan **NIK**:")
    return NIK

async def register_nik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nik'] = update.message.text
    await update.message.reply_text("4️⃣ Masukkan **ALAMAT LENGKAP**:")
    return ALAMAT

async def register_alamat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['alamat'] = update.message.text
    await update.message.reply_text("5️⃣ Masukkan **EMAIL**:")
    return EMAIL

async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['email'] = update.message.text
    await update.message.reply_text("6️⃣ Masukkan **NAMA AGENCY / PT**:")
    return AGENCY

async def register_agency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['agency'] = update.message.text
    
    nama = context.user_data['nama']
    hp = context.user_data['no_hp']
    nik = context.user_data['nik']
    alamat = context.user_data['alamat']
    email = context.user_data['email']
    agency = context.user_data['agency']

    summary_text = (
        "📋 **KONFIRMASI DATA**\n\n"
        f"👤 Nama: {nama}\n"
        f"📞 HP: {hp}\n"
        f"🆔 NIK: {nik}\n"
        f"🏠 Alamat: {alamat}\n"
        f"📧 Email: {email}\n"
        f"🏢 Agency: {agency}\n\n"
        "⚠️ **Pastikan data yang sudah diisi benar dan sesuai, silahkan cek kembali sebelum submit.**"
    )

    keyboard = [["✅ KIRIM DATA", "❌ ULANGI"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(summary_text, reply_markup=reply_markup, parse_mode='Markdown')
    return CONFIRM

async def register_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username or "No Username"

    if choice == "❌ ULANGI":
        await update.message.reply_text(
            "🔄 Registrasi diulang. Silakan ketik /register kembali.", 
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    if choice == "✅ KIRIM DATA":
        user_data_input = {
            "user_id": user_id,
            "nama_lengkap": context.user_data['nama'],
            "no_hp": context.user_data['no_hp'],
            "nik": context.user_data['nik'],
            "alamat": context.user_data['alamat'],
            "email": context.user_data['email'],
            "agency": context.user_data['agency'],
            "quota": 1000,
            "status": "pending"
        }
        
        try:
            supabase.table('users').insert(user_data_input).execute()
            
            await update.message.reply_text(
                "✅ **DATA TERKIRIM**\n\nTerima kasih. Data Anda sedang diverifikasi oleh Admin.",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode='Markdown'
            )

            # Notifikasi ke Admin Pribadi (Approval)
            keyboard = [
                [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"),
                 InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")]
            ]
            
            report_text = (
                f"🔔 **PENDAFTARAN BARU**\nUser: @{username}\n"
                f"Nama: {user_data_input['nama_lengkap']}\n"
                f"Agency: {user_data_input['agency']}\n"
                f"HP: {user_data_input['no_hp']}"
            )
            
            await context.bot.send_message(chat_id=ADMIN_ID, text=report_text, reply_markup=InlineKeyboardMarkup(keyboard))

        except Exception as e:
            await update.message.reply_text("❌ Error saat menyimpan data. Mungkin Anda sudah terdaftar?", reply_markup=ReplyKeyboardRemove())
            
        return ConversationHandler.END

    else:
        await update.message.reply_text("Silakan pilih tombol **KIRIM DATA** atau **ULANGI**.")
        return CONFIRM

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- APPROVAL HANDLER ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    action, target_user_id = data.split("_")
    
    if update.effective_user.id != ADMIN_ID: return

    if action == "approve":
        update_user_status(target_user_id, 'active')
        await query.edit_message_text(f"✅ User `{target_user_id}` di-APPROVE.", parse_mode='Markdown')
        try:
            await context.bot.send_message(chat_id=target_user_id, text="🎉 **AKUN AKTIF!**\nSilakan gunakan bot.")
        except: pass

    elif action == "reject":
        update_user_status(target_user_id, 'rejected')
        await query.edit_message_text(f"❌ User `{target_user_id}` di-REJECT.", parse_mode='Markdown')
        try:
            await context.bot.send_message(chat_id=target_user_id, text="⛔ **REGISTRASI DITOLAK**")
        except: pass

# --- MAIN SEARCH ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_input = update.message.text
    
    user_data = get_user(user_id)
    if not user_data:
        await update.message.reply_text("⛔ Anda belum terdaftar. Ketik /register")
        return

    if user_data.get('status') == 'pending':
        await update.message.reply_text("⏳ Akun menunggu verifikasi Admin.")
        return
    elif user_data.get('status') == 'rejected':
        await update.message.reply_text("⛔ Akun Anda dinonaktifkan.")
        return

    if user_data['quota'] <= 0:
        await update.message.reply_text("⚠️ Kuota habis.")
        return

    await update.message.reply_text("⏳ *Sedang mencari data...*", parse_mode='Markdown')
    
    try:
        clean_keyword = user_input.replace(" ", "").upper()
        response = supabase.table('kendaraan').select("*").or_(
            f"nopol.eq.{clean_keyword},noka.eq.{clean_keyword},nosin.eq.{clean_keyword}"
        ).execute()
        results = response.data
    except Exception:
        results = []

    if results and len(results) > 0:
        update_quota_usage(user_id, user_data['quota'])
        data = results[0]
        
        # Kirim Balasan ke User
        reply_text = (
            f"✅ **DATA DITEMUKAN**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🚙 **Unit:** {data.get('type', '-')}\n"
            f"🔢 **Nopol:** `{data.get('nopol', '-')}`\n"
            f"📅 **Tahun:** {data.get('tahun', '-')}\n"
            f"🎨 **Warna:** {data.get('warna', '-')}\n"
            f"----------------------------------\n"
            f"🔧 **Noka:** `{data.get('noka', '-')}`\n"
            f"⚙️ **Nosin:** `{data.get('nosin', '-')}`\n"
            f"----------------------------------\n"
            f"⚠️ **OVD:** {data.get('ovd', '-')}\n"
            f"🏦 **Finance:** {data.get('finance', '-')}\n"
            f"🏢 **Branch:** {data.get('branch', '-')}\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ *CATATAN PENTING:*\n"
            f"Ini bukan alat untuk melakukan penarikan, silahkan konfirmasi kepada PIC leasing tersebut.\n"
            f"Terima kasih."
        )
        await update.message.reply_text(reply_text, parse_mode='Markdown')

        # 🔥 TRIGGER NOTIFIKASI KE GRUP 🔥
        await notify_hit_to_group(context, user_data, data)

    else:
        reply_text = f"❌ **DATA TIDAK DITEMUKAN**\n\nKeyword: `{user_input}`"
        await update.message.reply_text(reply_text, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 **MATEL BOT SYSTEM**\nKetik /register untuk mendaftar.", parse_mode='Markdown')

async def help_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🛠 **MENU ADMIN**\n/users, /ban, /unban, /delete")

if __name__ == '__main__':
    application = ApplicationBuilder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register_start)],
        states={
            NAMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_nama)],
            NO_HP: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_hp)],
            NIK: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_nik)],
            ALAMAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_alamat)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)],
            AGENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_agency)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_confirm)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('users', list_users))
    application.add_handler(CommandHandler('ban', ban_user))
    application.add_handler(CommandHandler('unban', unban_user))
    application.add_handler(CommandHandler('delete', delete_user))
    application.add_handler(CommandHandler('admin', help_admin))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print(f"✅ Bot Matel berjalan... (Super Admin: {ADMIN_ID})")
    application.run_polling()