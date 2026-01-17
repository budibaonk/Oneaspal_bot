"""
################################################################################
#                                                                              #
#                      PROJECT: ONEASPAL BOT (THE TURBO FINDER)                #
#                      VERSION: 4.39 (GOLDEN STABLE - ANTI STUCK)              #
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
from datetime import datetime
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
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GLOBAL_INFO = ""

try:
    ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
    LOG_GROUP_ID = int(os.environ.get("LOG_GROUP_ID", 0))
except:
    ADMIN_ID = 0; LOG_GROUP_ID = 0

if not URL or not KEY or not TOKEN: print("❌ CREDENTIAL ERROR"); exit()
try: supabase = create_client(URL, KEY); print("✅ DB CONNECTED")
except Exception as e: print(f"❌ DB ERROR: {e}"); exit()

# ##############################################################################
# BAGIAN 2: KAMUS DATA
# ##############################################################################

COLUMN_ALIASES = {
    'nopol': ['nopolisi', 'nomorpolisi', 'nopol', 'noplat', 'nomorplat', 'nomorkendaraan', 'tnkb', 'licenseplate', 'plat'],
    'type': ['type', 'tipe', 'unit', 'model', 'vehicle', 'jenis', 'deskripsiunit', 'merk', 'object', 'kendaraan', 'item', 'brand', 'namaunit', 'kend'],
    'tahun': ['tahun', 'year', 'thn', 'rakitan', 'th', 'yearofmanufacture'],
    'warna': ['warna', 'color', 'colour', 'cat', 'kelir'],
    'noka': ['noka', 'norangka', 'nomorrangka', 'chassis', 'chasis', 'vin', 'rangka', 'no_rangka'],
    'nosin': ['nosin', 'nomesin', 'nomormesin', 'engine', 'mesin', 'engineno', 'noengine'],
    'finance': ['finance', 'leasing', 'lising', 'multifinance', 'cabang', 'partner', 'mitra', 'principal'],
    'ovd': ['ovd', 'overdue', 'dpd', 'keterlambatan', 'odh', 'hari', 'telat', 'aging', 'od'],
    'branch': ['branch', 'area', 'kota', 'pos', 'cabang', 'lokasi', 'wilayah', 'region']
}

# ##############################################################################
# BAGIAN 3: DEFINISI STATE
# ##############################################################################

R_ROLE_CHOICE, R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_CONFIRM = range(7)
A_NOPOL, A_TYPE, A_LEASING, A_NOKIR, A_CONFIRM = range(7, 12)
L_NOPOL, L_CONFIRM = range(12, 14) 
D_NOPOL, D_CONFIRM = range(14, 16)
U_LEASING_USER, U_LEASING_ADMIN, U_CONFIRM_UPLOAD = range(16, 19)
REJECT_REASON = 19
ADMIN_ACT_REASON = 20

# ##############################################################################
# BAGIAN 4: HELPER FUNCTIONS
# ##############################################################################

async def post_init(application: Application):
    await application.bot.set_my_commands([
        ("start", "🔄 Restart / Menu"),
        ("cekkuota", "💳 Cek Sisa Kuota"),
        ("tambah", "➕ Input Manual"),
        ("lapor", "🗑️ Lapor Unit Selesai"),
        ("register", "📝 Daftar Mitra"),
        ("admin", "📩 Hubungi Admin"),
        ("panduan", "📖 Buku Panduan"),
    ])

def get_user(user_id):
    try:
        response = supabase.table('users').select("*").eq('user_id', user_id).execute()
        return response.data[0] if response.data else None
    except: return None

def update_user_status(user_id, status):
    try: supabase.table('users').update({'status': status}).eq('user_id', user_id).execute(); return True
    except: return False

def update_quota_usage(user_id, current_quota):
    try: supabase.table('users').update({'quota': max(0, current_quota - 1)}).eq('user_id', user_id).execute()
    except: pass

def topup_quota(user_id, amount):
    try:
        user = get_user(user_id)
        if user:
            new = user.get('quota', 0) + amount
            supabase.table('users').update({'quota': new}).eq('user_id', user_id).execute()
            return True, new
        return False, 0
    except: return False, 0

def clean_text(text): return html.escape(str(text)) if text else "-"

def standardize_leasing_name(name):
    if not name: return "UNKNOWN"
    clean = re.sub(r'^\d+\s+', '', str(name).upper().strip())
    clean = re.sub(r'\(.*?\)', '', clean).strip()
    mapping = {"OTTO": "OTO", "OTTO.COM": "OTO", "BRI FINANCE": "BRI", "WOORI": "WOORI FINANCE", "MITSUI": "MITSUI LEASING"}
    return mapping.get(clean, clean)

def normalize_text(text): return re.sub(r'[^a-zA-Z0-9]', '', str(text)).lower()

def fix_header_position(df):
    target = COLUMN_ALIASES['nopol']
    for i in range(min(20, len(df))):
        vals = [normalize_text(str(x)) for x in df.iloc[i].values]
        if any(alias in vals for alias in target):
            df.columns = df.iloc[i]; df = df.iloc[i+1:].reset_index(drop=True); return df
    return df

def smart_rename_columns(df):
    new = {}; found = []
    for col in df.columns:
        clean = normalize_text(col); renamed = False
        for std, aliases in COLUMN_ALIASES.items():
            if clean == std or clean in aliases: new[col] = std; found.append(std); renamed = True; break
        if not renamed: new[col] = col
    df.rename(columns=new, inplace=True); return df, found

def read_file_robust(content, fname):
    if fname.lower().endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            with z.open(z.namelist()[0]) as f: content = f.read(); fname = z.namelist()[0]
    if fname.lower().endswith(('.xlsx', '.xls')):
        try: return pd.read_excel(io.BytesIO(content), dtype=str)
        except: return pd.read_excel(io.BytesIO(content), dtype=str, engine='openpyxl')
    return pd.read_csv(io.BytesIO(content), sep=None, engine='python', dtype=str)

# ##############################################################################
# BAGIAN 5: ADMIN & USER MANAGER (SMART PANEL & LOADING LEASING)
# ##############################################################################

async def manage_user_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid = int(update.message.text.split('_')[1]); u = get_user(tid)
        if not u: return await update.message.reply_text("❌ User tidak ditemukan.")
        role = u.get('role', 'matel'); status = u.get('status', 'active')
        info_role = "🎖️ KORLAP" if role == 'korlap' else f"🛡️ {role.upper()}"
        msg = (f"👮‍♂️ <b>USER MANAGER</b>\n━━━━━━━━━━━━━━━━━━\n👤 <b>Nama:</b> {clean_text(u.get('nama_lengkap'))}\n🏅 <b>Role:</b> {info_role}\n📊 <b>Status:</b> {status.upper()}\n📱 <b>ID:</b> <code>{tid}</code>\n🔋 <b>Kuota:</b> {u.get('quota', 0)}\n🏢 <b>Agency:</b> {clean_text(u.get('agency'))}\n━━━━━━━━━━━━━━━━━━")
        
        # SMART BUTTONS
        btn_role = InlineKeyboardButton("⬇️ TURUN JABATAN", callback_data=f"adm_demote_{tid}") if role == 'korlap' else InlineKeyboardButton("🎖️ ANGKAT KORLAP", callback_data=f"adm_promote_{tid}")
        btn_ban = InlineKeyboardButton("⛔ BAN USER", callback_data=f"adm_ban_{tid}") if status == 'active' else InlineKeyboardButton("✅ UNBAN", callback_data=f"adm_unban_{tid}")
        
        kb = [[InlineKeyboardButton("💰 +100 HIT", callback_data=f"adm_topup_{tid}_100"), InlineKeyboardButton("💰 +500 HIT", callback_data=f"adm_topup_{tid}_500")],
              [btn_role], [btn_ban, InlineKeyboardButton("🗑️ HAPUS", callback_data=f"adm_del_{tid}")],
              [InlineKeyboardButton("❌ TUTUP", callback_data="close_panel")]]
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    except: pass

async def get_leasing_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = await update.message.reply_text("⏳ *Memulai Audit...*", parse_mode='Markdown')
    try:
        counts = Counter(); off = 0; BATCH = 1000
        while True:
            res = supabase.table('kendaraan').select("finance").range(off, off+BATCH-1).execute(); data = res.data
            if not data: break
            counts.update([str(d.get('finance')).strip().upper() if d.get('finance') else "UNKNOWN" for d in data])
            if len(data) < BATCH: break
            off += BATCH
            # LOADING BAR PER 50K
            if off % 50000 == 0:
                try: await msg.edit_text(f"⏳ *Sedang Menghitung...*\nSudah scan: `{off:,}` data", parse_mode='Markdown')
                except: pass
        rpt = "🏦 **AUDIT LEASING (FINAL)**\n━━━━━━━━━━━━━━━━━━\n"
        for k,v in counts.most_common(): 
            if k not in ["UNKNOWN", "NAN"]: rpt += f"🔹 **{k}:** `{v:,}`\n"
        if len(rpt)>4000: rpt=rpt[:4000]+"..."
        await msg.edit_text(rpt, parse_mode='Markdown')
    except: await msg.edit_text("❌ Error.")

# ADMIN UTILS
async def admin_help(update, context):
    if update.effective_user.id == ADMIN_ID: await update.message.reply_text("🔐 **ADMIN**\n/users, /m_ID, /topup ID JML, /stats, /leasing, /angkat_korlap ID KOTA")
async def admin_topup(update, context):
    if update.effective_user.id == ADMIN_ID:
        try: topup_quota(int(context.args[0]), int(context.args[1])); await update.message.reply_text("✅ Topup Sukses.")
        except: await update.message.reply_text("⚠️ `/topup ID JML`")
async def add_agency(update, context):
    if update.effective_user.id == ADMIN_ID: supabase.table('agencies').insert({"name":" ".join(context.args)}).execute(); await update.message.reply_text("✅ Agency Added.")
async def contact_admin(update, context):
    u=get_user(update.effective_user.id); 
    if u: await context.bot.send_message(ADMIN_ID, f"📩 **MITRA:** {u['nama_lengkap']}\n💬 {' '.join(context.args)}"); await update.message.reply_text("✅ Terkirim.")
async def set_info(update, context):
    global GLOBAL_INFO; 
    if update.effective_user.id==ADMIN_ID: GLOBAL_INFO=" ".join(context.args); await update.message.reply_text("✅ Info Set.")
async def del_info(update, context):
    global GLOBAL_INFO; 
    if update.effective_user.id==ADMIN_ID: GLOBAL_INFO=""; await update.message.reply_text("🗑️ Info Deleted.")
async def list_users(update, context):
    if update.effective_user.id != ADMIN_ID: return
    try:
        res = supabase.table('users').select("*").execute(); active = [u for u in res.data if u['status']=='active']
        msg = f"📋 <b>DAFTAR MITRA ({len(active)})</b>\n━━━━━━━━━━━━━━━━━━\n"
        for i, u in enumerate(active, 1):
            msg += f"{i}. {u['nama_lengkap']} (ID: <code>{u['user_id']}</code>)\n   👉 /m_{u['user_id']}\n"
            if len(msg)>3800: await update.message.reply_text(msg, parse_mode='HTML'); msg=""
        if msg: await update.message.reply_text(msg, parse_mode='HTML')
    except: await update.message.reply_text("❌ Error.")
async def get_stats(update, context):
    if update.effective_user.id == ADMIN_ID:
        t = supabase.table('kendaraan').select("*", count="exact", head=True).execute().count
        u = supabase.table('users').select("*", count="exact", head=True).execute().count
        await update.message.reply_text(f"📊 **STATS**\nData: `{t:,}`\nUser: `{u}`", parse_mode='Markdown')

# ##############################################################################
# BAGIAN 6: USER FEATURES
# ##############################################################################

async def start(update, context):
    u = get_user(update.effective_user.id)
    info = f"📢 <b>INFO:</b> {clean_text(GLOBAL_INFO)}\n━━━━━━━━━━━━━━━━━━\n\n" if GLOBAL_INFO else ""
    if u and u.get('role')=='pic':
        msg=f"{info}🤖 <b>SYSTEM ONEASPAL (ENTERPRISE)</b>\nSelamat Datang, <b>{u['nama_lengkap']}</b>\n\n<b>Workspace Anda Siap.</b>"
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=ReplyKeyboardMarkup([["🔄 SINKRONISASI DATA", "📂 DATABASE SAYA"], ["📞 BANTUAN TEKNIS"]], resize_keyboard=True))
    elif u:
        msg=f"{info}🤖 <b>Selamat Datang di Oneaspalbot</b>\n\n<b>Salam Satu Aspal!</b> 👋\nHalo, Rekan Mitra Lapangan.\n\nCari data melalui:\n✅ Nomor Polisi (Nopol)\n✅ Nomor Rangka (Noka)\n✅ Nomor Mesin (Nosin)"
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text(f"🤖 <b>ONEASPAL: The Turbo Finder</b>\n\nSelamat Datang.\nSilakan registrasi:\n👉 /register", parse_mode='HTML')

async def panduan(update, context):
    msg = ("📖 <b>PANDUAN PENGGUNAAN ONEASPAL</b>\n\n"
           "1️⃣ <b>Cari Data Kendaraan</b>\n   - Ketik Nopol secara lengkap atau sebagian.\n   - Contoh: <code>B 1234 ABC</code> atau <code>1234</code>\n\n"
           "2️⃣ <b>Upload File (Mitra)</b>\n   - Kirim file Excel/CSV/ZIP ke bot ini.\n   - Bot akan membaca otomatis.\n\n"
           "3️⃣ <b>Upload Satuan / Kiriman</b>\n   - Gunakan perintah /tambah untuk input data manual.\n   - Cocok untuk data kiriman harian.\n\n"
           "4️⃣ <b>Lapor Unit Selesai</b>\n   - Gunakan perintah /lapor jika unit sudah ditarik/selesai.\n\n"
           "5️⃣ <b>Cek Kuota</b>\n   - Ketik /cekkuota untuk melihat sisa HIT.\n\n"
           "6️⃣ <b>Bantuan Admin</b>\n   - Ketik /admin [pesan] untuk menghubungi support.")
    await update.message.reply_text(msg, parse_mode='HTML')

async def cek_kuota(update, context):
    u = get_user(update.effective_user.id)
    if not u: return
    msg = f"💳 **INFO AKUN**\n━━━━━━━━━━━━━━━━━━\n👤 {u['nama_lengkap']}\n🔋 **SISA KUOTA:** `{u.get('quota',0)}` HIT\n━━━━━━━━━━━━━━━━━━"
    await update.message.reply_text(msg, parse_mode='Markdown')

async def handle_photo_topup(update, context):
    if update.effective_chat.type!="private": return
    u = get_user(update.effective_user.id); 
    if not u: return
    await update.message.reply_text("✅ **Bukti diterima!**", quote=True)
    msg = f"💰 **TOPUP**\n👤 {u['nama_lengkap']}\n🆔 `{u['user_id']}`\n📝 {update.message.caption or '-'}"
    kb = [[InlineKeyboardButton("✅ 50", callback_data=f"topup_{u['user_id']}_50"), InlineKeyboardButton("✅ 100", callback_data=f"topup_{u['user_id']}_100")], [InlineKeyboardButton("❌ TOLAK", callback_data=f"topup_{u['user_id']}_rej")]]
    await context.bot.send_photo(ADMIN_ID, update.message.photo[-1].file_id, caption=msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def notify_hit_to_group(context, u, d):
    try:
        msg = (f"🚨 <b>UNIT DITEMUKAN! (HIT)</b>\n━━━━━━━━━━━━━━━━━━\n"
               f"👤 <b>Penemu:</b> {clean_text(u.get('nama_lengkap'))} ({clean_text(u.get('agency'))})\n"
               f"📍 <b>Kota:</b> {clean_text(u.get('alamat'))}\n\n"
               f"🚙 <b>Unit:</b> {clean_text(d.get('type'))}\n"
               f"🔢 <b>Nopol:</b> <code style='color:orange'>{clean_text(d.get('nopol'))}</code>\n"
               f"📅 <b>Tahun:</b> {clean_text(d.get('tahun'))}\n"
               f"🎨 <b>Warna:</b> {clean_text(d.get('warna'))}\n"
               f"----------------------------------\n"
               f"🔧 <b>Noka:</b> <code style='color:orange'>{clean_text(d.get('noka'))}</code>\n"
               f"⚙️ <b>Nosin:</b> <code style='color:orange'>{clean_text(d.get('nosin'))}</code>\n"
               f"----------------------------------\n"
               f"⚠️ <b>OVD:</b> {clean_text(d.get('ovd'))} WO\n"
               f"🏦 <b>Finance:</b> {clean_text(d.get('finance'))}\n"
               f"🏢 <b>Branch:</b> {clean_text(d.get('branch'))}\n━━━━━━━━━━━━━━━━━━")
        kb = [[InlineKeyboardButton("📞 Hubungi Penemu (WA)", url=f"https://wa.me/{u.get('no_hp','').replace('0','62',1)}")]]
        await context.bot.send_message(LOG_GROUP_ID, msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    except: pass

async def handle_message(update, context):
    text = update.message.text; u = get_user(update.effective_user.id)
    if text == "🔄 SINKRONISASI DATA": return await upload_start(update, context)
    if text == "📂 DATABASE SAYA": return await cek_kuota(update, context)
    if text == "📞 BANTUAN TEKNIS": return await contact_admin(update, context)
    if not u or u['status']!='active': return await update.message.reply_text("⛔ Akses Ditolak/Pending.")
    if u.get('quota', 0) <= 0: return await update.message.reply_text("⛔ Kuota Habis.")
    
    kw = re.sub(r'[^a-zA-Z0-9]', '', text.upper())
    if len(kw) < 3: return await update.message.reply_text("⚠️ Minimal 3 karakter.")
    
    await context.bot.send_chat_action(update.effective_chat.id, constants.ChatAction.TYPING)
    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.ilike.%{kw}%,noka.eq.{kw},nosin.eq.{kw}").execute()
        if res.data:
            d = res.data[0]; update_quota_usage(u['user_id'], u['quota'])
            txt = (f"✅ <b>DATA DITEMUKAN</b>\n━━━━━━━━━━━━━━━━━━\n"
                   f"🚙 <b>Unit:</b> {clean_text(d.get('type'))}\n"
                   f"🔢 <b>Nopol:</b> {clean_text(d.get('nopol'))}\n"
                   f"📅 <b>Tahun:</b> {clean_text(d.get('tahun'))}\n"
                   f"🎨 <b>Warna:</b> {clean_text(d.get('warna'))}\n"
                   f"----------------------------------\n"
                   f"🔧 <b>Noka:</b> <code style='color:orange'>{clean_text(d.get('noka'))}</code>\n"
                   f"⚙️ <b>Nosin:</b> <code style='color:orange'>{clean_text(d.get('nosin'))}</code>\n"
                   f"----------------------------------\n"
                   f"⚠️ <b>OVD:</b> {clean_text(d.get('ovd'))}\n"
                   f"🏦 <b>Finance:</b> {clean_text(d.get('finance'))}\n"
                   f"🏢 <b>Branch:</b> {clean_text(d.get('branch'))}\n"
                   f"━━━━━━━━━━━━━━━━━━\n"
                   f"⚠️ <b>CATATAN PENTING:</b>\nIni bukan alat yang SAH untuk penarikan. Konfirmasi ke PIC leasing.")
            await update.message.reply_text(txt, parse_mode='HTML')
            await notify_hit_to_group(context, u, d)
        else: await update.message.reply_text(f"❌ <b>TIDAK DITEMUKAN</b>\n<code>{kw}</code>", parse_mode='HTML')
    except: await update.message.reply_text("❌ Error DB.")

# ##############################################################################
# BAGIAN 7: UPLOAD SYSTEM (ANTI STUCK - DELETE & REPLY STRATEGY)
# ##############################################################################

async def upload_start(update, context):
    if not get_user(update.effective_user.id): return
    context.user_data['fid'] = update.message.document.file_id
    if update.effective_user.id == ADMIN_ID:
        msg = await update.message.reply_text("⏳ **Menganalisa File...**", parse_mode='Markdown')
        try:
            f = await update.message.document.get_file(); c = await f.download_as_bytearray()
            df = read_file_robust(c, update.message.document.file_name); df = fix_header_position(df); df, found = smart_rename_columns(df)
            context.user_data['df'] = df.to_dict(orient='records')
            await msg.delete()
            
            # SCAN SUKSES SCREEN
            fin_status = "✅ ADA" if 'finance' in df.columns else "⚠️ TIDAK ADA"
            scan_report = (f"✅ <b>SCAN SUKSES (v4.39)</b>\n━━━━━━━━━━━━━━━━━━\n"
                           f"📊 <b>Kolom Dikenali:</b> {', '.join(found)}\n"
                           f"📁 <b>Total Baris:</b> {len(df)}\n"
                           f"🏦 <b>Kolom Leasing:</b> {fin_status}\n━━━━━━━━━━━━━━━━━━\n\n"
                           f"👉 <b>MASUKKAN NAMA LEASING:</b>\n<i>(Ketik 'SKIP' jika menggunakan kolom file)</i>")
            await update.message.reply_text(scan_report, reply_markup=ReplyKeyboardMarkup([["SKIP"], ["❌ BATAL"]], resize_keyboard=True), parse_mode='HTML')
            return U_LEASING_ADMIN
        except Exception as e: await msg.edit_text(f"❌ Error File: {e}"); return ConversationHandler.END
    else:
        await update.message.reply_text("📄 File diterima. Ketik Nama Leasing:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return U_LEASING_USER

async def upload_leasing_admin(update, context):
    nm = update.message.text.upper(); df = pd.DataFrame(context.user_data['df'])
    if nm != 'SKIP': df['finance'] = standardize_leasing_name(nm); fin_disp = nm
    else: df['finance'] = df['finance'].apply(standardize_leasing_name) if 'finance' in df.columns else 'UNKNOWN'; fin_disp = "AUTO CLEAN"
    
    df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
    df = df.drop_duplicates(subset=['nopol'], keep='last').replace({np.nan: None})
    context.user_data['final_df'] = df.to_dict(orient='records')
    
    s = df.iloc[0]
    prev = (f"🔎 <b>PREVIEW DATA (v4.39)</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"🏦 <b>Mode:</b> {fin_disp}\n📊 <b>Total:</b> {len(df)} Data\n\n"
            f"📝 <b>SAMPEL DATA BARIS 1:</b>\n"
            f"🔹 Leasing: {s.get('finance','-')}\n🔹 Nopol: <code style='color:orange'>{s.get('nopol','-')}</code>\n"
            f"🔹 Unit: {s.get('type','-')}\n🔹 Noka: {s.get('noka','-')}\n🔹 OVD: {s.get('ovd','-')}\n"
            f"━━━━━━━━━━━━━━━━━━\n⚠️ <b>Silakan konfirmasi untuk menyimpan data.</b>")
    await update.message.reply_text(prev, reply_markup=ReplyKeyboardMarkup([["🚀 UPDATE DATA"], ["🗑️ HAPUS MASSAL"], ["❌ BATAL"]], one_time_keyboard=True), parse_mode='HTML')
    return U_CONFIRM_UPLOAD

async def upload_confirm_admin(update, context):
    act = update.message.text
    if act == "❌ BATAL": return await cancel(update, context)
    
    # 1. PESAN LOADING AWAL
    msg = await update.message.reply_text("⏳ <b>MEMULAI UPDATE DATABASE...</b>\nMohon tunggu, jangan matikan bot...", parse_mode='HTML', reply_markup=ReplyKeyboardRemove())
    
    data = context.user_data.get('final_df'); total_data = len(data); suc = 0; start_t = time.time()
    
    try:
        BATCH = 1000 # Aman untuk Pro Plan
        list_nopol = [x['nopol'] for x in data] if act == "🗑️ HAPUS MASSAL" else []
        
        for i in range(0, total_data, BATCH):
            chunk = data[i:i+BATCH]
            try:
                if act == "🚀 UPDATE DATA": supabase.table('kendaraan').upsert(chunk, on_conflict='nopol').execute()
                elif act == "🗑️ HAPUS MASSAL": supabase.table('kendaraan').delete().in_('nopol', list_nopol[i:i+BATCH]).execute()
                suc += len(chunk)
            except Exception as e: print(f"⚠️ Batch Error: {e}"); continue

            # UPDATE VISUAL (SANGAT JARANG AGAR TIDAK KENA RATE LIMIT)
            if i > 0 and i % 10000 == 0:
                try: await msg.edit_text(f"⏳ <b>MEMPROSES DATA...</b>\n🚀 {i:,} / {total_data:,} data...", parse_mode='HTML')
                except: pass 
            await asyncio.sleep(0.01)
            
        dur = round(time.time() - start_t, 2)
        
        # 2. HAPUS PESAN LOADING
        try: await msg.delete()
        except: pass
        
        # 3. KIRIM PESAN BARU (PASTI MUNCUL)
        report = (f"✅ <b>UPLOAD SUKSES 100%!</b>\n━━━━━━━━━━━━━━━━━━\n"
                  f"📊 <b>Total Data:</b> {suc:,}\n❌ <b>Gagal:</b> {total_data - suc}\n"
                  f"⏱ <b>Waktu:</b> {dur} detik\n🚀 <b>Status:</b> Database Updated Successfully!")
        await update.message.reply_text(report, parse_mode='HTML')
        
    except Exception as e: await update.message.reply_text(f"❌ <b>SYSTEM ERROR:</b>\n{e}", parse_mode='HTML')
    return ConversationHandler.END

async def upload_leasing_user(update, context):
    if update.message.text=="❌ BATAL": return await cancel(update, context)
    u=get_user(update.effective_user.id); await context.bot.send_document(ADMIN_ID, context.user_data['fid'], caption=f"📥 **UPLOAD**\n👤 {u['nama_lengkap']}\n🏦 {update.message.text}")
    await update.message.reply_text("✅ Terkirim ke Admin."); return ConversationHandler.END

# ##############################################################################
# BAGIAN 8: HANDLER KONVERSASI
# ##############################################################################

async def cancel(update, context): await update.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

async def register_start(update, context):
    if get_user(update.effective_user.id): return await update.message.reply_text("✅ Terdaftar.")
    await update.message.reply_text("🤖 **REGISTRASI**\nPilih Jalur:", reply_markup=ReplyKeyboardMarkup([["1️⃣ MITRA LAPANGAN"], ["2️⃣ PIC LEASING"], ["❌ BATAL"]])); return R_ROLE_CHOICE
async def register_role(update, context):
    if update.message.text=="❌ BATAL": return await cancel(update, context)
    context.user_data['role'] = 'pic' if "PIC" in update.message.text else 'matel'
    await update.message.reply_text("1️⃣ Nama Lengkap:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]])); return R_NAMA
async def register_save(update, context):
    if update.message.text=="❌ BATAL": return await cancel(update, context)
    context.user_data['agency'] = update.message.text
    d = {"user_id":update.effective_user.id, "nama_lengkap":context.user_data['nama'], "role":context.user_data['role'], "status":"pending", "quota":1000, "agency":context.user_data['agency']}
    supabase.table('users').insert(d).execute()
    await update.message.reply_text("✅ Terkirim. Tunggu Admin.", reply_markup=ReplyKeyboardRemove())
    await context.bot.send_message(ADMIN_ID, f"🔔 **REG BARU**\n{d['nama_lengkap']} ({d['role']})", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ ACC", callback_data=f"appu_{d['user_id']}"), InlineKeyboardButton("❌ TOLAK", callback_data=f"reju_{d['user_id']}"]]))
    return ConversationHandler.END
async def r_nama(u,c): 
    if u.message.text=="❌ BATAL": return await cancel(u,c)
    c.user_data['nama']=u.message.text; await u.message.reply_text("2️⃣ Agency/PT:"); return R_AGENCY

async def add_start(update, context): await update.message.reply_text("➕ **TAMBAH**\nNopol:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]])); return A_NOPOL
async def add_nopol(u,c): 
    if u.message.text=="❌ BATAL": return await cancel(u,c)
    c.user_data['n']=u.message.text.upper(); await u.message.reply_text("Type:"); return A_TYPE
async def add_type(u,c): 
    if u.message.text=="❌ BATAL": return await cancel(u,c)
    c.user_data['t']=u.message.text; await u.message.reply_text("Leasing:"); return A_LEASING
async def add_leas(u,c): 
    if u.message.text=="❌ BATAL": return await cancel(u,c)
    c.user_data['l']=u.message.text; await u.message.reply_text("OVD:"); return A_NOKIR
async def add_ovd(u,c): 
    if u.message.text=="❌ BATAL": return await cancel(u,c)
    c.user_data['o']=u.message.text; await u.message.reply_text("✅ Kirim?", reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ BATAL"]])); return A_CONFIRM
async def add_done(u,c):
    if u.message.text!="✅ KIRIM": return await cancel(u,c)
    d={"nopol":c.user_data['n'],"type":c.user_data['t'],"finance":c.user_data['l'],"ovd":c.user_data['o']}
    supabase.table('kendaraan').upsert(d).execute()
    await u.message.reply_text("✅ Data Tersimpan.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

async def lapor_start(update, context):
    msg="🗑️ **LAPOR UNIT SELESAI/AMAN**\n\nAnda melaporkan bahwa unit sudah Selesai/Lunas dari Leasing.\nAdmin akan memverifikasi laporan ini sebelum data dihapus.\n\n👉 **Masukkan Nomor Polisi (Nopol) unit:**"
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]]), parse_mode='Markdown'); return L_NOPOL
async def lapor_check(u,c):
    if u.message.text=="❌ BATAL": return await cancel(u,c)
    c.user_data['ln']=u.message.text; await u.message.reply_text("✅ Kirim Laporan?", reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ BATAL"]])); return L_CONFIRM
async def lapor_done(u,c):
    if u.message.text!="✅ KIRIM": return await cancel(u,c)
    await u.message.reply_text("✅ Laporan Terkirim.", reply_markup=ReplyKeyboardRemove()); 
    await c.bot.send_message(ADMIN_ID, f"🗑️ **REQ HAPUS**\nNopol: {c.user_data['ln']}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ HAPUS", callback_data=f"del_acc_{c.user_data['ln']}_0")]]))
    return ConversationHandler.END

# ACTION HANDLERS
async def cb_handler(update, context):
    q=update.callback_query; await q.answer(); d=q.data
    if "adm_promote_" in d: supabase.table('users').update({'role':'korlap'}).eq('user_id',int(d.split("_")[2])).execute(); await q.edit_message_text("✅ Jadi KORLAP")
    elif "adm_demote_" in d: supabase.table('users').update({'role':'matel'}).eq('user_id',int(d.split("_")[2])).execute(); await q.edit_message_text("⬇️ Jadi MATEL")
    elif "adm_ban_" in d: update_user_status(int(d.split("_")[2]), 'rejected'); await q.edit_message_text("⛔ BANNED")
    elif "adm_unban_" in d: update_user_status(int(d.split("_")[2]), 'active'); await q.edit_message_text("✅ UNBANNED")
    elif "adm_del_" in d: supabase.table('users').delete().eq('user_id',int(d.split("_")[2])).execute(); await q.edit_message_text("🗑️ DELETED")
    elif "adm_topup_" in d: topup_quota(int(d.split("_")[2]), int(d.split("_")[3])); await q.edit_message_text("✅ Topup OK")
    elif "appu_" in d: update_user_status(int(d.split("_")[1]), 'active'); await q.edit_message_text("✅ User ACC"); await context.bot.send_message(d.split("_")[1], "🎉 Akun Aktif!")
    elif "del_acc_" in d: supabase.table('kendaraan').delete().eq('nopol',d.split("_")[2]).execute(); await q.edit_message_text("✅ Data Dihapus")
    elif d=="close_panel": await q.delete_message()

if __name__ == '__main__':
    print("🚀 ONEASPAL BOT v4.39 (GOLDEN STABLE) STARTING...")
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    
    # [IMPORTANT] HANDLER ORDER
    app.add_handler(MessageHandler(filters.Regex(r'^/m_\d+$'), manage_user_panel))
    
    app.add_handler(ConversationHandler(entry_points=[MessageHandler(filters.Document.ALL, upload_start)], states={U_LEASING_USER:[MessageHandler(filters.TEXT, upload_leasing_user)], U_LEASING_ADMIN:[MessageHandler(filters.TEXT, upload_leasing_admin)], U_CONFIRM_UPLOAD:[MessageHandler(filters.TEXT, upload_confirm_admin)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('register', register_start)], states={R_ROLE_CHOICE:[MessageHandler(filters.TEXT, register_role)], R_NAMA:[MessageHandler(filters.TEXT, r_nama)], R_AGENCY:[MessageHandler(filters.TEXT, register_save)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('tambah', add_start)], states={A_NOPOL:[MessageHandler(filters.TEXT & ~filters.Regex('^❌ BATAL$'), add_nopol)], A_TYPE:[MessageHandler(filters.TEXT & ~filters.Regex('^❌ BATAL$'), add_type)], A_LEASING:[MessageHandler(filters.TEXT & ~filters.Regex('^❌ BATAL$'), add_leas)], A_NOKIR:[MessageHandler(filters.TEXT & ~filters.Regex('^❌ BATAL$'), add_ovd)], A_CONFIRM:[MessageHandler(filters.TEXT, add_done)]}, fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('lapor', lapor_start)], states={L_NOPOL:[MessageHandler(filters.TEXT & ~filters.Regex('^❌ BATAL$'), lapor_check)], L_CONFIRM:[MessageHandler(filters.TEXT, lapor_done)]}, fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]))

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('cekkuota', cek_kuota))
    app.add_handler(CommandHandler('topup', admin_topup))
    app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('leasing', get_leasing_list)) 
    app.add_handler(CommandHandler('users', list_users))
    app.add_handler(CommandHandler('panduan', panduan))
    app.add_handler(CommandHandler('admin', contact_admin))
    app.add_handler(CommandHandler('addagency', add_agency)) 
    app.add_handler(CommandHandler('adminhelp', admin_help)) 
    app.add_handler(CommandHandler('setinfo', set_info))
    app.add_handler(CommandHandler('delinfo', del_info))
    app.add_handler(CommandHandler('angkat_korlap', angkat_korlap)) 
    
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_topup))
    app.add_handler(CallbackQueryHandler(cb_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ BOT ONLINE!")
    app.run_polling()