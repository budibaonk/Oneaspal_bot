################################################################################
#                                                                              #
#                      PROJECT: ONEASPAL BOT (ASSET RECOVERY)                  #
#                      VERSION: 6.30 (FINAL SYNC - INTELLIGENCE READY)         #
#                      ROLE:    MAIN APPLICATION CORE                          #
#                      AUTHOR:  CTO (GEMINI) & CEO (BAONK)                     #
#                                                                              #
################################################################################

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
import json
import html
import difflib
import pytz
import urllib.parse
import shutil
from dotenv import load_dotenv
from collections import Counter
from datetime import datetime, timedelta, timezone, time as dt_time

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

# [FIX] Import ClientOptions untuk menangani Timeout
try:
    from supabase.lib.client_options import ClientOptions
except ImportError:
    from supabase import ClientOptions

# --- KONFIGURASI ADMIN ---
# Masukkan ID Telegram Anda di sini agar fitur /rekap dan Notifikasi jalan
ADMIN_IDS = ['7530512170']

# ##############################################################################
# BAGIAN 1: KONFIGURASI SISTEM
# ##############################################################################

load_dotenv()

# Logger level diset ke INFO agar terlihat di terminal
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
print("🔍 SYSTEM DIAGNOSTIC STARTUP (v6.30)")
print("="*50)

try:
    ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
    LOG_GROUP_ID = int(os.environ.get("LOG_GROUP_ID", 0))
    print(f"✅ ADMIN ID TERDETEKSI: {ADMIN_ID}")
    
    if LOG_GROUP_ID == 0:
        print("⚠️ PERINGATAN: LOG_GROUP_ID BERNILAI 0!")
        print("   Notifikasi ke Group Pusat TIDAK AKAN JALAN.")
        print("   Cek file .env Anda, pastikan LOG_GROUP_ID diisi dengan benar.")
    else:
        print(f"✅ LOG_GROUP_ID TERDETEKSI: {LOG_GROUP_ID}")
        
except ValueError:
    ADMIN_ID = 0
    LOG_GROUP_ID = 0
    print("❌ ERROR: ADMIN_ID atau LOG_GROUP_ID di .env bukan angka!")

if not URL or not KEY or not TOKEN:
    print("❌ CRITICAL: TOKEN/URL/KEY Supabase Hilang dari .env")
    exit()
else:
    print("✅ Credential Database & Bot: OK")

try:
    # [FIX] Set Timeout ke 300 detik (5 Menit) agar upload besar tidak putus
    opts = ClientOptions(postgrest_client_timeout=300)
    supabase: Client = create_client(URL, KEY, options=opts)
    print("✅ Koneksi Supabase: BERHASIL (Timeout 300s)")
except Exception as e:
    print(f"⚠️ Warning ClientOptions: {e}")
    # Fallback ke default jika library lama
    supabase: Client = create_client(URL, KEY)
    print("✅ Koneksi Supabase: BERHASIL (Default Mode)")

print("="*50 + "\n")


# ##############################################################################
# BAGIAN 2: KAMUS DATA
# ##############################################################################

COLUMN_ALIASES = {
    'nopol': ['nopolisi', 'nomorpolisi', 'nopol', 'noplat', 'nomorplat', 'nomorkendaraan', 'tnkb', 'licenseplate', 'plat', 'police_no', 'no polisi', 'no. polisi'],
    'type': ['type', 'tipe', 'unit', 'model', 'vehicle', 'jenis', 'assetdescription', 'deskripsiunit', 'merk', 'object', 'kendaraan', 'item', 'merkname', 'brand', 'product', 'tipekendaraan', 'tipeunit', 'typekendaraan', 'typeunit'],
    'tahun': ['tahun', 'year', 'thn', 'rakitan', 'th', 'yearofmanufacture', 'assetyear', 'manufacturingyear'],
    'warna': ['warna', 'color', 'colour', 'cat', 'kelir', 'assetcolour'],
    'noka': ['noka', 'norangka', 'nomorrangka', 'chassis', 'chasis', 'vin', 'rangka', 'chassisno', 'vinno', 'serial_number', 'bodyno', 'frameno', 'no rangka', 'no. rangka'],
    'nosin': ['nosin', 'nomesin', 'nomormesin', 'engine', 'mesin', 'engineno', 'noengine', 'engine_number', 'machineno', 'mesinno', 'no mesin', 'no. mesin'],
    'finance': ['finance', 'leasing', 'lising', 'multifinance', 'cabang', 'partner', 'mitra', 'principal', 'company', 'client'],
    'ovd': ['ovd', 'overdue', 'dpd', 'keterlambatan', 'odh', 'hari', 'telat', 'aging', 'od', 'bucket', 'daysoverdue', 'osp'],
    'branch': ['branch', 'area', 'kota', 'pos', 'cabang', 'lokasi', 'wilayah', 'region', 'areaname', 'branchname', 'resort']
}

VALID_DB_COLUMNS = ['nopol', 'type', 'finance', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'branch']

# ##############################################################################
# BAGIAN 3: DEFINISI STATE CONVERSATION
# ##############################################################################

# Ubah range jadi 8, dan tambahkan R_PHOTO_ID sebelum R_CONFIRM
R_ROLE_CHOICE, R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_PHOTO_ID, R_CONFIRM = range(8)
# Definisi State untuk Percakapan Tambah Manual
ADD_NOPOL, ADD_UNIT, ADD_LEASING, ADD_PHONE, ADD_NOTE, ADD_CONFIRM = range(6)
L_NOPOL, L_REASON, L_CONFIRM = range(14, 17) 
D_NOPOL, D_CONFIRM = range(17, 19)
U_LEASING_USER, U_LEASING_ADMIN, U_CONFIRM_UPLOAD = range(19, 22)

REJECT_REASON = 22
ADMIN_ACT_REASON = 23
SUPPORT_MSG = 24
VAL_REJECT_REASON = 25


# ##############################################################################
# BAGIAN 4: FUNGSI HELPER UTAMA
# ##############################################################################

async def post_init(application: Application):
    await application.bot.set_my_commands([
        ("start", "🔄 Restart / Menu"),
        ("cekkuota", "💳 Cek Masa Aktif"),
        ("stop", "⛔ Stop Proses Upload"),
        ("infobayar", "💰 Perpanjang Langganan"),
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
        now_dt = datetime.now(TZ_JAKARTA)
        
        if now_dt > expiry_dt: return False, "EXPIRED"

        last_usage_str = user.get('last_usage_date')
        today_str = now_dt.strftime('%Y-%m-%d')
        daily_usage = user.get('daily_usage', 0)

        if last_usage_str != today_str:
            supabase.table('users').update({'daily_usage': 0, 'last_usage_date': today_str}).eq('user_id', user['user_id']).execute()
            daily_usage = 0
        
        limit = DAILY_LIMIT_KORLAP if user.get('role') == 'korlap' else DAILY_LIMIT_MATEL
        if daily_usage >= limit: return False, "DAILY_LIMIT"

        return True, "OK"
    except Exception as e:
        print(f"Sub Check Error: {e}")
        return False, "ERROR"

def increment_daily_usage(user_id, current_usage):
    try:
        # Ambil waktu sekarang format ISO lengkap (Jam:Menit:Detik)
        now_iso = datetime.now(TZ_JAKARTA).isoformat()
        
        # Update daily usage DAN last_seen
        supabase.table('users').update({
            'daily_usage': current_usage + 1,
            'last_seen': now_iso  # <--- INI KUNCINYA
        }).eq('user_id', user_id).execute()
    except: pass

def add_subscription_days(user_id, days_to_add):
    try:
        user = get_user(user_id)
        if not user: return False, None
        
        now = datetime.now(TZ_JAKARTA)
        current_expiry_str = user.get('expiry_date')
        
        if current_expiry_str:
            current_expiry = datetime.fromisoformat(current_expiry_str.replace('Z', '+00:00')).astimezone(TZ_JAKARTA)
            if current_expiry > now:
                new_expiry = current_expiry + timedelta(days=days_to_add)
            else:
                new_expiry = now + timedelta(days=days_to_add)
        else:
            new_expiry = now + timedelta(days=days_to_add)
            
        supabase.table('users').update({'expiry_date': new_expiry.isoformat()}).eq('user_id', user_id).execute()
        return True, new_expiry
    except Exception as e:
        print(f"Topup Error: {e}")
        return False, None

def clean_text(text):
    if not text: return "-"
    return html.escape(str(text))

def format_wa_link(phone_number):
    """Mengubah format HP 08xx jadi Link WA."""
    if not phone_number: return "-"
    clean_hp = re.sub(r'[^0-9]', '', str(phone_number))
    if clean_hp.startswith('0'): 
        clean_hp = '62' + clean_hp[1:]
    return f'<a href="https://wa.me/{clean_hp}">{phone_number}</a>'

def standardize_leasing_name(name):
    if not name: return "UNKNOWN"
    clean = str(name).upper().strip()
    clean = re.sub(r'^\d+\s+', '', clean)
    clean = re.sub(r'\(.*?\)', '', clean).strip()
    return clean

# [CRITICAL UPDATE] LOGIC PENCATATAN LOG DIUBAH MENERIMA USER OBJECT
def log_successful_hit(user_db, unit_data):
    try:
        leasing_raw = str(unit_data.get('finance', 'UNKNOWN')).upper().strip()
        nopol_val = unit_data.get('nopol', '-')
        unit_val = unit_data.get('type', '-')

        # Ambil data dari object user_db yang sudah dipassing
        user_id = user_db.get('user_id')
        user_name = user_db.get('nama_lengkap', 'Unknown')
        user_hp = user_db.get('no_hp', '-')
        user_agency = user_db.get('agency', '-')

        payload = {
            "leasing": leasing_raw,
            "nopol": nopol_val,
            "unit": unit_val,
            "user_id": user_id,
            "nama_matel": user_name,
            "no_hp": user_hp,      # SEKARANG TERISI
            "nama_pt": user_agency # SEKARANG TERISI
        }
        supabase.table('finding_logs').insert(payload).execute()
        
    except Exception as e:
        print(f"⚠️ Gagal menyimpan log ke database: {e}")

# ##############################################################################
# BAGIAN 5: ENGINE FILE
# ##############################################################################

def normalize_text(text):
    if not isinstance(text, str): return str(text).lower()
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()

def fix_header_position(df):
    target = COLUMN_ALIASES['nopol']
    for i in range(min(30, len(df))): 
        vals = [normalize_text(str(x)) for x in df.iloc[i].values]
        if any(alias in vals for alias in target):
            df.columns = df.iloc[i] 
            df = df.iloc[i+1:].reset_index(drop=True) 
            return df
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
    """
    Versi SUPER ROBUST: Mampu membaca CSV bandel & Excel.
    """
    fname = fname.lower()
    
    # 1. Cek ZIP
    if fname.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            valid = [f for f in z.namelist() if f.endswith(('.csv','.xlsx','.xls'))]
            if not valid: raise ValueError("ZIP Kosong")
            with z.open(valid[0]) as f: 
                content = f.read()
                fname = valid[0].lower()
    
    # 2. Cek EXCEL
    if fname.endswith(('.xlsx', '.xls')):
        try: return pd.read_excel(io.BytesIO(content), dtype=str)
        except Exception as e: raise ValueError(f"Gagal baca Excel: {e}")

    # 3. Cek CSV (Coba berbagai jurus)
    try:
        return pd.read_csv(io.BytesIO(content), sep=';', dtype=str, on_bad_lines='skip', encoding='utf-8')
    except: pass
    try:
        return pd.read_csv(io.BytesIO(content), sep=',', dtype=str, on_bad_lines='skip', encoding='utf-8')
    except: pass
    try:
        return pd.read_csv(io.BytesIO(content), sep=';', dtype=str, on_bad_lines='skip', encoding='latin1')
    except: pass

    raise ValueError("Format file tidak bisa dibaca. Pastikan CSV (Pemisah ; atau ,) atau Excel.")


# ##############################################################################
# BAGIAN 6: FITUR ADMIN - ACTION
# ##############################################################################

async def angkat_korlap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        if len(context.args) < 2:
            return await update.message.reply_text("⚠️ Format: `/angkat_korlap [ID] [KOTA]`", parse_mode='Markdown')
        target_id = int(context.args[0]); wilayah = " ".join(context.args[1:]).upper()
        data = {"role": "korlap", "wilayah_korlap": wilayah, "quota": 5000} 
        supabase.table('users').update(data).eq('user_id', target_id).execute()
        await update.message.reply_text(f"✅ **SUKSES!**\nUser ID `{target_id}` sekarang adalah **KORLAP {wilayah}**.\nLimit Harian: 2000 Cek.", parse_mode='Markdown')
    except Exception as e: await update.message.reply_text(f"❌ Gagal: {e}")

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
        msg_user = (f"⛔ **PENDAFTARAN DITOLAK**\n\n⚠️ <b>Alasan:</b> {reason}\n\n<i>Data Anda telah dihapus. Silakan lakukan registrasi ulang dengan data yang benar via /register</i>")
        await context.bot.send_message(target_uid, msg_user, parse_mode='HTML')
    except: pass
    try:
        mid = context.user_data.get('reg_msg_id'); cid = context.user_data.get('reg_chat_id')
        await context.bot.edit_message_reply_markup(chat_id=cid, message_id=mid, reply_markup=None)
        await context.bot.send_message(chat_id=cid, text=f"❌ User {target_uid} berhasil DITOLAK & DIHAPUS.\nAlasan: {reason}")
    except: pass
    await update.message.reply_text("✅ Proses Selesai.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

async def val_reject_start(update, context):
    query = update.callback_query; await query.answer()
    data = query.data.split("_")
    context.user_data['val_rej_nopol'] = data[2]
    context.user_data['val_rej_uid'] = data[3]
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"❌ **TOLAK PENGAJUAN**\nUnit: {data[2]}\n\nKetik ALASAN Penolakan:",
        reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
    )
    return VAL_REJECT_REASON

async def val_reject_complete(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    nopol = context.user_data.get('val_rej_nopol')
    uid = context.user_data.get('val_rej_uid')
    reason = update.message.text
    try:
        msg = (f"⛔ **PENGAJUAN DITOLAK**\nUnit: {nopol}\n⚠️ <b>Alasan:</b> {reason}\n\nSilakan perbaiki data dan ajukan ulang jika perlu.")
        await context.bot.send_message(chat_id=int(uid), text=msg, parse_mode='HTML')
    except Exception as e: logger.error(f"Gagal kirim notif tolak: {e}")
    await update.message.reply_text(f"✅ Notifikasi penolakan dikirim ke User.\nAlasan: {reason}", reply_markup=ReplyKeyboardRemove())
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
# BAGIAN 7: FITUR ADMIN - USER MANAGER & ANALYTICS
# ##############################################################################

async def admin_help(update, context):
    # Menggunakan ADMIN_IDS (List) agar konsisten dengan perbaikan error sebelumnya
    if str(update.effective_user.id) not in ADMIN_IDS: return

    msg = (
        "🔐 **ADMIN COMMANDS v6.29**\n\n"
        "📢 **INFO / PENGUMUMAN**\n"
        "• `/setinfo [Pesan]` (Pasang Banner)\n"
        "• `/delinfo` (Hapus Banner)\n\n"
        "👮‍♂️ **ROLE & AGENCY**\n"
        "• `/angkat_korlap [ID] [KOTA]`\n"
        "• `/addagency [NAMA_PT]` (Tambah DB Agency)\n\n"
        "📊 **ANALYTICS**\n"
        "• `/rekap` (Rekap Global Hari Ini)\n"
        "• `/rekap[Leasing]` (Contoh: `/rekapBCA`)\n"
        "• `/stats` (Total Data)\n"
        "• `/leasing` (Audit Jumlah Data)\n\n"
        "🏢 **GROUP NOTIFIKASI**\n"
        "• `/setgroup [NAMA_LEASING]` (Utk Leasing)\n"
        "• `/setagency [NAMA_PT]` (Utk Agency B2B)\n"
        "• `/testgroup` (Cek Koneksi Admin Pusat)\n\n"
        "👥 **USERS**\n"
        "• `/rekap_member` (Rekap Member Baru) 🆕\n"
        "• `/users` (List User Aktif)\n"
        "• `/m_ID` (Manage User per ID)\n"
        "• `/topup [ID] [HARI]`\n"
        "• `/balas [ID] [MSG]`\n\n"
        "⚙️ **SYSTEM & DATA**\n"
        "• `/stop` (Hentikan Upload)\n"
        "• `/hapus` (Hapus Unit Manual)\n"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def rekap_harian(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    msg = await update.message.reply_text("⏳ **Sedang menghitung data MURNI MATEL hari ini...**", parse_mode='Markdown')
    
    try:
        now = datetime.now(TZ_JAKARTA)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Tarik data (Data di finding_logs otomatis sudah terfilter bersih)
        res = supabase.table('finding_logs').select("leasing").gte('created_at', start_of_day.isoformat()).execute()
        data = res.data
        
        if not data:
            return await msg.edit_text("📊 **REKAP HARIAN (MURNI LAPANGAN)**\n\nBelum ada unit ditemukan (HIT) hari ini.")

        counts = Counter([d['leasing'] for d in data])
        total_hits = len(data)
        
        report = (
            f"📊 **REKAP TEMUAN (HIT) HARI INI**\n"
            f"📅 Tanggal: {now.strftime('%d %b %Y')}\n"
            f"🔥 **Total Unit Ketemu:** {total_hits} Unit\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
        
        for leasing, jumlah in counts.most_common():
            if leasing in ["-", "UNKNOWN", "NAN"]: leasing = "LAIN-LAIN"
            report += f"🔹 **{leasing}:** {jumlah} Unit\n"
            
        report += "━━━━━━━━━━━━━━━━━━\n#OneAspalAnalytics (Clean Data)"
        
        await msg.edit_text(report, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Rekap Error: {e}")
        await msg.edit_text(f"❌ Gagal menarik data rekap: {e}")

async def rekap_spesifik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    raw_text = update.message.text.split()[0]
    target_leasing = raw_text.lower().replace("/rekap", "").strip().upper()
    
    if not target_leasing: return 
    
    msg = await update.message.reply_text(f"⏳ **Mencari Data Temuan: {target_leasing}...**", parse_mode='Markdown')
    
    try:
        now = datetime.now(TZ_JAKARTA)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        res = supabase.table('finding_logs').select("*")\
            .gte('created_at', start_of_day.isoformat())\
            .ilike('leasing', f'%{target_leasing}%')\
            .order('created_at', desc=True)\
            .execute()
        
        data = res.data
        total_hits = len(data)
        
        if total_hits == 0:
            return await msg.edit_text(f"📊 **REKAP HARIAN: {target_leasing}**\n\nNihil. Belum ada unit ditemukan hari ini.")
            
        header = (
            f"📊 **LAPORAN HARIAN KHUSUS: {target_leasing}**\n"
            f"📅 Tanggal: {now.strftime('%d %b %Y')}\n"
            f"🔥 **Total Hit:** {total_hits} Unit\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
        
        footer = "\n━━━━━━━━━━━━━━━━━━\n#OneAspalAnalytics"
        
        messages = []
        current_report = header
        
        for i, d in enumerate(data):
            nopol = d.get('nopol', '-')
            unit = d.get('unit', '-')
            matel = d.get('nama_matel', 'Anonim')
            hp = d.get('no_hp', 'No HP -')
            pt = d.get('nama_pt', 'PT -')
            
            line = f"{i+1}. **{nopol}** | {unit}\n"
            line += f"   └ 👤 {matel} ({hp}) | 🏢 {pt}\n"
            
            if len(current_report) + len(line) + len(footer) > 3800:
                messages.append(current_report + footer)
                current_report = f"📊 **LANJUTAN REKAP: {target_leasing}**\n━━━━━━━━━━━━━━━━━━\n" + line
            else:
                current_report += line
        
        messages.append(current_report + footer)
        
        for index, text in enumerate(messages):
            if index == 0:
                await msg.edit_text(text, parse_mode='Markdown')
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode='Markdown')
                
    except Exception as e:
        logger.error(f"Rekap Spesifik Error: {e}")
        await msg.edit_text(f"❌ Error: {e}")

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
        
        if not active_list: 
            return await update.message.reply_text("📂 Tidak ada mitra aktif.")
        
        msg = f"📋 <b>DAFTAR MITRA (Total: {len(active_list)})</b>\n━━━━━━━━━━━━━━━━━━\n"
        now = datetime.now(TZ_JAKARTA)
        no_preview = LinkPreviewOptions(is_disabled=True)

        if pic_list:
            msg += "🏦 <b>INTERNAL LEASING (PIC)</b>\n"
            for i, u in enumerate(pic_list, 1):
                nama = clean_text(u.get('nama_lengkap'))
                agency = clean_text(u.get('agency'))
                uid = u['user_id']
                wa_link = format_wa_link(u.get('no_hp'))
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
                exp_str = u.get('expiry_date')
                if exp_str:
                    exp_dt = datetime.fromisoformat(exp_str.replace('Z', '+00:00')).astimezone(TZ_JAKARTA)
                    delta = exp_dt - now
                    days_left_str = "❌ EXP" if delta.days < 0 else f"⏳ {delta.days} Hari"
                else: days_left_str = "❌ NULL"
                nama = clean_text(u.get('nama_lengkap'))
                agency = clean_text(u.get('agency'))
                uid = u['user_id']
                wa_link = format_wa_link(u.get('no_hp'))
                entry = (f"{i}. {icon} <b>{nama}</b>\n   {days_left_str} | 🏢 {agency}\n   📱 {wa_link} | ⚙️ /m_{uid}\n\n")
                if len(msg) + len(entry) > 4000: 
                    await update.message.reply_text(msg, parse_mode='HTML', link_preview_options=no_preview)
                    msg = ""
                msg += entry
        if msg: 
            await update.message.reply_text(msg, parse_mode='HTML', link_preview_options=no_preview)
    except Exception as e: 
        await update.message.reply_text(f"❌ Error: {e}")

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
        if expiry != 'EXPIRED': expiry = datetime.fromisoformat(expiry.replace('Z', '+00:00')).astimezone(TZ_JAKARTA).strftime('%d %b %Y')
        wa_link = format_wa_link(u.get('no_hp'))
        msg = (f"👮‍♂️ <b>USER MANAGER</b>\n━━━━━━━━━━━━━━━━━━\n👤 <b>Nama:</b> {clean_text(u.get('nama_lengkap'))}\n📱 <b>WA:</b> {wa_link}\n🏅 <b>Role:</b> {info_role} {wilayah}\n📊 <b>Status:</b> {icon_status}\n📱 <b>ID:</b> <code>{tid}</code>\n📅 <b>Exp:</b> {expiry}\n🏢 <b>Agency:</b> {clean_text(u.get('agency'))}\n━━━━━━━━━━━━━━━━━━")
        btn_role = InlineKeyboardButton("⬇️ BERHENTIKAN KORLAP", callback_data=f"adm_demote_{tid}") if role_now == 'korlap' else InlineKeyboardButton("🎖️ ANGKAT KORLAP", callback_data=f"adm_promote_{tid}")
        btn_ban = InlineKeyboardButton("⛔ BAN USER", callback_data=f"adm_ban_{tid}") if status_now == 'active' else InlineKeyboardButton("✅ UNBAN (PULIHKAN)", callback_data=f"adm_unban_{tid}")
        kb = [[InlineKeyboardButton("📅 +5 Hari", callback_data=f"adm_topup_{tid}_5"), InlineKeyboardButton("📅 +30 Hari", callback_data=f"adm_topup_{tid}_30")], [btn_role], [btn_ban, InlineKeyboardButton("🗑️ HAPUS DATA", callback_data=f"adm_del_{tid}")], [InlineKeyboardButton("❌ TUTUP PANEL", callback_data="close_panel")]]
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML', link_preview_options=LinkPreviewOptions(is_disabled=True))
    except Exception as e: await update.message.reply_text(f"❌ Error Panel: {e}")

async def rekap_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Validasi Admin (Pastikan variable ini sesuai dengan config Anda: ADMIN_ID atau ADMIN_IDS)
    user_id = str(update.effective_user.id)
    # Cek akses (Support list ADMIN_IDS atau single ADMIN_ID)
    if 'ADMIN_IDS' in globals() and user_id not in ADMIN_IDS: return
    elif 'ADMIN_ID' in globals() and user_id != str(ADMIN_ID): return

    msg = await update.message.reply_text("⏳ <b>Sedang menarik data member...</b>", parse_mode='HTML')

    try:
        # 1. Ambil Waktu Sekarang
        now = datetime.now(TZ_JAKARTA)
        today_str = now.strftime('%Y-%m-%d')
        display_date = now.strftime('%d %B %Y')
        
        # 2. Hitung Register Hari Ini (Semua status)
        res_today = supabase.table('users').select('user_id', count='exact').gte('created_at', f"{today_str} 00:00:00").execute()
        count_today = res_today.count if res_today.count else 0

        # 3. Ambil Data Pending
        res_pending = supabase.table('users').select('*').eq('status', 'pending').execute()
        pending_users = res_pending.data
        count_pending = len(pending_users)

        # 4. Susun Laporan (PAKAI HTML TAGS: <b>, <i>)
        rpt = (
            f"📊 <b>REKAP MEMBER HARIAN</b>\n"
            f"📅 Tanggal: {display_date}\n\n"
            f"➕ <b>Daftar Hari Ini:</b> {count_today} Orang\n"
            f"⏳ <b>Pending Approval:</b> {count_pending} Orang\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )

        if count_pending > 0:
            rpt += "<b>ANTREAN REVIEW:</b>\n(Klik command utk validasi)\n\n"
            for u in pending_users:
                uid = u['user_id']
                # clean_text agar nama yg ada simbol aneh tidak bikin error
                raw_nama = u.get('nama_lengkap') or u.get('full_name') or 'Tanpa Nama'
                nama = clean_text(raw_nama) 
                
                # Command /cek_ID aman di mode HTML
                rpt += f"👉 /cek_{uid} | {nama}\n"
        else:
            rpt += "✅ <i>Tidak ada antrean pending.</i>"

        await msg.edit_text(rpt, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Rekap Error: {e}")
        # Fallback kalau error, kirim text polos aja biar ketahuan errornya apa
        await msg.edit_text(f"❌ Error: {str(e)}")

# ==============================================================================
# BAGIAN 8: FITUR AUDIT & ADMIN UTILS
# ==============================================================================

async def auto_cleanup_logs(context: ContextTypes.DEFAULT_TYPE):
    try:
        cutoff_date = datetime.now(TZ_JAKARTA) - timedelta(days=5)
        cutoff_str = cutoff_date.isoformat()
        supabase.table('finding_logs').delete().lt('created_at', cutoff_str).execute()
        print(f"🧹 [AUTO CLEANUP] Log lama (< {cutoff_date.strftime('%d-%b')}) berhasil dihapus.")
    except Exception as e:
        logger.error(f"❌ AUTO CLEANUP ERROR: {e}")

async def get_stats(update, context):
    if update.effective_user.id != ADMIN_ID: return
    try:
        t = supabase.table('kendaraan').select("*", count="exact", head=True).execute().count
        u = supabase.table('users').select("*", count="exact", head=True).execute().count
        k = supabase.table('users').select("*", count="exact", head=True).eq('role', 'korlap').execute().count
        await update.message.reply_text(f"📊 **STATS v6.0**\n📂 Data: `{t:,}`\n👥 Total User: `{u}`\n🎖️ Korlap: `{k}`", parse_mode='Markdown')
    except: pass

async def get_leasing_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = await update.message.reply_text("⏳ **Menghitung Statistik Data...**", parse_mode='Markdown')
    try:
        response = await asyncio.to_thread(lambda: supabase.rpc('get_leasing_summary').execute())
        data = response.data 
        if not data: return await msg.edit_text("❌ Database Kosong atau Fungsi SQL belum dipasang.")
        total_global = sum(item['total'] for item in data)
        rpt = (f"🏦 **AUDIT LEASING (LIVE)**\n📦 Total Data: `{total_global:,}` Unit\n━━━━━━━━━━━━━━━━━━\n")
        for item in data:
            k = str(item.get('finance', 'UNKNOWN')).upper()
            v = item.get('total', 0)
            if k not in ["UNKNOWN", "NONE", "NAN", "-", "", "NULL"]: 
                entry = f"🔹 **{k}:** `{v:,}`\n"
                if len(rpt) + len(entry) > 4000:
                    rpt += "\n...(dan leasing kecil lainnya)"
                    break 
                rpt += entry
        await msg.edit_text(rpt, parse_mode='Markdown')
    except Exception as e: 
        logger.error(f"Audit Error: {e}")
        await msg.edit_text(f"❌ **Error:** {e}\n\n_Pastikan sudah run script SQL 'get_leasing_summary' di Supabase._")

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
        name = " ".join(context.args)
        if not name: return await update.message.reply_text("⚠️ Nama Agency kosong.")
        supabase.table('agencies').insert({"name": name}).execute()
        await update.message.reply_text(f"✅ Agency '{name}' ditambahkan.")
    except: await update.message.reply_text("❌ Error.")

async def admin_reply(update, context):
    if update.effective_user.id != ADMIN_ID: return
    try:
        if len(context.args) < 2: return await update.message.reply_text("⚠️ Format: `/balas [ID] [Pesan]`", parse_mode='Markdown')
        target_uid = int(context.args[0]); msg_reply = " ".join(context.args[1:])
        await context.bot.send_message(target_uid, f"📩 **BALASAN ADMIN**\n━━━━━━━━━━━━━━━━━━\n💬 {msg_reply}", parse_mode='Markdown')
        await update.message.reply_text(f"✅ Terkirim ke `{target_uid}`.")
    except Exception as e: await update.message.reply_text(f"❌ Gagal: {e}")

async def contact_admin(update, context):
    await update.message.reply_text("📝 **LAYANAN BANTUAN**\n\nSilakan ketik pesan/kendala Anda di bawah ini:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True))
    return SUPPORT_MSG

async def support_send(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    u = get_user(update.effective_user.id); msg_content = update.message.text
    msg_admin = (f"📩 **PESAN DARI MITRA**\n━━━━━━━━━━━━━━━━━━\n👤 <b>Nama:</b> {clean_text(u.get('nama_lengkap'))}\n🏢 <b>Agency:</b> {clean_text(u.get('agency'))}\n📱 <b>ID:</b> <code>{u['user_id']}</code>\n━━━━━━━━━━━━━━━━━━\n💬 <b>Pesan:</b>\n{msg_content}\n━━━━━━━━━━━━━━━━━━\n👉 <b>Balas:</b> <code>/balas {u['user_id']} [Pesan]</code>")
    await context.bot.send_message(ADMIN_ID, msg_admin, parse_mode='HTML')
    await update.message.reply_text("✅ **Pesan Terkirim!**\nMohon tunggu balasan dari Admin.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

# --- FITUR BARU: CEK USER (JUMP TO CONFIRM) ---
async def cek_user_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in str(ADMIN_ID): return
    
    # 1. Ambil ID dari text /cek_12345
    try: target_uid = int(update.message.text.split('_')[1])
    except: return
    
    # 2. Ambil data dari Database
    res = supabase.table('users').select('*').eq('user_id', target_uid).execute()
    if not res.data: return await update.message.reply_text("❌ Data hilang/sudah diproses.")
    
    d = res.data[0] # Data user
    
    # 3. Format Pesan (SAMA PERSIS DENGAN REGISTER_CONFIRM)
    role_db = d.get('role', 'matel')
    wa_link = format_wa_link(d.get('no_hp'))
    
    msg_admin = (
        f"🔔 <b>REVIEW REGISTRASI ({role_db.upper()})</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Nama:</b> {clean_text(d.get('nama_lengkap'))}\n"
        f"🆔 <b>User ID:</b> <code>{d['user_id']}</code>\n"
        f"🏢 <b>Agency:</b> {clean_text(d.get('agency'))}\n"
        f"📍 <b>Domisili:</b> {clean_text(d.get('alamat'))}\n"
        f"📱 <b>HP/WA:</b> {wa_link}\n"
        f"📧 <b>Email:</b> {clean_text(d.get('email'))}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<i>Silakan validasi data mitra ini.</i>"
    )
    
    # 4. Tombol Aksi (Approve & Reject)
    kb = [
        [InlineKeyboardButton("✅ TERIMA (AKTIFKAN)", callback_data=f"appu_{d['user_id']}")], 
        [InlineKeyboardButton("❌ TOLAK (HAPUS)", callback_data=f"reju_{d['user_id']}")]
    ]
    
    await update.message.reply_text(
        msg_admin, 
        reply_markup=InlineKeyboardMarkup(kb), 
        parse_mode='HTML', 
        link_preview_options=LinkPreviewOptions(is_disabled=True)
    )
    

# ##############################################################################
# BAGIAN 9: USER FEATURES & NOTIFIKASI (UPDATE: SHARE WA & COPY BUTTON)
# ##############################################################################

async def cek_kuota(update, context):
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return
    
    global GLOBAL_INFO
    info_banner = f"📢 <b>INFO PUSAT:</b> {clean_text(GLOBAL_INFO)}\n━━━━━━━━━━━━━━━━━━\n" if GLOBAL_INFO else ""

    if u.get('role') == 'pic':
        msg = (f"{info_banner}📂 **DATABASE SAYA**\n━━━━━━━━━━━━━━━━━━\n👤 **User:** {u.get('nama_lengkap')}\n🏢 **Leasing:** {u.get('agency')}\n🔋 **Status Akses:** UNLIMITED (Enterprise)\n━━━━━━━━━━━━━━━━━━\n✅ Sinkronisasi data berjalan normal.")
    else:
        exp_date = u.get('expiry_date')
        status_aktif = "❌ SUDAH EXPIRED" # Default state
        
        if exp_date:
            try:
                # [UPDATE CTO] Logika Parsing Tanggal Anti-Error
                # 1. Bersihkan string dari format yang membingungkan
                clean_date = str(exp_date).replace('Z', '+00:00')
                
                # 2. Coba parse (baca) tanggalnya
                exp_dt = datetime.fromisoformat(clean_date)
                
                # 3. Pastikan ada Timezonenya (kalau dari SQL kadang polosan)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                
                # 4. Konversi ke WIB (Jakarta)
                exp_dt_wib = exp_dt.astimezone(TZ_JAKARTA)
                
                # 5. Hitung sisa waktu
                now_wib = datetime.now(TZ_JAKARTA)
                formatted_date = exp_dt_wib.strftime('%d %b %Y %H:%M')
                
                if exp_dt_wib > now_wib:
                    remaining = exp_dt_wib - now_wib
                    status_aktif = f"✅ AKTIF s/d {formatted_date}\n⏳ Sisa Waktu: {remaining.days} Hari"
                else:
                    status_aktif = f"❌ SUDAH EXPIRED (Sejak {formatted_date})"
                    
            except ValueError:
                # Jika format database aneh banget, anggap expired (Fail Safe)
                status_aktif = "❌ ERROR: Format Tanggal Invalid"

        role_msg = f"🎖️ **KORLAP {u.get('wilayah_korlap','')}**" if u.get('role')=='korlap' else f"🛡️ **MITRA LAPANGAN**"
        msg = (f"{info_banner}💳 **INFO LANGGANAN**\n━━━━━━━━━━━━━━━━━━\n{role_msg}\n👤 {u.get('nama_lengkap')}\n\n{status_aktif}\n📊 <b>Cek Hari Ini:</b> {u.get('daily_usage', 0)}x\n━━━━━━━━━━━━━━━━━━\n<i>Perpanjang? Ketik /infobayar</i>")
    
    await update.message.reply_text(msg, parse_mode='HTML')

async def info_bayar(update, context):
    msg = ("💰 **PAKET LANGGANAN (UNLIMITED CEK)**\n━━━━━━━━━━━━━━━━━━\n1️⃣ **5 HARI** = Rp 25.000\n2️⃣ **10 HARI** = Rp 50.000\n3️⃣ **20 HARI** = Rp 75.000\n🔥 **30 HARI** = Rp 100.000 (BEST DEAL!)\n\n" + f"{BANK_INFO}")
    await update.message.reply_text(msg, parse_mode='HTML')

async def handle_photo_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    u = get_user(update.effective_user.id); 
    if not u: return
    await update.message.reply_text("✅ **Bukti diterima!** Sedang diverifikasi Admin...", quote=True)
    expiry_info = u.get('expiry_date') or "EXPIRED"
    msg = (f"💰 **TOPUP DURASI REQUEST**\n👤 {u['nama_lengkap']}\n🆔 `{u['user_id']}`\n📅 Expired: {expiry_info}\n📝 Note: {update.message.caption or '-'}\n\n👉 <b>Manual:</b> <code>/topup {u['user_id']} [HARI]</code>")
    kb = [[InlineKeyboardButton("✅ 5 HARI", callback_data=f"topup_{u['user_id']}_5"), InlineKeyboardButton("✅ 10 HARI", callback_data=f"topup_{u['user_id']}_10")], [InlineKeyboardButton("✅ 20 HARI", callback_data=f"topup_{u['user_id']}_20"), InlineKeyboardButton("✅ 30 HARI", callback_data=f"topup_{u['user_id']}_30")], [InlineKeyboardButton("🔢 MANUAL / CUSTOM", callback_data=f"man_topup_{u['user_id']}")], [InlineKeyboardButton("❌ TOLAK", callback_data=f"topup_{u['user_id']}_rej")]]
    await context.bot.send_photo(ADMIN_ID, update.message.photo[-1].file_id, caption=msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')


# --- [BARU] HELPER: TOMBOL AKSI GRUP (HUBUNGI + SHARE WA + SALIN) ---
def get_action_buttons(matel_user, unit_data):
    # 1. Link WA Penemu
    user_hp = matel_user.get('no_hp', '-')
    clean_num = re.sub(r'[^0-9]', '', str(user_hp))
    if clean_num.startswith('0'): clean_num = '62' + clean_num[1:]
    wa_penemu = f"https://wa.me/{clean_num}"
    
    # 2. Format Teks Share WA (SAMA PERSIS DENGAN FORMAT LAPORAN)
    share_text = (
        f"*LAPORAN TEMUAN UNIT (ONE ASPAL)*\n"
        f"----------------------------------\n"
        f"🚙 Unit: {unit_data.get('type', '-')}\n"
        f"🔢 Nopol: {unit_data.get('nopol', '-')}\n"
        f"🎨 Warna: {unit_data.get('warna', '-')}\n"
        f"📅 Tahun: {unit_data.get('tahun', '-')}\n"
        f"🔧 Noka: {unit_data.get('noka', '-')}\n"
        f"⚙️ Nosin: {unit_data.get('nosin', '-')}\n"
        f"🏦 Finance: {unit_data.get('finance', '-')}\n"
        f"⚠️ OVD: {unit_data.get('ovd', '-')}\n"
        f"🏢 Branch: {unit_data.get('branch', '-')}\n"
        f"📍 Lokasi: {matel_user.get('alamat', '-')}\n"
        f"👤 Penemu: {matel_user.get('nama_lengkap', '-')} ({matel_user.get('agency', '-')})\n"
        f"----------------------------------\n"
        f"⚠️ *PENTING & DISCLAIMER:*\n"
        f"Informasi ini BUKAN alat yang SAH untuk penarikan unit (Eksekusi).\n"
        f"Mohon untuk konfirmasi ke Pic Leasing atau Kantor."
    )
    encoded_share = urllib.parse.quote(share_text)
    share_link = f"https://wa.me/?text={encoded_share}"
    
    # 3. Callback Copy (Safe Nopol)
    nopol_safe = str(unit_data.get('nopol', '-')).replace(" ", "")
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 Hubungi Penemu", url=wa_penemu)],
        [
            InlineKeyboardButton("📲 Share WA", url=share_link), 
            InlineKeyboardButton("📋 Salin Data", callback_data=f"cp_{nopol_safe}")
        ]
    ])

# --- FUNGSI FORMAT PESAN NOTIFIKASI (PUSAT) ---
def create_notification_text(matel_user, unit_data, header_title):
    clean_nopol = clean_text(unit_data.get('nopol'))
    clean_unit = clean_text(unit_data.get('type'))
    return (
        f"{header_title}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Penemu:</b> {clean_text(matel_user.get('nama_lengkap'))} ({clean_text(matel_user.get('agency'))})\n"
        f"📍 <b>Lokasi:</b> {clean_text(matel_user.get('alamat'))}\n\n"
        f"🚙 <b>Unit:</b> {clean_unit}\n"
        f"🔢 <b>Nopol:</b> {clean_nopol}\n"
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

# 1. NOTIFIKASI KE ADMIN PUSAT (LOG GROUP)
async def notify_hit_to_group(context, u, d):
    try:
        if LOG_GROUP_ID == 0: return
        msg = create_notification_text(u, d, "🚨 <b>UNIT DITEMUKAN! (LOG PUSAT)</b>")
        kb = get_action_buttons(u, d) # Pakai Helper Baru
        await context.bot.send_message(LOG_GROUP_ID, msg, reply_markup=kb, parse_mode='HTML')
    except Exception as e: print(f"❌ Gagal Kirim Notif Admin Pusat: {e}")

# 2. NOTIFIKASI KE GROUP LEASING (PIC)
async def notify_leasing_group(context, matel_user, unit_data):
    leasing_unit = str(unit_data.get('finance', '')).strip().upper()
    if len(leasing_unit) < 3: return
    try:
        res = supabase.table('leasing_groups').select("*").execute()
        groups = res.data
        target_group_ids = []
        for g in groups:
            g_name = str(g['leasing_name']).upper()
            if g_name in leasing_unit or leasing_unit in g_name:
                target_group_ids.append(g['group_id'])
        if not target_group_ids: return
        
        msg = create_notification_text(matel_user, unit_data, "🚨 <b>UNIT DITEMUKAN! (HIT LEASING)</b>")
        kb = get_action_buttons(matel_user, unit_data) # Pakai Helper Baru
        
        for gid in target_group_ids:
            if int(gid) == int(LOG_GROUP_ID): continue 
            try: await context.bot.send_message(gid, msg, reply_markup=kb, parse_mode='HTML')
            except: pass
    except Exception as e: logger.error(f"Error Notify Leasing: {e}")

# 3. NOTIFIKASI KE GROUP AGENCY (MONITORING)
async def notify_agency_group(context, matel_user, unit_data):
    user_agency = str(matel_user.get('agency', '')).strip().upper()
    if len(user_agency) < 3: return
    try:
        res = supabase.table('agency_groups').select("*").execute()
        groups = res.data
        target_group_ids = []
        for g in groups:
            g_name = str(g['agency_name']).upper()
            is_match = g_name in user_agency or user_agency in g_name
            if not is_match:
                similarity = difflib.SequenceMatcher(None, g_name, user_agency).ratio()
                if similarity > 0.8: is_match = True
            if is_match:
                target_group_ids.append(g['group_id'])
        if not target_group_ids: return
        
        msg = create_notification_text(matel_user, unit_data, f"👮‍♂️ <b>LAPORAN ANGGOTA ({user_agency})</b>")
        kb = get_action_buttons(matel_user, unit_data) # Pakai Helper Baru
        
        for gid in target_group_ids:
            if int(gid) == int(LOG_GROUP_ID): continue
            try: await context.bot.send_message(gid, msg, reply_markup=kb, parse_mode='HTML')
            except: pass
    except Exception as e: logger.error(f"Error Notify Agency: {e}")

# [V5.5] REGISTER LEASING GROUP
async def set_leasing_group(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if update.effective_chat.type not in ['group', 'supergroup']:
        return await update.message.reply_text("⚠️ Perintah ini hanya bisa digunakan di dalam GRUP Leasing.")
    if not context.args:
        return await update.message.reply_text("⚠️ Format: `/setgroup [NAMA_LEASING]`\nContoh: `/setgroup BCA`")
    leasing_name = " ".join(context.args).upper()
    chat_id = update.effective_chat.id
    try:
        supabase.table('leasing_groups').delete().eq('group_id', chat_id).execute()
        supabase.table('leasing_groups').insert({"group_id": chat_id, "leasing_name": leasing_name}).execute()
        await update.message.reply_text(f"✅ <b>GRUP TERDAFTAR!</b>\n\nGrup ini sekarang adalah <b>OFFICIAL ALERT GROUP</b> untuk: <b>{leasing_name}</b>.\nSetiap unit '{leasing_name}' ditemukan, notifikasi akan masuk ke sini.", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal set grup: {e}")

# [V6.0] REGISTER AGENCY GROUP
async def set_agency_group(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if update.effective_chat.type not in ['group', 'supergroup']:
        return await update.message.reply_text("⚠️ Perintah ini hanya bisa digunakan di dalam GRUP Agency.")
    if not context.args:
        return await update.message.reply_text("⚠️ Format: `/setagency [NAMA_PT]`\nContoh: `/setagency PT ELANG PERKASA`")
    agency_name = " ".join(context.args).upper()
    chat_id = update.effective_chat.id
    try:
        supabase.table('agency_groups').delete().eq('group_id', chat_id).execute()
        supabase.table('agency_groups').insert({"group_id": chat_id, "agency_name": agency_name}).execute()
        await update.message.reply_text(f"✅ <b>AGENCY TERDAFTAR!</b>\n\nGrup ini sekarang adalah <b>MONITORING ROOM</b> untuk: <b>{agency_name}</b>.\nSetiap Matel dari PT ini menemukan unit, notifikasi masuk sini.", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal set grup: {e}")

# ==============================================================================
# BAGIAN 10: FITUR UPLOAD (MOBILE OPTIMIZED & DISK BASED)
# ==============================================================================

async def upload_start(update, context):
    uid = update.effective_user.id
    if not get_user(uid): return await update.message.reply_text("⛔ Akses Ditolak.")
    
    # Simpan File ID untuk User Flow (Forward ke Admin)
    context.user_data['upload_file_id'] = update.message.document.file_id
    context.user_data['upload_file_name'] = update.message.document.file_name

    # --- ROUTING: ADMIN vs USER ---
    # Jika bukan Admin, masuk ke flow 'upload_leasing_user' (Lapor Upload)
    # Cek support untuk ADMIN_ID (int) atau ADMIN_IDS (list)
    is_admin = False
    if 'ADMIN_ID' in globals() and uid == ADMIN_ID: is_admin = True
    if 'ADMIN_IDS' in globals() and str(uid) in ADMIN_IDS: is_admin = True
    
    if not is_admin:
        await update.message.reply_text(
            "📄 File diterima.\n**Untuk leasing apa file ini?**", 
            parse_mode='Markdown', 
            reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)
        )
        return U_LEASING_USER

    # --- FLOW ADMIN (PROSES DATA) ---
    
    # 1. Siapkan Folder Temp
    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    
    # 2. Download File ke Disk
    fname = update.message.document.file_name
    file_path = os.path.join(temp_dir, f"{uid}_{int(time.time())}_{fname}")
    
    msg = await update.message.reply_text("⏳ **Mendownload & Menganalisa File...**", parse_mode='Markdown')
    
    try:
        f = await update.message.document.get_file()
        await f.download_to_drive(file_path)
        
        # 3. Baca File (Preview Mode)
        with open(file_path, 'rb') as f_read:
            file_content = f_read.read()
            
        df = read_file_robust(file_content, fname)
        df = fix_header_position(df)
        df, found = smart_rename_columns(df)
        
        if 'nopol' not in df.columns: 
            os.remove(file_path)
            return await msg.edit_text("❌ Gagal deteksi kolom NOPOL. Pastikan header benar.")

        fin = 'finance' in df.columns
        
        # Simpan Info File
        context.user_data['upload_path'] = file_path
        context.user_data['upload_cols'] = df.columns.tolist()
        context.user_data['preview_records'] = df.head(5).to_dict(orient='records')
        
        await msg.delete()
        
        report = (
            f"✅ **SCAN BERHASIL (Mobile Mode)**\n"
            f"📊 Kolom: {', '.join(found)}\n"
            f"📁 Total Baris: {len(df):,}\n"
            f"🏦 Leasing: {'✅ ADA' if fin else '⚠️ TIDAK ADA'}\n\n"
            f"👉 Masukkan Nama Leasing (atau SKIP):"
        )
        await update.message.reply_text(report, reply_markup=ReplyKeyboardMarkup([["SKIP"], ["❌ BATAL"]], resize_keyboard=True))
        return U_LEASING_ADMIN

    except Exception as e:
        if os.path.exists(file_path): os.remove(file_path)
        logger.error(f"Upload Error: {e}")
        await msg.edit_text(f"❌ Error Analisa: {e}")
        return ConversationHandler.END

async def upload_leasing_user(update, context):
    nm = update.message.text
    if nm == "❌ BATAL": return await cancel(update, context)
    
    u = get_user(update.effective_user.id)
    file_id = context.user_data.get('upload_file_id')
    
    # Forward ke Admin
    caption = f"📥 **UPLOAD MITRA**\n👤 {u['nama_lengkap']}\n🏦 {nm}"
    try:
        # Kirim ke ADMIN_ID utama
        if 'ADMIN_ID' in globals() and ADMIN_ID != 0:
            await context.bot.send_document(ADMIN_ID, file_id, caption=caption)
    except: pass

    await update.message.reply_text("✅ Terkirim ke Admin.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def upload_leasing_admin(update, context):
    nm = update.message.text.upper()
    preview_data = context.user_data.get('preview_records', [])
    cols = context.user_data.get('upload_cols', [])
    
    if not preview_data:
        return await update.message.reply_text("❌ Sesi kedaluwarsa. Ulangi upload.")

    if nm != 'SKIP': 
        clean_name = standardize_leasing_name(nm)
        fin_display = clean_name
    else:
        if 'finance' in cols: fin_display = "SESUAI FILE (Otomatis)"
        else: fin_display = "UNKNOWN"
    
    context.user_data['target_leasing'] = nm 

    # --- PREVIEW LENGKAP ---
    s = preview_data[0].copy()
    if nm != 'SKIP': s['finance'] = clean_name
    
    labels = {
        'nopol': '🔢 Nopol', 'type': '🚙 Unit', 'finance': '🏦 Leasing',
        'tahun': '📅 Tahun', 'warna': '🎨 Warna', 'noka': '🔧 Noka',
        'nosin': '⚙️ Nosin', 'ovd': '⚠️ OVD', 'branch': '🏢 Cabang'
    }
    
    detail_str = ""
    for k, label in labels.items():
        val = s.get(k)
        if val and str(val).strip().lower() not in ['nan', 'none', '', '-']:
            detail_str += f"   {label}: {val}\n"
    if not detail_str: detail_str = "   (Data kosong/tidak terbaca)"
    
    preview_msg = (
        f"🔎 **PREVIEW UPLOAD**\n"
        f"🏦 Target Leasing: {fin_display}\n"
        f"📝 **Contoh Data Baris 1:**\n"
        f"{detail_str}\n"
        f"⚠️ Klik EKSEKUSI untuk memproses."
    )
    await update.message.reply_text(preview_msg, reply_markup=ReplyKeyboardMarkup([["🚀 EKSEKUSI", "❌ BATAL"]], one_time_keyboard=True))
    return U_CONFIRM_UPLOAD

async def upload_confirm_admin(update, context):
    if update.message.text != "🚀 EKSEKUSI": 
        path = context.user_data.get('upload_path')
        if path and os.path.exists(path): os.remove(path)
        return await cancel(update, context)
    
    file_path = context.user_data.get('upload_path')
    target_leasing = context.user_data.get('target_leasing')
    
    if not file_path or not os.path.exists(file_path):
        return await update.message.reply_text("❌ File hilang. Silakan upload ulang.")

    status_msg = await update.message.reply_text("⏳ **MEMPROSES FILE...**", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')

    try:
        with open(file_path, 'rb') as f_read: content = f_read.read()
        fname = os.path.basename(file_path)
        df = read_file_robust(content, fname)
        df = fix_header_position(df)
        df, _ = smart_rename_columns(df)
        
        if target_leasing != 'SKIP':
            clean_name = standardize_leasing_name(target_leasing)
            df['finance'] = clean_name
        else:
            if 'finance' in df.columns: df['finance'] = df['finance'].apply(standardize_leasing_name)
            else: df['finance'] = 'UNKNOWN'
        
        # Sanitasi & Filter
        df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        df = df.drop_duplicates(subset=['nopol'], keep='last').replace({np.nan: None})
        
        valid_cols = ['nopol', 'type', 'finance', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'branch']
        for c in valid_cols:
            if c not in df.columns: df[c] = None
        
        final_data = json.loads(json.dumps(df[valid_cols].to_dict(orient='records'), default=str))
        total_data = len(final_data)

        # PROSES UPLOAD BATCH
        await status_msg.edit_text(f"🚀 **MENGUPLOAD {total_data:,} DATA...**")
        
        suc, fail = 0, 0
        BATCH = 500
        start_time = time.time()

        def process_batch_sync(batch_data):
            try:
                supabase.table('kendaraan').upsert(batch_data, on_conflict='nopol', count=None).execute()
                return len(batch_data), 0
            except: return 0, len(batch_data)

        for i in range(0, total_data, BATCH):
            if context.user_data.get('stop_signal'):
                await status_msg.edit_text("🛑 **DIHENTIKAN USER.**")
                break
            batch = final_data[i:i+BATCH]
            s_b, f_b = await asyncio.to_thread(process_batch_sync, batch)
            suc += s_b; fail += f_b
            
            if i % (BATCH*5) == 0:
                elapsed = int(time.time() - start_time)
                try: await status_msg.edit_text(f"⏳ **PROGRESS UPLOAD**\n🚀 Data: {suc:,} / {total_data:,}\n⏱ Waktu: {elapsed}s")
                except: pass

        duration = int(time.time() - start_time)
        await status_msg.edit_text(f"✅ **SELESAI!**\n📊 Total: {total_data:,}\n✅ Sukses: {suc:,}\n❌ Gagal: {fail:,}\n⏱ {duration}s")

    except Exception as e:
        logger.error(f"Upload Process Error: {e}")
        await status_msg.edit_text(f"❌ **GAGAL:** {e}")
    finally:
        if file_path and os.path.exists(file_path): 
            try: os.remove(file_path)
            except: pass
        context.user_data.clear()
    return ConversationHandler.END

async def stop_upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['stop_signal'] = True
    await update.message.reply_text("⚠️ **Menghentikan proses...**")
    return ConversationHandler.END

async def cancel(update, context): 
    path = context.user_data.get('upload_path')
    if path and os.path.exists(path): 
        try: os.remove(path)
        except: pass
    context.user_data.clear()
    await update.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ==============================================================================
# BAGIAN 11: REGISTRASI & START
# ==============================================================================

async def register_start(update, context):
    if get_user(update.effective_user.id): return await update.message.reply_text("✅ Anda sudah terdaftar.")
    msg = ("🤖 **ONEASPAL REGISTRATION**\n\nSilakan pilih **Jalur Profesi** Anda:\n\n1️⃣ **MITRA LAPANGAN (MATEL)**\n_(Untuk Profcoll & Jasa Pengamanan Aset)_\n\n2️⃣ **PIC LEASING (INTERNAL)**\n_(Khusus Staff Internal Leasing/Finance)_")
    kb = [["1️⃣ MITRA LAPANGAN"], ["2️⃣ PIC LEASING"], ["❌ BATAL"]]
    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)); return R_ROLE_CHOICE

async def register_role_choice(update, context):
    choice = update.message.text
    if choice == "❌ BATAL": return await cancel(update, context)
    if "1️⃣" in choice: context.user_data['reg_role'] = 'matel'; await update.message.reply_text("🛡️ **FORMULIR MITRA LAPANGAN**\n\n1️⃣ Masukkan **Nama Lengkap**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]])); return R_NAMA
    elif "2️⃣" in choice: context.user_data['reg_role'] = 'pic'; await update.message.reply_text("🤝 **FORMULIR INTERNAL LEASING**\n\n1️⃣ Masukkan **Nama Lengkap**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]])); return R_NAMA
    else: return await register_start(update, context)

async def register_nama(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['r_nama'] = update.message.text; await update.message.reply_text("2️⃣ No HP (WA):"); return R_HP
async def register_hp(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    hp = update.message.text; context.user_data['r_hp'] = hp
    await update.message.reply_text("3️⃣ **Alamat Email:**\n_(Kami butuh email untuk backup data akun Anda)_\n\n👉 _Silakan ketik Email Anda:_", parse_mode='Markdown'); return R_EMAIL

async def register_email(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['r_email'] = update.message.text
    role = context.user_data.get('reg_role', 'matel')
    if role == 'pic': txt = ("4️⃣ **Lokasi Cabang Kantor:**\n_(Contoh: Kelapa Gading, BSD, Bandung Pusat)_\n\n👉 _Ketik nama CABANG tempat Anda bertugas:_")
    else: txt = ("4️⃣ **Domisili / Wilayah Operasi:**\n_(Contoh: Jakarta Timur, Bekasi, Surabaya)_\n\n👉 _Ketik KOTA/DOMISILI Anda:_")
    await update.message.reply_text(txt, parse_mode='Markdown'); return R_KOTA

async def register_kota(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['r_kota'] = update.message.text
    role = context.user_data.get('reg_role', 'matel')
    if role == 'pic': txt = ("5️⃣ **Nama Leasing / Finance:**\n⚠️ _Wajib Nama Resmi (JANGAN DISINGKAT)_\n_(Contoh: BCA FINANCE, ADIRA DINAMIKA, ACC)_\n\n👉 _Ketik Nama FINANCE Anda:_")
    else: txt = ("5️⃣ **Nama Agency / PT:**\n⚠️ _Wajib Nama Lengkap Sesuai Legalitas_\n_(Contoh: PT ELANG PERKASA, PT MAJU JAYA)_\n\n👉 _Ketik Nama AGENCY Anda:_")
    await update.message.reply_text(txt, parse_mode='Markdown'); return R_AGENCY

async def register_agency(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    
    # Simpan Input Agency/Finance
    context.user_data['r_agency'] = update.message.text
    role = context.user_data.get('reg_role', 'matel')
    
    # --- LOGIKA BARU ---
    if role == 'pic':
        # Jika PIC, Minta Foto ID Card
        await update.message.reply_text(
            "📸 **VERIFIKASI IDENTITAS (WAJIB)**\n\n"
            "Sesuai prosedur keamanan, silakan **Kirim Foto ID CARD / NAMETAG KANTOR** Anda sekarang.\n\n"
            "⚠️ _Foto harus jelas untuk diverifikasi Admin._",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
        )
        return R_PHOTO_ID
    else:
        # Jika Matel, Langsung Konfirmasi (Seperti Dulu)
        d = context.user_data
        summary = (f"📝 **KONFIRMASI PENDAFTARAN**\n━━━━━━━━━━━━━━━━━━\n👤 **Nama:** {d['r_nama']}\n📱 **HP:** {d['r_hp']}\n📧 **Email:** {d['r_email']}\n📍 **Domisili:** {d['r_kota']}\n🛡️ **Agency:** {d['r_agency']}\n━━━━━━━━━━━━━━━━━━\nApakah data di atas sudah benar?")
        await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True), parse_mode='Markdown')
        return R_CONFIRM
    
async def register_photo_id(update, context):
    # Cek apakah user mengirim foto
    if not update.message.photo:
        await update.message.reply_text("⚠️ Mohon kirimkan **FOTO** ID Card, bukan dokumen/teks.", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
        return R_PHOTO_ID

    # Ambil ID file foto resolusi terbesar
    photo_file_id = update.message.photo[-1].file_id
    context.user_data['r_photo_proof'] = photo_file_id
    
    d = context.user_data
    # Tampilkan Konfirmasi Akhir untuk PIC
    summary = (
        f"📝 **KONFIRMASI REGISTRASI (PIC)**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Nama:** {d['r_nama']}\n"
        f"📱 **HP:** {d['r_hp']}\n"
        f"📧 **Email:** {d['r_email']}\n"
        f"🏢 **Cabang:** {d['r_kota']}\n"
        f"🏦 **Finance:** {d['r_agency']}\n"
        f"📸 **ID Card:** [Terlampir]\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Kirim data ke Admin untuk verifikasi?"
    )
    await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True), parse_mode='Markdown')
    return R_CONFIRM

async def register_confirm(update, context):
    if update.message.text != "✅ KIRIM": return await cancel(update, context)
    
    d = context.user_data
    role_db = d.get('reg_role', 'matel')
    quota_init = 5000 if role_db == 'pic' else 1000
    
    # Masukkan ke Database
    data_user = {
        "user_id": update.effective_user.id, "nama_lengkap": d['r_nama'], 
        "no_hp": d['r_hp'], "email": d['r_email'], "alamat": d['r_kota'], 
        "agency": d['r_agency'], "quota": quota_init, "status": "pending", 
        "role": role_db, "ref_korlap": None
    }
    
    try:
        supabase.table('users').insert(data_user).execute()
        
        # Balasan ke User
        if role_db == 'pic': 
            await update.message.reply_text("✅ **PENDAFTARAN TERKIRIM**\nAkses Enterprise Workspace sedang diverifikasi Admin.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
        else: 
            await update.message.reply_text("✅ **PENDAFTARAN TERKIRIM**\nData Mitra sedang diverifikasi Admin Pusat.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
        
        # Siapkan Pesan Admin
        wa_link = format_wa_link(d['r_hp']) 
        msg_admin = (
            f"🔔 <b>REGISTRASI BARU ({role_db.upper()})</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Nama:</b> {clean_text(d['r_nama'])}\n"
            f"🆔 <b>User ID:</b> <code>{update.effective_user.id}</code>\n"
            f"🏢 <b>Agency/Fin:</b> {clean_text(d['r_agency'])}\n"
            f"📍 <b>Area:</b> {clean_text(d['r_kota'])}\n"
            f"📱 <b>HP/WA:</b> {wa_link}\n"
            f"📧 <b>Email:</b> {clean_text(d['r_email'])}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
        
        kb = [[InlineKeyboardButton("✅ TERIMA (AKTIFKAN)", callback_data=f"appu_{update.effective_user.id}")], [InlineKeyboardButton("❌ TOLAK (HAPUS)", callback_data=f"reju_{update.effective_user.id}")]]
        
        # --- LOGIKA KIRIM KE ADMIN ---
        # Jika PIC dan ada Foto -> Kirim Foto + Caption
        if role_db == 'pic' and 'r_photo_proof' in d:
            await context.bot.send_photo(
                chat_id=ADMIN_ID, 
                photo=d['r_photo_proof'], 
                caption=msg_admin + "📸 <i>Bukti ID Card terlampir.</i>", 
                reply_markup=InlineKeyboardMarkup(kb), 
                parse_mode='HTML'
            )
        # Jika Matel -> Kirim Teks Biasa
        else:
            await context.bot.send_message(
                chat_id=ADMIN_ID, 
                text=msg_admin + "<i>Silakan validasi data mitra ini.</i>", 
                reply_markup=InlineKeyboardMarkup(kb), 
                parse_mode='HTML', 
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
            
    except Exception as e: 
        logger.error(f"Reg Error: {e}")
        await update.message.reply_text("❌ Gagal Terkirim. User ID Anda mungkin sudah terdaftar.", reply_markup=ReplyKeyboardRemove())
        
    return ConversationHandler.END


# ==============================================================================
# BAGIAN 12: START & CORE SEARCH ENGINE
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    try:
        # 1. Cek User di Database
        data = supabase.table("users").select("*").eq("user_id", user.id).execute()
        
        # === SKENARIO 1: USER BARU (BELUM TERDAFTAR) ===
        if not data.data:
            msg_guest = (
                f"🤖 <b>SELAMAT DATANG DI ONE ASPAL BOT</b>\n"
                f"<i>Sistem Manajemen Aset & Recovery Terpadu</i>\n\n"
                f"Halo, <b>{clean_text(user.full_name)}</b>! 👋\n"
                f"Anda belum terdaftar sebagai mitra kami.\n\n"
                f"🚀 <b>LANGKAH SELANJUTNYA:</b>\n"
                f"Silakan daftarkan diri Anda untuk akses penuh.\n"
                f"👉 <b>Ketik /register</b>\n\n"
                f"<i>Kami melayani Mitra Lapangan (Matel) & PIC Leasing Resmi.</i>"
            )
            await update.message.reply_text(msg_guest, parse_mode='HTML')
            return

        # === SKENARIO 2: USER SUDAH ADA DI DATABASE ===
        user_db = data.data[0]
        status = user_db.get('status', 'pending')
        
        # Cek Status Akun
        if status == 'pending':
            await update.message.reply_text(
                f"⏳ <b>AKUN SEDANG DIVERIFIKASI</b>\n"
                f"Halo {clean_text(user_db.get('nama_lengkap'))}, data pendaftaran Anda sudah masuk dan sedang direview Admin.\n"
                f"Mohon tunggu notifikasi selanjutnya.",
                parse_mode='HTML'
            )
            return
        elif status == 'rejected':
            await update.message.reply_text("⛔ <b>PENDAFTARAN DITOLAK</b>\nSilakan hubungi Admin untuk info lebih lanjut.", parse_mode='HTML')
            return
        elif status != 'active':
            await update.message.reply_text("⛔ <b>AKUN NONAKTIF</b>\nHubungi Admin untuk mengaktifkan kembali.", parse_mode='HTML')
            return

        # === SKENARIO 3: USER AKTIF (Tampilkan Menu Sesuai Role) ===
        role_user = user_db.get('role', 'matel')
        
        # Ambil Info Global (Jika ada)
        global GLOBAL_INFO
        info_txt = f"📢 <b>INFO:</b> {clean_text(GLOBAL_INFO)}\n━━━━━━━━━━━━━━━━━━\n\n" if GLOBAL_INFO else ""

        # A. TAMPILAN PIC LEASING (TEKS ORIGINAL SESUAI REQUEST)
        if role_user == 'pic':
            nama_pic = clean_text(user_db.get('nama_lengkap'))
            
            # [PENTING] Kalimat ini dikembalikan ke versi Original SOP
            welcome_text = (
                f"{info_txt}"
                f"Selamat Pagi, Pak {nama_pic}.\n\n"
                f"Izin memperkenalkan fitur <b>Private Enterprise</b> di OneAspal Bot.\n\n"
                f"Kami menyediakan <b>Private Cloud</b> agar Bapak bisa menyimpan data kendaraan dengan aman menggunakan <b>Blind Check System</b>.\n\n"
                f"🔐 <b>Keamanan Data:</b>\n"
                f"Di sistem ini, Bapak <b>TIDAK</b> dikategorikan menyebarkan data kepada orang lain (Aman secara SOP). Bapak hanya mengarsipkan data digital untuk menunjang <b>Performance Pekerjaan</b> Bapak sendiri.\n\n"
                f"Data Bapak <b>TIDAK BISA</b> dilihat atau didownload user lain. Sistem hanya akan memberi notifikasi kepada Bapak jika unit tersebut ditemukan di lapangan.\n\n"
                f"Silakan dicoba fitur <b>Upload Data</b>-nya, Pak (Menu Sinkronisasi).\n\n"
                f"<i>Jika ada pertanyaan, silakan balas pesan ini melalui tombol <b>📞 BANTUAN TEKNIS</b> di menu utama.</i>"
            )
            
            kb = [["🔄 SINKRONISASI DATA", "📂 DATABASE SAYA"], ["📞 BANTUAN TEKNIS"]]
            await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

        # B. TAMPILAN MITRA LAPANGAN (MATEL/KORLAP)
        else:
            welcome_text = (
                f"{info_txt}"
                f"🦅 <b>ONE ASPAL BOT: ASSET RECOVERY</b>\n"
                f"Halo, <b>{clean_text(user_db.get('nama_lengkap'))}</b>! 🫡\n\n"
                f"⚡ <b>READY TO SERVE:</b>\n"
                f"Database <b>Terlengkap & Terupdate</b> siap digunakan.\n"
                f"Bot didesain <b>Super Cepat & Hemat Kuota</b>.\n\n"
                f"🔎 <b>CARA PENCARIAN:</b>\n"
                f"Ketik NOPOL / NOKA / NOSIN langsung di sini.\n"
                f"Contoh: <code>B1234ABC</code>\n\n"
                f"💡 <b>SHORTCUT:</b>\n"
                f"/cekkuota - Sisa paket\n"
                f"/lapor - Lapor unit aman\n"
                f"/admin - Bantuan Admin\n\n"
                f"<i>Salam Satu Aspal! 🏴‍☠️</i>"
            )
            await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=ReplyKeyboardRemove())

    except Exception as e:
        logger.error(f"Error start: {e}")
        await update.message.reply_text(f"⚠️ <b>SISTEM SEDANG SIBUK</b>\nSilakan coba lagi.\n<i>Error: {e}</i>", parse_mode='HTML')

async def panduan(update, context):
    u = get_user(update.effective_user.id)
    if u and u.get('role') == 'pic': 
        msg = ("📖 <b>PANDUAN ENTERPRISE WORKSPACE</b>\n━━━━━━━━━━━━━━━━━━\n\n1️⃣ <b>SINKRONISASI DATA (Private Cloud)</b>\n• Klik tombol <b>🔄 SINKRONISASI DATA</b>.\n• Upload file Excel data tarikan Anda.\n• Data akan diamankan di server pribadi (Tidak terlihat user lain).\n\n2️⃣ <b>MONITORING UNIT</b>\n• Sistem bekerja otomatis 24 jam.\n• Jika Matel menemukan unit Anda, Notifikasi akan masuk ke:\n   👉 <b>GRUP LEASING OFFICIAL</b> (Pastikan Grup sudah didaftarkan).\n\n3️⃣ <b>CEK STATUS DATA (VALIDASI)</b>\n• Ingin memastikan data sudah masuk atau sudah terhapus?\n• Cukup <b>ketik Nopol</b> unit tersebut di sini.\n• Jika muncul = Data Aktif (Tayang).\n• Jika 'Tidak Ditemukan' = Data Sudah Bersih.\n\n4️⃣ <b>MANAJEMEN ARSIP</b>\n• Untuk menghapus data unit yang sudah lunas/aman, gunakan fitur <b>Update/Hapus Massal</b> saat upload file baru.\n\n<i>Butuh bantuan? Klik tombol 📞 BANTUAN TEKNIS.</i>")
    else: 
        msg = ("📖 <b>PANDUAN PENGGUNAAN ONEASPAL</b>\n\n1️⃣ <b>Cari Data Kendaraan</b>\n   - Ketik Nopol secara lengkap atau sebagian.\n   - Contoh: <code>B 1234 ABC</code> atau <code>1234</code>\n\n2️⃣ <b>Upload File (Mitra)</b>\n   - Kirim file Excel/CSV/ZIP ke bot ini.\n   - Bot akan membaca otomatis.\n\n3️⃣ <b>Upload Satuan / Kiriman</b>\n   - Gunakan perintah /tambah untuk input data manual.\n\n4️⃣ <b>Lapor Unit Selesai</b>\n   - Gunakan perintah /lapor jika unit sudah ditarik.\n\n5️⃣ <b>Cek Kuota</b>\n   - Ketik /cekkuota untuk melihat sisa HIT.\n\n6️⃣ <b>Bantuan Admin</b>\n   - Ketik /admin [pesan] untuk support.\n\n7️⃣ <b>Perpanjang Langganan</b>\n   - Ketik /infobayar untuk Topup.")
    await update.message.reply_text(msg, parse_mode='HTML')

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
        elif reason == "DAILY_LIMIT": return await update.message.reply_text("⛔ **BATAS HARIAN TERCAPAI**\nAnda telah mencapai limit cek hari ini. Reset otomatis jam 00:00.", parse_mode='Markdown')
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
    except Exception as e: logger.error(f"Search error: {e}"); await update.message.reply_text("❌ Error DB.")

async def show_unit_detail_original(update, context, d, u):
    txt = (f"🚨 <b>UNIT DITEMUKAN! (HIT)</b>\n━━━━━━━━━━━━━━━━━━\n🚙 <b>Unit:</b> {clean_text(d.get('type', '-'))}\n🔢 <b>Nopol:</b> {clean_text(d.get('nopol', '-'))}\n🎨 <b>Warna:</b> {clean_text(d.get('warna', '-'))}\n📅 <b>Tahun:</b> {clean_text(d.get('tahun', '-'))}\n----------------------------------\n🔧 <b>Noka:</b> {clean_text(d.get('noka', '-'))}\n⚙️ <b>Nosin:</b> {clean_text(d.get('nosin', '-'))}\n----------------------------------\n🏦 <b>Finance:</b> {clean_text(d.get('finance', '-'))}\n⚠️ <b>OVD:</b> {clean_text(d.get('ovd', '-'))}\n🏢 <b>Branch:</b> {clean_text(d.get('branch', '-'))}\n━━━━━━━━━━━━━━━━━━\nInformasi ini BUKAN alat yang SAH untuk penarikan unit (Eksekusi).\nMohon untuk konfirmasi ke Pic Leasing atau Kantor.")
    share_text = (f"*LAPORAN TEMUAN UNIT (ONE ASPAL)*\n----------------------------------\n🚙 Unit: {d.get('type', '-')}\n🔢 Nopol: {d.get('nopol', '-')}\n🎨 Warna: {d.get('warna', '-')}\n📅 Tahun: {d.get('tahun', '-')}\n🔧 Noka: {d.get('noka', '-')}\n⚙️ Nosin: {d.get('nosin', '-')}\n🏦 Finance: {d.get('finance', '-')}\n⚠️ OVD: {d.get('ovd', '-')}\n🏢 Branch: {d.get('branch', '-')}\n📍 Lokasi: {u.get('alamat', '-')}\n👤 Penemu: {u.get('nama_lengkap', '-')} ({u.get('agency', '-')})\n----------------------------------\n⚠️ *PENTING & DISCLAIMER:*\nInformasi ini BUKAN alat yang SAH untuk penarikan unit (Eksekusi).\nMohon untuk konfirmasi ke Pic Leasing atau Kantor.")
    encoded_text = urllib.parse.quote(share_text); wa_url = f"https://wa.me/?text={encoded_text}"
    nopol_safe = d['nopol'].replace(" ", "") 
    kb = [[InlineKeyboardButton("📲 SHARE KE WA (Lapor PIC)", url=wa_url)], [InlineKeyboardButton("📋 SALIN TEKS LENGKAP", callback_data=f"cp_{nopol_safe}")]]
    await context.bot.send_message(chat_id=update.effective_chat.id, text=txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    await notify_hit_to_group(context, u, d)    # Ke Admin Pusat
    await notify_leasing_group(context, u, d)   # Ke Leasing
    await notify_agency_group(context, u, d)    # Ke Agency
    increment_daily_usage(u['user_id'], u.get('daily_usage', 0))
    # [FIX CALL] Pass full user object 'u' instead of just id/name
    log_successful_hit(u, d)

async def show_multi_choice(update, context, data_list, keyword):
    global GLOBAL_INFO; info_txt = f"📢 INFO: {GLOBAL_INFO}\n\n" if GLOBAL_INFO else ""
    txt = f"{info_txt}🔎 Ditemukan **{len(data_list)} data** mirip '`{keyword}`':\n\n"
    keyboard = []
    for i, item in enumerate(data_list):
        nopol = item['nopol']; unit = item.get('type', 'Unknown')[:10]; leasing = item.get('finance', 'Unknown')
        btn_text = f"{nopol} | {unit} | {leasing}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"view_{item['nopol']}")])
        if i >= 9: break 
    if len(data_list) > 10: txt += "_(Menampilkan 10 hasil teratas)_"
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


# ==============================================================================
# BAGIAN 13: HANDLER KONVERSASI
# ==============================================================================

async def add_manual_start(update, context):
    await update.message.reply_text("📝 **TAMBAH DATA MANUAL**\nMode ini untuk memasukkan data unit satu per satu.\n\n1️⃣ **Silakan Ketik NOPOL:**\n_(Contoh: B 1234 ABC)_", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)); return ADD_NOPOL
async def add_nopol(update, context):
    text = update.message.text
    if text == "❌ BATAL": return await cancel(update, context)
    nopol_clean = re.sub(r'[^a-zA-Z0-9]', '', text).upper()
    if len(nopol_clean) < 3: await update.message.reply_text("⚠️ Nopol terlalu pendek. Silakan ketik ulang:"); return ADD_NOPOL
    context.user_data['new_nopol'] = nopol_clean
    await update.message.reply_text(f"✅ Nopol: **{nopol_clean}**\n\n2️⃣ **Ketik Tipe / Merk Mobil:**", parse_mode='Markdown'); return ADD_UNIT
async def add_unit(update, context):
    text = update.message.text
    if text == "❌ BATAL": return await cancel(update, context)
    context.user_data['new_unit'] = text.upper()
    await update.message.reply_text(f"✅ Unit: **{text.upper()}**\n\n3️⃣ **Ketik Nama Leasing / Finance:**", parse_mode='Markdown'); return ADD_LEASING
async def add_leasing(update, context):
    text = update.message.text
    if text == "❌ BATAL": return await cancel(update, context)
    context.user_data['new_finance'] = text.upper()
    await update.message.reply_text(f"✅ Leasing: **{text.upper()}**\n\n4️⃣ **Ketik No HP Kiriman / Pelapor:**", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["⏩ LEWATI", "❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)); return ADD_PHONE
async def add_phone(update, context):
    text = update.message.text
    if text == "❌ BATAL": return await cancel(update, context)
    phone_info = "-" if text == "⏩ LEWATI" else text
    context.user_data['new_phone'] = phone_info
    await update.message.reply_text("5️⃣ **Keterangan Tambahan (Opsional):**", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["⏩ LEWATI", "❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)); return ADD_NOTE
async def add_note(update, context):
    text = update.message.text
    if text == "❌ BATAL": return await cancel(update, context)
    note = "-" if text == "⏩ LEWATI" else text
    context.user_data['new_note'] = note
    d = context.user_data
    msg = (f"📋 **KONFIRMASI DATA BARU**\n━━━━━━━━━━━━━━━━━━\n🔢 **Nopol:** {d['new_nopol']}\n🚙 **Unit:** {d['new_unit']}\n🏦 **Leasing:** {d['new_finance']}\n📱 **Info HP:** {d['new_phone']}\n📝 **Ket:** {d['new_note']}\n━━━━━━━━━━━━━━━━━━\nApakah data sudah benar?")
    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["✅ SIMPAN", "❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)); return ADD_CONFIRM
async def add_save(update, context):
    if update.message.text != "✅ SIMPAN": return await cancel(update, context)
    
    d = context.user_data
    user = update.effective_user
    u_db = get_user(user.id)
    
    # Simpan data sementara di memory bot (via context_data) untuk diambil saat Admin klik tombol
    # Kita pakai prefix 'prop_' (proposal) + nopol agar unik
    prop_id = d['new_nopol']
    
    # Siapkan paket data yang akan di-insert nanti
    final_ovd = f"{d['new_note']} (Info: {d['new_phone']})"
    payload = {
        "nopol": d['new_nopol'], 
        "type": d['new_unit'], 
        "finance": d['new_finance'], 
        "ovd": final_ovd, 
        "branch": "-", 
        "tahun": "-", 
        "warna": "-", 
        "noka": "-", 
        "nosin": "-"
    }
    
    # Simpan di memory bot sementara (akan hilang jika bot restart, tapi cukup untuk verifikasi cepat)
    context.bot_data[f"prop_{prop_id}"] = payload
    
    # 1. Info ke User
    await update.message.reply_text(
        f"⏳ **DATA TERKIRIM UNTUK VERIFIKASI**\n"
        f"Data Nopol `{d['new_nopol']}` sedang ditinjau Admin sebelum ditayangkan.", 
        parse_mode='Markdown', 
        reply_markup=ReplyKeyboardRemove()
    )
    
    # 2. Info ke Admin (Minta Persetujuan)
    msg_admin = (
        f"📝 **PENGAJUAN DATA BARU (MANUAL)**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Pengirim:** {clean_text(u_db.get('nama_lengkap', user.full_name))}\n"
        f"🏢 **Agency:** {clean_text(u_db.get('agency', '-'))}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔢 **Nopol:** `{d['new_nopol']}`\n"
        f"🚙 **Unit:** {d['new_unit']}\n"
        f"🏦 **Leasing:** {d['new_finance']}\n"
        f"📱 **Info HP:** {d['new_phone']}\n"
        f"📝 **Ket:** {d['new_note']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ _Data belum masuk database sebelum Anda setujui._"
    )
    
    # Tombol Terima / Tolak
    # Callback data: v_acc_NOPOL_USERID (Acc) atau v_rej_NOPOL_USERID (Reject)
    kb = [
        [InlineKeyboardButton("✅ SETUJUI (TAYANGKAN)", callback_data=f"v_acc_{prop_id}_{user.id}")],
        [InlineKeyboardButton("❌ TOLAK", callback_data=f"v_rej_{prop_id}_{user.id}")]
    ]
    
    try:
        await context.bot.send_message(ADMIN_ID, msg_admin, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    except Exception as e:
        logger.error(f"Gagal kirim ke admin: {e}")
        
    return ConversationHandler.END

async def lapor_delete_start(update, context):
    if not get_user(update.effective_user.id): return
    msg = ("🗑️ **LAPOR UNIT SELESAI/AMAN**\n\nAdmin akan memverifikasi laporan ini sebelum data dihapus.\n\n👉 **Masukkan Nomor Polisi (Nopol) unit:**")
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True), parse_mode='Markdown'); return L_NOPOL
async def lapor_delete_check(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    n = update.message.text.upper().replace(" ", ""); res = supabase.table('kendaraan').select("*").eq('nopol', n).execute()
    if not res.data: await update.message.reply_text(f"❌ Nopol `{n}` tidak ditemukan di database.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown'); return ConversationHandler.END
    unit_data = res.data[0]; context.user_data['lapor_nopol'] = n; context.user_data['lapor_type'] = unit_data.get('type', '-'); context.user_data['lapor_finance'] = unit_data.get('finance', '-')
    await update.message.reply_text(f"✅ **Unit Ditemukan:**\n🚙 {unit_data.get('type')}\n🏦 {unit_data.get('finance')}\n\n👉 **Masukkan ALASAN penghapusan:**", parse_mode='Markdown'); return L_REASON
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

async def delete_unit_start(update, context): 
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🗑️ **HAPUS MANUAL**\nNopol:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]])); return D_NOPOL
async def delete_unit_check(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    n = update.message.text.upper().replace(" ", ""); context.user_data['del_nopol'] = n
    await update.message.reply_text(f"Hapus `{n}`?", reply_markup=ReplyKeyboardMarkup([["✅ YA", "❌ BATAL"]])); return D_CONFIRM
async def delete_unit_confirm(update, context):
    if update.message.text == "✅ YA": supabase.table('kendaraan').delete().eq('nopol', context.user_data['del_nopol']).execute(); await update.message.reply_text("✅ Terhapus.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def stop_upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['stop_signal'] = True
    await update.message.reply_text("⚠️ **Menghentikan proses...** (Tunggu sebentar)")
    return ConversationHandler.END

async def cancel(update, context): 
    context.user_data.clear()
    await update.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- MASTER CALLBACK HANDLER (CLEAN VERSION) ---
async def callback_handler(update, context):
    query = update.callback_query
    await query.answer() # Wajib agar loading di tombol hilang
    data = query.data 
    
    # [DEBUG] Cek tombol apa yang ditekan di Terminal
    print(f"🔘 Tombol Ditekan: {data}")

    # 1. STOP UPLOAD
    if data == "stop_upload_task":
        context.user_data['stop_signal'] = True
        await query.edit_message_text("🛑 <b>BERHENTI!</b>\nMenunggu proses batch terakhir selesai...", parse_mode='HTML')

    # 2. VIEW DETAIL UNIT
    elif data.startswith("view_"):
        nopol_target = data.replace("view_", "")
        u = get_user(update.effective_user.id)
        res = supabase.table('kendaraan').select("*").eq('nopol', nopol_target).execute()
        if res.data: 
            await show_unit_detail_original(update, context, res.data[0], u)
        else: 
            await query.edit_message_text("❌ Data unit sudah tidak tersedia.")
    
    # 3. MANUAL TOPUP ADMIN (PERBAIKAN FEEDBACK)
    elif data.startswith("topup_") or data.startswith("adm_topup_"):
        parts = data.split("_")
        uid = int(parts[-2])
        days_str = parts[-1] 
        
        if days_str == "rej":
            await context.bot.send_message(uid, "❌ Permintaan Topup DITOLAK Admin.")
            await query.edit_message_caption("❌ DITOLAK.")
        else:
            days = int(days_str)
            suc, new_exp = add_subscription_days(uid, days)
            
            if suc:
                exp_str = new_exp.strftime('%d %b %Y')
                
                # 1. FEEDBACK KE USER (Notifikasi)
                try:
                    await context.bot.send_message(uid, f"✅ **TOPUP BERHASIL!**\n\nPaket: +{days} Hari\nAktif s/d: {exp_str}\n\nTerima kasih! 🦅")
                except: pass

                # 2. FEEDBACK KE ADMIN (Visual Alert & Laporan)
                # Pop-up di layar (Toast)
                await query.answer(f"✅ SUKSES! Kuota User +{days} Hari.", show_alert=True)
                
                # Update Caption Tombol (Agar ketahuan sudah diproses)
                try:
                    await query.edit_message_caption(f"✅ SUKSES (+{days} Hari)\nExp Baru: {exp_str}")
                except Exception:
                    pass # Abaikan jika pesan tidak berubah
                
                # Laporan Chat ke Admin (Sesuai Request)
                try:
                    user_info = get_user(uid)
                    nama_user = user_info.get('nama_lengkap', 'Unknown')
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"👮‍♂️ **LAPORAN TOPUP MANUAL**\n━━━━━━━━━━━━━━━━━━\n👤 <b>User:</b> {nama_user}\n🆔 <b>ID:</b> <code>{uid}</code>\n➕ <b>Tambah:</b> {days} Hari\n📅 <b>Expired Baru:</b> {exp_str}\n━━━━━━━━━━━━━━━━━━\n✅ <i>Transaksi Berhasil Dicatat.</i>",
                        parse_mode='HTML'
                    )
                except: pass
                
            else: 
                await query.answer("❌ GAGAL! Cek Log Server.", show_alert=True)

    # 4. MENU PEMBAYARAN
    elif data == "buy_manual":
        msg = (
            f"🏦 <b>TRANSFER MANUAL</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"<b>BCA:</b> 1234-5678-900 (Budi Baonk)\n"
            f"<b>DANA:</b> 0812-3456-7890\n\n"
            f"👇 <b>LANGKAH SELANJUTNYA:</b>\n"
            f"1. Transfer sesuai nominal.\n"
            f"2. <b>FOTO</b> bukti transfer.\n"
            f"3. <b>KIRIM FOTO</b> ke bot ini."
        )
        await query.message.reply_text(msg, parse_mode='HTML')

    elif data.startswith("buy_"):
        await query.message.reply_text("⚠️ Fitur QRIS Otomatis sedang maintenance. Silakan gunakan Transfer Manual.")

    elif data.startswith("man_topup_"):
        uid = data.split("_")[2]
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"ℹ️ **MODE MANUAL**\n\nSilakan ketik perintah berikut:\n<code>/topup {uid} [JUMLAH_HARI]</code>", parse_mode='HTML')

    # 5. ADMIN USER MANAGEMENT
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
    
    # 6. APPROVE REGISTER (appu_)
    elif data.startswith("appu_"): 
        target_uid = int(data.split("_")[1])
        
        # [LOGIKA TRIAL 3 HARI]
        now = datetime.now(TZ_JAKARTA)
        trial_end = now + timedelta(days=3)
        
        # Update Database
        supabase.table('users').update({
            'status': 'active',
            'expiry_date': trial_end.isoformat()
        }).eq('user_id', target_uid).execute()
        
        # Feedback ke Admin
        exp_display = trial_end.strftime('%d %b %Y')
        try:
            await query.edit_message_caption(f"✅ User {target_uid} DIAKTIFKAN.\n🎁 Trial: 3 Hari (s/d {exp_display})")
        except:
            await query.edit_message_text(f"✅ User {target_uid} DIAKTIFKAN.\n🎁 Trial: 3 Hari (s/d {exp_display})")
        
        # Ambil data user untuk notifikasi
        target_user = get_user(target_uid)
        
        if target_user and target_user.get('role') == 'pic':
            # PESAN UNTUK PIC (Tetap)
            nama_pic = clean_text(target_user.get('nama_lengkap', 'Partner'))
            msg_pic = (
                f"Selamat Pagi, Pak {nama_pic}.\n\n"
                f"Izin memperkenalkan fitur <b>Private Enterprise</b> di OneAspal Bot.\n"
                f"Kami menyediakan <b>Private Cloud</b> agar Bapak bisa menyimpan data kendaraan dengan aman menggunakan <b>Blind Check System</b>.\n\n"
                f"🔐 <b>Keamanan Data:</b>\n"
                f"Di sistem ini, Bapak <b>TIDAK</b> dikategorikan menyebarkan data kepada orang lain (Aman secara SOP). Bapak hanya mengarsipkan data digital untuk menunjang <b>Performance Pekerjaan</b> Bapak sendiri.\n\n"
                f"Data Bapak <b>TIDAK BISA</b> dilihat atau didownload user lain. Sistem hanya akan memberi notifikasi kepada Bapak jika unit tersebut ditemukan di lapangan.\n\n"
                f"Silakan dicoba fitur <b>Upload Data</b>-nya, Pak (Menu Sinkronisasi).\n\n"
                f"<i>Jika ada pertanyaan, silakan balas pesan ini melalui tombol <b>📞 BANTUAN TEKNIS</b> di menu utama.</i>"
            )
            try: await context.bot.send_message(target_uid, msg_pic, parse_mode='HTML')
            except: pass

        else:
            # PESAN UNTUK MATEL (Trial 3 Hari + Ikon Petir ⚡)
            nama_user = target_user.get('nama_lengkap', 'Mitra')
            msg_mitra = (
                f"🦅 **SELAMAT BERGABUNG DI ONE ASPAL BOT** 🦅\n"
                f"Halo, {nama_user}! Akun Anda telah **DISETUJUI** ✅.\n\n"
                f"🎁 **BONUS PENDAFTARAN:**\n"
                f"Anda mendapatkan akses <b>TRIAL GRATIS 3 HARI</b>.\n"
                f"📅 <b>Aktif s/d:</b> {exp_display}\n\n"
                f"Fitur kami dirancang **Super Cepat** ⚡ dan **Hemat Kuota** 📉 "
                f"untuk menunjang kinerja Anda di lapangan.\n\n"
                f"🔎 **CARA PENCARIAN:**\n"
                f"Cukup ketik NOPOL, NOKA, atau NOSIN langsung di sini.\n"
                f"Contoh: `B1234ABC` (Tanpa spasi lebih baik)\n\n"
                f"💡 **MENU UTAMA:**\n"
                f"/cekkuota - Cek masa aktif\n"
                f"/infobayar - Perpanjang Langganan\n"
                f"/admin - Bantuan Teknis\n\n"
                f"Selamat bekerja! Salam Satu Aspal. 🏴‍☠️"
            )
            try: await context.bot.send_message(target_uid, msg_mitra, parse_mode='Markdown')
            except: pass
            
    # 7. REJECT REGISTER (reju_)
    elif data.startswith("reju_"):
        target_uid = int(data.split("_")[1])
        # Hapus User
        supabase.table('users').delete().eq('user_id', target_uid).execute()
        
        try:
            await query.edit_message_caption(f"❌ User {target_uid} DITOLAK & DIHAPUS.")
        except:
            await query.edit_message_text(f"❌ User {target_uid} DITOLAK & DIHAPUS.")
            
        try: await context.bot.send_message(target_uid, "⛔ Pendaftaran Ditolak. Silakan daftar ulang dengan data yang benar.")
        except: pass
    
    # 8. COPY TEXT BUTTON
    # COPY TEXT BUTTON (Clean Version)
    elif data.startswith("cp_"):
        nopol_target = data.replace("cp_", "")
        u = get_user(update.effective_user.id)
        if not u: return
        try:
            res = supabase.table('kendaraan').select("*").eq('nopol', nopol_target).execute()
            if not res.data:
                await query.answer("❌ Data unit tidak ditemukan.", show_alert=True)
                return
            d = res.data[0]
            
            # Format Text (Sudah sesuai standar WA)
            share_text = (
                f"*LAPORAN TEMUAN UNIT (ONE ASPAL)*\n"
                f"----------------------------------\n"
                f"🚙 Unit: {d.get('type', '-')}\n"
                f"🔢 Nopol: {d.get('nopol', '-')}\n"
                f"🎨 Warna: {d.get('warna', '-')}\n"
                f"📅 Tahun: {d.get('tahun', '-')}\n"
                f"🔧 Noka: {d.get('noka', '-')}\n"
                f"⚙️ Nosin: {d.get('nosin', '-')}\n"
                f"🏦 Finance: {d.get('finance', '-')}\n"
                f"⚠️ OVD: {d.get('ovd', '-')}\n"
                f"🏢 Branch: {d.get('branch', '-')}\n"
                f"📍 Lokasi: {u.get('alamat', '-')}\n"
                f"👤 Penemu: {u.get('nama_lengkap', '-')} ({u.get('agency', '-')})\n"
                f"----------------------------------\n"
                f"⚠️ *PENTING & DISCLAIMER:*\n"
                f"Informasi ini BUKAN alat yang SAH untuk penarikan unit (Eksekusi).\n"
                f"Mohon untuk konfirmasi ke Pic Leasing atau Kantor."
            )
            
            # [REVISI] Langsung Code Block (Tanpa Kata-Kata Pengantar)
            msg_copy = f"<code>{share_text}</code>"
            
            await query.message.reply_text(msg_copy, parse_mode='HTML')
            await query.answer("✅ Teks siap disalin!")
            
        except Exception as e:
            await query.answer("❌ Gagal Copy.", show_alert=True)

    # 9. APPROVE / REJECT INPUT MANUAL
    elif data.startswith("v_acc_"): 
        parts = data.split("_")
        nopol = parts[2]
        user_id_sender = parts[3]
        item = context.bot_data.get(f"prop_{nopol}")
        if item:
            try:
                supabase.table('kendaraan').upsert(item).execute()
                del context.bot_data[f"prop_{nopol}"]
                await query.edit_message_text(f"✅ Data `{nopol}` DISETUJUI & Sudah Tayang di Database.")
                try:
                    await context.bot.send_message(user_id_sender, f"✅ **DATA DISETUJUI!**\nUnit `{nopol}` yang Anda input sudah tayang di database.", parse_mode='Markdown')
                except: pass
            except Exception as e:
                await query.edit_message_text(f"❌ Error Database: {e}")
        else:
            await query.edit_message_text("⚠️ Data kadaluwarsa (Bot sempat restart). Minta user input ulang.")

    elif data.startswith("v_rej_"):
        parts = data.split("_")
        nopol = parts[2]
        user_id_sender = parts[3]
        if f"prop_{nopol}" in context.bot_data:
            del context.bot_data[f"prop_{nopol}"]
        
        context.user_data['val_rej_nopol'] = nopol
        context.user_data['val_rej_uid'] = user_id_sender
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ **TOLAK PENGAJUAN MANUAL**\nUnit: {nopol}\n\nKetik ALASAN Penolakan:",
            reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
        )
        return VAL_REJECT_REASON

    # 10. APPROVE / REJECT LAPOR DELETE
    elif data.startswith("del_acc_"):
        parts = data.split("_")
        nopol_target = parts[2]
        user_id_pelapor = parts[3]
        
        try:
            supabase.table('kendaraan').delete().eq('nopol', nopol_target).execute()
            await query.edit_message_caption(f"✅ <b>DISETUJUI & DIHAPUS</b>\nUnit: {nopol_target} telah dibersihkan dari database.", parse_mode='HTML')
            try: 
                await context.bot.send_message(user_id_pelapor, f"✅ <b>LAPORAN DISETUJUI</b>\nUnit <code>{nopol_target}</code> telah kami hapus dari database. Terima kasih kontribusinya.", parse_mode='HTML')
            except: pass
        except Exception as e:
            await query.answer(f"❌ Gagal Hapus: {e}", show_alert=True)

    elif data.startswith("del_rej_"):
        user_id_pelapor = data.split("_")[2]
        await query.edit_message_caption("❌ <b>LAPORAN DITOLAK</b>", parse_mode='HTML')
        try: 
            await context.bot.send_message(user_id_pelapor, "⚠️ Laporan penghapusan unit Anda ditolak oleh Admin. Data dinilai masih valid.", parse_mode='HTML')
        except: pass


if __name__ == '__main__':
    print("🚀 ONEASPAL BOT v6.30 (INTELLIGENCE READY) STARTING...")
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler('stop', stop_upload_command)) # Priority
    
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Document.ALL, upload_start)], 
        states={
            U_LEASING_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_leasing_user)], 
            U_LEASING_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_leasing_admin)], 
            U_CONFIRM_UPLOAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_confirm_admin)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)],
        allow_reentry=True
    ))

    app.add_handler(MessageHandler(filters.Regex(r'^/m_\d+$'), manage_user_panel))
    app.add_handler(MessageHandler(filters.Regex(r'^/cek_\d+$'), cek_user_pending))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(admin_action_start, pattern='^adm_(ban|unban|del)_')], states={ADMIN_ACT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_action_complete)]}, fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(reject_start, pattern='^reju_')], states={REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, reject_complete)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(val_reject_start, pattern='^v_rej_')], states={VAL_REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, val_reject_complete)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    
    # [UPDATE] REGISTER HANDLER DENGAN FOTO ID
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('register', register_start)], 
        states={
            R_ROLE_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_role_choice)], 
            R_NAMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_nama)], 
            R_HP: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_hp)], 
            R_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)], 
            R_KOTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_kota)], 
            R_AGENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_agency)], 
            
            # --- STATE BARU: HANDLER FOTO ID CARD ---
            R_PHOTO_ID: [MessageHandler(filters.PHOTO, register_photo_id)],
            # ----------------------------------------

            R_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_confirm)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]
    ))
    
    conv_add_manual = ConversationHandler(entry_points=[CommandHandler('tambah', add_manual_start)], states={ADD_NOPOL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_nopol)], ADD_UNIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_unit)], ADD_LEASING: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_leasing)], ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)], ADD_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_note)], ADD_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_save)],}, fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex("^❌ BATAL$"), cancel)])
    app.add_handler(conv_add_manual)

    app.add_handler(ConversationHandler(entry_points=[CommandHandler('lapor', lapor_delete_start)], states={L_NOPOL: [MessageHandler(filters.TEXT, lapor_delete_check)], L_REASON: [MessageHandler(filters.TEXT, lapor_reason)], L_CONFIRM: [MessageHandler(filters.TEXT, lapor_delete_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('hapus', delete_unit_start)], states={D_NOPOL: [MessageHandler(filters.TEXT, delete_unit_check)], D_CONFIRM: [MessageHandler(filters.TEXT, delete_unit_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('cekkuota', cek_kuota))
    app.add_handler(CommandHandler('infobayar', info_bayar)) 
    app.add_handler(CommandHandler('topup', admin_topup))
    app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('leasing', get_leasing_list)) 
    app.add_handler(CommandHandler('rekap', rekap_harian))
    app.add_handler(CommandHandler("rekap_member", rekap_member))
    app.add_handler(CommandHandler('users', list_users))
    app.add_handler(CommandHandler('angkat_korlap', angkat_korlap)) 
    app.add_handler(CommandHandler('testgroup', test_group))
    app.add_handler(CommandHandler('balas', admin_reply))
    app.add_handler(CommandHandler('setgroup', set_leasing_group)) 
    app.add_handler(CommandHandler('setagency', set_agency_group))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('admin', contact_admin), MessageHandler(filters.Regex('^📞 BANTUAN TEKNIS$'), contact_admin)], states={SUPPORT_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_send)]}, fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)])) 
    app.add_handler(CommandHandler('panduan', panduan))
    app.add_handler(CommandHandler('setinfo', set_info)) 
    app.add_handler(CommandHandler('delinfo', del_info))        
    app.add_handler(CommandHandler('addagency', add_agency)) 
    app.add_handler(CommandHandler('adminhelp', admin_help)) 
    app.add_handler(MessageHandler(filters.Regex(r'^/rekap[a-zA-Z0-9]+$') & filters.COMMAND, rekap_spesifik))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_topup))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    job_queue = app.job_queue
    # Perhatikan "time=" tetap, tapi isinya jadi "dt_time"
    # job_queue.run_daily(auto_cleanup_logs, time=dt_time(hour=3, minute=0, second=0, tzinfo=TZ_JAKARTA), days=(0, 1, 2, 3, 4, 5, 6))
    
    print("⏰ Jadwal Cleanup Otomatis: AKTIF (Jam 03:00 WIB)")

    print("✅ BOT ONLINE! (v6.30 - INTELLIGENCE READY)")
    app.run_polling()