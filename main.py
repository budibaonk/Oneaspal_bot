"""
################################################################################
#                                                                              #
#                      PROJECT: ONEASPAL BOT (ASSET RECOVERY)                  #
#                      VERSION: 6.2 (DYNAMIC REKAP EDITION)                    #
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
    constants
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
print("🔍 SYSTEM DIAGNOSTIC STARTUP (v6.2)")
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
A_NOPOL, A_TYPE, A_LEASING, A_NOKIRIMAN, A_OVD, A_KET, A_CONFIRM = range(7, 14)
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
    if fname.lower().endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            valid = [f for f in z.namelist() if not f.startswith('__') and f.lower().endswith(('.csv','.xlsx','.xls','.txt'))]
            if not valid: raise ValueError("ZIP Kosong")
            with z.open(valid[0]) as f: content = f.read(); fname = valid[0]
     
    if fname.lower().endswith(('.xlsx', '.xls')):
        try: return pd.read_excel(io.BytesIO(content), dtype=str)
        except: 
            try: return pd.read_excel(io.BytesIO(content), dtype=str, engine='openpyxl')
            except: pass 
            
    configs = [
        {'sep': ';', 'enc': 'utf-8-sig', 'quote': csv.QUOTE_NONE},
        {'sep': ';', 'enc': 'latin1',    'quote': csv.QUOTE_NONE},
        {'sep': ',', 'enc': 'utf-8-sig', 'quote': csv.QUOTE_MINIMAL}, 
        {'sep': ',', 'enc': 'latin1',    'quote': csv.QUOTE_MINIMAL},
        {'sep': '\t', 'enc': 'utf-16',   'quote': csv.QUOTE_MINIMAL}, 
        {'sep': '\t', 'enc': 'utf-8',    'quote': csv.QUOTE_MINIMAL}
    ]
    
    for cfg in configs:
        try:
            df = pd.read_csv(io.BytesIO(content), sep=cfg['sep'], dtype=str, encoding=cfg['enc'], engine='python', on_bad_lines='skip', quoting=cfg['quote'])
            if len(df.columns) > 1: return df
        except: continue
            
    try: return pd.read_csv(io.BytesIO(content), sep=None, engine='python', dtype=str)
    except: return pd.DataFrame()


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
        "🔐 **ADMIN COMMANDS v6.2**\n\n"
        "📢 **INFO / PENGUMUMAN**\n"
        "• `/setinfo [Pesan]` (Pasang Banner)\n"
        "• `/delinfo` (Hapus Banner)\n\n"
        "👮‍♂️ **ROLE**\n"
        "• `/angkat_korlap [ID] [KOTA]`\n\n"
        "📊 **ANALYTICS (NEW)**\n"
        "• `/rekap` (Rekap Global Hari Ini)\n"
        "• `/rekap[Leasing]` (Rekap Khusus)\n"
        "  _Contoh: /rekapJtii, /rekapAdira_\n\n"
        "🏢 **LEASING GROUP**\n"
        "• `/setgroup [NAMA_LEASING]`\n"
        "_(Gunakan di dalam Grup Notif)_\n\n"
        "👥 **USERS**\n"
        "• `/users`\n"
        "• `/m_ID`\n"
        "• `/topup [ID] [HARI]`\n"
        "• `/balas [ID] [MSG]`\n\n"
        "⚙️ **SYSTEM**\n"
        "• `/stats`\n"
        "• `/leasing`"
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

# [NEW v6.2] REKAP SPESIFIK LEASING (COMMAND DINAMIS)
async def rekap_spesifik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    # Parse Command: /rekapBCA -> BCA
    raw_text = update.message.text.split()[0] # Ambil command saja
    target_leasing = raw_text.lower().replace("/rekap", "").strip().upper()
    
    if not target_leasing: return # Harusnya masuk ke handler /rekap biasa
    
    msg = await update.message.reply_text(f"⏳ **Mencari Data Temuan: {target_leasing}...**", parse_mode='Markdown')
    
    try:
        now = datetime.now(TZ_JAKARTA)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Query ILIKE agar fleksibel (Misal: /rekapAdira -> match 'ADIRA DINAMIKA', 'ADIRA FINANCE')
        res = supabase.table('finding_logs').select("*")\
            .gte('created_at', start_of_day.isoformat())\
            .ilike('leasing', f'%{target_leasing}%')\
            .execute()
        
        data = res.data
        total_hits = len(data)
        
        if total_hits == 0:
            return await msg.edit_text(f"📊 **REKAP HARIAN: {target_leasing}**\n\nNihil. Belum ada unit ditemukan hari ini.")
            
        # Header Laporan
        report = (
            f"📊 **LAPORAN HARIAN KHUSUS: {target_leasing}**\n"
            f"📅 Tanggal: {now.strftime('%d %b %Y')}\n"
            f"🔥 **Total Hit:** {total_hits} Unit\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
        
        # Detail Unit (Tampilkan max 15 agar tidak kepanjangan)
        limit_show = 15
        for i, d in enumerate(data[:limit_show]):
            nopol = d.get('nopol', '-')
            unit = d.get('unit', '-')
            matel = d.get('nama_matel', 'Matel')
            report += f"{i+1}. {nopol} | {unit} (Oleh: {matel})\n"
            
        if total_hits > limit_show:
            report += f"\n... dan {total_hits - limit_show} unit lainnya."
            
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
        
        if pic_list:
            msg += "🏦 <b>INTERNAL LEASING (PIC)</b>\n"
            for i, u in enumerate(pic_list, 1):
                nama = clean_text(u.get('nama_lengkap'))
                agency = clean_text(u.get('agency'))
                kota = clean_text(u.get('alamat'))
                uid = u['user_id']
                entry = (f"{i}. 🤝 <b>{nama}</b>\n   UNLIMITED | 🏢 {agency} | 📍 {kota}\n   ⚙️ /m_{uid}\n\n")
                if len(msg) + len(entry) > 4000: await update.message.reply_text(msg, parse_mode='HTML'); msg = ""
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
                kota = clean_text(u.get('alamat'))
                uid = u['user_id']
                entry = (f"{i}. {icon} <b>{nama}</b>\n   {days_left_str} | 🏢 {agency} | 📍 {kota}\n   ⚙️ /m_{uid}\n\n")
                if len(msg) + len(entry) > 4000: await update.message.reply_text(msg, parse_mode='HTML'); msg = ""
                msg += entry
            
        if msg: await update.message.reply_text(msg, parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def manage_user_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid = int(update.message.text.split('_')[1])
        u = get_user(tid)
        if not u: return await update.message.reply_text("❌ User tidak ditemukan.")
        role_now = u.get('role', 'matel'); status_now = u.get('status', 'active')
        info_role = "🎖️ KORLAP" if role_now == 'korlap' else f"🛡️ {role_now.upper()}"
        wilayah = f"({u.get('wilayah_korlap', '-')})" if role_now == 'korlap' else ""
        icon_status = "✅ AKTIF" if status_now == 'active' else "⛔ BANNED"
        expiry = u.get('expiry_date', 'EXPIRED')
        if expiry != 'EXPIRED': expiry = datetime.fromisoformat(expiry.replace('Z', '+00:00')).astimezone(TZ_JAKARTA).strftime('%d %b %Y')
        msg = (f"👮‍♂️ <b>USER MANAGER</b>\n━━━━━━━━━━━━━━━━━━\n👤 <b>Nama:</b> {clean_text(u.get('nama_lengkap'))}\n🏅 <b>Role:</b> {info_role} {wilayah}\n📊 <b>Status:</b> {icon_status}\n📱 <b>ID:</b> <code>{tid}</code>\n📅 <b>Exp:</b> {expiry}\n🏢 <b>Agency:</b> {clean_text(u.get('agency'))}\n━━━━━━━━━━━━━━━━━━")
        btn_role = InlineKeyboardButton("⬇️ BERHENTIKAN KORLAP", callback_data=f"adm_demote_{tid}") if role_now == 'korlap' else InlineKeyboardButton("🎖️ ANGKAT KORLAP", callback_data=f"adm_promote_{tid}")
        btn_ban = InlineKeyboardButton("⛔ BAN USER", callback_data=f"adm_ban_{tid}") if status_now == 'active' else InlineKeyboardButton("✅ UNBAN (PULIHKAN)", callback_data=f"adm_unban_{tid}")
        kb = [[InlineKeyboardButton("📅 +5 Hari", callback_data=f"adm_topup_{tid}_5"), InlineKeyboardButton("📅 +30 Hari", callback_data=f"adm_topup_{tid}_30")], [btn_role], [btn_ban, InlineKeyboardButton("🗑️ HAPUS DATA", callback_data=f"adm_del_{tid}")], [InlineKeyboardButton("❌ TUTUP PANEL", callback_data="close_panel")]]
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Error Panel: {e}")


# ==============================================================================
# BAGIAN 8: FITUR AUDIT & ADMIN UTILS
# ==============================================================================

# [NEW] FITUR AUTO CLEANUP LOGS
async def auto_cleanup_logs(context: ContextTypes.DEFAULT_TYPE):
    """
    Menghapus data finding_logs yang lebih tua dari 5 hari.
    Dijalankan otomatis oleh JobQueue.
    """
    try:
        # Hitung batas waktu (Sekarang - 5 Hari)
        cutoff_date = datetime.now(TZ_JAKARTA) - timedelta(days=5)
        cutoff_str = cutoff_date.isoformat()
        
        # Hapus data di Supabase (lt = less than / kurang dari tanggal cutoff)
        res = supabase.table('finding_logs').delete().lt('created_at', cutoff_str).execute()
        
        # Log ke terminal admin (opsional)
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
    msg = await update.message.reply_text("⏳ *Memulai Audit Leasing...*", parse_mode='Markdown')
    try:
        counts = Counter(); off = 0; BATCH = 1000
        while True:
            res = supabase.table('kendaraan').select("finance").range(off, off+BATCH-1).execute()
            data = res.data; 
            if not data: break
            counts.update([str(d.get('finance')).strip().upper() if d.get('finance') else "UNKNOWN" for d in data])
            if len(data) < BATCH: break
            off += BATCH
            if off % 50000 == 0:
                try: await msg.edit_text(f"⏳ *Sedang Menghitung...*\nSudah scan: `{off:,}` data", parse_mode='Markdown')
                except: pass
        rpt = "🏦 **AUDIT LEASING (FINAL)**\n━━━━━━━━━━━━━━━━━━\n"
        for k, v in counts.most_common():
            if k not in ["UNKNOWN", "NONE", "NAN", "-"]: rpt += f"🔹 **{k}:** `{v:,}`\n"
        if len(rpt) > 4000: rpt = rpt[:4000] + "\n...(dan lainnya)"
        await msg.edit_text(rpt, parse_mode='Markdown')
    except Exception as e: await msg.edit_text(f"❌ Error: {e}")

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


# ##############################################################################
# BAGIAN 9: USER FEATURES & NOTIFIKASI
# ##############################################################################

async def cek_kuota(update, context):
    u = get_user(update.effective_user.id)
    if not u or u['status']!='active': return
    
    # --- LOGIC BANNER INFO ---
    global GLOBAL_INFO
    info_banner = f"📢 <b>INFO PUSAT:</b> {clean_text(GLOBAL_INFO)}\n━━━━━━━━━━━━━━━━━━\n" if GLOBAL_INFO else ""
    # -------------------------

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

# [V6.0] NOTIF GROUP LEASING (DENGAN LOGGING ERROR AGAR KETAHUAN JIKA GAGAL)
async def notify_leasing_group(context, matel_user, unit_data):
    leasing_unit = str(unit_data.get('finance', '')).strip().upper()
    if len(leasing_unit) < 3: return

    try:
        res = supabase.table('leasing_groups').select("*").execute()
        groups = res.data
        
        target_group_ids = []
        for g in groups:
            g_name = str(g['leasing_name']).upper()
            # Logika Pencocokan: Jika Nama Grup ada di Nama Leasing Unit (atau sebaliknya)
            if g_name in leasing_unit or leasing_unit in g_name:
                target_group_ids.append(g['group_id'])
        
        if not target_group_ids: 
            # (Optional) Print jika tidak ada group yang cocok (untuk debugging)
            # print(f"⚠️ Leasing '{leasing_unit}' tidak punya Group terdaftar.")
            return

        hp_raw = matel_user.get('no_hp', '-')
        hp_wa = '62' + hp_raw[1:] if hp_raw.startswith('0') else hp_raw
        
        msg_group = (
            f"🚨 <b>UNIT DITEMUKAN! (HIT)</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
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

        kb = [[InlineKeyboardButton("📞 Hubungi Penemu (WA)", url=f"https://wa.me/{hp_wa}")]]

        for gid in target_group_ids:
            try: 
                await context.bot.send_message(gid, msg_group, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
                print(f"✅ Notif Terkirim ke Leasing Group: {gid}")
            except Exception as e: 
                print(f"❌ Gagal Kirim ke Leasing Group ({gid}): {e}")
                logger.error(f"Gagal Notif Group Leasing: {e}")
            
    except Exception as e: logger.error(f"Gagal Notif Group Leasing: {e}")

# [V6.0] NOTIF GROUP ADMIN PUSAT (DEBUGGED)
async def notify_hit_to_group(context, u, d):
    try:
        # CEK ID GROUP
        if LOG_GROUP_ID == 0: 
            print("⚠️ ALERT: Tidak bisa kirim notif Admin Pusat karena LOG_GROUP_ID = 0")
            return

        hp_raw = u.get('no_hp', '-'); hp_wa = '62' + hp_raw[1:] if hp_raw.startswith('0') else hp_raw
        
        msg = (f"🚨 <b>UNIT DITEMUKAN! (HIT)</b>\n━━━━━━━━━━━━━━━━━━\n👤 <b>Penemu:</b> {clean_text(u.get('nama_lengkap'))} ({clean_text(u.get('agency'))})\n📍 <b>Kota:</b> {clean_text(u.get('alamat'))}\n\n🚙 <b>Unit:</b> {clean_text(d.get('type'))}\n🔢 <b>Nopol:</b> {clean_text(d.get('nopol'))}\n📅 <b>Tahun:</b> {clean_text(d.get('tahun'))}\n🎨 <b>Warna:</b> {clean_text(d.get('warna'))}\n----------------------------------\n🔧 <b>Noka:</b> {clean_text(d.get('noka'))}\n⚙️ <b>Nosin:</b> {clean_text(d.get('nosin'))}\n----------------------------------\n⚠️ <b>OVD:</b> {clean_text(d.get('ovd'))}\n🏦 <b>Finance:</b> {clean_text(d.get('finance'))}\n🏢 <b>Branch:</b> {clean_text(d.get('branch'))}\n━━━━━━━━━━━━━━━━━━")
        
        kb = [[InlineKeyboardButton("📞 Hubungi Penemu (WA)", url=f"https://wa.me/{hp_wa}")]]
        
        # COBA KIRIM
        await context.bot.send_message(LOG_GROUP_ID, msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        print(f"✅ Notif Terkirim ke Admin Pusat ({LOG_GROUP_ID})")
        
    except Exception as e: 
        print(f"❌ Gagal Kirim Notif Admin Pusat: {e}")
        logger.error(f"Fail notif group: {e}")

# [V5.5] NEW COMMAND TO REGISTER LEASING GROUP
async def set_leasing_group(update, context):
    if update.effective_user.id != ADMIN_ID: return
    if update.effective_chat.type not in ['group', 'supergroup']:
        return await update.message.reply_text("⚠️ Perintah ini hanya bisa digunakan di dalam GRUP Leasing.")
    
    if not context.args:
        return await update.message.reply_text("⚠️ Format: `/setgroup [NAMA_LEASING]`\nContoh: `/setgroup BCA`")
    
    leasing_name = " ".join(context.args).upper()
    chat_id = update.effective_chat.id
    
    try:
        # Hapus mapping lama jika ada, lalu insert baru
        supabase.table('leasing_groups').delete().eq('group_id', chat_id).execute()
        supabase.table('leasing_groups').insert({"group_id": chat_id, "leasing_name": leasing_name}).execute()
        await update.message.reply_text(f"✅ <b>GRUP TERDAFTAR!</b>\n\nGrup ini sekarang adalah <b>OFFICIAL ALERT GROUP</b> untuk: <b>{leasing_name}</b>.\nSetiap unit '{leasing_name}' ditemukan, notifikasi akan masuk ke sini.", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal set grup: {e}")


# ==============================================================================
# BAGIAN 10: UPLOAD SYSTEM
# ==============================================================================

async def upload_start(update, context):
    if not get_user(update.effective_user.id): return
    context.user_data['fid'] = update.message.document.file_id
    if update.effective_user.id == ADMIN_ID:
        msg = await update.message.reply_text("⏳ **Menganalisa File...**", parse_mode='Markdown')
        try:
            f = await update.message.document.get_file(); c = await f.download_as_bytearray()
            df = read_file_robust(c, update.message.document.file_name)
            df = fix_header_position(df)
            df, found = smart_rename_columns(df)
            context.user_data['df'] = df.to_dict(orient='records')
            await msg.delete()
            fin_status = "✅ ADA" if 'finance' in df.columns else "⚠️ TIDAK ADA"
            scan_report = (f"✅ <b>SCAN SUKSES (v6.0)</b>\n━━━━━━━━━━━━━━━━━━\n📊 <b>Kolom Dikenali:</b> {', '.join(found)}\n📁 <b>Total Baris:</b> {len(df)}\n🏦 <b>Kolom Leasing:</b> {fin_status}\n━━━━━━━━━━━━━━━━━━\n\n👉 <b>MASUKKAN NAMA LEASING UNTUK DATA INI:</b>\n<i>(Ketik 'SKIP' jika ingin menggunakan kolom leasing dari file)</i>")
            await update.message.reply_text(scan_report, reply_markup=ReplyKeyboardMarkup([["SKIP"], ["❌ BATAL"]], resize_keyboard=True), parse_mode='HTML')
            return U_LEASING_ADMIN
        except Exception as e: 
            await msg.edit_text(f"❌ Error File: {e}"); return ConversationHandler.END
    else:
        await update.message.reply_text("📄 File diterima. Ketik Nama Leasing:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return U_LEASING_USER

async def upload_leasing_user(update, context): 
    nm = update.message.text; 
    if nm=="❌ BATAL": return await cancel(update, context)
    u = get_user(update.effective_user.id)
    await context.bot.send_document(ADMIN_ID, context.user_data['fid'], caption=f"📥 **UPLOAD USER ({u.get('role').upper()})**\n👤 {u['nama_lengkap']}\n🏦 {nm}")
    if u.get('role') == 'pic': resp = "✅ **SINKRONISASI BERHASIL**\nData Anda telah diamankan di Database Pribadi."
    else: resp = "✅ **TERKIRIM**\nTerima kasih kontribusinya! Admin akan memverifikasi data ini."
    await update.message.reply_text(resp, parse_mode='Markdown'); return ConversationHandler.END

async def upload_leasing_admin(update, context):
    try:
        nm = update.message.text
        if nm == "❌ BATAL": return await cancel(update, context)
        
        nm = nm.upper().strip()
        
        if 'df' not in context.user_data:
            await update.message.reply_text("❌ Sesi kedaluwarsa. Silakan upload ulang file.")
            return ConversationHandler.END
            
        df = pd.DataFrame(context.user_data['df'])
        df = df.astype(str) # Paksa semua jadi string untuk mencegah error tipe data
        
        # Logika Penentuan Nama Leasing
        if nm != 'SKIP': 
            # Jika Manual: Timpa semua kolom finance dengan nama baru
            df['finance'] = standardize_leasing_name(nm)
            fin_disp = nm
        else: 
            # [FIX] Logika SKIP yang lebih aman
            if 'finance' in df.columns: 
                df['finance'] = df['finance'].apply(standardize_leasing_name)
                fin_disp = "AUTO (DARI FILE)"
            else: 
                df['finance'] = 'UNKNOWN'
                fin_disp = "AUTO CLEAN (KOSONG)"

        # Filtering Nopol
        if 'nopol' in df.columns:
            df['nopol'] = df['nopol'].str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
            df = df[df['nopol'].str.len() > 2]
            df = df.drop_duplicates(subset=['nopol'], keep='last')
            df = df.replace({'nan': '-', 'None': '-', 'NaN': '-'})
            
            final_df = pd.DataFrame()
            for col in VALID_DB_COLUMNS:
                if col in df.columns: final_df[col] = df[col]
                else: final_df[col] = "-"

            context.user_data['final_df'] = final_df.to_dict(orient='records')
            
            if not final_df.empty:
                s = final_df.iloc[0]
                prev_info = (
                    f"🔹 Leasing: {s.get('finance','-')}\n"
                    f"🔹 Nopol: <code style='color:orange'>{s.get('nopol','-')}</code>\n"
                    f"🔹 Unit: {s.get('type','-')}\n"
                    f"🔹 Noka: {s.get('noka','-')}\n"
                    f"🔹 OVD: {s.get('ovd','-')}"
                )
            else: 
                prev_info = "⚠️ Data Kosong setelah filtering (Cek kolom Nopol)"

            prev = (
                f"🔎 <b>PREVIEW DATA</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🏦 <b>Mode:</b> {fin_disp}\n"
                f"📊 <b>Total Siap Upload:</b> {len(final_df)} Data\n\n"
                f"📝 <b>SAMPEL DATA BARIS 1:</b>\n{prev_info}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ <b>Silakan konfirmasi untuk menyimpan data.</b>"
            )
            kb = [["🚀 UPDATE DATA"], ["🗑️ HAPUS MASSAL"], ["❌ BATAL"]]
            await update.message.reply_text(prev, reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True), parse_mode='HTML')
            return U_CONFIRM_UPLOAD
        else:
            await update.message.reply_text("❌ <b>ERROR:</b> Kolom NOPOL tidak ditemukan.\nPastikan file memiliki header: <i>No Polisi, Plat, Nopolisi</i>, dll.", parse_mode='HTML')
            return ConversationHandler.END

    except Exception as e:
        logger.error(f"Upload Error: {e}")
        await update.message.reply_text(f"❌ <b>TERJADI KESALAHAN SYSTEM:</b>\n{e}\n\n<i>Silakan coba upload ulang atau hubungi admin.</i>", parse_mode='HTML')
        return ConversationHandler.END

async def upload_confirm_admin(update, context):
    act = update.message.text
    if act == "❌ BATAL": return await cancel(update, context)
    msg = await update.message.reply_text("⏳ <b>MEMULAI UPDATE DATABASE...</b>\nMohon tunggu, jangan matikan bot...", parse_mode='HTML', reply_markup=ReplyKeyboardRemove())
    data = context.user_data.get('final_df'); total_data = len(data); suc = 0; start_t = time.time()
    last_error = ""
    
    try:
        BATCH = 50 
        list_nopol = [x['nopol'] for x in data] if act == "🗑️ HAPUS MASSAL" else []
        for i in range(0, total_data, BATCH):
            chunk = data[i:i+BATCH]
            try:
                if act == "🚀 UPDATE DATA": supabase.table('kendaraan').upsert(chunk, on_conflict='nopol').execute()
                elif act == "🗑️ HAPUS MASSAL": supabase.table('kendaraan').delete().in_('nopol', list_nopol[i:i+BATCH]).execute()
                suc += len(chunk)
            except Exception as e:
                if '57014' in str(e) or 'timeout' in str(e).lower():
                    mini_batch_size = 5
                    for j in range(0, len(chunk), mini_batch_size):
                        mini_chunk = chunk[j:j+mini_batch_size]
                        try:
                            if act == "🚀 UPDATE DATA": supabase.table('kendaraan').upsert(mini_chunk, on_conflict='nopol').execute()
                            elif act == "🗑️ HAPUS MASSAL": 
                                mini_nopol = [x['nopol'] for x in mini_chunk]
                                supabase.table('kendaraan').delete().in_('nopol', mini_nopol).execute()
                            suc += len(mini_chunk)
                            await asyncio.sleep(0.5) 
                        except Exception as e2: last_error = str(e2); continue
                else: last_error = str(e); continue
            
            if i > 0 and i % 500 == 0:
                try: await msg.edit_text(f"⏳ <b>MEMPROSES DATA...</b>\n🚀 {i:,} / {total_data:,} data...", parse_mode='HTML')
                except: pass 
            await asyncio.sleep(0.1)
            
        dur = round(time.time() - start_t, 2)
        try: await msg.delete()
        except: pass
        
        status_msg = "✅ SUKSES" if suc > 0 else "❌ GAGAL TOTAL"
        error_info = f"\n⚠️ <b>Last Error:</b> {last_error[:100]}..." if last_error else ""
        report = (f"{status_msg}\n━━━━━━━━━━━━━━━━━━\n📊 <b>Berhasil Masuk:</b> {suc:,}\n❌ <b>Gagal:</b> {total_data - suc}\n⏱ <b>Waktu:</b> {dur} detik{error_info}")
        await update.message.reply_text(report, parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ <b>SYSTEM ERROR:</b>\n{e}", parse_mode='HTML')
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
    context.user_data['r_hp'] = update.message.text; await update.message.reply_text("3️⃣ Email:"); return R_EMAIL
async def register_email(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['r_email'] = update.message.text; await update.message.reply_text("4️⃣ Kota Domisili:"); return R_KOTA
async def register_kota(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['r_kota'] = update.message.text
    
    # --- LOGIC PENENTUAN PERTANYAAN SELANJUTNYA ---
    if context.user_data['reg_role'] == 'pic':
        txt = "5️⃣ **Nama Leasing / Finance:**\n_(Contoh: BCA Finance, Adira, ACC)_"
    else:
        # [UPDATE] PERTEGAS INSTRUKSI NAMA PT
        txt = "5️⃣ **Nama Agency / PT:**\n_(Wajib isi NAMA LENGKAP PT, BUKAN SINGKATAN!)\nContoh: PT ELANG PERKASA (✅) | EP (❌)_"
        
    await update.message.reply_text(txt, parse_mode='Markdown'); return R_AGENCY
async def register_agency(update, context): 
    msg = update.message.text
    if msg == "❌ BATAL": return await cancel(update, context)
    if len(msg) < 3 or msg.strip() == "-": await update.message.reply_text("⚠️ **Nama PT/Agency Wajib Diisi!**\nMinimal 3 huruf. Silakan ketik ulang:"); return R_AGENCY
    context.user_data['r_agency'] = msg.upper()
    summary = (f"📝 <b>KONFIRMASI DATA</b>\n━━━━━━━━━━━━━━━━━━\n👤 <b>Nama:</b> {clean_text(context.user_data.get('r_nama'))}\n📱 <b>HP:</b> {clean_text(context.user_data.get('r_hp'))}\n📧 <b>Email:</b> {clean_text(context.user_data.get('r_email'))}\n📍 <b>Kota:</b> {clean_text(context.user_data.get('r_kota'))}\n🏢 <b>Agency:</b> {clean_text(context.user_data.get('r_agency'))}\n━━━━━━━━━━━━━━━━━━")
    await update.message.reply_text(f"{summary}\n\n✅ <b>Data sudah benar?</b>", reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ ULANGI"]], resize_keyboard=True), parse_mode='HTML')
    return R_CONFIRM

async def register_confirm(update, context):
    if update.message.text != "✅ KIRIM": return await cancel(update, context)
    role_db = context.user_data.get('reg_role', 'matel'); quota_init = 5000 if role_db == 'pic' else 1000
    d = {"user_id": update.effective_user.id, "nama_lengkap": context.user_data['r_nama'], "no_hp": context.user_data['r_hp'], "email": context.user_data['r_email'], "alamat": context.user_data['r_kota'], "agency": context.user_data['r_agency'], "quota": quota_init, "status": "pending", "role": role_db, "ref_korlap": None}
    try:
        supabase.table('users').insert(d).execute()
        if role_db == 'pic': await update.message.reply_text("✅ **PENDAFTARAN TERKIRIM**\nAkses Enterprise Workspace sedang diverifikasi Admin.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
        else: await update.message.reply_text("✅ **PENDAFTARAN TERKIRIM**\nData Mitra sedang diverifikasi Admin Pusat.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
        msg_admin = (f"🔔 <b>REGISTRASI BARU ({role_db.upper()})</b>\n━━━━━━━━━━━━━━━━━━\n👤 <b>Nama:</b> {clean_text(d['nama_lengkap'])}\n🆔 <b>User ID:</b> <code>{d['user_id']}</code>\n🏢 <b>Agency:</b> {clean_text(d['agency'])}\n📍 <b>Domisili:</b> {clean_text(d['alamat'])}\n📱 <b>HP/WA:</b> {clean_text(d['no_hp'])}\n📧 <b>Email:</b> {clean_text(d['email'])}\n━━━━━━━━━━━━━━━━━━\n<i>Silakan validasi data mitra ini.</i>")
        kb = [[InlineKeyboardButton("✅ TERIMA (AKTIFKAN)", callback_data=f"appu_{d['user_id']}")], [InlineKeyboardButton("❌ TOLAK (HAPUS)", callback_data=f"reju_{d['user_id']}")]]
        await context.bot.send_message(ADMIN_ID, msg_admin, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    except Exception as e: logger.error(f"Reg Error: {e}"); await update.message.reply_text("❌ Gagal Terkirim. User ID Anda mungkin sudah terdaftar sebelumnya.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ==============================================================================
# BAGIAN 12: START & CORE SEARCH ENGINE
# ==============================================================================

async def start(update, context):
    u = get_user(update.effective_user.id)
    global GLOBAL_INFO; info = f"📢 <b>INFO:</b> {clean_text(GLOBAL_INFO)}\n━━━━━━━━━━━━━━━━━━\n\n" if GLOBAL_INFO else ""
    if u and u.get('role') == 'pic':
        msg = (f"{info}🤖 <b>SYSTEM ONEASPAL (ENTERPRISE)</b>\n\nSelamat Datang, <b>{clean_text(u.get('nama_lengkap'))}</b>\n<i>Status: Verified Internal Staff</i>\n\n<b>Workspace Anda Siap.</b>\nSinkronisasi data unit Anda ke dalam <i>Private Cloud</i> kami.\n\n🔒 <b>Keamanan Data Terjamin.</b>")
        kb = [["🔄 SINKRONISASI DATA", "📂 DATABASE SAYA"], ["📞 BANTUAN TEKNIS"]]; await update.message.reply_text(msg, parse_mode='HTML', reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)); return
    if u:
        msg = (f"{info}🤖 <b>Selamat Datang di Oneaspalbot</b>\n\n<b>Salam Satu Aspal!</b> 👋\nHalo, Rekan Mitra Lapangan.\n\n<b>Oneaspalbot</b> adalah asisten digital profesional.\n\nCari data melalui:\n✅ Nomor Polisi (Nopol)\n✅ Nomor Rangka (Noka)\n✅ Nomor Mesin (Nosin)")
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=ReplyKeyboardRemove()); return
    msg_guest = (f"🤖 <b>ONEASPAL: Digital Asset Recovery System</b>\n<i>Sistem Manajemen Database Aset Fidusia Terpadu</i>\n\nSelamat Datang di Ekosistem OneAspal.\nPlatform ini dirancang khusus untuk menunjang efektivitas profesi:\n\n1️⃣ <b>INTERNAL LEASING & COLLECTION</b>\nTransformasi digital pengelolaan data aset.\n\n2️⃣ <b>PROFESI JASA PENAGIHAN (MATEL)</b>\nDukungan data <i>real-time</i> dengan akurasi tinggi.\n\n🔐 <b>Akses Terbatas (Private System)</b>\nSilakan lakukan registrasi:\n👉 /register\n\n<i>Salam Satu Aspal.</i>")
    await update.message.reply_text(msg_guest, parse_mode='HTML')

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
    increment_daily_usage(u['user_id'], u.get('daily_usage', 0))
    
    # 1. ANALYTICS (HANYA MATEL)
    user_role = u.get('role', 'matel')
    if user_role != 'pic':
        log_successful_hit(u['user_id'], u.get('nama_lengkap'), d)

    # 2. TAMPILKAN KE USER (SEMUA ROLE)
    info_txt = f"📢 <b>INFO:</b> {clean_text(GLOBAL_INFO)}\n━━━━━━━━━━━━━━━━━━\n" if GLOBAL_INFO else ""
    txt = (
        f"{info_txt}✅ <b>DATA DITEMUKAN</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"🚙 <b>Unit:</b> {clean_text(d.get('type'))}\n"
        f"🔢 <b>Nopol:</b> <code>{clean_text(d.get('nopol'))}</code>\n"
        f"📅 <b>Tahun:</b> {clean_text(d.get('tahun'))}\n"
        f"🎨 <b>Warna:</b> {clean_text(d.get('warna'))}\n"
        f"----------------------------------\n"
        f"🔧 <b>Noka:</b> <code>{clean_text(d.get('noka'))}</code>\n"
        f"⚙️ <b>Nosin:</b> <code>{clean_text(d.get('nosin'))}</code>\n"
        f"----------------------------------\n"
        f"⚠️ <b>OVD:</b> {clean_text(d.get('ovd'))}\n"
        f"🏦 <b>Finance:</b> {clean_text(d.get('finance'))}\n"
        f"🏢 <b>Branch:</b> {clean_text(d.get('branch'))}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <b>CATATAN PENTING:</b>\n"
        f"<i>Ini bukan alat yang SAH untuk penarikan. Konfirmasi ke PIC leasing.</i>"
    )
    await context.bot.send_message(chat_id=update.effective_chat.id, text=txt, parse_mode='HTML')
    
    # 3. NOTIFIKASI GROUP (SEMUA ROLE HARUS MUNCUL UNTUK TESTING)
    await notify_hit_to_group(context, u, d)  
    await notify_leasing_group(context, u, d) 

async def show_multi_choice(update, context, data_list, keyword):
    # --- LOGIC BANNER INFO ---
    global GLOBAL_INFO
    info_txt = f"📢 INFO: {GLOBAL_INFO}\n\n" if GLOBAL_INFO else ""
    # -------------------------
    
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

async def cancel(update, context): await update.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

# --- MASTER CALLBACK HANDLER ---
async def callback_handler(update, context):
    query = update.callback_query; await query.answer(); data = query.data 
    
    if data.startswith("topup_") or data.startswith("adm_topup_"):
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

    elif data.startswith("view_"):
        nopol_target = data.replace("view_", ""); u = get_user(update.effective_user.id)
        res = supabase.table('kendaraan').select("*").eq('nopol', nopol_target).execute()
        if res.data: await show_unit_detail_original(update, context, res.data[0], u)
        else: await query.edit_message_text("❌ Data unit sudah tidak tersedia.")
    elif data.startswith("adm_promote_"):
        uid = int(data.split("_")[2]); supabase.table('users').update({'role': 'korlap'}).eq('user_id', uid).execute()
        await query.edit_message_text(f"✅ User {uid} DIPROMOSIKAN jadi KORLAP.")
        try: await context.bot.send_message(uid, "🎉 **SELAMAT!** Anda telah diangkat menjadi **KORLAP**.")
        except: pass
    elif data.startswith("adm_demote_"): uid = int(data.split("_")[2]); supabase.table('users').update({'role': 'matel'}).eq('user_id', uid).execute(); await query.edit_message_text(f"⬇️ User {uid} DITURUNKAN jadi MATEL.")
    elif data == "close_panel": await query.delete_message()
    
    elif data.startswith("appu_"): 
        target_uid = int(data.split("_")[1])
        update_user_status(target_uid, 'active')
        target_user = get_user(target_uid)
        await query.edit_message_text(f"✅ User {target_uid} telah Diaktifkan.")
        if target_user and target_user.get('role') == 'pic':
            nama_pic = clean_text(target_user.get('nama_lengkap', 'Partner'))
            msg_pic = (f"Selamat Pagi, Pak {nama_pic}.\n\nIzin memperkenalkan fitur <b>Private Enterprise</b> di OneAspal Bot.\n\nKami menyediakan <b>Private Cloud</b> agar Bapak bisa menyimpan data kendaraan dengan aman menggunakan <b>Blind Check System</b>.\n\n🔐 <b>Keamanan Data:</b>\nDi sistem ini, Bapak <b>TIDAK</b> dikategorikan menyebarkan data kepada orang lain (Aman secara SOP). Bapak hanya mengarsipkan data digital untuk menunjang <b>Performance Pekerjaan</b> Bapak sendiri.\n\nData Bapak <b>TIDAK BISA</b> dilihat atau didownload user lain. Sistem hanya akan memberi notifikasi kepada Bapak jika unit tersebut ditemukan di lapangan.\n\nSilakan dicoba fitur <b>Upload Data</b>-nya, Pak (Menu Sinkronisasi).\n\n<i>Jika ada pertanyaan, silakan balas pesan ini melalui tombol <b>📞 BANTUAN TEKNIS</b> di menu utama.</i>")
            try: await context.bot.send_message(target_uid, msg_pic, parse_mode='HTML')
            except: pass
        else:
            try: await context.bot.send_message(target_uid, "🎉 **AKUN AKTIF!**\nSelamat Datang di OneAspal. Silakan gunakan bot dengan bijak.", parse_mode='Markdown')
            except: pass
            
    elif data.startswith("reju_"): update_user_status(data.split("_")[1], 'rejected'); await query.edit_message_text("❌ User TOLAK."); await context.bot.send_message(data.split("_")[1], "⛔ Pendaftaran Ditolak.")
    elif data.startswith("v_acc_"): 
        n=data.split("_")[2]
        item=context.bot_data.get(f"prop_{n}")
        if item:
            supabase.table('kendaraan').upsert(item).execute()
            await query.edit_message_text("✅ Masuk DB.")
            await context.bot.send_message(data.split("_")[3], f"✅ Data `{n}` DISETUJUI & Sudah Tayang.")
        else:
            await query.edit_message_text("⚠️ Data kedaluwarsa (Restart bot).")
    
    elif data.startswith("del_acc_"): supabase.table('kendaraan').delete().eq('nopol', data.split("_")[2]).execute(); await query.edit_message_text("✅ Dihapus."); await context.bot.send_message(data.split("_")[3], "✅ Hapus ACC.")
    elif data.startswith("del_rej_"): await query.edit_message_text("❌ Ditolak."); await context.bot.send_message(data.split("_")[2], "❌ Hapus TOLAK.")


if __name__ == '__main__':
    print("🚀 ONEASPAL BOT v6.2 (DYNAMIC REKAP EDITION) STARTING...")
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    
    app.add_handler(MessageHandler(filters.Regex(r'^/m_\d+$'), manage_user_panel))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(admin_action_start, pattern='^adm_(ban|unban|del)_')], states={ADMIN_ACT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_action_complete)]}, fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(reject_start, pattern='^reju_')], states={REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, reject_complete)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(val_reject_start, pattern='^v_rej_')], 
        states={VAL_REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, val_reject_complete)]}, 
        fallbacks=[CommandHandler('cancel', cancel)]
    ))

    app.add_handler(ConversationHandler(entry_points=[MessageHandler(filters.Document.ALL, upload_start)], states={U_LEASING_USER: [MessageHandler(filters.TEXT, upload_leasing_user)], U_LEASING_ADMIN: [MessageHandler(filters.TEXT, upload_leasing_admin)], U_CONFIRM_UPLOAD: [MessageHandler(filters.TEXT, upload_confirm_admin)]}, fallbacks=[CommandHandler('cancel', cancel)], allow_reentry=True))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('register', register_start)], states={R_ROLE_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_role_choice)], R_NAMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_nama)], R_HP: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_hp)], R_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)], R_KOTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_kota)], R_AGENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_agency)], R_CONFIRM:[MessageHandler(filters.TEXT & ~filters.COMMAND, register_confirm)]}, fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('tambah', add_data_start)], states={A_NOPOL: [MessageHandler(filters.TEXT, add_nopol)], A_TYPE: [MessageHandler(filters.TEXT, add_type)], A_LEASING: [MessageHandler(filters.TEXT, add_leasing)], A_NOKIRIMAN: [MessageHandler(filters.TEXT, add_nokiriman)], A_OVD: [MessageHandler(filters.TEXT, add_ovd)], A_KET: [MessageHandler(filters.TEXT, add_ket)], A_CONFIRM: [MessageHandler(filters.TEXT, add_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('lapor', lapor_delete_start)], states={L_NOPOL: [MessageHandler(filters.TEXT, lapor_delete_check)], L_REASON: [MessageHandler(filters.TEXT, lapor_reason)], L_CONFIRM: [MessageHandler(filters.TEXT, lapor_delete_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('hapus', delete_unit_start)], states={D_NOPOL: [MessageHandler(filters.TEXT, delete_unit_check)], D_CONFIRM: [MessageHandler(filters.TEXT, delete_unit_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))

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
    
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('admin', contact_admin), MessageHandler(filters.Regex('^📞 BANTUAN TEKNIS$'), contact_admin)], states={SUPPORT_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_send)]}, fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)])) 
    
    app.add_handler(CommandHandler('panduan', panduan))
    app.add_handler(CommandHandler('setinfo', set_info)) 
    app.add_handler(CommandHandler('delinfo', del_info))      
    app.add_handler(CommandHandler('addagency', add_agency)) 
    app.add_handler(CommandHandler('adminhelp', admin_help)) 
    
    # -------------------------------------------------------------
    # NEW HANDLER FOR DYNAMIC COMMANDS /rekapLeasing
    # -------------------------------------------------------------
    app.add_handler(MessageHandler(filters.Regex(r'^/rekap[a-zA-Z0-9]+$') & filters.COMMAND, rekap_spesifik))
        
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_topup))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    # ------------------------------------------------------------------
    # [NEW] JOB QUEUE (JADWAL OTOMATIS)
    # ------------------------------------------------------------------
    job_queue = app.job_queue
    
    # Jalankan auto_cleanup_logs setiap hari jam 03:00 WIB
    job_queue.run_daily(
        auto_cleanup_logs, 
        time=time(hour=3, minute=0, second=0, tzinfo=TZ_JAKARTA), 
        days=(0, 1, 2, 3, 4, 5, 6) # Setiap hari (Senin-Minggu)
    )
    print("⏰ Jadwal Cleanup Otomatis: AKTIF (Jam 03:00 WIB)")
    # ------------------------------------------------------------------

    print("✅ BOT ONLINE! (v6.2 - DYNAMIC REKAP)")
    app.run_polling()