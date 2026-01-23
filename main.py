################################################################################
#                                                                              #
#                      PROJECT: ONEASPAL BOT (ASSET RECOVERY)                  #
#                      VERSION: 6.26 (STABLE MASTERPIECE FINAL)                #
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
import html
import difflib
from collections import Counter
from datetime import datetime, timedelta, time
import pytz
import urllib.parse
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
print("🔍 SYSTEM DIAGNOSTIC STARTUP (v6.26)")
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
    supabase: Client = create_client(URL, KEY)
    print("✅ Koneksi Supabase: BERHASIL")
except Exception as e:
    print(f"❌ Koneksi Supabase: GAGAL ({e})")
    exit()

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

R_ROLE_CHOICE, R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_CONFIRM = range(7)
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
        supabase.table('users').update({'daily_usage': current_usage + 1}).eq('user_id', user_id).execute()
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

# [FUNGSI LOGGING]
def log_successful_hit(user_id, user_name, unit_data):
    try:
        leasing_raw = str(unit_data.get('finance', 'UNKNOWN')).upper().strip()
        data = {
            "user_id": user_id,
            "nama_matel": user_name,
            "leasing": leasing_raw,
            "nopol": unit_data.get('nopol'),
            "unit": unit_data.get('type')
        }
        supabase.table('finding_logs').insert(data).execute()
        print(f"📝 LOG DATABASE: Temuan {unit_data.get('nopol')} oleh {user_name} berhasil dicatat.")
    except Exception as e:
        print(f"❌ LOG DATABASE ERROR: {e}")


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
    # Jurus 1: Pemisah Titik Koma (;) - Paling umum di Indo
    try:
        return pd.read_csv(io.BytesIO(content), sep=';', dtype=str, on_bad_lines='skip', encoding='utf-8')
    except: pass
    
    # Jurus 2: Pemisah Koma (,)
    try:
        return pd.read_csv(io.BytesIO(content), sep=',', dtype=str, on_bad_lines='skip', encoding='utf-8')
    except: pass
    
    # Jurus 3: Encoding Latin1 (Windows Legacy)
    try:
        return pd.read_csv(io.BytesIO(content), sep=';', dtype=str, on_bad_lines='skip', encoding='latin1')
    except: pass

    # Menyerah
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
    if update.effective_user.id != ADMIN_ID: return
    msg = (
        "🔐 **ADMIN COMMANDS v6.26 (FULL)**\n\n"
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
            .execute()
        data = res.data
        total_hits = len(data)
        if total_hits == 0:
            return await msg.edit_text(f"📊 **REKAP HARIAN: {target_leasing}**\n\nNihil. Belum ada unit ditemukan hari ini.")
        report = (
            f"📊 **LAPORAN HARIAN KHUSUS: {target_leasing}**\n"
            f"📅 Tanggal: {now.strftime('%d %b %Y')}\n"
            f"🔥 **Total Hit:** {total_hits} Unit\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
        limit_show = 15
        for i, d in enumerate(data[:limit_show]):
            nopol = d.get('nopol', '-')
            unit = d.get('unit', '-')
            matel = d.get('nama_matel', 'Matel')
            report += f"{i+1}. {nopol} | {unit} (Oleh: {matel})\n"
        if total_hits > limit_show: report += f"\n... dan {total_hits - limit_show} unit lainnya."
        report += "\n━━━━━━━━━━━━━━━━━━\n#OneAspalAnalytics"
        await msg.edit_text(report, parse_mode='Markdown')
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
        if not active_list: return await update.message.reply_text("📂 Tidak ada mitra aktif.")
        msg = f"📋 <b>DAFTAR MITRA (Total: {len(active_list)})</b>\n━━━━━━━━━━━━━━━━━━\n"
        now = datetime.now(TZ_JAKARTA)
        no_preview = LinkPreviewOptions(is_disabled=True)
        if pic_list:
            msg += "🏦 <b>INTERNAL LEASING (PIC)</b>\n"
            for i, u in enumerate(pic_list, 1):
                wa_link = format_wa_link(u.get('no_hp'))
                entry = (f"{i}. 🤝 <b>{clean_text(u.get('nama_lengkap'))}</b>\n   📱 {wa_link} | 🏢 {clean_text(u.get('agency'))}\n   ⚙️ /m_{u['user_id']}\n\n")
                if len(msg) + len(entry) > 4000: 
                    await update.message.reply_text(msg, parse_mode='HTML', link_preview_options=no_preview)
                    msg = ""
                msg += entry
            msg += "━━━━━━━━━━━━━━━━━━\n"
        if field_list:
            msg += "🛡️ <b>MITRA LAPANGAN</b>\n"
            for i, u in enumerate(field_list, 1):
                exp_str = u.get('expiry_date')
                if exp_str:
                    exp_dt = datetime.fromisoformat(exp_str.replace('Z', '+00:00')).astimezone(TZ_JAKARTA)
                    delta = exp_dt - now
                    days_left = "❌ EXP" if delta.days < 0 else f"⏳ {delta.days} Hari"
                else: days_left = "❌ NULL"
                wa_link = format_wa_link(u.get('no_hp'))
                icon = "🎖️" if u.get('role') == 'korlap' else "🛡️"
                entry = (f"{i}. {icon} <b>{clean_text(u.get('nama_lengkap'))}</b>\n   {days_left} | 🏢 {clean_text(u.get('agency'))}\n   📱 {wa_link} | ⚙️ /m_{u['user_id']}\n\n")
                if len(msg) + len(entry) > 4000: 
                    await update.message.reply_text(msg, parse_mode='HTML', link_preview_options=no_preview)
                    msg = ""
                msg += entry
        if msg: await update.message.reply_text(msg, parse_mode='HTML', link_preview_options=no_preview)
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def manage_user_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid = int(update.message.text.split('_')[1]); u = get_user(tid)
        if not u: return await update.message.reply_text("❌ User tidak ditemukan.")
        role_now = u.get('role', 'matel'); status_now = u.get('status', 'active')
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


# ==============================================================================
# BAGIAN 8: FITUR AUDIT & ADMIN UTILS
# ==============================================================================

async def auto_cleanup_logs(context: ContextTypes.DEFAULT_TYPE):
    try:
        cutoff_date = datetime.now(TZ_JAKARTA) - timedelta(days=5)
        supabase.table('finding_logs').delete().lt('created_at', cutoff_date.isoformat()).execute()
        print(f"🧹 [AUTO CLEANUP] Log lama berhasil dihapus.")
    except Exception as e: logger.error(f"❌ AUTO CLEANUP ERROR: {e}")

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
        if not data: return await msg.edit_text("❌ Database Kosong.")
        total_global = sum(item['total'] for item in data)
        rpt = (f"🏦 **AUDIT LEASING (LIVE)**\n📦 Total Data: `{total_global:,}` Unit\n━━━━━━━━━━━━━━━━━━\n")
        for item in data:
            k = str(item.get('finance', 'UNKNOWN')).upper(); v = item.get('total', 0)
            if k not in ["UNKNOWN", "NONE", "NAN", "-", "", "NULL"]: 
                entry = f"🔹 **{k}:** `{v:,}`\n"
                if len(rpt) + len(entry) > 4000: rpt += "\n...(dan leasing kecil lainnya)"; break 
                rpt += entry
        await msg.edit_text(rpt, parse_mode='Markdown')
    except Exception as e: 
        logger.error(f"Audit Error: {e}")
        await msg.edit_text(f"❌ **Error:** {e}")

async def set_info(update, context):
    global GLOBAL_INFO
    if update.effective_user.id==ADMIN_ID: GLOBAL_INFO = " ".join(context.args); await update.message.reply_text("✅ Info Set.")
async def del_info(update, context):
    global GLOBAL_INFO
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


# ##############################################################################
# BAGIAN 9: USER FEATURES & NOTIFIKASI
# ##############################################################################

async def cek_kuota(update, context):
    u = get_user(update.effective_user.id)
    if not u or u['status']!='active': return
    global GLOBAL_INFO
    info_banner = f"📢 <b>INFO PUSAT:</b> {clean_text(GLOBAL_INFO)}\n━━━━━━━━━━━━━━━━━━\n" if GLOBAL_INFO else ""
    if u.get('role') == 'pic':
        msg = (f"{info_banner}📂 **DATABASE SAYA**\n━━━━━━━━━━━━━━━━━━\n👤 **User:** {u.get('nama_lengkap')}\n🏢 **Leasing:** {u.get('agency')}\n🔋 **Status Akses:** UNLIMITED (Enterprise)\n━━━━━━━━━━━━━━━━━━\n✅ Sinkronisasi data berjalan normal.")
    else:
        exp_date = u.get('expiry_date')
        if exp_date:
            exp_dt = datetime.fromisoformat(exp_date.replace('Z', '+00:00')).astimezone(TZ_JAKARTA)
            status_aktif = f"✅ AKTIF s/d {exp_dt.strftime('%d %b %Y %H:%M')}"
            remaining = exp_dt - datetime.now(TZ_JAKARTA)
            if remaining.days < 0: status_aktif = "❌ SUDAH EXPIRED"
            else: status_aktif += f"\n⏳ Sisa Waktu: {remaining.days} Hari"
        else: status_aktif = "❌ SUDAH EXPIRED"
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

def create_notification_text(matel_user, unit_data, header_title):
    return (
        f"{header_title}\n━━━━━━━━━━━━━━━━━━\n👤 <b>Penemu:</b> {clean_text(matel_user.get('nama_lengkap'))} ({clean_text(matel_user.get('agency'))})\n📍 <b>Lokasi:</b> {clean_text(matel_user.get('alamat'))}\n\n🚙 <b>Unit:</b> {clean_text(unit_data.get('type'))}\n🔢 <b>Nopol:</b> {clean_text(unit_data.get('nopol'))}\n📅 <b>Tahun:</b> {clean_text(unit_data.get('tahun'))}\n🎨 <b>Warna:</b> {clean_text(unit_data.get('warna'))}\n----------------------------------\n🔧 <b>Noka:</b> {clean_text(unit_data.get('noka'))}\n⚙️ <b>Nosin:</b> {clean_text(unit_data.get('nosin'))}\n----------------------------------\n⚠️ <b>OVD:</b> {clean_text(unit_data.get('ovd'))}\n🏦 <b>Finance:</b> {clean_text(unit_data.get('finance'))}\n🏢 <b>Branch:</b> {clean_text(unit_data.get('branch'))}\n━━━━━━━━━━━━━━━━━━"
    )

async def notify_hit_to_group(context, u, d):
    try:
        if LOG_GROUP_ID == 0: return
        msg = create_notification_text(u, d, "🚨 <b>UNIT DITEMUKAN! (LOG PUSAT)</b>")
        clean_num = re.sub(r'[^0-9]', '', str(u.get('no_hp')))
        if clean_num.startswith('0'): clean_num = '62' + clean_num[1:]
        kb = [[InlineKeyboardButton("📞 Hubungi Penemu (WA)", url=f"https://wa.me/{clean_num}")]]
        await context.bot.send_message(LOG_GROUP_ID, msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    except Exception as e: print(f"❌ Gagal Kirim Notif Pusat: {e}")

async def notify_leasing_group(context, matel_user, unit_data):
    leasing_unit = str(unit_data.get('finance', '')).strip().upper()
    if len(leasing_unit) < 3: return
    try:
        res = supabase.table('leasing_groups').select("*").execute(); groups = res.data
        target_group_ids = [g['group_id'] for g in groups if str(g['leasing_name']).upper() in leasing_unit or leasing_unit in str(g['leasing_name']).upper()]
        if not target_group_ids: return
        msg = create_notification_text(matel_user, unit_data, "🚨 <b>UNIT DITEMUKAN! (HIT LEASING)</b>")
        clean_num = re.sub(r'[^0-9]', '', str(matel_user.get('no_hp')))
        if clean_num.startswith('0'): clean_num = '62' + clean_num[1:]
        kb = [[InlineKeyboardButton("📞 Hubungi Penemu (WA)", url=f"https://wa.me/{clean_num}")]]
        for gid in target_group_ids:
            if int(gid) == int(LOG_GROUP_ID): continue 
            try: await context.bot.send_message(gid, msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
            except: pass
    except Exception as e: logger.error(f"Error Notify Leasing: {e}")

async def notify_agency_group(context, matel_user, unit_data):
    user_agency = str(matel_user.get('agency', '')).strip().upper()
    if len(user_agency) < 3: return
    try:
        res = supabase.table('agency_groups').select("*").execute(); groups = res.data
        target_group_ids = [g['group_id'] for g in groups if str(g['agency_name']).upper() in user_agency or user_agency in str(g['agency_name']).upper()]
        if not target_group_ids: return
        msg = create_notification_text(matel_user, unit_data, f"👮‍♂️ <b>LAPORAN ANGGOTA ({user_agency})</b>")
        clean_num = re.sub(r'[^0-9]', '', str(matel_user.get('no_hp')))
        if clean_num.startswith('0'): clean_num = '62' + clean_num[1:]
        kb = [[InlineKeyboardButton("📞 Hubungi Anggota", url=f"https://wa.me/{clean_num}")]]
        for gid in target_group_ids:
            if int(gid) == int(LOG_GROUP_ID): continue
            try: await context.bot.send_message(gid, msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
            except: pass
    except Exception as e: logger.error(f"Error Notify Agency: {e}")

async def set_leasing_group(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if update.effective_chat.type not in ['group', 'supergroup']: return await update.message.reply_text("⚠️ Gunakan di dalam GRUP Leasing.")
    if not context.args: return await update.message.reply_text("⚠️ Format: `/setgroup NAMA_LEASING`")
    leasing_name = " ".join(context.args).upper(); chat_id = update.effective_chat.id
    try:
        supabase.table('leasing_groups').delete().eq('group_id', chat_id).execute()
        supabase.table('leasing_groups').insert({"group_id": chat_id, "leasing_name": leasing_name}).execute()
        await update.message.reply_text(f"✅ <b>GRUP TERDAFTAR!</b>\nUntuk Leasing: <b>{leasing_name}</b>.", parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Gagal: {e}")

async def set_agency_group(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if update.effective_chat.type not in ['group', 'supergroup']: return await update.message.reply_text("⚠️ Gunakan di dalam GRUP Agency.")
    if not context.args: return await update.message.reply_text("⚠️ Format: `/setagency NAMA_PT`")
    agency_name = " ".join(context.args).upper(); chat_id = update.effective_chat.id
    try:
        supabase.table('agency_groups').delete().eq('group_id', chat_id).execute()
        supabase.table('agency_groups').insert({"group_id": chat_id, "agency_name": agency_name}).execute()
        await update.message.reply_text(f"✅ <b>AGENCY TERDAFTAR!</b>\nUntuk PT: <b>{agency_name}</b>.", parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Gagal: {e}")


# ==============================================================================
# BAGIAN 10: UPLOAD SYSTEM (DIRECT STABLE)
# ==============================================================================

async def upload_start(update, context):
    uid = update.effective_user.id
    if not get_user(uid): return await update.message.reply_text("⛔ Akses Ditolak.")
    context.user_data['upload_file_id'] = update.message.document.file_id
    if uid != ADMIN_ID:
        await update.message.reply_text("📄 File diterima. Leasing apa?", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
        return U_LEASING_USER
    msg = await update.message.reply_text("⏳ **Analisa File...**", parse_mode='Markdown')
    try:
        f = await update.message.document.get_file(); c = await f.download_as_bytearray()
        df = read_file_robust(c, update.message.document.file_name)
        df = fix_header_position(df); df, found = smart_rename_columns(df)
        if 'nopol' not in df.columns: return await msg.edit_text("❌ Gagal deteksi NOPOL.")
        context.user_data['df_records'] = df.to_dict(orient='records'); await msg.delete()
        report = (f"✅ **SCAN SUKSES**\n📊 **Total Baris:** {len(df)}\n👉 **NAMA LEASING?** (Atau 'SKIP')")
        await update.message.reply_text(report, reply_markup=ReplyKeyboardMarkup([["SKIP"], ["❌ BATAL"]], resize_keyboard=True))
        return U_LEASING_ADMIN
    except Exception as e: await msg.edit_text(f"❌ Error: {e}"); return ConversationHandler.END

async def upload_leasing_user(update, context):
    u = get_user(update.effective_user.id)
    await context.bot.send_document(ADMIN_ID, context.user_data['upload_file_id'], caption=f"📥 **UPLOAD MITRA**\n👤 {u['nama_lengkap']}\n🏦 {update.message.text}")
    await update.message.reply_text("✅ Terkirim ke Admin.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

async def upload_leasing_admin(update, context):
    nm = update.message.text.upper()
    if nm == "❌ BATAL": return await cancel(update, context)
    df = pd.DataFrame(context.user_data['df_records'])
    if nm != 'SKIP': df['finance'] = standardize_leasing_name(nm)
    elif 'finance' in df.columns: df['finance'] = df['finance'].apply(standardize_leasing_name)
    else: df['finance'] = 'UNKNOWN'
    
    # MESIN CUCI IDENTITAS (FIX JTII)
    for col in ['nopol', 'noka', 'nosin']:
        if col in df.columns: df[col] = df[col].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
    
    df = df.drop_duplicates(subset=['nopol'], keep='last').replace({np.nan: "-", "nan": "-", "None": "-"})
    valid = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch']
    for c in valid: 
        if c not in df.columns: df[c] = "-"
    
    context.user_data['final_data_records'] = df[valid].to_dict(orient='records'); s = df.iloc[0]
    preview = (f"🔎 **PREVIEW DATA**\n📊 **Total:** {len(df)} Data\n🔹 Nopol: `{s['nopol']}`\n🔹 Unit: {s['type']}\n⚠️ Klik **🚀 EKSEKUSI**.")
    await update.message.reply_text(preview, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["🚀 EKSEKUSI", "❌ BATAL"]], one_time_keyboard=True))
    return U_CONFIRM_UPLOAD

async def upload_confirm_admin(update, context):
    """
    FUNGSI EKSEKUSI TUNGGAL (DIRECT PATH)
    Menanam data langsung dengan pembersihan otomatis.
    """
    act = update.message.text
    if act == "❌ BATAL": return await cancel(update, context)
    if act != "🚀 EKSEKUSI": return
    
    data = context.user_data.get('final_data_records')
    if not data:
        await update.message.reply_text("❌ Sesi habis, silakan upload ulang.")
        return ConversationHandler.END

    msg_status = await update.message.reply_text(
        "🚀 **MEMULAI EKSEKUSI...**\n🧹 _Menanamkan data ke database (Manual Batching)..._", 
        parse_mode='Markdown', 
        reply_markup=ReplyKeyboardRemove()
    )
    
    start_time = time.time()
    try:
        # Pecah batch per 100 agar stabil
        for i in range(0, len(data), 100):
            batch = data[i:i+100]
            await asyncio.to_thread(lambda: supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute())
        
        dur = round(time.time() - start_time, 2)
        await msg_status.edit_text(
            f"✅ **BERHASIL!**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 Total: `{len(data)}` unit\n"
            f"⏱️ Waktu: `{dur} detik`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Data siap dicari di sistem.",
            parse_mode='Markdown'
        )
    except Exception as e:
        await msg_status.edit_text(f"❌ **GAGAL SIMPAN:**\n{e}")
        
    return ConversationHandler.END


# ==============================================================================
# BAGIAN 11: REGISTRASI & START
# ==============================================================================

async def register_start(update, context):
    if get_user(update.effective_user.id): return await update.message.reply_text("✅ Anda sudah terdaftar.")
    msg = ("🤖 **ONEASPAL REGISTRATION**\n1️⃣ MITRA LAPANGAN\n2️⃣ PIC LEASING")
    kb = [["1️⃣ MITRA LAPANGAN"], ["2️⃣ PIC LEASING"], ["❌ BATAL"]]
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)); return R_ROLE_CHOICE

async def register_role_choice(update, context):
    choice = update.message.text
    if choice == "❌ BATAL": return await cancel(update, context)
    context.user_data['reg_role'] = 'matel' if "1️⃣" in choice else 'pic'
    await update.message.reply_text("👤 Nama Lengkap:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]])); return R_NAMA
async def register_nama(update, context): 
    context.user_data['r_nama'] = update.message.text; await update.message.reply_text("2️⃣ No HP (WA):"); return R_HP
async def register_hp(update, context): 
    context.user_data['r_hp'] = update.message.text; await update.message.reply_text("3️⃣ Email:"); return R_EMAIL
async def register_email(update, context): 
    context.user_data['r_email'] = update.message.text; await update.message.reply_text("4️⃣ Kota / Cabang:"); return R_KOTA
async def register_kota(update, context): 
    context.user_data['r_kota'] = update.message.text; await update.message.reply_text("5️⃣ PT / Leasing:"); return R_AGENCY
async def register_agency(update, context):
    context.user_data['r_agency'] = update.message.text; d = context.user_data
    summary = (f"📝 **KONFIRMASI**\n👤 {d['r_nama']}\n🏢 {d['r_agency']}\nKirim?")
    await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ BATAL"]])); return R_CONFIRM
async def register_confirm(update, context):
    if update.message.text != "✅ KIRIM": return await cancel(update, context)
    role_db = context.user_data.get('reg_role', 'matel')
    d = {"user_id": update.effective_user.id, "nama_lengkap": context.user_data['r_nama'], "no_hp": context.user_data['r_hp'], "email": context.user_data['r_email'], "alamat": context.user_data['r_kota'], "agency": context.user_data['r_agency'], "quota": 1000, "status": "pending", "role": role_db}
    try:
        supabase.table('users').insert(d).execute()
        await update.message.reply_text("✅ Terkirim ke Admin.", reply_markup=ReplyKeyboardRemove())
        wa_link = format_wa_link(d['no_hp']) 
        msg_admin = (f"🔔 **REGIS BARU**\n👤 {d['nama_lengkap']}\n🏢 {d['agency']}\n📱 {wa_link}")
        kb = [[InlineKeyboardButton("✅ TERIMA", callback_data=f"appu_{d['user_id']}")], [InlineKeyboardButton("❌ TOLAK", callback_data=f"reju_{d['user_id']}")]]
        await context.bot.send_message(ADMIN_ID, msg_admin, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML', link_preview_options=LinkPreviewOptions(is_disabled=True))
    except: await update.message.reply_text("❌ Gagal. Sudah terdaftar?")
    return ConversationHandler.END


# ==============================================================================
# BAGIAN 12: SEARCH & CORE
# ==============================================================================

async def start(update, context):
    u = get_user(update.effective_user.id)
    global GLOBAL_INFO; info = f"📢 <b>INFO:</b> {clean_text(GLOBAL_INFO)}\n━━━━━━━━━━━━━━━━━━\n\n" if GLOBAL_INFO else ""
    if u and u.get('role') == 'pic':
        msg = (f"{info}🤖 <b>SYSTEM ONEASPAL (ENTERPRISE)</b>\nSelamat Datang, <b>{clean_text(u.get('nama_lengkap'))}</b>")
        kb = [["🔄 SINKRONISASI DATA", "📂 DATABASE SAYA"], ["📞 BANTUAN TEKNIS"]]; await update.message.reply_text(msg, parse_mode='HTML', reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)); return
    if u:
        msg = (f"{info}🤖 <b>Selamat Datang di Oneaspalbot</b>\nHalo, Rekan Mitra Lapangan.")
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=ReplyKeyboardRemove()); return
    msg_guest = (f"🤖 <b>ONEASPAL: Digital Asset Recovery System</b>\nSilakan daftar: /register")
    await update.message.reply_text(msg_guest, parse_mode='HTML')

async def panduan(update, context):
    msg = ("📖 <b>PANDUAN ONEASPAL</b>\n1️⃣ Cari Data: Ketik Nopol\n2️⃣ Upload: Kirim File Excel")
    await update.message.reply_text(msg, parse_mode='HTML')

async def handle_message(update, context):
    text = update.message.text
    if text == "🔄 SINKRONISASI DATA": return await upload_start(update, context)
    if text == "📂 DATABASE SAYA": return await cek_kuota(update, context)
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return await update.message.reply_text("⛔ Akses Pending/Ditolak.")
    is_active, reason = check_subscription_access(u)
    if not is_active: return await update.message.reply_text(f"⛔ {reason}")
    kw = re.sub(r'[^a-zA-Z0-9]', '', text.upper())
    if len(kw) < 3: return await update.message.reply_text("⚠️ Min 3 karakter.")
    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.ilike.%{kw}%,noka.eq.{kw},nosin.eq.{kw}").limit(20).execute()
        if not res.data: return await update.message.reply_text(f"❌ TIDAK DITEMUKAN: `{kw}`", parse_mode='Markdown')
        final = None
        for item in res.data:
            if re.sub(r'[^a-zA-Z0-9]', '', item['nopol']).upper() == kw: final = item; break
        if final: await show_unit_detail_original(update, context, final, u)
        elif len(res.data) == 1: await show_unit_detail_original(update, context, res.data[0], u)
        else:
            kb = [[InlineKeyboardButton(f"{i['nopol']} | {i['type'][:10]}", callback_data=f"view_{i['nopol']}")] for i in res.data[:10]]
            await update.message.reply_text(f"🔎 Hasil mirip `{kw}`:", reply_markup=InlineKeyboardMarkup(kb))
    except: await update.message.reply_text("❌ Error DB.")

async def show_unit_detail_original(update, context, d, u):
    txt = (f"🚨 <b>UNIT DITEMUKAN! (HIT)</b>\n━━━━━━━━━━━━━━━━━━\n🚙 <b>Unit:</b> {d['type']}\n🔢 <b>Nopol:</b> {d['nopol']}\n🏦 <b>Finance:</b> {d['finance']}\n⚠️ <b>OVD:</b> {d['ovd']}\n🏢 <b>Branch:</b> {d.get('branch', '-')}\n━━━━━━━━━━━━━━━━━━\nBUKAN ALAT SAH EKSEKUSI.")
    share_text = (f"*LAPORAN TEMUAN UNIT*\nUnit: {d['type']}\nNopol: {d['nopol']}\nFinance: {d['finance']}\nPenemu: {u['nama_lengkap']}")
    wa_url = f"https://wa.me/?text={urllib.parse.quote(share_text)}"
    kb = [[InlineKeyboardButton("📲 SHARE WA", url=wa_url)], [InlineKeyboardButton("📋 SALIN", callback_data=f"cp_{d['nopol'].replace(' ','')}")] ]
    await context.bot.send_message(chat_id=update.effective_chat.id, text=txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    await notify_hit_to_group(context, u, d); await notify_leasing_group(context, u, d); await notify_agency_group(context, u, d)
    increment_daily_usage(u['user_id'], u.get('daily_usage', 0)); log_successful_hit(u['user_id'], u['nama_lengkap'], d)


# ==============================================================================
# BAGIAN 13: MANUAL & CALLBACK
# ==============================================================================

async def add_manual_start(update, context):
    await update.message.reply_text("🔢 Masukkan Nopol:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]])); return ADD_NOPOL
async def add_nopol(update, context): 
    context.user_data['new_nopol'] = update.message.text.upper().replace(" ",""); await update.message.reply_text("🚙 Unit/Tipe:"); return ADD_UNIT
async def add_unit(update, context): 
    context.user_data['new_unit'] = update.message.text.upper(); await update.message.reply_text("🏦 Finance:"); return ADD_LEASING
async def add_leasing(update, context): 
    context.user_data['new_finance'] = update.message.text.upper(); await update.message.reply_text("📝 OVD/Ket:"); return ADD_NOTE
async def add_note(update, context):
    context.user_data['new_note'] = update.message.text; d = context.user_data
    await update.message.reply_text(f"Kirim `{d['new_nopol']}`?", reply_markup=ReplyKeyboardMarkup([["✅ SIMPAN", "❌ BATAL"]])); return ADD_CONFIRM
async def add_save(update, context):
    if update.message.text == "✅ SIMPAN":
        d = context.user_data; di = {"nopol": d['new_nopol'], "type": d['new_unit'], "finance": d['new_finance'], "ovd": d['new_note']}
        supabase.table('kendaraan').upsert(di, on_conflict='nopol').execute()
        await update.message.reply_text("✅ Tersimpan.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def cancel(update, context): await update.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

async def callback_handler(update, context):
    query = update.callback_query; await query.answer(); data = query.data 
    if data.startswith("view_"):
        n = data.replace("view_", ""); u = get_user(update.effective_user.id)
        res = supabase.table('kendaraan').select("*").eq('nopol', n).execute()
        if res.data: await show_unit_detail_original(update, context, res.data[0], u)
    elif data.startswith("appu_"):
        uid = data.split("_")[1]; update_user_status(uid, 'active'); await query.edit_message_text(f"✅ User {uid} AKTIF.")
    elif data.startswith("cp_"):
        n = data.replace("cp_", ""); await query.message.reply_text(f"📋 **COPY:**\n`{n}`", parse_mode='Markdown')
    elif data == "close_panel": await query.delete_message()


if __name__ == '__main__':
    print("🚀 BOT v6.26 STARTING...")
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    
    # HANDLER UPLOAD
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Document.ALL, upload_start)], 
        states={
            U_LEASING_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_leasing_user)], 
            U_LEASING_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_leasing_admin)], 
            U_CONFIRM_UPLOAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, upload_confirm_admin)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    
    # HANDLER REGIS
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('register', register_start)], states={R_ROLE_CHOICE:[MessageHandler(filters.TEXT, register_role_choice)], R_NAMA:[MessageHandler(filters.TEXT, register_nama)], R_HP:[MessageHandler(filters.TEXT, register_hp)], R_EMAIL:[MessageHandler(filters.TEXT, register_email)], R_KOTA:[MessageHandler(filters.TEXT, register_kota)], R_AGENCY:[MessageHandler(filters.TEXT, register_agency)], R_CONFIRM:[MessageHandler(filters.TEXT, register_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))

    # HANDLER MANUAL
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('tambah', add_manual_start)], states={ADD_NOPOL:[MessageHandler(filters.TEXT, add_nopol)], ADD_UNIT:[MessageHandler(filters.TEXT, add_unit)], ADD_LEASING:[MessageHandler(filters.TEXT, add_leasing)], ADD_NOTE:[MessageHandler(filters.TEXT, add_note)], ADD_CONFIRM:[MessageHandler(filters.TEXT, add_save)]}, fallbacks=[CommandHandler('cancel', cancel)]))

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('cekkuota', cek_kuota))
    app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('leasing', get_leasing_list))
    app.add_handler(CommandHandler('rekap', rekap_harian))
    app.add_handler(CommandHandler('users', list_users))
    app.add_handler(CommandHandler('setgroup', set_leasing_group))
    app.add_handler(CommandHandler('setagency', set_agency_group))
    app.add_handler(CommandHandler('topup', admin_topup))
    app.add_handler(CommandHandler('balas', admin_reply))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_topup))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.Regex(r'^/m_\d+$'), manage_user_panel))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    app.job_queue.run_daily(auto_cleanup_logs, time=time(3,0,0, tzinfo=TZ_JAKARTA))
    app.run_polling()