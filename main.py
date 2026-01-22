"""
################################################################################
#                                                                              #
#                      PROJECT: ONEASPAL BOT (ASSET RECOVERY)                  #
#                      VERSION: 6.10 (STRUCTURE FIX & STABILITY)               #
#                      ROLE:    MAIN APPLICATION CORE                          #
#                      AUTHOR:  CTO (GEMINI) & CEO (BAONK)                     #
#                                                                              #
################################################################################
"""

import os
import logging
import pandas as pd
import io
import numpy as np
import time
import re
import asyncio 
import csv 
import zipfile 
import html
from collections import Counter
from datetime import datetime, timedelta, time
import pytz 
from dotenv import load_dotenv

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, 
    ReplyKeyboardRemove, 
    constants,
    LinkPreviewOptions
)
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

# ##############################################################################
# BAGIAN 1: KONFIGURASI SISTEM
# ##############################################################################

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
TOKEN = os.environ.get("TELEGRAM_TOKEN")

TZ_JAKARTA = pytz.timezone('Asia/Jakarta')

DAILY_LIMIT_MATEL = 500  
DAILY_LIMIT_KORLAP = 2000 

GLOBAL_INFO = ""

BANK_INFO = """
🏧 <b>METODE PEMBAYARAN</b>
━━━━━━━━━━━━━━━━━━
<b>BCA:</b> UNDER CONSTRUCTION
<b>A/N:</b> UNDER CONSTRUCTION
━━━━━━━━━━━━━━━━━━
👇 <b>LANGKAH SELANJUTNYA:</b>
1. Transfer sesuai nominal paket.
2. <b>FOTO</b> bukti transfer Anda.
3. <b>KIRIM FOTO</b> tersebut ke chat ini.
4. Admin akan memproses akun Anda.
"""

# --- DIAGNOSTIC STARTUP ---
print("\n" + "="*50)
print("🔍 SYSTEM DIAGNOSTIC STARTUP (v6.10)")
print("="*50)

try:
    ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
    LOG_GROUP_ID = int(os.environ.get("LOG_GROUP_ID", 0))
    print(f"✅ ADMIN ID: {ADMIN_ID}")
    print(f"✅ LOG GROUP ID: {LOG_GROUP_ID}")
except ValueError:
    ADMIN_ID = 0
    LOG_GROUP_ID = 0
    print("❌ ERROR: ID di .env bukan angka!")

if not URL or not KEY or not TOKEN:
    print("❌ CRITICAL: Credential Hilang!")
    exit()

try:
    supabase: Client = create_client(URL, KEY)
    print("✅ Supabase: Connected")
except Exception as e:
    print(f"❌ Supabase Error: {e}")
    exit()

print("="*50 + "\n")


# ##############################################################################
# BAGIAN 2: KAMUS DATA
# ##############################################################################

COLUMN_ALIASES = {
    'nopol': ['nopol', 'nopolisi', 'nomorpolisi', 'noplat', 'nomorplat', 'tnkb', 'licenseplate', 'plat', 'police_no', 'plate_number', 'platenumber'],
    'type': ['type', 'tipe', 'unit', 'model', 'vehicle', 'jenis', 'deskripsiunit', 'merk', 'object', 'kendaraan', 'item', 'brand', 'product'],
    'tahun': ['tahun', 'year', 'thn', 'rakitan', 'th', 'yearofmanufacture', 'prod_year'],
    'warna': ['warna', 'color', 'colour', 'cat', 'kelir'],
    'noka': ['noka', 'norangka', 'nomorrangka', 'chassis', 'chasis', 'vin', 'rangka', 'chassisno', 'frameno', 'chassis_number'],
    'nosin': ['nosin', 'nomesin', 'nomormesin', 'engine', 'mesin', 'engineno', 'engine_number', 'machineno'],
    'finance': ['finance', 'leasing', 'lising', 'lesing', 'multifinance', 'partner', 'mitra', 'principal', 'client'],
    'ovd': ['ovd', 'overdue', 'dpd', 'keterlambatan', 'odh', 'hari', 'telat', 'aging', 'days_late'],
    'branch': ['branch', 'area', 'kota', 'pos', 'cabang', 'lokasi', 'wilayah', 'region']
}

VALID_DB_COLUMNS = ['nopol', 'type', 'finance', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'branch']


# ##############################################################################
# BAGIAN 3: DEFINISI STATE CONVERSATION
# ##############################################################################

R_ROLE_CHOICE, R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_CONFIRM = range(7)
A_NOPOL, A_TYPE, A_LEASING, A_NOKIRIMAN, A_OVD, A_KET, A_CONFIRM = range(7, 14)
L_NOPOL, L_REASON, L_CONFIRM = range(14, 17) 
D_NOPOL, D_CONFIRM = range(17, 19)
U_LEASING_USER, U_LEASING_ADMIN, U_CONFIRM_UPLOAD = range(19, 22)

REJECT_REASON = 22
ADMIN_ACT_REASON = 23
SUPPORT_MSG = 24
VAL_REJECT_REASON = 25


# ##############################################################################
# BAGIAN 4: HELPER FUNCTIONS (UTILITIES)
# ##############################################################################

async def post_init(application: Application):
    await application.bot.set_my_commands([
        ("start", "🔄 Restart / Menu"),
        ("cekkuota", "💳 Cek Masa Aktif"),
        ("stop", "⛔ Stop Proses Upload"),
        ("tambah", "➕ Input Manual"),
        ("lapor", "🗑️ Lapor Unit Selesai"),
        ("register", "📝 Daftar Mitra"),
        ("admin", "📩 Hubungi Admin"),
        ("panduan", "📖 Buku Panduan"),
    ])
    print("✅ [INIT] Command List Updated!")

def get_user(user_id):
    try:
        response = supabase.table('users').select("*").eq('user_id', user_id).execute()
        return response.data[0] if response.data else None
    except: return None

def update_user_status(user_id, status):
    try:
        supabase.table('users').update({'status': status}).eq('user_id', user_id).execute()
        return True
    except: return False

def check_subscription_access(user):
    try:
        if user.get('role') == 'pic': return True, "OK"

        expiry_str = user.get('expiry_date')
        if not expiry_str: return False, "EXPIRED"
        
        expiry_dt = datetime.fromisoformat(expiry_str.replace('Z', '+00:00')).astimezone(TZ_JAKARTA)
        if datetime.now(TZ_JAKARTA) > expiry_dt: return False, "EXPIRED"

        last_usage_str = user.get('last_usage_date')
        today_str = now_dt = datetime.now(TZ_JAKARTA).strftime('%Y-%m-%d')
        
        if last_usage_str != today_str:
            supabase.table('users').update({'daily_usage': 0, 'last_usage_date': today_str}).eq('user_id', user['user_id']).execute()
            user['daily_usage'] = 0
        
        limit = DAILY_LIMIT_KORLAP if user.get('role') == 'korlap' else DAILY_LIMIT_MATEL
        if user.get('daily_usage', 0) >= limit: return False, "DAILY_LIMIT"

        return True, "OK"
    except: return False, "ERROR"

def increment_daily_usage(user_id, current_usage):
    try:
        supabase.table('users').update({'daily_usage': current_usage + 1}).eq('user_id', user_id).execute()
    except: pass

def add_subscription_days(user_id, days):
    try:
        u = get_user(user_id)
        if not u: return False, None
        now = datetime.now(TZ_JAKARTA)
        curr_str = u.get('expiry_date')
        
        if curr_str:
            curr = datetime.fromisoformat(curr_str.replace('Z', '+00:00')).astimezone(TZ_JAKARTA)
            new_exp = (curr + timedelta(days=days)) if curr > now else (now + timedelta(days=days))
        else:
            new_exp = now + timedelta(days=days)
            
        supabase.table('users').update({'expiry_date': new_exp.isoformat()}).eq('user_id', user_id).execute()
        return True, new_exp
    except: return False, None

def clean_text(text):
    if not text: return "-"
    return html.escape(str(text))

def format_wa_link(phone_number):
    if not phone_number: return "-"
    clean_hp = re.sub(r'[^0-9]', '', str(phone_number))
    if clean_hp.startswith('0'):
        clean_hp = '62' + clean_hp[1:]
    return f'<a href="https://wa.me/{clean_hp}">{phone_number}</a>'

def standardize_leasing_name(name):
    if not name: return "UNKNOWN"
    clean = str(name).upper().strip()
    clean = re.sub(r'^\d+\s+', '', clean)
    return re.sub(r'\(.*?\)', '', clean).strip()

def log_successful_hit(user_id, user_name, unit_data):
    try:
        data = {
            "user_id": user_id, 
            "nama_matel": user_name,
            "leasing": str(unit_data.get('finance', 'UNKNOWN')).upper().strip(),
            "nopol": unit_data.get('nopol'), 
            "unit": unit_data.get('type')
        }
        supabase.table('finding_logs').insert(data).execute()
    except Exception as e: 
        print(f"Log Error: {e}")


# ##############################################################################
# BAGIAN 5: FILE PARSING & PREPARATION
# ##############################################################################

def normalize_text(text):
    return re.sub(r'[^a-zA-Z0-9]', '', str(text)).lower()

def fix_header_position(df):
    target = COLUMN_ALIASES['nopol']
    for i in range(min(30, len(df))): 
        vals = [normalize_text(str(x)) for x in df.iloc[i].values]
        if any(alias in vals for alias in target):
            df.columns = df.iloc[i] 
            return df.iloc[i+1:].reset_index(drop=True)
    return df

def smart_rename_columns(df):
    new = {}; found = []
    df.columns = [str(c).strip().replace('\ufeff', '') for c in df.columns]
    for col in df.columns:
        clean = normalize_text(col); renamed = False
        for std, aliases in COLUMN_ALIASES.items():
            if clean == std or clean in aliases:
                new[col] = std; found.append(std); renamed = True; break
        if not renamed: new[col] = col
    df.rename(columns=new, inplace=True)
    return df, found

def read_file_robust(content, fname):
    if fname.lower().endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            valid = [f for f in z.namelist() if f.lower().endswith(('.csv','.xlsx','.xls'))]
            if not valid: raise ValueError("ZIP Kosong")
            with z.open(valid[0]) as f: content = f.read()
    
    try: return pd.read_excel(io.BytesIO(content), dtype=str)
    except: pass
    
    for enc in ['utf-8-sig', 'latin1', 'utf-16']:
        try:
            df = pd.read_csv(io.BytesIO(content), sep=None, engine='python', dtype=str, encoding=enc)
            if len(df.columns) > 1: return df
        except: continue
    return pd.DataFrame()


# ##############################################################################
# BAGIAN 6: ADMIN ACTION HANDLERS
# ##############################################################################

async def angkat_korlap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        if len(context.args) < 2: return await update.message.reply_text("Format: /angkat_korlap [ID] [KOTA]")
        tid = int(context.args[0]); region = " ".join(context.args[1:]).upper()
        supabase.table('users').update({'role': 'korlap', 'wilayah_korlap': region, 'quota': 5000}).eq('user_id', tid).execute()
        await update.message.reply_text(f"✅ User {tid} jadi KORLAP {region}")
    except Exception as e: await update.message.reply_text(f"Gagal: {e}")

async def reject_start(update, context):
    query = update.callback_query; await query.answer()
    context.user_data['reg_msg_id'] = query.message.message_id
    context.user_data['reg_chat_id'] = query.message.chat_id
    context.user_data['reject_target_uid'] = query.data.split("_")[1]
    await context.bot.send_message(chat_id=update.effective_chat.id, text="📝 Ketik **ALASAN** Penolakan:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True))
    return REJECT_REASON

async def reject_complete(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    target_uid = context.user_data.get('reject_target_uid'); reason = update.message.text
    try: supabase.table('users').delete().eq('user_id', target_uid).execute()
    except: pass
    try: 
        msg_user = (f"⛔ **PENDAFTARAN DITOLAK**\n\n⚠️ <b>Alasan:</b> {reason}\n\n<i>Data Anda telah dihapus. Silakan lakukan registrasi ulang.</i>")
        await context.bot.send_message(target_uid, msg_user, parse_mode='HTML')
    except: pass
    try:
        mid = context.user_data.get('reg_msg_id'); cid = context.user_data.get('reg_chat_id')
        await context.bot.edit_message_reply_markup(chat_id=cid, message_id=mid, reply_markup=None)
        await context.bot.send_message(chat_id=cid, text=f"❌ User {target_uid} DITOLAK.\nAlasan: {reason}")
    except: pass
    await update.message.reply_text("✅ Proses Selesai.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

async def val_reject_start(update, context):
    query = update.callback_query; await query.answer()
    data = query.data.split("_")
    context.user_data['val_rej_nopol'] = data[2]
    context.user_data['val_rej_uid'] = data[3]
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"❌ **TOLAK PENGAJUAN**\nUnit: {data[2]}\n\nKetik ALASAN Penolakan:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True))
    return VAL_REJECT_REASON

async def val_reject_complete(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    nopol = context.user_data.get('val_rej_nopol')
    uid = context.user_data.get('val_rej_uid')
    reason = update.message.text
    try:
        msg = (f"⛔ **PENGAJUAN DITOLAK**\nUnit: {nopol}\n⚠️ <b>Alasan:</b> {reason}\n\nSilakan perbaiki data dan ajukan ulang.")
        await context.bot.send_message(chat_id=int(uid), text=msg, parse_mode='HTML')
    except: pass
    await update.message.reply_text(f"✅ Notifikasi dikirim.\nAlasan: {reason}", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def admin_action_start(update, context):
    query = update.callback_query; await query.answer()
    parts = query.data.split("_"); context.user_data['adm_act_type'] = parts[1]; context.user_data['adm_act_uid'] = parts[2]
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🛡️ **ACTION: {parts[1].upper()}**\nKetik ALASAN:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True))
    return ADMIN_ACT_REASON

async def admin_action_complete(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    act = context.user_data.get('adm_act_type'); uid = context.user_data.get('adm_act_uid'); reason = update.message.text
    if act == "ban": update_user_status(uid, 'rejected'); msg = f"⛔ **BANNED**\nAlasan: {reason}"
    elif act == "unban": update_user_status(uid, 'active'); msg = f"✅ **UNBANNED**\nCatatan: {reason}"
    elif act == "del": supabase.table('users').delete().eq('user_id', uid).execute(); msg = f"🗑️ **DELETED**\nAlasan: {reason}"
    try: await context.bot.send_message(uid, msg)
    except: pass
    await update.message.reply_text(f"✅ Action {act} Sukses.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END


# ##############################################################################
# BAGIAN 7: USER FEATURES (DEFINISI FUNGSI YANG HILANG SEBELUMNYA)
# ##############################################################################

async def start(update, context):
    u = get_user(update.effective_user.id)
    global GLOBAL_INFO
    info = f"📢 <b>INFO:</b> {clean_text(GLOBAL_INFO)}\n━━━━━━━━━━━━━━━━━━\n\n" if GLOBAL_INFO else ""
    
    if u and u.get('role') == 'pic':
        msg = (
            f"{info}🤖 <b>SYSTEM ONEASPAL (ENTERPRISE)</b>\n\n"
            f"Selamat Datang, <b>{clean_text(u.get('nama_lengkap'))}</b>\n"
            f"<i>Status: Verified Internal Staff</i>\n\n"
            f"<b>Workspace Anda Siap.</b>\n"
            f"Sinkronisasi data unit Anda ke dalam <i>Private Cloud</i> kami.\n\n"
            f"🔒 <b>Keamanan Data Terjamin.</b>"
        )
        kb = [["🔄 SINKRONISASI DATA", "📂 DATABASE SAYA"], ["📞 BANTUAN TEKNIS"]]
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return

    if u:
        msg = (
            f"{info}🤖 <b>Selamat Datang di Oneaspalbot</b>\n\n"
            f"<b>Salam Satu Aspal!</b> 👋\n"
            f"Halo, Rekan Mitra Lapangan.\n\n"
            f"<b>Oneaspalbot</b> adalah asisten digital profesional.\n\n"
            f"Cari data melalui:\n✅ Nomor Polisi (Nopol)\n✅ Nomor Rangka (Noka)\n✅ Nomor Mesin (Nosin)"
        )
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=ReplyKeyboardRemove())
        return

    msg_guest = (
        f"🤖 <b>ONEASPAL: Digital Asset Recovery System</b>\n"
        f"<i>Sistem Manajemen Database Aset Fidusia Terpadu</i>\n\n"
        f"Selamat Datang di Ekosistem OneAspal.\n"
        f"Platform ini dirancang khusus untuk menunjang efektivitas profesi:\n\n"
        f"1️⃣ <b>INTERNAL LEASING & COLLECTION</b>\n"
        f"Transformasi digital pengelolaan data aset.\n\n"
        f"2️⃣ <b>PROFESI JASA PENAGIHAN (MATEL)</b>\n"
        f"Dukungan data <i>real-time</i> dengan akurasi tinggi.\n\n"
        f"🔐 <b>Akses Terbatas (Private System)</b>\n"
        f"Silakan lakukan registrasi:\n👉 /register\n\n"
        f"<i>Salam Satu Aspal.</i>"
    )
    await update.message.reply_text(msg_guest, parse_mode='HTML')

async def panduan(update, context):
    u = get_user(update.effective_user.id)
    if u and u.get('role') == 'pic': 
        msg = (
            "📖 <b>PANDUAN ENTERPRISE WORKSPACE</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            "1️⃣ <b>SINKRONISASI DATA (Private Cloud)</b>\n"
            "• Klik tombol <b>🔄 SINKRONISASI DATA</b>.\n"
            "• Upload file Excel data tarikan Anda.\n"
            "• Data akan diamankan di server pribadi (Tidak terlihat user lain).\n\n"
            "2️⃣ <b>MONITORING UNIT</b>\n"
            "• Sistem bekerja otomatis 24 jam.\n"
            "• Jika Matel menemukan unit Anda, Notifikasi akan masuk ke:\n"
            "   👉 <b>GRUP LEASING OFFICIAL</b> (Pastikan Grup sudah didaftarkan).\n\n"
            "3️⃣ <b>CEK STATUS DATA (VALIDASI)</b>\n"
            "• Ingin memastikan data sudah masuk atau sudah terhapus?\n"
            "• Cukup <b>ketik Nopol</b> unit tersebut di sini.\n"
            "• Jika muncul = Data Aktif (Tayang).\n"
            "• Jika 'Tidak Ditemukan' = Data Sudah Bersih.\n\n"
            "4️⃣ <b>MANAJEMEN ARSIP</b>\n"
            "• Untuk menghapus data unit yang sudah lunas/aman, gunakan fitur <b>Update/Hapus Massal</b> saat upload file baru.\n\n"
            "<i>Butuh bantuan? Klik tombol 📞 BANTUAN TEKNIS.</i>"
        )
    else: 
        msg = (
            "📖 <b>PANDUAN PENGGUNAAN ONEASPAL</b>\n\n"
            "1️⃣ <b>Cari Data Kendaraan</b>\n"
            "   - Ketik Nopol secara lengkap atau sebagian.\n"
            "   - Contoh: <code>B 1234 ABC</code> atau <code>1234</code>\n\n"
            "2️⃣ <b>Upload File (Mitra)</b>\n"
            "   - Kirim file Excel/CSV/ZIP ke bot ini.\n"
            "   - Bot akan membaca otomatis.\n\n"
            "3️⃣ <b>Upload Satuan / Kiriman</b>\n"
            "   - Gunakan perintah /tambah untuk input data manual.\n\n"
            "4️⃣ <b>Lapor Unit Selesai</b>\n"
            "   - Gunakan perintah /lapor jika unit sudah ditarik.\n\n"
            "5️⃣ <b>Cek Kuota</b>\n"
            "   - Ketik /cekkuota untuk melihat sisa HIT.\n\n"
            "6️⃣ <b>Bantuan Admin</b>\n"
            "   - Ketik /admin [pesan] untuk support.\n\n"
            "7️⃣ <b>Perpanjang Langganan</b>\n"
            "   - Ketik /infobayar untuk Topup."
        )
    await update.message.reply_text(msg, parse_mode='HTML')

# --- FUNGSI CEK KUOTA YANG SEBELUMNYA CRASH ---
async def cek_kuota(update, context):
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return
    
    global GLOBAL_INFO
    info_banner = f"📢 <b>INFO PUSAT:</b> {clean_text(GLOBAL_INFO)}\n━━━━━━━━━━━━━━━━━━\n" if GLOBAL_INFO else ""
    
    if u.get('role') == 'pic':
        msg = (
            f"{info_banner}📂 **DATABASE SAYA**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 **User:** {u.get('nama_lengkap')}\n"
            f"🏢 **Leasing:** {u.get('agency')}\n"
            f"🔋 **Status Akses:** UNLIMITED (Enterprise)\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✅ Sinkronisasi data berjalan normal."
        )
    else:
        exp_date = u.get('expiry_date')
        status_aktif = "❌ SUDAH EXPIRED"
        
        if exp_date:
            exp_dt = datetime.fromisoformat(exp_date.replace('Z', '+00:00')).astimezone(TZ_JAKARTA)
            status_aktif = f"✅ AKTIF s/d {exp_dt.strftime('%d %b %Y %H:%M')}"
            remaining = exp_dt - datetime.now(TZ_JAKARTA)
            if remaining.days < 0: status_aktif = "❌ SUDAH EXPIRED"
            else: status_aktif += f"\n⏳ Sisa Waktu: {remaining.days} Hari"
        
        role_msg = f"🎖️ **KORLAP {u.get('wilayah_korlap','') or ''}**" if u.get('role') == 'korlap' else f"🛡️ **MITRA LAPANGAN**"
        
        msg = (
            f"{info_banner}💳 **INFO LANGGANAN**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{role_msg}\n"
            f"👤 {u.get('nama_lengkap')}\n\n"
            f"{status_aktif}\n"
            f"📊 <b>Cek Hari Ini:</b> {u.get('daily_usage', 0)}x\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<i>Perpanjang? Ketik /infobayar</i>"
        )
        
    await update.message.reply_text(msg, parse_mode='HTML')

async def info_bayar(update, context):
    msg = (
        f"💰 **PAKET LANGGANAN**\n━━━━━━━━━━━━━━━━━━\n"
        f"1️⃣ **5 HARI** = Rp 25.000\n"
        f"2️⃣ **10 HARI** = Rp 50.000\n"
        f"3️⃣ **20 HARI** = Rp 75.000\n"
        f"🔥 **30 HARI** = Rp 100.000\n\n"
        f"{BANK_INFO}"
    )
    await update.message.reply_text(msg, parse_mode='HTML')

async def handle_photo_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    u = get_user(update.effective_user.id)
    if not u: return
    
    await update.message.reply_text("✅ **Bukti diterima!** Sedang diverifikasi Admin...", quote=True)
    msg = (
        f"💰 **TOPUP DURASI REQUEST**\n"
        f"👤 {u['nama_lengkap']}\n"
        f"🆔 `{u['user_id']}`\n"
        f"📝 Note: {update.message.caption or '-'}\n\n"
        f"👉 <b>Manual:</b> <code>/topup {u['user_id']} [HARI]</code>"
    )
    kb = [
        [InlineKeyboardButton("✅ 5 HARI", callback_data=f"topup_{u['user_id']}_5"), InlineKeyboardButton("✅ 10 HARI", callback_data=f"topup_{u['user_id']}_10")],
        [InlineKeyboardButton("✅ 20 HARI", callback_data=f"topup_{u['user_id']}_20"), InlineKeyboardButton("✅ 30 HARI", callback_data=f"topup_{u['user_id']}_30")],
        [InlineKeyboardButton("🔢 MANUAL / CUSTOM", callback_data=f"man_topup_{u['user_id']}")],
        [InlineKeyboardButton("❌ TOLAK", callback_data=f"topup_{u['user_id']}_rej")]
    ]
    await context.bot.send_photo(ADMIN_ID, update.message.photo[-1].file_id, caption=msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

async def cancel(update, context): 
    await update.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ##############################################################################
# BAGIAN 8: NOTIFIKASI & LOGGING
# ##############################################################################

async def notify_leasing_group(context, matel_user, unit_data):
    leasing_unit = str(unit_data.get('finance', '')).strip().upper()
    if len(leasing_unit) < 3: return
    try:
        res = supabase.table('leasing_groups').select("*").execute()
        target_group_ids = []
        for g in res.data:
            if str(g['leasing_name']).upper() in leasing_unit or leasing_unit in str(g['leasing_name']).upper():
                target_group_ids.append(g['group_id'])
        
        if not target_group_ids: return
        
        hp_wa = format_wa_link(matel_user.get('no_hp'))
        
        msg_group = (
            f"🚨 <b>UNIT DITEMUKAN! (HIT)</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Penemu:</b> {clean_text(matel_user.get('nama_lengkap'))} ({clean_text(matel_user.get('agency'))})\n"
            f"📍 <b>Kota:</b> {clean_text(matel_user.get('alamat'))}\n\n"
            f"🚙 <b>Unit:</b> {clean_text(unit_data.get('type'))}\n"
            f"🔢 <b>Nopol:</b> {clean_text(unit_data.get('nopol'))}\n"
            f"📅 <b>Tahun:</b> {clean_text(unit_data.get('tahun'))}\n"
            f"🎨 <b>Warna:</b> {clean_text(unit_data.get('warna'))}\n"
            f"----------------------------------\n"
            f"🔧 <b>Noka:</b> {clean_text(unit_data.get('noka'))}\n"
            f"⚙️ <b>Nosin:</b> {clean_text(unit_data.get('nosin'))}\n"
            f"----------------------------------\n"
            f"⚠️ <b>OVD:</b> {clean_text(unit_data.get('ovd'))}\n"
            f"🏦 <b>Finance:</b> {clean_text(unit_data.get('finance'))}\n"
            f"🏢 <b>Branch:</b> {clean_text(unit_data.get('branch'))}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        
        # Link WA di tombol (harus murni angka)
        hp_num = re.sub(r'[^0-9]', '', str(matel_user.get('no_hp')))
        if hp_num.startswith('0'): hp_num = '62' + hp_num[1:]
        kb = [[InlineKeyboardButton("📞 Hubungi Penemu (WA)", url=f"https://wa.me/{hp_num}")]]
        
        for gid in target_group_ids:
            try: await context.bot.send_message(gid, msg_group, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
            except: pass
    except: pass

async def notify_hit_to_group(context, u, d):
    try:
        if LOG_GROUP_ID == 0: return
        hp_num = re.sub(r'[^0-9]', '', str(u.get('no_hp')))
        if hp_num.startswith('0'): hp_num = '62' + hp_num[1:]
        
        msg = (
            f"🚨 <b>UNIT DITEMUKAN! (HIT)</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Penemu:</b> {clean_text(u.get('nama_lengkap'))} ({clean_text(u.get('agency'))})\n"
            f"📍 <b>Kota:</b> {clean_text(u.get('alamat'))}\n\n"
            f"🚙 <b>Unit:</b> {clean_text(d.get('type'))}\n"
            f"🔢 <b>Nopol:</b> {clean_text(d.get('nopol'))}\n"
            f"📅 <b>Tahun:</b> {clean_text(d.get('tahun'))}\n"
            f"🎨 <b>Warna:</b> {clean_text(d.get('warna'))}\n"
            f"----------------------------------\n"
            f"🔧 <b>Noka:</b> {clean_text(d.get('noka'))}\n"
            f"⚙️ <b>Nosin:</b> {clean_text(d.get('nosin'))}\n"
            f"----------------------------------\n"
            f"⚠️ <b>OVD:</b> {clean_text(d.get('ovd'))}\n"
            f"🏦 <b>Finance:</b> {clean_text(d.get('finance'))}\n"
            f"🏢 <b>Branch:</b> {clean_text(d.get('branch'))}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        kb = [[InlineKeyboardButton("📞 Hubungi Penemu (WA)", url=f"https://wa.me/{hp_num}")]]
        await context.bot.send_message(LOG_GROUP_ID, msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    except Exception as e: print(f"❌ Gagal Kirim Notif Admin Pusat: {e}")


# ##############################################################################
# BAGIAN 9: BACKGROUND WORKER & UPLOAD
# ##############################################################################

async def background_upload_process(update, context, act, data, chat_id):
    stop_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⛔ HENTIKAN PROSES", callback_data="stop_upload_task")]])
    status_msg = await context.bot.send_message(chat_id=chat_id, text=f"🚀 <b>MEMULAI {act}...</b>\nMohon tunggu. Jangan kirim file lain dulu.", parse_mode='HTML', reply_markup=stop_kb)
    
    BATCH_SIZE = 50
    total = len(data)
    success = 0
    fail = 0
    errors = []
    
    context.user_data['stop_signal'] = False
    start_time = time.time()
    
    try:
        for i in range(0, total, BATCH_SIZE):
            if context.user_data.get('stop_signal'):
                await status_msg.edit_text("⛔ <b>PROSES DIHENTIKAN OLEH USER.</b>", reply_markup=None)
                return

            chunk = data[i:i+BATCH_SIZE]
            nops = [str(x['nopol']) for x in chunk]
            
            try:
                if act == "🚀 UPDATE DATA":
                    await asyncio.to_thread(lambda: supabase.table('kendaraan').upsert(chunk, on_conflict='nopol').execute())
                
                elif act == "🗑️ HAPUS MASSAL":
                    try:
                        await asyncio.to_thread(lambda: supabase.rpc('delete_by_nopol', {'nopol_list': nops}).execute())
                    except:
                        await asyncio.to_thread(lambda: supabase.table('kendaraan').delete().in_('nopol', nops).execute())

                success += len(chunk)
            
            except Exception as e:
                fail += len(chunk)
                err_txt = str(e)
                if "timeout" in err_txt.lower(): err_txt = "Connection Timeout"
                elif "json" in err_txt.lower(): err_txt = "Server Error"
                errors.append(err_txt)
                print(f"Batch Error: {err_txt}")

            if i % 200 == 0 and i > 0:
                pct = int((i/total)*100)
                try:
                    await status_msg.edit_text(f"⏳ <b>PROGRESS: {pct}%</b>\n✅ Sukses: {success}\n❌ Gagal: {fail}", parse_mode='HTML', reply_markup=stop_kb)
                except: pass
            
            await asyncio.sleep(0.5) 

        dur = round(time.time() - start_time, 1)
        err_report = f"\n⚠️ <b>Sebab Error:</b> {errors[0]}" if errors else ""
        final_rpt = (f"✅ <b>SELESAI ({act})</b>\n━━━━━━━━━━━━━━━━━━\n📊 Total: {total:,}\n✅ Berhasil: {success:,}\n❌ Gagal: {fail:,}\n⏱ Waktu: {dur}s{err_report}")
        await status_msg.edit_text(final_rpt, parse_mode='HTML', reply_markup=None)

    except Exception as e:
        await status_msg.edit_text(f"❌ <b>CRITICAL ERROR:</b> {e}", reply_markup=None)

async def stop_upload_command(update, context):
    if update.effective_user.id != ADMIN_ID: return
    context.user_data['stop_signal'] = True
    await update.message.reply_text("🛑 Sinyal STOP dikirim. Menunggu batch terakhir selesai...")

async def upload_start(update, context):
    if update.effective_user.id != ADMIN_ID: 
        await update.message.reply_text("📄 Kirim file Excel/CSV.")
        return U_LEASING_USER
    
    context.user_data['fid'] = update.message.document.file_id
    msg = await update.message.reply_text("⏳ <b>Membaca File...</b>", parse_mode='HTML')
    
    try:
        f = await update.message.document.get_file()
        c = await f.download_as_bytearray()
        df = read_file_robust(c, update.message.document.file_name)
        df = fix_header_position(df)
        df, found = smart_rename_columns(df)
        
        if 'nopol' not in df.columns:
            await msg.edit_text("❌ Kolom NOPOL tidak ditemukan.")
            return ConversationHandler.END
            
        context.user_data['df'] = df.to_dict(orient='records')
        await msg.delete()
        
        txt = (
            f"✅ <b>FILE TERBACA</b>\n"
            f"Total Baris: {len(df)}\n"
            f"Kolom: {', '.join(found)}\n\n"
            f"Ketik Nama Leasing (atau SKIP):"
        )
        await update.message.reply_text(txt, reply_markup=ReplyKeyboardMarkup([["SKIP", "❌ BATAL"]], resize_keyboard=True), parse_mode='HTML')
        return U_LEASING_ADMIN
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")
        return ConversationHandler.END

async def upload_leasing_admin(update, context):
    nm = update.message.text
    if nm == "❌ BATAL": return await cancel(update, context)
    
    msg = await update.message.reply_text("⏳ <b>Membersihkan Data...</b>", parse_mode='HTML')
    
    def clean_data(raw, name):
        df = pd.DataFrame(raw).astype(str)
        if name != 'SKIP': df['finance'] = standardize_leasing_name(name)
        df['nopol'] = df['nopol'].str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        df = df[df['nopol'].str.len() > 2].drop_duplicates('nopol', keep='last')
        df = df.replace({'nan': '-', 'None': '-', 'NaN': '-'})
        
        final = pd.DataFrame()
        for c in VALID_DB_COLUMNS: 
            final[c] = df[c] if c in df.columns else "-"
        return final.to_dict(orient='records')

    final_data = await asyncio.to_thread(clean_data, context.user_data['df'], nm)
    context.user_data['final_df'] = final_data
    
    await msg.delete()
    
    txt = (
        f"🔎 <b>SIAP EKSEKUSI</b>\n"
        f"Total Bersih: {len(final_data)} Data\n\n"
        f"Pilih Tindakan:"
    )
    kb = [["🚀 UPDATE DATA"], ["🗑️ HAPUS MASSAL"], ["❌ BATAL"]]
    await update.message.reply_text(txt, reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True), parse_mode='HTML')
    return U_CONFIRM_UPLOAD

async def upload_confirm_admin(update, context):
    act = update.message.text
    if act == "❌ BATAL": return await cancel(update, context)
    
    data = context.user_data.get('final_df')
    chat_id = update.effective_chat.id
    
    await update.message.reply_text("🆗 Perintah diterima. Memproses di latar belakang...", reply_markup=ReplyKeyboardRemove())
    
    asyncio.create_task(background_upload_process(update, context, act, data, chat_id))
    return ConversationHandler.END

async def upload_leasing_user(update, context):
    await update.message.reply_text("✅ Terkirim.")
    return ConversationHandler.END


# ##############################################################################
# BAGIAN 10: ADMIN FEATURES & CALLBACKS
# ##############################################################################

async def list_users(update, context):
    if update.effective_user.id != ADMIN_ID: return
    await context.bot.send_chat_action(update.effective_chat.id, constants.ChatAction.TYPING)
    try:
        res = supabase.table('users').select("*").execute()
        active_list = [u for u in res.data if u.get('status') == 'active']
        
        pic_list = [u for u in active_list if u.get('role') == 'pic']
        field_list = [u for u in active_list if u.get('role') != 'pic'] 
        
        pic_list.sort(key=lambda x: (x.get('nama_lengkap') or "").lower())
        field_list.sort(key=lambda x: (x.get('nama_lengkap') or "").lower())
        
        if not active_list: return await update.message.reply_text("📂 Tidak ada mitra aktif.")
        
        msg = f"📋 <b>DAFTAR MITRA (Total: {len(active_list)})</b>\n━━━━━━━━━━━━━━━━━━\n"
        no_preview = LinkPreviewOptions(is_disabled=True)

        if pic_list:
            msg += "🏦 <b>INTERNAL LEASING (PIC)</b>\n"
            for i, u in enumerate(pic_list, 1):
                nama = clean_text(u.get('nama_lengkap'))
                agency = clean_text(u.get('agency'))
                wa_link = format_wa_link(u.get('no_hp')) 
                uid = u['user_id']
                entry = (f"{i}. 🤝 <b>{nama}</b>\n   📱 {wa_link} | 🏢 {agency}\n   ⚙️ /m_{uid}\n\n")
                if len(msg) + len(entry) > 4000: 
                    await update.message.reply_text(msg, parse_mode='HTML', link_preview_options=no_preview)
                    msg = ""
                msg += entry
            msg += "━━━━━━━━━━━━━━━━━━\n"

        if field_list:
            msg += "🛡️ <b>MITRA LAPANGAN</b>\n"
            for i, u in enumerate(field_list, 1):
                role = u.get('role', 'matel')
                icon = "🎖️" if role == 'korlap' else "🛡️"
                nama = clean_text(u.get('nama_lengkap'))
                agency = clean_text(u.get('agency'))
                wa_link = format_wa_link(u.get('no_hp'))
                uid = u['user_id']
                entry = (f"{i}. {icon} <b>{nama}</b>\n   📱 {wa_link} | 🏢 {agency}\n   ⚙️ /m_{uid}\n\n")
                if len(msg) + len(entry) > 4000: 
                    await update.message.reply_text(msg, parse_mode='HTML', link_preview_options=no_preview)
                    msg = ""
                msg += entry
            
        if msg: await update.message.reply_text(msg, parse_mode='HTML', link_preview_options=no_preview)

    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def manage_user_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid = int(update.message.text.split('_')[1])
        u = get_user(tid)
        if not u: return await update.message.reply_text("❌ User tidak ditemukan.")
        
        role_now = u.get('role', 'matel')
        status_now = u.get('status', 'active')
        info_role = "🎖️ KORLAP" if role_now == 'korlap' else f"🛡️ {role_now.upper()}"
        wilayah = f"({u.get('wilayah_korlap', '-')})" if role_now == 'korlap' else ""
        icon_status = "✅ AKTIF" if status_now == 'active' else "⛔ BANNED"
        
        expiry = u.get('expiry_date', 'EXPIRED')
        if expiry != 'EXPIRED': 
            expiry = datetime.fromisoformat(expiry.replace('Z', '+00:00')).astimezone(TZ_JAKARTA).strftime('%d %b %Y')
        
        wa_link = format_wa_link(u.get('no_hp'))
        
        msg = (
            f"👮‍♂️ <b>USER MANAGER</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Nama:</b> {clean_text(u.get('nama_lengkap'))}\n"
            f"📱 <b>WA:</b> {wa_link}\n"
            f"🏅 <b>Role:</b> {info_role} {wilayah}\n"
            f"📊 <b>Status:</b> {icon_status}\n"
            f"📱 <b>ID:</b> <code>{tid}</code>\n"
            f"📅 <b>Exp:</b> {expiry}\n"
            f"🏢 <b>Agency:</b> {clean_text(u.get('agency'))}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        
        btn_role = InlineKeyboardButton("⬇️ BERHENTIKAN KORLAP", callback_data=f"adm_demote_{tid}") if role_now == 'korlap' else InlineKeyboardButton("🎖️ ANGKAT KORLAP", callback_data=f"adm_promote_{tid}")
        btn_ban = InlineKeyboardButton("⛔ BAN USER", callback_data=f"adm_ban_{tid}") if status_now == 'active' else InlineKeyboardButton("✅ UNBAN (PULIHKAN)", callback_data=f"adm_unban_{tid}")
        kb = [[InlineKeyboardButton("📅 +5 Hari", callback_data=f"adm_topup_{tid}_5"), InlineKeyboardButton("📅 +30 Hari", callback_data=f"adm_topup_{tid}_30")], [btn_role], [btn_ban, InlineKeyboardButton("🗑️ HAPUS DATA", callback_data=f"adm_del_{tid}")], [InlineKeyboardButton("❌ TUTUP PANEL", callback_data="close_panel")]]
        
        no_preview = LinkPreviewOptions(is_disabled=True)
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML', link_preview_options=no_preview)
        
    except Exception as e: await update.message.reply_text(f"❌ Error Panel: {e}")

async def callback_handler(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "stop_upload_task":
        context.user_data['stop_signal'] = True
        await query.edit_message_text("🛑 <b>BERHENTI!</b>\nMenunggu proses batch terakhir selesai...", parse_mode='HTML')

    elif data.startswith("view_"):
        nopol = data.replace("view_", "")
        u = get_user(update.effective_user.id)
        res = supabase.table('kendaraan').select("*").eq('nopol', nopol).execute()
        if res.data: await show_unit_detail_original(update, context, res.data[0], u)
        else: await query.edit_message_text("❌ Data unit sudah tidak tersedia.")
    
    elif data.startswith("topup_"):
        parts = data.split("_")
        uid = int(parts[len(parts)-2])
        days = parts[len(parts)-1]
        if days == "rej":
            await context.bot.send_message(uid, "❌ Permintaan Topup DITOLAK Admin.")
            await query.edit_message_caption("❌ DITOLAK.")
        else:
            suc, new_exp = add_subscription_days(uid, int(days))
            if suc:
                exp_str = new_exp.strftime('%d %b %Y')
                await context.bot.send_message(uid, f"✅ **TOPUP SUKSES!**\nPaket: {days} Hari\nAktif s/d: {exp_str}")
                await query.edit_message_caption(f"✅ SUKSES (+{days} Hari)\nExp: {exp_str}")
            else: await query.edit_message_caption("❌ Gagal System.")

    elif data.startswith("man_topup_"):
        uid = data.split("_")[2]
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"ℹ️ **MODE MANUAL**\n\nSilakan ketik perintah berikut:\n<code>/topup {uid} [JUMLAH_HARI]</code>", parse_mode='HTML')

    elif data.startswith("adm_promote_"):
        uid = int(data.split("_")[2])
        supabase.table('users').update({'role': 'korlap'}).eq('user_id', uid).execute()
        await query.edit_message_text(f"✅ User {uid} DIPROMOSIKAN jadi KORLAP.")
        try: await context.bot.send_message(uid, "🎉 **SELAMAT!** Anda telah diangkat menjadi **KORLAP**.")
        except: pass

    elif data.startswith("adm_demote_"):
        uid = int(data.split("_")[2])
        supabase.table('users').update({'role': 'matel'}).eq('user_id', uid).execute()
        await query.edit_message_text(f"⬇️ User {uid} DITURUNKAN jadi MATEL.")

    elif data == "close_panel":
        await query.delete_message()
    
    elif data.startswith("appu_"): 
        target_uid = int(data.split("_")[1])
        update_user_status(target_uid, 'active')
        await query.edit_message_text(f"✅ User {target_uid} telah Diaktifkan.")
        try: await context.bot.send_message(target_uid, "🎉 **AKUN AKTIF!**", parse_mode='Markdown')
        except: pass

    elif data.startswith("reju_"):
        uid = data.split("_")[1]
        update_user_status(uid, 'rejected')
        await query.edit_message_text("❌ User TOLAK.")
        try: await context.bot.send_message(uid, "⛔ Pendaftaran Ditolak.")
        except: pass

    elif data.startswith("v_acc_"): 
        n = data.split("_")[2]
        item = context.bot_data.get(f"prop_{n}")
        if item:
            supabase.table('kendaraan').upsert(item).execute()
            await query.edit_message_text("✅ Masuk DB.")
            await context.bot.send_message(data.split("_")[3], f"✅ Data `{n}` DISETUJUI & Sudah Tayang.")
        else: await query.edit_message_text("⚠️ Data kedaluwarsa (Restart bot).")

    elif data.startswith("del_acc_"):
        nopol = data.split("_")[2]
        supabase.table('kendaraan').delete().eq('nopol', nopol).execute()
        await query.edit_message_text("✅ Dihapus.")
        await context.bot.send_message(data.split("_")[3], "✅ Hapus ACC.")

    elif data.startswith("del_rej_"):
        await query.edit_message_text("❌ Ditolak.")
        await context.bot.send_message(data.split("_")[2], "❌ Hapus TOLAK.")

async def handle_message(update, context):
    text = update.message.text
    if text == "🔄 SINKRONISASI DATA": return await upload_start(update, context)
    if text == "📂 DATABASE SAYA": return await cek_kuota(update, context)
    
    u = get_user(update.effective_user.id)
    if not u: return await update.message.reply_text("⛔ **AKSES DITOLAK**\nSilakan ketik /register.", parse_mode='Markdown')
    if u['status'] != 'active': return await update.message.reply_text("⏳ **AKUN PENDING**\nTunggu Admin.", parse_mode='Markdown')
    
    is_active, reason = check_subscription_access(u)
    if not is_active:
        if reason == "EXPIRED": return await update.message.reply_text("⛔ **MASA AKTIF HABIS**\nSilakan ketik /infobayar untuk perpanjang.", parse_mode='Markdown')
        elif reason == "DAILY_LIMIT": return await update.message.reply_text("⛔ **BATAS HARIAN TERCAPAI**", parse_mode='Markdown')

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    kw = re.sub(r'[^a-zA-Z0-9]', '', text.upper())
    if len(kw) < 3: return await update.message.reply_text("⚠️ Minimal 3 karakter.")

    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.ilike.%{kw}%,noka.eq.{kw},nosin.eq.{kw}").limit(20).execute()
        data_found = res.data
        if not data_found: return await update.message.reply_text(f"❌ <b>TIDAK DITEMUKAN</b>\n<code>{kw}</code>", parse_mode='HTML')

        final_result = None; exact_match = False
        for item in data_found:
            clean_db_nopol = re.sub(r'[^a-zA-Z0-9]', '', item['nopol']).upper()
            if clean_db_nopol == kw: final_result = item; exact_match = True; break
        
        if exact_match: await show_unit_detail_original(update, context, final_result, u)
        elif len(data_found) == 1: await show_unit_detail_original(update, context, data_found[0], u)
        else: await show_multi_choice(update, context, data_found, kw)
    except Exception as e: 
        logger.error(f"Search error: {e}")
        await update.message.reply_text("❌ Error DB.")

async def show_multi_choice(update, context, data_list, keyword):
    global GLOBAL_INFO
    info_txt = f"📢 INFO: {GLOBAL_INFO}\n\n" if GLOBAL_INFO else ""
    txt = f"{info_txt}🔎 Ditemukan **{len(data_list)} data** mirip '`{keyword}`':\n\n"
    keyboard = []
    for i, item in enumerate(data_list):
        nopol = item['nopol']; unit = item.get('type', 'Unknown')[:10]; leasing = item.get('finance', 'Unknown')
        keyboard.append([InlineKeyboardButton(f"{nopol} | {unit} | {leasing}", callback_data=f"view_{item['nopol']}")])
        if i >= 9: break 
    if len(data_list) > 10: txt += "_(Menampilkan 10 hasil teratas)_"
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- HANDLER MANUAL INPUT ---
async def add_data_start(update, context):
    if not get_user(update.effective_user.id): return
    await update.message.reply_text("➕ **TAMBAH UNIT BARU**\n\n1️⃣ Masukkan **Nomor Polisi (Nopol)**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True), parse_mode='Markdown'); return A_NOPOL
async def add_nopol(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['a_nopol'] = update.message.text.upper(); await update.message.reply_text("2️⃣ Masukkan **Tipe/Jenis Kendaraan**:", parse_mode='Markdown'); return A_TYPE
async def add_type(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['a_type'] = update.message.text.upper(); await update.message.reply_text("3️⃣ Masukkan **Nama Leasing/Finance**:", parse_mode='Markdown'); return A_LEASING
async def add_leasing(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['a_leasing'] = update.message.text.upper(); await update.message.reply_text("4️⃣ Masukkan **Nomor Kiriman**:\n_(Ketik '-' jika tidak ada)_", parse_mode='Markdown'); return A_NOKIRIMAN
async def add_nokiriman(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['a_nokiriman'] = update.message.text; await update.message.reply_text("5️⃣ Masukkan **OVD (Overdue)**:\n_(Contoh: 300 Hari)_", parse_mode='Markdown'); return A_OVD
async def add_ovd(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['a_ovd'] = update.message.text; await update.message.reply_text("6️⃣ Masukkan **Keterangan Tambahan**:\n_(Ketik '-' jika tidak ada)_", parse_mode='Markdown'); return A_KET
async def add_ket(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['a_ket'] = update.message.text; summary = (f"📝 **KONFIRMASI DATA**\n▪️ Nopol: `{context.user_data['a_nopol']}`\n▪️ Unit: {context.user_data['a_type']}\n▪️ Leasing: {context.user_data['a_leasing']}\n▪️ No. Kiriman: {context.user_data['a_nokiriman']}\n▪️ OVD: {context.user_data['a_ovd']}\n▪️ Ket: {context.user_data['a_ket']}")
    await update.message.reply_text(f"{summary}\n\n✅ Kirim ke Admin?", reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ BATAL"]]), parse_mode='Markdown'); return A_CONFIRM
async def add_confirm(update, context):
    if update.message.text != "✅ KIRIM": return await cancel(update, context)
    u = get_user(update.effective_user.id); n = context.user_data['a_nopol']
    context.bot_data[f"prop_{n}"] = {"nopol": n, "type": context.user_data['a_type'], "finance": context.user_data['a_leasing'], "ovd": context.user_data['a_ovd'], "branch": context.user_data['a_nokiriman'], "warna": context.user_data['a_ket']}
    await update.message.reply_text("✅ **Permintaan Terkirim!**\nAdmin akan memverifikasi data Anda.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
    msg_admin = (f"📥 **PENGAJUAN DATA BARU**\n━━━━━━━━━━━━━━━━━━\n👤 **Mitra:** {clean_text(u.get('nama_lengkap'))}\n🏢 **Agency:** {clean_text(u.get('agency'))}\n━━━━━━━━━━━━━━━━━━\n🔢 **Nopol:** `{n}`\n🚙 **Unit:** {context.user_data['a_type']}\n🏦 **Leasing:** {context.user_data['a_leasing']}\n📄 **No. Kiriman:** {context.user_data['a_nokiriman']}\n⚠️ **OVD:** {context.user_data['a_ovd']}\n📝 **Ket:** {context.user_data['a_ket']}\n━━━━━━━━━━━━━━━━━━")
    kb = [[InlineKeyboardButton("✅ Terima", callback_data=f"v_acc_{n}_{u['user_id']}"), InlineKeyboardButton("❌ Tolak", callback_data=f"v_rej_{n}_{u['user_id']}")]]
    await context.bot.send_message(ADMIN_ID, msg_admin, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'); return ConversationHandler.END

async def lapor_delete_start(update, context):
    if not get_user(update.effective_user.id): return
    msg = ("🗑️ **LAPOR UNIT SELESAI/AMAN**\n\nAdmin akan memverifikasi laporan ini sebelum data dihapus.\n\n👉 **Masukkan Nomor Polisi (Nopol) unit:**")
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True), parse_mode='Markdown'); return L_NOPOL
async def lapor_delete_check(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    n = update.message.text.upper().replace(" ", ""); res = supabase.table('kendaraan').select("*").eq('nopol', n).execute()
    if not res.data: await update.message.reply_text(f"❌ Nopol `{n}` tidak ditemukan di database.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown'); return ConversationHandler.END
    unit_data = res.data[0]; context.user_data['lapor_nopol'] = n; context.user_data['lapor_type'] = unit_data.get('type', '-'); context.user_data['lapor_finance'] = unit_data.get('finance', '-')
    await update.message.reply_text(f"✅ **Unit Ditemukan:**\n🚙 {unit_data.get('type')}\n🏦 {unit_data.get('finance')}\n\n👉 **Masukkan ALASAN penghapusan:**\n_(Contoh: Sudah Lunas / Unit Ditarik / Salah Input)_", parse_mode='Markdown'); return L_REASON
async def lapor_reason(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['lapor_reason'] = update.message.text
    msg = (f"⚠️ **KONFIRMASI LAPORAN**\n\nHapus Unit: `{context.user_data['lapor_nopol']}`?\nAlasan: {context.user_data['lapor_reason']}")
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM LAPORAN", "❌ BATAL"]]), parse_mode='Markdown'); return L_CONFIRM
async def lapor_delete_confirm(update, context):
    if update.message.text != "✅ KIRIM LAPORAN": return await cancel(update, context)
    n = context.user_data['lapor_nopol']; reason = context.user_data['lapor_reason']; u = get_user(update.effective_user.id)
    await update.message.reply_text("✅ **Laporan Terkirim!** Admin sedang meninjau.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
    msg_admin = (f"🗑️ **PENGAJUAN HAPUS UNIT**\n━━━━━━━━━━━━━━━━━━\n👤 **Pelapor:** {clean_text(u.get('nama_lengkap'))}\n🏢 **Agency:** {clean_text(u.get('agency'))}\n━━━━━━━━━━━━━━━━━━\n🔢 **Nopol:** `{n}`\n🚙 **Unit:** {context.user_data['lapor_type']}\n🏦 **Leasing:** {context.user_data['lapor_finance']}\n📝 **Alasan:** {reason}\n━━━━━━━━━━━━━━━━━━")
    kb = [[InlineKeyboardButton("✅ Setujui Hapus", callback_data=f"del_acc_{n}_{u['user_id']}"), InlineKeyboardButton("❌ Tolak", callback_data=f"del_rej_{u['user_id']}")]]
    await context.bot.send_message(ADMIN_ID, msg_admin, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML'); return ConversationHandler.END

# --- OTHER ADMIN FEATURES ---
async def get_leasing_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = await update.message.reply_text("⏳ *Sedang Menghitung (5 Juta Data)...*\n_Mengambil rekap langsung dari Database..._", parse_mode='Markdown')
    try:
        response = await asyncio.to_thread(lambda: supabase.rpc('get_leasing_summary').execute())
        data = response.data
        if not data: return await msg.edit_text("❌ Database Kosong atau Fungsi SQL belum dipasang.")
        rpt = "🏦 **AUDIT LEASING (LIVE)**\n━━━━━━━━━━━━━━━━━━\n"
        total_global = sum(d['total'] for d in data)
        rpt += f"📦 **Total Data:** `{total_global:,}` Unit\n━━━━━━━━━━━━━━━━━━\n"
        for item in data:
            k = str(item.get('finance', 'UNKNOWN')).upper(); v = item.get('total', 0)
            if k not in ["UNKNOWN", "NONE", "NAN", "-", "", "NULL"]: 
                entry = f"🔹 **{k}:** `{v:,}`\n"
                if len(rpt) + len(entry) > 4000: rpt += "\n...(dan leasing kecil lainnya)"; break 
                rpt += entry
        await msg.edit_text(rpt, parse_mode='Markdown')
    except Exception as e: logger.error(f"Audit Error: {e}"); await msg.edit_text(f"❌ **Error:** {e}\n\n_Pastikan sudah run script SQL 'get_leasing_summary' di Supabase._")

async def get_stats(update, context):
    if update.effective_user.id != ADMIN_ID: return
    try:
        t = supabase.table('kendaraan').select("*", count="exact", head=True).execute().count
        u = supabase.table('users').select("*", count="exact", head=True).execute().count
        k = supabase.table('users').select("*", count="exact", head=True).eq('role', 'korlap').execute().count
        await update.message.reply_text(f"📊 **STATS v6.0**\n📂 Data: `{t:,}`\n👥 Total User: `{u}`\n🎖️ Korlap: `{k}`", parse_mode='Markdown')
    except: pass

async def rekap_harian(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = await update.message.reply_text("⏳ **Sedang menghitung data MURNI MATEL hari ini...**", parse_mode='Markdown')
    try:
        now = datetime.now(TZ_JAKARTA); start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        res = supabase.table('finding_logs').select("leasing").gte('created_at', start_of_day.isoformat()).execute()
        data = res.data
        if not data: return await msg.edit_text("📊 **REKAP HARIAN (MURNI LAPANGAN)**\n\nBelum ada unit ditemukan (HIT) hari ini.")
        counts = Counter([d['leasing'] for d in data])
        report = f"📊 **REKAP TEMUAN (HIT) HARI INI**\n📅 Tanggal: {now.strftime('%d %b %Y')}\n🔥 **Total Unit Ketemu:** {len(data)} Unit\n━━━━━━━━━━━━━━━━━━\n"
        for leasing, jumlah in counts.most_common():
            if leasing in ["-", "UNKNOWN", "NAN"]: leasing = "LAIN-LAIN"
            report += f"🔹 **{leasing}:** {jumlah} Unit\n"
        report += "━━━━━━━━━━━━━━━━━━\n#OneAspalAnalytics (Clean Data)"
        await msg.edit_text(report, parse_mode='Markdown')
    except Exception as e: await msg.edit_text(f"❌ Gagal menarik data rekap: {e}")

async def rekap_spesifik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    raw_text = update.message.text.split()[0]; target_leasing = raw_text.lower().replace("/rekap", "").strip().upper()
    if not target_leasing: return
    msg = await update.message.reply_text(f"⏳ **Mencari Data Temuan: {target_leasing}...**", parse_mode='Markdown')
    try:
        now = datetime.now(TZ_JAKARTA); start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        res = supabase.table('finding_logs').select("*").gte('created_at', start_of_day.isoformat()).ilike('leasing', f'%{target_leasing}%').execute()
        data = res.data; total_hits = len(data)
        if total_hits == 0: return await msg.edit_text(f"📊 **REKAP HARIAN: {target_leasing}**\n\nNihil. Belum ada unit ditemukan hari ini.")
        report = f"📊 **LAPORAN HARIAN KHUSUS: {target_leasing}**\n📅 Tanggal: {now.strftime('%d %b %Y')}\n🔥 **Total Hit:** {total_hits} Unit\n━━━━━━━━━━━━━━━━━━\n"
        limit_show = 15
        for i, d in enumerate(data[:limit_show]):
            report += f"{i+1}. {d.get('nopol','-')} | {d.get('unit','-')} (Oleh: {d.get('nama_matel','Matel')})\n"
        if total_hits > limit_show: report += f"\n... dan {total_hits - limit_show} unit lainnya."
        report += "\n━━━━━━━━━━━━━━━━━━\n#OneAspalAnalytics"
        await msg.edit_text(report, parse_mode='Markdown')
    except Exception as e: await msg.edit_text(f"❌ Error: {e}")

async def admin_help(update, context):
    if update.effective_user.id != ADMIN_ID: return
    msg = ("🔐 **ADMIN COMMANDS v6.10**\n\n📢 **INFO**\n• `/setinfo [Pesan]`\n• `/delinfo`\n\n👮‍♂️ **ROLE**\n• `/angkat_korlap [ID] [KOTA]`\n\n📊 **ANALYTICS**\n• `/rekap`\n• `/rekap[Leasing]`\n\n🏢 **LEASING GROUP**\n• `/setgroup [NAMA_LEASING]`\n\n👥 **USERS**\n• `/users`\n• `/m_ID`\n• `/topup [ID] [HARI]`\n• `/balas [ID] [MSG]`\n\n⚙️ **SYSTEM**\n• `/stats`\n• `/leasing`\n• `/stop` (Hentikan Upload)")
    await update.message.reply_text(msg, parse_mode='Markdown')

async def set_leasing_group(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if update.effective_chat.type not in ['group', 'supergroup']: return await update.message.reply_text("⚠️ Gunakan di dalam GRUP Leasing.")
    if not context.args: return await update.message.reply_text("⚠️ Format: `/setgroup [NAMA_LEASING]`")
    leasing_name = " ".join(context.args).upper(); chat_id = update.effective_chat.id
    try:
        supabase.table('leasing_groups').delete().eq('group_id', chat_id).execute()
        supabase.table('leasing_groups').insert({"group_id": chat_id, "leasing_name": leasing_name}).execute()
        await update.message.reply_text(f"✅ <b>GRUP TERDAFTAR!</b>\n\nUntuk: <b>{leasing_name}</b>.", parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Gagal: {e}")

async def auto_cleanup_logs(context: ContextTypes.DEFAULT_TYPE):
    try:
        cutoff = (datetime.now(TZ_JAKARTA) - timedelta(days=5)).isoformat()
        supabase.table('finding_logs').delete().lt('created_at', cutoff).execute()
        print("🧹 [AUTO CLEANUP] Log lama dihapus.")
    except Exception as e: logger.error(f"❌ AUTO CLEANUP ERROR: {e}")

async def set_info(update, context):
    global GLOBAL_INFO; 
    if update.effective_user.id==ADMIN_ID: GLOBAL_INFO = " ".join(context.args); await update.message.reply_text("✅ Info Set.")
async def del_info(update, context):
    global GLOBAL_INFO; 
    if update.effective_user.id==ADMIN_ID: GLOBAL_INFO = ""; await update.message.reply_text("🗑️ Info Deleted.")
async def test_group(update, context):
    if update.effective_user.id==ADMIN_ID:
        try: await context.bot.send_message(LOG_GROUP_ID, "🔔 TEST GROUP NOTIFIKASI"); await update.message.reply_text("✅ OK")
        except Exception as e: await update.message.reply_text(f"❌ Fail: {e}")
async def admin_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid, days = int(context.args[0]), int(context.args[1])
        suc, new_exp = add_subscription_days(tid, days)
        if suc: await update.message.reply_text(f"✅ Sukses! User {tid} aktif s/d {new_exp.strftime('%d-%m-%Y')}.")
        else: await update.message.reply_text("❌ Gagal Topup.")
    except: await update.message.reply_text("⚠️ Format: `/topup ID HARI`")
async def add_agency(update, context):
    if update.effective_user.id != ADMIN_ID: return
    try:
        name = " ".join(context.args); supabase.table('agencies').insert({"name": name}).execute(); await update.message.reply_text(f"✅ Agency '{name}' ditambahkan.")
    except: await update.message.reply_text("❌ Error.")
async def admin_reply(update, context):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_uid = int(context.args[0]); msg_reply = " ".join(context.args[1:])
        await context.bot.send_message(target_uid, f"📩 **BALASAN ADMIN**\n━━━━━━━━━━━━━━━━━━\n💬 {msg_reply}", parse_mode='Markdown')
        await update.message.reply_text(f"✅ Terkirim ke `{target_uid}`.")
    except: await update.message.reply_text(f"❌ Gagal.")
async def contact_admin(update, context):
    await update.message.reply_text("📝 **LAYANAN BANTUAN**\n\nSilakan ketik pesan/kendala Anda di bawah ini:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True))
    return SUPPORT_MSG
async def support_send(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    u = get_user(update.effective_user.id); msg_content = update.message.text
    msg_admin = (f"📩 **PESAN DARI MITRA**\n━━━━━━━━━━━━━━━━━━\n👤 <b>Nama:</b> {clean_text(u.get('nama_lengkap'))}\n🏢 <b>Agency:</b> {clean_text(u.get('agency'))}\n📱 <b>ID:</b> <code>{u['user_id']}</code>\n━━━━━━━━━━━━━━━━━━\n💬 <b>Pesan:</b>\n{msg_content}\n━━━━━━━━━━━━━━━━━━\n👉 <b>Balas:</b> <code>/balas {u['user_id']} [Pesan]</code>")
    await context.bot.send_message(ADMIN_ID, msg_admin, parse_mode='HTML')
    await update.message.reply_text("✅ **Pesan Terkirim!**", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END


# ##############################################################################
# BAGIAN 11: MAIN ENTRY POINT
# ##############################################################################

if __name__ == '__main__':
    print("🚀 ONEASPAL BOT v6.10 (FIXED) STARTING...")
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    
    # --- CONVERSATION HANDLERS (PRIORITY 1) ---
    app.add_handler(MessageHandler(filters.Regex(r'^/m_\d+$'), manage_user_panel))
    
    # Upload Conv
    conv_upload = ConversationHandler(
        entry_points=[MessageHandler(filters.Document.ALL, upload_start)],
        states={
            U_LEASING_USER: [MessageHandler(filters.TEXT, upload_leasing_user)],
            U_LEASING_ADMIN: [MessageHandler(filters.TEXT, upload_leasing_admin)],
            U_CONFIRM_UPLOAD: [MessageHandler(filters.TEXT, upload_confirm_admin)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )
    app.add_handler(conv_upload)

    # Register Conv
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('register', register_start)], states={R_ROLE_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_role_choice)], R_NAMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_nama)], R_HP: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_hp)], R_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)], R_KOTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_kota)], R_AGENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_agency)], R_CONFIRM:[MessageHandler(filters.TEXT & ~filters.COMMAND, register_confirm)]}, fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]))
    
    # Manual Input Conv
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('tambah', add_data_start)], states={A_NOPOL: [MessageHandler(filters.TEXT, add_nopol)], A_TYPE: [MessageHandler(filters.TEXT, add_type)], A_LEASING: [MessageHandler(filters.TEXT, add_leasing)], A_NOKIRIMAN: [MessageHandler(filters.TEXT, add_nokiriman)], A_OVD: [MessageHandler(filters.TEXT, add_ovd)], A_KET: [MessageHandler(filters.TEXT, add_ket)], A_CONFIRM: [MessageHandler(filters.TEXT, add_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    
    # Lapor Conv
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('lapor', lapor_delete_start)], states={L_NOPOL: [MessageHandler(filters.TEXT, lapor_delete_check)], L_REASON: [MessageHandler(filters.TEXT, lapor_reason)], L_CONFIRM: [MessageHandler(filters.TEXT, lapor_delete_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    
    # Admin Action Convs (Callback Triggered)
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(admin_action_start, pattern='^adm_(ban|unban|del)_')], states={ADMIN_ACT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_action_complete)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(reject_start, pattern='^reju_')], states={REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, reject_complete)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(val_reject_start, pattern='^v_rej_')], states={VAL_REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, val_reject_complete)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    
    # Support Conv
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('admin', contact_admin), MessageHandler(filters.Regex('^📞 BANTUAN TEKNIS$'), contact_admin)], states={SUPPORT_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_send)]}, fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)])) 
    
    # --- COMMAND HANDLERS (PRIORITY 2) ---
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('cekkuota', cek_kuota))
    app.add_handler(CommandHandler('infobayar', info_bayar)) 
    app.add_handler(CommandHandler('topup', admin_topup))
    app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('leasing', get_leasing_list)) 
    app.add_handler(CommandHandler('rekap', rekap_harian)) 
    app.add_handler(CommandHandler('users', list_users))
    app.add_handler(CommandHandler('angkat_korlap', angkat_korlap)) 
    app.add_handler(CommandHandler('testgroup', test_group))
    app.add_handler(CommandHandler('balas', admin_reply))
    app.add_handler(CommandHandler('setgroup', set_leasing_group)) 
    app.add_handler(CommandHandler('panduan', panduan))
    app.add_handler(CommandHandler('setinfo', set_info)) 
    app.add_handler(CommandHandler('delinfo', del_info))       
    app.add_handler(CommandHandler('addagency', add_agency)) 
    app.add_handler(CommandHandler('adminhelp', admin_help)) 
    app.add_handler(CommandHandler('stop', stop_upload_command))
    
    # --- OTHER HANDLERS (PRIORITY 3) ---
    app.add_handler(MessageHandler(filters.Regex(r'^/rekap[a-zA-Z0-9]+$') & filters.COMMAND, rekap_spesifik))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_topup))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    # Main Message Handler (Must be last)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    # --- JOBS ---
    job_queue = app.job_queue
    job_queue.run_daily(
        auto_cleanup_logs, 
        time=time(hour=3, minute=0, second=0, tzinfo=TZ_JAKARTA), 
        days=(0, 1, 2, 3, 4, 5, 6)
    )
    print("⏰ Jadwal Cleanup Otomatis: AKTIF (Jam 03:00 WIB)")

    app.run_polling()