"""
################################################################################
#                                                                              #
#                      PROJECT: ONEASPAL BOT (ASSET RECOVERY)                  #
#                      VERSION: 4.31 (ULTIMATE RESTORATION & FIX)              #
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
# BAGIAN 1: KONFIGURASI SISTEM & SECURITY
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

GLOBAL_INFO = ""

try:
    ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
    LOG_GROUP_ID = int(os.environ.get("LOG_GROUP_ID", 0))
except ValueError:
    ADMIN_ID = 0
    LOG_GROUP_ID = 0

print(f"✅ [BOOT] SYSTEM STARTING... ADMIN ID: {ADMIN_ID}")

if not URL or not KEY or not TOKEN:
    print("❌ [CRITICAL] Credential tidak lengkap! Cek .env")
    exit()

try:
    supabase: Client = create_client(URL, KEY)
    print("✅ [BOOT] KONEKSI DATABASE BERHASIL!")
except Exception as e:
    print(f"❌ [CRITICAL] DATABASE ERROR: {e}")
    exit()


# ##############################################################################
# BAGIAN 2: KAMUS DATA
# ##############################################################################

COLUMN_ALIASES = {
    'nopol': ['nopolisi', 'nomorpolisi', 'nopol', 'noplat', 'nomorplat', 'nomorkendaraan', 'tnkb', 'licenseplate', 'plat', 'police_no'],
    'type': ['type', 'tipe', 'unit', 'model', 'vehicle', 'jenis', 'assetdescription', 'deskripsiunit', 'merk', 'object', 'kendaraan', 'item'],
    'tahun': ['tahun', 'year', 'thn', 'rakitan', 'th', 'yearofmanufacture', 'assetyear', 'manufacturingyear'],
    'warna': ['warna', 'color', 'colour', 'cat', 'kelir', 'assetcolour'],
    'noka': ['noka', 'norangka', 'nomorrangka', 'chassis', 'chasis', 'vin', 'rangka', 'chassisno', 'vinno', 'serial_number'],
    'nosin': ['nosin', 'nomesin', 'nomormesin', 'engine', 'mesin', 'engineno', 'noengine', 'engine_number'],
    'finance': ['finance', 'leasing', 'lising', 'multifinance', 'cabang', 'partner', 'mitra', 'principal', 'company', 'client'],
    'ovd': ['ovd', 'overdue', 'dpd', 'keterlambatan', 'odh', 'hari', 'telat', 'aging', 'od', 'bucket', 'daysoverdue'],
    'branch': ['branch', 'area', 'kota', 'pos', 'cabang', 'lokasi', 'wilayah', 'region', 'areaname', 'branchname']
}


# ##############################################################################
# BAGIAN 3: DEFINISI STATE CONVERSATION
# ##############################################################################

# A. Registrasi
R_ROLE_CHOICE, R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_CONFIRM = range(7)

# B. Tambah Data
A_NOPOL, A_TYPE, A_LEASING, A_NOKIR, A_CONFIRM = range(7, 12)

# C. Lapor Hapus
L_NOPOL, L_CONFIRM = range(12, 14) 

# D. Hapus Manual (Admin)
D_NOPOL, D_CONFIRM = range(14, 16)

# E. Upload File
U_LEASING_USER, U_LEASING_ADMIN, U_CONFIRM_UPLOAD = range(16, 19)

# F. Admin Reasoning
REJECT_REASON = 19
ADMIN_ACT_REASON = 20


# ##############################################################################
# BAGIAN 4: FUNGSI HELPER UTAMA
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

def update_quota_usage(user_id, current_quota):
    try:
        new_q = max(0, current_quota - 1)
        supabase.table('users').update({'quota': new_q}).eq('user_id', user_id).execute()
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

def clean_text(text):
    if not text: return "-"
    return html.escape(str(text))

def standardize_leasing_name(name):
    if not name: return "UNKNOWN"
    clean = str(name).upper().strip()
    clean = re.sub(r'^\d+\s+', '', clean)
    clean = re.sub(r'\(.*?\)', '', clean).strip()
    mapping = {
        "OTTO": "OTO", "OTTO.COM": "OTO", "BRI FINANCE": "BRI",
        "WOORI FINANCE": "WOORI", "TRUE FINANCE": "TRUE",
        "APOLLO FINANCE": "APOLLO", "SMART FINANCE": "SMART",
        "MITSUI": "MITSUI LEASING"
    }
    return mapping.get(clean, clean)


# ##############################################################################
# BAGIAN 5: ENGINE FILE (ADAPTIVE POLYGLOT)
# ##############################################################################

def normalize_text(text):
    if not isinstance(text, str): return str(text).lower()
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()

def fix_header_position(df):
    target = COLUMN_ALIASES['nopol']
    for i in range(min(20, len(df))):
        vals = [normalize_text(str(x)) for x in df.iloc[i].values]
        if any(alias in vals for alias in target):
            df.columns = df.iloc[i]
            df = df.iloc[i+1:].reset_index(drop=True)
            return df
    return df

def smart_rename_columns(df):
    new = {}; found = []
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
    encs = ['utf-8-sig', 'utf-8', 'cp1252', 'latin1', 'utf-16']
    seps = [None, ';', ',', '\t', '|']
    for e in encs:
        for s in seps:
            try:
                df = pd.read_csv(io.BytesIO(content), sep=s, dtype=str, encoding=e, engine='python', on_bad_lines='skip')
                if len(df.columns)>1: return df
            except: continue
    return pd.read_csv(io.BytesIO(content), sep=None, engine='python', dtype=str)


# ##############################################################################
# BAGIAN 6: FITUR ADMIN - ACTION & PROMOTION (WITH KORLAP TOGGLE)
# ##############################################################################

async def angkat_korlap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Fitur Manual via Command
    if update.effective_user.id != ADMIN_ID: return
    try:
        if len(context.args) < 2:
            return await update.message.reply_text("⚠️ Format: `/angkat_korlap [ID] [KOTA]`", parse_mode='Markdown')
        target_id = int(context.args[0]); wilayah = " ".join(context.args[1:]).upper()
        data = {"role": "korlap", "wilayah_korlap": wilayah, "quota": 5000} 
        supabase.table('users').update(data).eq('user_id', target_id).execute()
        await update.message.reply_text(f"✅ **SUKSES!**\nUser ID `{target_id}` sekarang adalah **KORLAP {wilayah}**.", parse_mode='Markdown')
    except Exception as e: await update.message.reply_text(f"❌ Gagal: {e}")

async def reject_start(update, context):
    query = update.callback_query; await query.answer()
    context.user_data['reject_target_uid'] = query.data.split("_")[1]
    await context.bot.send_message(chat_id=update.effective_chat.id, text="📝 Ketik **ALASAN** Penolakan:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True))
    return REJECT_REASON

async def reject_complete(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    target_uid = context.user_data.get('reject_target_uid')
    update_user_status(target_uid, 'rejected')
    try: await context.bot.send_message(target_uid, f"⛔ **PENDAFTARAN DITOLAK**\nAlasan: {update.message.text}")
    except: pass
    await update.message.reply_text("✅ User Ditolak.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

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
# BAGIAN 7: FITUR ADMIN - USER MANAGER & PANEL (NEW: KORLAP TOGGLE)
# ##############################################################################

async def admin_help(update, context):
    if update.effective_user.id != ADMIN_ID: return
    msg = ("🔐 **ADMIN COMMANDS v4.31**\n\n👮‍♂️ **ROLE**\n• `/angkat_korlap [ID] [KOTA]`\n\n👥 **USERS**\n• `/users`\n• `/m_ID`\n• `/topup [ID] [JML]`\n\n⚙️ **SYSTEM**\n• `/stats`\n• `/leasing`")
    await update.message.reply_text(msg, parse_mode='Markdown')

async def list_users(update, context):
    if update.effective_user.id != ADMIN_ID: return
    await context.bot.send_chat_action(update.effective_chat.id, constants.ChatAction.TYPING)
    try:
        res = supabase.table('users').select("*").execute()
        active_list = [u for u in res.data if u.get('status') == 'active']
        if not active_list: return await update.message.reply_text("📂 Kosong.")
        msg = "📋 <b>DAFTAR MITRA (v4.31)</b>\n━━━━━━━━━━━━━━━━━━\n"
        for i, u in enumerate(active_list, 1):
            role_icon = "🎖️" if u.get('role')=='korlap' else "🤝" if u.get('role')=='pic' else "🛡️"
            role_name = str(u.get('role', 'matel')).upper()
            msg += f"{i}. {role_icon} <b>{clean_text(u.get('nama_lengkap'))}</b> ({role_name})\n   ID: <code>{u['user_id']}</code> | 📍 {clean_text(u.get('alamat'))}\n   👉 /m_{u['user_id']}\n\n"
            if len(msg) > 3800: await update.message.reply_text(msg, parse_mode='HTML'); msg=""
        if msg: await update.message.reply_text(msg, parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def manage_user_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Cek Admin
    if update.effective_user.id != ADMIN_ID: return
    
    try:
        # Ambil ID dari text /m_123456
        tid = int(update.message.text.split('_')[1])
        u = get_user(tid)
        
        if not u: 
            return await update.message.reply_text("❌ User tidak ditemukan di database.")
        
        # Cek Data User
        role_now = u.get('role', 'matel')      # matel / korlap / pic
        status_now = u.get('status', 'active') # active / rejected
        
        # Info Header
        info_role = "🎖️ KORLAP" if role_now == 'korlap' else f"🛡️ {role_now.upper()}"
        wilayah = f"({u.get('wilayah_korlap', '-')})" if role_now == 'korlap' else ""
        icon_status = "✅ AKTIF" if status_now == 'active' else "⛔ BANNED"
        
        msg = (
            f"👮‍♂️ <b>USER MANAGER</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Nama:</b> {clean_text(u.get('nama_lengkap'))}\n"
            f"🏅 <b>Role:</b> {info_role} {wilayah}\n"
            f"📊 <b>Status:</b> {icon_status}\n"
            f"📱 <b>ID:</b> <code>{tid}</code>\n"
            f"🔋 <b>Kuota:</b> {u.get('quota', 0)}\n"
            f"🏢 <b>Agency:</b> {clean_text(u.get('agency'))}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        
        # --- LOGIKA TOMBOL PINTAR (SMART BUTTONS) ---
        
        # 1. Tombol Role (Korlap)
        if role_now == 'korlap':
            btn_role = InlineKeyboardButton("⬇️ BERHENTIKAN KORLAP", callback_data=f"adm_demote_{tid}")
        else:
            btn_role = InlineKeyboardButton("🎖️ ANGKAT KORLAP", callback_data=f"adm_promote_{tid}")

        # 2. Tombol Status (Ban/Unban)
        if status_now == 'active':
            btn_ban = InlineKeyboardButton("⛔ BAN USER", callback_data=f"adm_ban_{tid}")
        else:
            btn_ban = InlineKeyboardButton("✅ UNBAN (PULIHKAN)", callback_data=f"adm_unban_{tid}")

        # Susunan Keyboard
        kb = [
            [InlineKeyboardButton("💰 +100 HIT", callback_data=f"adm_topup_{tid}_100"), InlineKeyboardButton("💰 +500 HIT", callback_data=f"adm_topup_{tid}_500")],
            [btn_role], 
            [btn_ban, InlineKeyboardButton("🗑️ HAPUS DATA", callback_data=f"adm_del_{tid}")],
            [InlineKeyboardButton("❌ TUTUP PANEL", callback_data="close_panel")]
        ]
        
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error Panel: {e}")


# ==============================================================================
# BAGIAN 8: FITUR AUDIT & ADMIN UTILS
# ==============================================================================

async def get_stats(update, context):
    if update.effective_user.id != ADMIN_ID: return
    try:
        t = supabase.table('kendaraan').select("*", count="exact", head=True).execute().count
        u = supabase.table('users').select("*", count="exact", head=True).execute().count
        k = supabase.table('users').select("*", count="exact", head=True).eq('role', 'korlap').execute().count
        await update.message.reply_text(f"📊 **STATS v4.31**\n📂 Data: `{t:,}`\n👥 Total User: `{u}`\n🎖️ Korlap: `{k}`", parse_mode='Markdown')
    except: pass

async def get_leasing_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    # Pesan awal
    msg = await update.message.reply_text("⏳ *Memulai Audit Leasing...*", parse_mode='Markdown')
    
    try:
        counts = Counter()
        off = 0
        BATCH = 1000
        
        while True:
            # Ambil data per batch
            res = supabase.table('kendaraan').select("finance").range(off, off+BATCH-1).execute()
            data = res.data
            
            if not data: break
            
            # Hitung data
            counts.update([str(d.get('finance')).strip().upper() if d.get('finance') else "UNKNOWN" for d in data])
            
            # Cek jika batch terakhir
            if len(data) < BATCH: break
            
            off += BATCH
            
            # --- BAGIAN LOADING YANG HILANG (RESTORED) ---
            if off % 50000 == 0:
                try: 
                    await msg.edit_text(f"⏳ *Sedang Menghitung...*\nSudah scan: `{off:,}` data", parse_mode='Markdown')
                except: pass
            # ---------------------------------------------

        # Format Laporan Akhir
        rpt = "🏦 **AUDIT LEASING (FINAL)**\n━━━━━━━━━━━━━━━━━━\n"
        # Sortir dari yang terbanyak
        for k, v in counts.most_common():
            if k not in ["UNKNOWN", "NONE", "NAN", "-"]: 
                rpt += f"🔹 **{k}:** `{v:,}`\n"
        
        # Potong jika kepanjangan (Telegram limit)
        if len(rpt) > 4000: rpt = rpt[:4000] + "\n...(dan lainnya)"
        
        await msg.edit_text(rpt, parse_mode='Markdown')
        
    except Exception as e: 
        await msg.edit_text(f"❌ Error: {e}")

async def set_info(update, context):
    global GLOBAL_INFO; 
    if update.effective_user.id==ADMIN_ID: GLOBAL_INFO = " ".join(context.args); await update.message.reply_text("✅ Info Set.")
async def del_info(update, context):
    global GLOBAL_INFO; 
    if update.effective_user.id==ADMIN_ID: GLOBAL_INFO = ""; await update.message.reply_text("🗑️ Info Deleted.")
async def test_group(update, context):
    if update.effective_user.id==ADMIN_ID:
        try: await context.bot.send_message(LOG_GROUP_ID, "🔔 TEST"); await update.message.reply_text("✅ OK")
        except Exception as e: await update.message.reply_text(f"❌ Fail: {e}")

async def admin_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid, amt = int(context.args[0]), int(context.args[1])
        if topup_quota(tid, amt)[0]: await update.message.reply_text(f"✅ Sukses Topup {amt} ke {tid}.")
        else: await update.message.reply_text("❌ Gagal Topup.")
    except: await update.message.reply_text("⚠️ Format: `/topup ID JML`")

async def add_agency(update, context):
    if update.effective_user.id != ADMIN_ID: return
    try:
        name = " ".join(context.args)
        if not name: return await update.message.reply_text("⚠️ Nama Agency kosong.")
        supabase.table('agencies').insert({"name": name}).execute()
        await update.message.reply_text(f"✅ Agency '{name}' ditambahkan.")
    except: await update.message.reply_text("❌ Error.")

async def contact_admin(update, context):
    u=get_user(update.effective_user.id); args = " ".join(context.args) if context.args else "Bantuan Teknis (Tombol)"
    if u: await context.bot.send_message(ADMIN_ID, f"📩 **MITRA:** {u['nama_lengkap']}\n💬 {args}"); await update.message.reply_text("✅ Pesan terkirim ke Support.")


# ==============================================================================
# BAGIAN 9: USER FEATURES & NOTIFIKASI
# ==============================================================================

async def cek_kuota(update, context):
    u = get_user(update.effective_user.id)
    if not u or u['status']!='active': return
    
    if u.get('role') == 'pic':
        msg = (f"📂 **DATABASE SAYA**\n━━━━━━━━━━━━━━━━━━\n"
               f"👤 **User:** {u.get('nama_lengkap')}\n"
               f"🏢 **Leasing:** {u.get('agency')}\n"
               f"🔋 **Status Akses:** UNLIMITED (Enterprise)\n"
               f"━━━━━━━━━━━━━━━━━━\n"
               f"✅ Sinkronisasi data berjalan normal.")
    else:
        role_msg = f"🎖️ **KORLAP {u.get('wilayah_korlap','')}**" if u.get('role')=='korlap' else f"🛡️ **MITRA LAPANGAN**"
        msg = (f"💳 **INFO AKUN**\n━━━━━━━━━━━━━━━━━━\n{role_msg}\n👤 {u.get('nama_lengkap')}\n🔋 **SISA KUOTA:** `{u.get('quota',0)}` HIT\n━━━━━━━━━━━━━━━━━━")
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def handle_photo_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    u = get_user(update.effective_user.id); 
    if not u: return
    await update.message.reply_text("✅ **Bukti diterima!** Sedang diverifikasi...", quote=True)
    msg = f"💰 **TOPUP REQUEST**\n👤 {u['nama_lengkap']}\n🆔 `{u['user_id']}`\n🔋 Saldo: {u.get('quota',0)}\n📝 {update.message.caption or '-'}"
    kb = [[InlineKeyboardButton("✅ 50", callback_data=f"topup_{u['user_id']}_50"), InlineKeyboardButton("✅ 100", callback_data=f"topup_{u['user_id']}_100")], [InlineKeyboardButton("❌ TOLAK", callback_data=f"topup_{u['user_id']}_rej")]]
    await context.bot.send_photo(ADMIN_ID, update.message.photo[-1].file_id, caption=msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

# --- FORMAT NOTIF HIT VERTIKAL (FIXED) ---
async def notify_hit_to_group(context, u, d):
    try:
        hp_raw = u.get('no_hp', '-')
        hp_wa = '62' + hp_raw[1:] if hp_raw.startswith('0') else hp_raw
        
        msg = (
            f"🚨 <b>UNIT DITEMUKAN! (HIT)</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
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
        kb = [[InlineKeyboardButton("📞 Hubungi Penemu (WA)", url=f"https://wa.me/{hp_wa}")]]
        await context.bot.send_message(LOG_GROUP_ID, msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    except Exception as e: logger.error(f"Fail notif group: {e}")


# ==============================================================================
# BAGIAN 10: UPLOAD SYSTEM (BLUE DIAMOND PREVIEW + BULK DELETE)
# ==============================================================================

async def upload_start(update, context):
    # Cek user valid
    if not get_user(update.effective_user.id): return
    
    context.user_data['fid'] = update.message.document.file_id
    
    # Kalo ADMIN -> Lakukan Smart Scan
    if update.effective_user.id == ADMIN_ID:
        msg = await update.message.reply_text("⏳ **Menganalisa File...**", parse_mode='Markdown')
        try:
            f = await update.message.document.get_file(); c = await f.download_as_bytearray()
            # Baca File
            df = read_file_robust(c, update.message.document.file_name)
            df = fix_header_position(df)
            df, found = smart_rename_columns(df)
            
            # Simpan ke memori sementara
            context.user_data['df'] = df.to_dict(orient='records')
            
            # Hapus pesan loading "Menganalisa..."
            await msg.delete()
            
            # [REVISI VISUAL] TAMPILAN SCAN SUKSES (SESUAI GAMBAR)
            fin_status = "✅ ADA" if 'finance' in df.columns else "⚠️ TIDAK ADA"
            scan_report = (
                f"✅ <b>SCAN SUKSES (v4.35)</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 <b>Kolom Dikenali:</b> {', '.join(found)}\n"
                f"📁 <b>Total Baris:</b> {len(df)}\n"
                f"🏦 <b>Kolom Leasing:</b> {fin_status}\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"👉 <b>MASUKKAN NAMA LEASING UNTUK DATA INI:</b>\n"
                f"<i>(Ketik 'SKIP' jika ingin menggunakan kolom leasing dari file)</i>"
            )
            
            await update.message.reply_text(scan_report, reply_markup=ReplyKeyboardMarkup([["SKIP"], ["❌ BATAL"]], resize_keyboard=True), parse_mode='HTML')
            return U_LEASING_ADMIN
            
        except Exception as e: 
            await msg.edit_text(f"❌ Error File: {e}")
            return ConversationHandler.END
    else:
        # Kalo User Biasa -> Langsung tanya leasing
        await update.message.reply_text("📄 File diterima. Ketik Nama Leasing:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return U_LEASING_USER

async def upload_leasing_user(update, context): 
    nm = update.message.text; 
    if nm=="❌ BATAL": return await cancel(update, context)
    u = get_user(update.effective_user.id)
    await context.bot.send_document(ADMIN_ID, context.user_data['upload_file_id'], caption=f"📥 **UPLOAD USER ({u.get('role').upper()})**\n👤 {u['nama_lengkap']}\n🏦 {nm}")
    if u.get('role') == 'pic': resp = "✅ **SINKRONISASI BERHASIL**\nData Anda telah diamankan di Database Pribadi."
    else: resp = "✅ **TERKIRIM**\nTerima kasih kontribusinya! Admin akan memverifikasi data ini."
    await update.message.reply_text(resp, parse_mode='Markdown'); return ConversationHandler.END

async def upload_leasing_admin(update, context):
    nm = update.message.text.upper(); df = pd.DataFrame(context.user_data['df'])
    if nm != 'SKIP': df['finance'] = standardize_leasing_name(nm); fin_disp = nm
    else: df['finance'] = df['finance'].apply(standardize_leasing_name) if 'finance' in df.columns else 'UNKNOWN'; fin_disp = "AUTO CLEAN"
    
    df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
    df = df.drop_duplicates(subset=['nopol'], keep='last').replace({np.nan: None})
    context.user_data['final_df'] = df.to_dict(orient='records')
    
    # [FIX VISUAL] BAHASA OFFICE (UPDATE DATA)
    s = df.iloc[0]
    prev = (f"🔎 <b>PREVIEW DATA (v4.36)</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"🏦 <b>Mode:</b> {fin_disp}\n📊 <b>Total:</b> {len(df)} Data\n\n"
            f"📝 <b>SAMPEL DATA BARIS 1:</b>\n"
            f"🔹 Leasing: {s.get('finance','-')}\n🔹 Nopol: <code style='color:orange'>{s.get('nopol','-')}</code>\n"
            f"🔹 Unit: {s.get('type','-')}\n🔹 Noka: {s.get('noka','-')}\n🔹 OVD: {s.get('ovd','-')}\n"
            f"━━━━━━━━━━━━━━━━━━\n⚠️ <b>Silakan konfirmasi untuk menyimpan data.</b>")
    
    # TOMBOL DIGANTI LEBIH PROFESIONAL
    kb = [["🚀 UPDATE DATA"], ["🗑️ HAPUS MASSAL"], ["❌ BATAL"]]
    await update.message.reply_text(prev, reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True), parse_mode='HTML')
    return U_CONFIRM_UPLOAD

async def upload_confirm_admin(update, context):
    act = update.message.text
    if act == "❌ BATAL": return await cancel(update, context)
    
    # Pesan Awal
    msg = await update.message.reply_text("⏳ <b>Memulai Sinkronisasi...</b>\nMohon tunggu...", parse_mode='HTML', reply_markup=ReplyKeyboardRemove())
    
    data = context.user_data.get('final_df')
    suc = 0
    total_data = len(data)
    start_t = time.time()
    
    try:
        BATCH = 1000 # Batch size aman
        list_nopol = [x['nopol'] for x in data] if act == "🗑️ HAPUS MASSAL" else []
        
        for i in range(0, total_data, BATCH):
            chunk = data[i:i+BATCH]
            
            # Eksekusi Database (Silent & Fast)
            try:
                if act == "🚀 UPDATE DATA": 
                    supabase.table('kendaraan').upsert(chunk, on_conflict='nopol').execute()
                elif act == "🗑️ HAPUS MASSAL": 
                    supabase.table('kendaraan').delete().in_('nopol', list_nopol[i:i+BATCH]).execute()
                suc += len(chunk)
            except Exception as e:
                print(f"⚠️ Batch Error: {e}")
                continue # Lanjut ke batch berikutnya walau ini gagal
            
            # [REVISI] UPDATE VISUAL LEBIH AKTIF (Setiap 5.000 data)
            if i % 5000 == 0 and i > 0:
                percent = int((i / total_data) * 100)
                # Bikin Bar Loading [▓▓▓░░░]
                filled = int(percent / 10)
                bar = "▓" * filled + "░" * (10 - filled)
                
                try: 
                    await msg.edit_text(
                        f"⏳ <b>UPDATE DATABASE... {percent}%</b>\n"
                        f"<code>[{bar}]</code>\n"
                        f"✅ Terproses: <b>{i:,}</b> / {total_data:,}", 
                        parse_mode='HTML'
                    )
                except: pass # Jika gagal edit visual, biarkan jalan terus
            
            await asyncio.sleep(0.05) # Istirahat super singkat
            
        dur = round(time.time() - start_t, 2)
        
        # Laporan Akhir
        report = (
            f"✅ <b>PROSES SELESAI!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>Total Data:</b> {suc:,}\n"
            f"❌ <b>Gagal:</b> {total_data - suc}\n"
            f"⏱ <b>Waktu:</b> {dur} detik\n"
            f"🚀 <b>Status:</b> Database Updated Successfully!"
        )
        await msg.edit_text(report, parse_mode='HTML')
        
    except Exception as e: 
        await msg.edit_text(f"❌ Error System: {e}")
        
    return ConversationHandler.END


# ==============================================================================
# BAGIAN 11: REGISTRASI & START (SIMPLE)
# ==============================================================================

async def register_start(update, context):
    if get_user(update.effective_user.id): return await update.message.reply_text("✅ Anda sudah terdaftar.")
    msg = ("🤖 **ONEASPAL REGISTRATION**\n\nSilakan pilih **Jalur Profesi** Anda:\n\n1️⃣ **MITRA LAPANGAN (MATEL)**\n_(Untuk Profcoll & Jasa Pengamanan Aset)_\n\n2️⃣ **PIC LEASING (INTERNAL)**\n_(Khusus Staff Internal Leasing/Finance)_")
    kb = [["1️⃣ MITRA LAPANGAN"], ["2️⃣ PIC LEASING"], ["❌ BATAL"]]
    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)); return R_ROLE_CHOICE

async def register_role_choice(update, context):
    choice = update.message.text
    if choice == "❌ BATAL": return await cancel(update, context)
    if "1️⃣" in choice:
        context.user_data['reg_role'] = 'matel'
        await update.message.reply_text("🛡️ **FORMULIR MITRA LAPANGAN**\n\n1️⃣ Masukkan **Nama Lengkap**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]])); return R_NAMA
    elif "2️⃣" in choice:
        context.user_data['reg_role'] = 'pic'
        await update.message.reply_text("🤝 **FORMULIR INTERNAL LEASING**\n\n1️⃣ Masukkan **Nama Lengkap**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]])); return R_NAMA
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
    if context.user_data['reg_role'] == 'pic': txt = "5️⃣ **Nama Leasing / Finance:**\n_(Contoh: BCA Finance, Adira, ACC)_"
    else: txt = "5️⃣ **Nama Agency / PT:**\n_(Isi '-' jika Freelance/Mandiri)_"
    await update.message.reply_text(txt); return R_AGENCY
async def register_agency(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    context.user_data['r_agency'] = update.message.text; await update.message.reply_text("✅ **DATA LENGKAP**\nKirim Pendaftaran?", reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ ULANGI"]])); return R_CONFIRM

async def register_confirm(update, context):
    if update.message.text != "✅ KIRIM": return await cancel(update, context)
    role_db = context.user_data.get('reg_role', 'matel'); quota_init = 5000 if role_db == 'pic' else 1000
    d = {"user_id": update.effective_user.id, "nama_lengkap": context.user_data['r_nama'], "no_hp": context.user_data['r_hp'], "email": context.user_data['r_email'], "alamat": context.user_data['r_kota'], "agency": context.user_data['r_agency'], "quota": quota_init, "status": "pending", "role": role_db, "ref_korlap": None}
    try:
        supabase.table('users').insert(d).execute()
        if role_db == 'pic': await update.message.reply_text("✅ **PENDAFTARAN TERKIRIM**\nAkses Enterprise Workspace sedang diverifikasi Admin.", reply_markup=ReplyKeyboardRemove())
        else: await update.message.reply_text("✅ **PENDAFTARAN TERKIRIM**\nData Mitra sedang diverifikasi Admin Pusat.", reply_markup=ReplyKeyboardRemove())
        msg_admin = (f"🔔 <b>REGISTRASI BARU ({role_db.upper()})</b>\n━━━━━━━━━━━━━━━━━━\n👤 <b>Nama:</b> {clean_text(d['nama_lengkap'])}\n🏢 <b>Agency/Leasing:</b> {clean_text(d['agency'])}\n📍 <b>Kota:</b> {clean_text(d['alamat'])}\n📱 <b>HP:</b> {clean_text(d['no_hp'])}\n━━━━━━━━━━━━━━━━━━")
        kb = [[InlineKeyboardButton("✅ TERIMA", callback_data=f"appu_{d['user_id']}"), InlineKeyboardButton("❌ TOLAK", callback_data=f"reju_{d['user_id']}")]]
        await context.bot.send_message(ADMIN_ID, msg_admin, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    except Exception as e: logger.error(f"Reg Error: {e}"); await update.message.reply_text("❌ Gagal. User ID mungkin sudah terdaftar.")
    return ConversationHandler.END


# ==============================================================================
# BAGIAN 12: START & PANDUAN (UPDATED)
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

# [UPDATE] PANDUAN SESUAI GAMBAR SCREENSHOT
async def panduan(update, context):
    u = get_user(update.effective_user.id)
    if u and u.get('role') == 'pic':
        msg = ("📖 <b>PANDUAN ENTERPRISE</b>\n\n<b>1. Sinkronisasi Data</b>\nTekan '🔄 SINKRONISASI DATA', kirim file Excel.\n\n<b>2. Monitoring</b>\nKetik Nopol di kolom chat.\n\n<b>3. Akun</b>\nTekan '📂 DATABASE SAYA'.")
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
            "   - Gunakan perintah /tambah untuk input data manual.\n"
            "   - Cocok untuk data kiriman harian.\n\n"
            "4️⃣ <b>Lapor Unit Selesai</b>\n"
            "   - Gunakan perintah /lapor jika unit sudah ditarik/selesai.\n\n"
            "5️⃣ <b>Cek Kuota</b>\n"
            "   - Ketik /cekkuota untuk melihat sisa HIT.\n\n"
            "6️⃣ <b>Bantuan Admin</b>\n"
            "   - Ketik /admin [pesan] untuk menghubungi support."
        )
    await update.message.reply_text(msg, parse_mode='HTML')

# --- FORMAT PENCARIAN VERTIKAL (FIXED) ---
async def handle_message(update, context):
    text = update.message.text; u = get_user(update.effective_user.id)
    if text == "🔄 SINKRONISASI DATA": return await upload_start(update, context)
    if text == "📂 DATABASE SAYA": return await cek_kuota(update, context)
    if text == "📞 BANTUAN TEKNIS": return await contact_admin(update, context)
    if not u: return await update.message.reply_text("⛔ **AKSES DITOLAK**\nSilakan ketik /register.", parse_mode='Markdown')
    if u['status'] != 'active': return await update.message.reply_text("⏳ **AKUN PENDING**\nTunggu Admin.", parse_mode='Markdown')
    if u.get('quota', 0) <= 0: return await update.message.reply_text("⛔ **KUOTA HABIS**", parse_mode='Markdown')
    
    kw = re.sub(r'[^a-zA-Z0-9]', '', text.upper())
    if len(kw) < 3: return await update.message.reply_text("⚠️ Minimal 3 karakter.")
    
    await context.bot.send_chat_action(update.effective_chat.id, constants.ChatAction.TYPING)
    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.ilike.%{kw}%,noka.eq.{kw},nosin.eq.{kw}").execute()
        if res.data:
            d = res.data[0]; update_quota_usage(u['user_id'], u['quota'])
            info_txt = f"📢 <b>INFO:</b> {clean_text(GLOBAL_INFO)}\n━━━━━━━━━━━━━━━━━━\n" if GLOBAL_INFO else ""
            
            # FORMAT VERTIKAL (FIXED - 100% MATCH SCREENSHOT)
            txt = (
                f"{info_txt}✅ <b>DATA DITEMUKAN</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
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
            await update.message.reply_text(txt, parse_mode='HTML')
            await notify_hit_to_group(context, u, d)
        else: await update.message.reply_text(f"❌ <b>TIDAK DITEMUKAN</b>\n<code>{kw}</code>", parse_mode='HTML')
    except: await update.message.reply_text("❌ Error DB.")


# ==============================================================================
# BAGIAN 13: HANDLER KONVERSASI (LAPOR + TAMBAH + HAPUS) - [FIX BATAL BUG]
# ==============================================================================

async def add_data_start(update, context):
    if not get_user(update.effective_user.id): return
    await update.message.reply_text("➕ **TAMBAH UNIT**\n1️⃣ Nopol:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]])); return A_NOPOL
async def add_nopol(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context) # FIX
    context.user_data['a_nopol'] = update.message.text.upper(); await update.message.reply_text("2️⃣ Type Mobil:"); return A_TYPE
async def add_type(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context) # FIX
    context.user_data['a_type'] = update.message.text; await update.message.reply_text("3️⃣ Leasing:"); return A_LEASING
async def add_leasing(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context) # FIX
    context.user_data['a_leasing'] = update.message.text; await update.message.reply_text("4️⃣ Ket (OVD):"); return A_NOKIR
async def add_nokir(update, context): 
    if update.message.text == "❌ BATAL": return await cancel(update, context) # FIX
    context.user_data['a_nokir'] = update.message.text; await update.message.reply_text("✅ Kirim?", reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ BATAL"]])); return A_CONFIRM
async def add_confirm(update, context):
    if update.message.text != "✅ KIRIM": return await cancel(update, context)
    n = context.user_data['a_nopol']
    context.bot_data[f"prop_{n}"] = {"nopol": n, "type": context.user_data['a_type'], "finance": context.user_data['a_leasing'], "ovd": context.user_data['a_nokir']}
    await update.message.reply_text("✅ Terkirim ke Admin.", reply_markup=ReplyKeyboardRemove())
    kb = [[InlineKeyboardButton("✅ Terima", callback_data=f"v_acc_{n}_{update.effective_user.id}"), InlineKeyboardButton("❌ Tolak", callback_data="v_rej")]]
    await context.bot.send_message(ADMIN_ID, f"📥 **DATA BARU**\nNopol: `{n}`", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return ConversationHandler.END

# --- LAPOR SESUAI GAMBAR ---
async def lapor_delete_start(update, context):
    if not get_user(update.effective_user.id): return
    msg = (
        "🗑️ **LAPOR UNIT SELESAI/AMAN**\n\n"
        "Anda melaporkan bahwa unit sudah Selesai/Lunas dari Leasing.\n"
        "Admin akan memverifikasi laporan ini sebelum data dihapus.\n\n"
        "👉 **Masukkan Nomor Polisi (Nopol) unit:**"
    )
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True), parse_mode='Markdown')
    return L_NOPOL
async def lapor_delete_check(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    n = update.message.text.upper().replace(" ", "")
    if not supabase.table('kendaraan').select("*").eq('nopol', n).execute().data: 
        await update.message.reply_text(f"❌ Nopol `{n}` tidak ditemukan.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END
    context.user_data['lapor_nopol'] = n
    await update.message.reply_text(f"⚠️ Lapor Hapus `{n}`?", reply_markup=ReplyKeyboardMarkup([["✅ KIRIM LAPORAN", "❌ BATAL"]])); return L_CONFIRM
async def lapor_delete_confirm(update, context):
    if update.message.text != "✅ KIRIM LAPORAN": return await cancel(update, context)
    n = context.user_data['lapor_nopol']; u = get_user(update.effective_user.id)
    await update.message.reply_text("✅ Laporan terkirim.", reply_markup=ReplyKeyboardRemove())
    kb = [[InlineKeyboardButton("✅ Setujui", callback_data=f"del_acc_{n}_{u['user_id']}"), InlineKeyboardButton("❌ Tolak", callback_data=f"del_rej_{u['user_id']}")]]
    await context.bot.send_message(ADMIN_ID, f"🗑️ **REQ HAPUS**\nNopol: `{n}`\nPelapor: {u['nama_lengkap']}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return ConversationHandler.END

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

async def callback_handler(update, context):
    q = update.callback_query; await q.answer(); d = q.data
    
    # --- ADMIN ACTIONS (NEW PROMOTION LOGIC) ---
    if d.startswith("adm_promote_"):
        uid = int(d.split("_")[2])
        supabase.table('users').update({'role': 'korlap'}).eq('user_id', uid).execute()
        await q.edit_message_text(f"✅ User {uid} DIPROMOSIKAN jadi KORLAP.")
        try: await context.bot.send_message(uid, "🎉 **SELAMAT!** Anda telah diangkat menjadi **KORLAP**.")
        except: pass
    elif d.startswith("adm_demote_"):
        uid = int(d.split("_")[2])
        supabase.table('users').update({'role': 'matel'}).eq('user_id', uid).execute()
        await q.edit_message_text(f"⬇️ User {uid} DITURUNKAN jadi MATEL.")
    
    # --- EXISTING ACTIONS ---
    elif d.startswith("adm_topup_"): topup_quota(int(d.split("_")[2]), int(d.split("_")[3])); await q.edit_message_text("✅ Topup OK.")
    elif d == "close_panel": await q.delete_message()
    elif d.startswith("topup_"):
        parts = d.split("_"); uid = int(parts[1])
        if parts[2] == "rej": await context.bot.send_message(uid, "❌ Topup DITOLAK."); await q.edit_message_caption("❌ Ditolak.")
        else: topup_quota(uid, int(parts[2])); await context.bot.send_message(uid, f"✅ Topup {parts[2]} OK."); await q.edit_message_caption("✅ Sukses.")
    elif d.startswith("appu_"): update_user_status(d.split("_")[1], 'active'); await q.edit_message_text("✅ User ACC."); await context.bot.send_message(d.split("_")[1], "🎉 **AKUN AKTIF!**")
    elif d.startswith("reju_"): update_user_status(d.split("_")[1], 'rejected'); await q.edit_message_text("❌ User TOLAK."); await context.bot.send_message(d.split("_")[1], "⛔ Ditolak.")
    elif d.startswith("v_acc_"): n=d.split("_")[2]; item=context.bot_data.get(f"prop_{n}"); supabase.table('kendaraan').upsert(item).execute(); await q.edit_message_text("✅ Masuk DB."); await context.bot.send_message(d.split("_")[3], f"✅ Data `{n}` ACC.")
    elif d == "v_rej": await q.edit_message_text("❌ Data Ditolak.")
    elif d.startswith("del_acc_"): supabase.table('kendaraan').delete().eq('nopol', d.split("_")[2]).execute(); await q.edit_message_text("✅ Dihapus."); await context.bot.send_message(d.split("_")[3], "✅ Hapus ACC.")
    elif d.startswith("del_rej_"): await q.edit_message_text("❌ Ditolak."); await context.bot.send_message(d.split("_")[2], "❌ Hapus TOLAK.")

if __name__ == '__main__':
    print("🚀 ONEASPAL BOT v4.31 (FIXED & RESTORED) STARTING...")
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    
    app.add_handler(MessageHandler(filters.Regex(r'^/m_\d+$'), manage_user_panel))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(admin_action_start, pattern='^adm_(ban|unban|del)_')], states={ADMIN_ACT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_action_complete)]}, fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(reject_start, pattern='^reju_')], states={REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, reject_complete)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[MessageHandler(filters.Document.ALL, upload_start)], states={U_LEASING_USER: [MessageHandler(filters.TEXT, upload_leasing_user)], U_LEASING_ADMIN: [MessageHandler(filters.TEXT, upload_leasing_admin)], U_CONFIRM_UPLOAD: [MessageHandler(filters.TEXT, upload_confirm_admin)]}, fallbacks=[CommandHandler('cancel', cancel)], allow_reentry=True))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('register', register_start)], states={R_ROLE_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_role_choice)], R_NAMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_nama)], R_HP: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_hp)], R_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)], R_KOTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_kota)], R_AGENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_agency)], R_CONFIRM:[MessageHandler(filters.TEXT & ~filters.COMMAND, register_confirm)]}, fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('tambah', add_data_start)], states={A_NOPOL: [MessageHandler(filters.TEXT, add_nopol)], A_TYPE: [MessageHandler(filters.TEXT, add_type)], A_LEASING: [MessageHandler(filters.TEXT, add_leasing)], A_NOKIR: [MessageHandler(filters.TEXT, add_nokir)], A_CONFIRM: [MessageHandler(filters.TEXT, add_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('lapor', lapor_delete_start)], states={L_NOPOL: [MessageHandler(filters.TEXT, lapor_delete_check)], L_CONFIRM: [MessageHandler(filters.TEXT, lapor_delete_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('hapus', delete_unit_start)], states={D_NOPOL: [MessageHandler(filters.TEXT, delete_unit_check)], D_CONFIRM: [MessageHandler(filters.TEXT, delete_unit_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('cekkuota', cek_kuota))
    app.add_handler(CommandHandler('topup', admin_topup))
    app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('leasing', get_leasing_list)) 
    app.add_handler(CommandHandler('users', list_users))
    app.add_handler(CommandHandler('angkat_korlap', angkat_korlap)) 
    app.add_handler(CommandHandler('testgroup', test_group)) 
    app.add_handler(CommandHandler('panduan', panduan))
    app.add_handler(CommandHandler('setinfo', set_info)) 
    app.add_handler(CommandHandler('delinfo', del_info)) 
    app.add_handler(CommandHandler('admin', contact_admin))
    app.add_handler(CommandHandler('addagency', add_agency)) 
    app.add_handler(CommandHandler('adminhelp', admin_help)) 
        
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_topup))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ BOT ONLINE! (v4.31 - Ultimate Restoration & Fix)")
    app.run_polling()