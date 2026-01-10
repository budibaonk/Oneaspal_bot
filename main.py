# UPDATE FINAL FULL VERSION
import os
...
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

# --- KONFIGURASI LOGGING ---
load_dotenv()
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- LOAD ENVIRONMENT VARIABLES ---
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
token: str = os.environ.get("TELEGRAM_TOKEN")

# --- ⚠️ KONFIGURASI ID (Pastikan ID ini benar) ---
ADMIN_ID = 7530512170          # ID Super Admin (Anda)
LOG_GROUP_ID = -1003627047676  # ID Grup Notifikasi

# --- CEK KONEKSI ---
if not url or not key or not token:
    print("❌ ERROR: Cek file .env Anda. Pastikan SUPABASE_URL, SUPABASE_KEY, dan TELEGRAM_TOKEN terisi.")
    exit()

try:
    supabase: Client = create_client(url, key)
except Exception as e:
    print(f"❌ Gagal koneksi Supabase: {e}")
    exit()

# --- STATE FORMULIR REGISTRASI ---
NAMA, NO_HP, NIK, ALAMAT, EMAIL, AGENCY, CONFIRM = range(7)

# ==============================================================================
#                             FUNGSI DATABASE HELPER
# ==============================================================================

def get_user(user_id):
    """Mengambil data user dari database berdasarkan user_id"""
    try:
        response = supabase.table('users').select("*").eq('user_id', user_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        logging.error(f"DB Error (get_user): {e}")
        return None

def update_user_status(user_id, status):
    """Update status user (active/rejected/pending)"""
    try:
        supabase.table('users').update({'status': status}).eq('user_id', user_id).execute()
    except Exception as e:
        logging.error(f"DB Error (update_status): {e}")

def update_quota_usage(user_id, current_quota):
    """Mengurangi kuota user sebesar 1"""
    try:
        new_quota = current_quota - 1
        supabase.table('users').update({'quota': new_quota}).eq('user_id', user_id).execute()
        return new_quota
    except Exception as e:
        logging.error(f"DB Error (update_quota): {e}")
        return current_quota

# ==============================================================================
#                        FUNGSI UPLOAD FILE (SUPER ADMIN)
# ==============================================================================

async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Menangani upload file CSV/Excel dari Admin.
    Fitur: Auto-detect separator (koma/titik koma), upsert data, error handling.
    """
    user_id = update.effective_user.id
    
    # 1. Proteksi Admin
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Anda tidak memiliki izin untuk mengupload database.")
        return

    document = update.message.document
    file_name = document.file_name.lower()

    # 2. Validasi Ekstensi File
    if not (file_name.endswith('.csv') or file_name.endswith('.xlsx') or file_name.endswith('.xls')):
        await update.message.reply_text("❌ Format salah. Harap upload file **.csv** atau **.xlsx** (Excel).", parse_mode='Markdown')
        return

    status_msg = await update.message.reply_text("⏳ **Sedang menganalisa file...**\nMohon tunggu sebentar.")

    try:
        # 3. Download File
        new_file = await document.get_file()
        file_content = await new_file.download_as_bytearray()
        
        # 4. Baca File dengan Pandas (Logic Deteksi Pemisah)
        if file_name.endswith('.csv'):
            try:
                # Prioritas 1: Coba baca pakai titik koma (Format umum di Indonesia)
                df = pd.read_csv(io.BytesIO(file_content), sep=';', dtype=str)
                # Jika hasilnya cuma 1 kolom, kemungkinan pemisahnya salah (harusnya koma)
                if len(df.columns) <= 1:
                    df = pd.read_csv(io.BytesIO(file_content), sep=',', dtype=str)
            except:
                # Fallback: Coba pakai engine python auto-detect
                df = pd.read_csv(io.BytesIO(file_content), sep=None, engine='python', dtype=str)
        else:
            # Jika Excel
            df = pd.read_excel(io.BytesIO(file_content), dtype=str)

        # 5. Normalisasi Header (Bersihkan nama kolom)
        # Ubah jadi huruf kecil semua, hapus spasi, ganti dengan underscore
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        
        # Kirim Laporan Debug Header ke Admin (Supaya tahu kolom apa yang terbaca)
        col_debug = df.columns.tolist()
        await context.bot.send_message(
            chat_id=user_id, 
            text=f"🔍 **Info Kolom Terbaca:**\n`{str(col_debug)}`", 
            parse_mode='Markdown'
        )

        # 6. Validasi Kolom 'nopol'
        if 'nopol' not in df.columns:
            # Coba cari alternatif nama kolom
            possible = [c for c in df.columns if 'no' in c and 'pol' in c]
            if possible:
                df.rename(columns={possible[0]: 'nopol'}, inplace=True)
            else:
                await status_msg.edit_text(f"❌ **ERROR HEADER:** Kolom 'nopol' tidak ditemukan.\nPastikan baris pertama file Anda adalah judul kolom.")
                return

        # 7. Pembersihan Data (Data Cleaning)
        # Nopol: Hapus spasi, hapus titik koma, jadikan Uppercase
        df['nopol'] = df['nopol'].astype(str).str.replace(' ', '').str.replace(';', '').str.upper()
        # Isi data kosong dengan string kosong (agar tidak error di database)
        df = df.fillna('')
        
        # Hapus baris yang nopol-nya 'NAN' atau kosong
        df = df[df['nopol'] != 'NAN']
        df = df[df['nopol'] != '']
        
        # Filter kolom agar sesuai struktur database Supabase
        expected_cols = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch']
        valid_cols = df.columns.intersection(expected_cols)
        final_data = df[valid_cols].to_dict(orient='records')
        
        total_rows = len(final_data)
        if total_rows == 0:
            await status_msg.edit_text("❌ File terbaca kosong atau format data tidak sesuai.")
            return

        await status_msg.edit_text(f"📥 **Mulai Upload {total_rows} data...**\nProses berjalan di background server.")

        # 8. Proses Upload (Batching)
        BATCH_SIZE = 1000
        success_count = 0
        
        for i in range(0, total_rows, BATCH_SIZE):
            batch = final_data[i : i + BATCH_SIZE]
            try:
                # Upsert: Update jika nopol ada, Insert jika baru
                supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
                success_count += len(batch)
            except Exception as e:
                logging.error(f"Error upload batch {i}: {e}")
                # Opsional: Beritahu admin jika ada batch yang gagal parah
                
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ **UPLOAD SUKSES!**\n\nTotal Data Diproses: {success_count} dari {total_rows}.\nSilakan test pencarian sekarang.",
            parse_mode='Markdown'
        )

    except Exception as e:
        logging.error(f"Error Upload: {e}")
        await status_msg.edit_text(f"❌ **SYSTEM ERROR:**\n{str(e)}")

# ==============================================================================
#                        FUNGSI NOTIFIKASI & TEST GROUP
# ==============================================================================

async def test_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test kirim pesan ke grup notifikasi"""
    if update.effective_user.id != ADMIN_ID: return
    
    try:
        await context.bot.send_message(
            chat_id=LOG_GROUP_ID, 
            text="🔔 **TES NOTIFIKASI SUKSES!**\nBot terhubung dengan grup ini.", 
            parse_mode='Markdown'
        )
        await update.message.reply_text(f"✅ Pesan terkirim ke ID Grup: `{LOG_GROUP_ID}`")
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal kirim ke grup: {e}")

async def notify_hit_to_group(context: ContextTypes.DEFAULT_TYPE, user_data, vehicle_data):
    """Mengirim notifikasi ke grup saat data ditemukan"""
    # Format nomor WA
    hp_raw = user_data.get('no_hp', '-')
    if hp_raw.startswith('0'):
        hp_wa = '62' + hp_raw[1:]
    else:
        hp_wa = hp_raw
    
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

# ==============================================================================
#                        FUNGSI ADMIN MANAGEMENT (User List, Ban, Unban)
# ==============================================================================

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return

    try:
        # Ambil 20 user terbaru
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
        await update.message.reply_text(f"⛔ User `{target_id}` berhasil di-NONAKTIFKAN (Banned).", parse_mode='Markdown')
    except IndexError:
        await update.message.reply_text("⚠️ Format salah. Gunakan: `/ban <user_id>`", parse_mode='Markdown')

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id = context.args[0]
        update_user_status(target_id, 'active')
        await update.message.reply_text(f"✅ User `{target_id}` berhasil di-AKTIFKAN kembali.", parse_mode='Markdown')
    except IndexError:
        await update.message.reply_text("⚠️ Format salah. Gunakan: `/unban <user_id>`", parse_mode='Markdown')

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id = context.args[0]
        supabase.table('users').delete().eq('user_id', target_id).execute()
        await update.message.reply_text(f"🗑️ User `{target_id}` berhasil DIHAPUS PERMANEN.", parse_mode='Markdown')
    except IndexError:
        await update.message.reply_text("⚠️ Format salah. Gunakan: `/delete <user_id>`", parse_mode='Markdown')

# ==============================================================================
#                        ALUR REGISTRASI (CONVERSATION HANDLER)
# ==============================================================================

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    existing_user = get_user(user_id)
    
    if existing_user:
        status = existing_user.get('status')
        await update.message.reply_text(f"ℹ️ Anda sudah terdaftar. Status: **{status}**", parse_mode='Markdown')
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
    
    # Rangkuman Data
    summary_text = (
        "📋 **KONFIRMASI DATA**\n\n"
        f"👤 Nama: {context.user_data['nama']}\n"
        f"📞 HP: {context.user_data['no_hp']}\n"
        f"🆔 NIK: {context.user_data['nik']}\n"
        f"🏠 Alamat: {context.user_data['alamat']}\n"
        f"📧 Email: {context.user_data['email']}\n"
        f"🏢 Agency: {context.user_data['agency']}\n\n"
        "⚠️ Cek kembali sebelum dikirim."
    )

    keyboard = [["✅ KIRIM DATA", "❌ ULANGI"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(summary_text, reply_markup=reply_markup, parse_mode='Markdown')
    return CONFIRM

async def register_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    user_id = update.effective_user.id
    
    if choice == "❌ ULANGI":
        await update.message.reply_text("🔄 Silakan ketik /register ulang.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    if choice == "✅ KIRIM DATA":
        data_insert = {
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
            supabase.table('users').insert(data_insert).execute()
            await update.message.reply_text("✅ **DATA TERKIRIM**\nMenunggu verifikasi Admin.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')

            # Notifikasi ke Admin
            keyboard = [
                [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"),
                 InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")]
            ]
            
            report_text = (
                f"🔔 **PENDAFTARAN BARU**\n"
                f"Nama: {data_insert['nama_lengkap']}\n"
                f"Agency: {data_insert['agency']}"
            )
            await context.bot.send_message(chat_id=ADMIN_ID, text=report_text, reply_markup=InlineKeyboardMarkup(keyboard))

        except Exception as e:
            await update.message.reply_text("❌ Error: Mungkin Anda sudah terdaftar.", reply_markup=ReplyKeyboardRemove())
            
        return ConversationHandler.END
    else:
        return CONFIRM

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ==============================================================================
#                        HANDLER UTAMA & CALLBACK
# ==============================================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani klik tombol Approve/Reject dari Admin"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_ID: return

    action, target_user_id = query.data.split("_")
    
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler Utama: Menangani text Nopol yang dikirim user"""
    user_id = update.effective_user.id
    user_input = update.message.text
    
    # 1. Cek User di Database
    user_data = get_user(user_id)
    
    if not user_data:
        await update.message.reply_text("⛔ Anda belum terdaftar. Ketik /register")
        return

    # 2. Cek Status
    if user_data.get('status') == 'pending':
        await update.message.reply_text("⏳ Akun menunggu verifikasi Admin.")
        return
    elif user_data.get('status') == 'rejected':
        await update.message.reply_text("⛔ Akun Anda dinonaktifkan.")
        return

    # 3. Cek Kuota
    if user_data['quota'] <= 0:
        await update.message.reply_text("⚠️ Kuota habis.")
        return

    await update.message.reply_text("⏳ *Sedang mencari data...*", parse_mode='Markdown')
    
    # 4. Proses Pencarian
    try:
        clean_keyword = user_input.replace(" ", "").upper()
        # Cari di kolom nopol, noka, atau nosin
        response = supabase.table('kendaraan').select("*").or_(
            f"nopol.eq.{clean_keyword},noka.eq.{clean_keyword},nosin.eq.{clean_keyword}"
        ).execute()
        results = response.data
    except Exception as e:
        logging.error(f"Search Error: {e}")
        results = []

    if results and len(results) > 0:
        # Data Ditemukan (HIT)
        update_quota_usage(user_id, user_data['quota'])
        data = results[0]
        
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

        # 🔥 Trigger Notifikasi ke Grup
        await notify_hit_to_group(context, user_data, data)

    else:
        # Data Tidak Ditemukan
        reply_text = f"❌ **DATA TIDAK DITEMUKAN**\n\nKeyword: `{user_input}`"
        await update.message.reply_text(reply_text, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 **MATEL BOT SYSTEM**\nKetik /register untuk mendaftar.", parse_mode='Markdown')

async def help_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text(
        "🛠 **MENU ADMIN**\n"
        "1. Upload File: Kirim file .xlsx/.csv langsung ke sini.\n"
        "2. /users - Lihat daftar user\n"
        "3. /ban <id> - Blokir user\n"
        "4. /unban <id> - Buka blokir\n"
        "5. /delete <id> - Hapus user\n"
        "6. /testgroup - Cek koneksi grup notifikasi"
    )

# ==============================================================================
#                               MAIN EXECUTION
# ==============================================================================

if __name__ == '__main__':
    application = ApplicationBuilder().token(token).build()

    # Conversation Handler (Register)
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
    
    # Command Handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('users', list_users))
    application.add_handler(CommandHandler('ban', ban_user))
    application.add_handler(CommandHandler('unban', unban_user))
    application.add_handler(CommandHandler('delete', delete_user))
    application.add_handler(CommandHandler('admin', help_admin))
    application.add_handler(CommandHandler('testgroup', test_group))

    # Callback Handler (Tombol)
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # File Upload Handler (Khusus Admin)
    # Menangkap semua jenis dokumen dari Admin ID
    application.add_handler(MessageHandler(filters.Document.ALL & filters.Chat(ADMIN_ID), handle_document_upload))
    
    # Main Message Handler (Pencarian Nopol)
    # Menangkap text biasa yang bukan command
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print(f"✅ Bot Matel berjalan... (Super Admin: {ADMIN_ID})")
    application.run_polling()