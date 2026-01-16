"""
################################################################################
#                                                                              #
#                      PROJECT: ONEASPAL BOT (ASSET RECOVERY)                  #
#                      VERSION: 4.13 (MASTERPIECE STANDARD)                    #
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

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
TOKEN = os.environ.get("TELEGRAM_TOKEN")

GLOBAL_INFO = ""
LOG_GROUP_ID = -1003627047676  

DEFAULT_ADMIN_ID = 7530512170
try:
    env_id = os.environ.get("ADMIN_ID")
    ADMIN_ID = int(env_id) if env_id else DEFAULT_ADMIN_ID
except ValueError:
    ADMIN_ID = DEFAULT_ADMIN_ID

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
# BAGIAN 2: KAMUS DATA (VERTIKAL MODE - LENGKAP)
# ##############################################################################

COLUMN_ALIASES = {
    'nopol': [
        'nopolisi', 'nomorpolisi', 'nopol', 'noplat', 'nomorplat', 
        'nomorkendaraan', 'nokendaraan', 'nomer', 'tnkb', 'licenseplate', 
        'plat', 'nopolisikendaraan', 'nopil', 'polisi', 'platnomor', 
        'platkendaraan', 'nomerpolisi', 'no.polisi', 'nopol.', 'no_pol', 'police_no'
    ],
    'type': [
        'type', 'tipe', 'unit', 'model', 'vehicle', 'jenis', 'assetdescription', 
        'deskripsiunit', 'merk', 'object', 'kendaraan', 'item', 
        'brand', 'typedeskripsi', 'vehiclemodel', 'namaunit', 'kend', 
        'namakendaraan', 'merktype', 'objek', 'jenisobjek', 'item_description',
        'vehicle_desc',
        # --- UPDATE BARU (MTF & TAF) ---
        'unitasset',                # Dari header: UNIT; asset
        'unitassetwarnatahun'       # Dari header: UNIT; ASSET/WARNA/TAHUN
    ],
    'tahun': [
        'tahun', 'year', 'thn', 'rakitan', 'th', 'yearofmanufacture', 'assetyear', 
        'thnrakit', 'manufacturingyear', 'tahunkendaraan', 'thkendaraan', 'tahun_pembuatan', 'model_year'
    ],
    'warna': [
        'warna', 'color', 'colour', 'cat', 'kelir', 'assetcolour', 'warnakendaraan', 'body_color'
    ],
    'noka': [
        'noka', 'norangka', 'nomorrangka', 'chassis', 'chasis', 'vin', 
        'rangka', 'chassisno', 'norangka1', 'chasisno', 'vinno', 'norang',
        'no_rangka', 'serial_number',
        # --- UPDATE BARU (MTF & TAF) ---
        'nokanochassis',            # Dari header: NOKA; nochassis
        'nokanorangka'              # Dari header: NOKA; NORANGKA
    ],
    'nosin': [
        'nosin', 'nomesin', 'nomormesin', 'engine', 'mesin', 'engineno', 
        'nomesin1', 'engineno', 'noengine', 'nomes', 'no_mesin', 'engine_number',
        # --- UPDATE BARU (MTF & TAF) ---
        'nosinnoengine',            # Dari header: NOSIN; noengine
        'nosinnomesin'              # Dari header: NOSIN; NOMESIN
    ],
    'finance': [
        'finance', 'leasing', 'lising', 'multifinance', 'cabang', 
        'partner', 'mitra', 'principal', 'company', 'client', 
        'financecompany', 'leasingname', 'keterangan', 'sumberdata', 
        'financetype', 'nama_leasing', 'nama_finance'
    ],
    'ovd': [
        'ovd', 'overdue', 'dpd', 'keterlambatan', 'hari', 'telat', 
        'aging', 'od', 'bucket', 'daysoverdue', 'overduedays', 
        'kiriman', 'kolektibilitas', 'kol', 'kolek', 'bucket_od',
        # --- UPDATE BARU (MTF) ---
        'oddaysoverdue'             # Dari header: OD; daysoverdue
    ],
    'branch': [
        'branch', 'area', 'kota', 'pos', 'cabang', 'lokasi', 
        'wilayah', 'region', 'areaname', 'branchname', 'dealer', 'nama_cabang',
        # --- UPDATE BARU (MTF) ---
        'cabangcabang'              # Dari header: CABANG; cabang
    ]
}


# ##############################################################################
# BAGIAN 3: DEFINISI STATE CONVERSATION
# ##############################################################################

# A. Registrasi
R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_CONFIRM = range(6)

# B. Tambah Data
A_NOPOL, A_TYPE, A_LEASING, A_NOKIR, A_CONFIRM = range(6, 11)

# C. Lapor Hapus
L_NOPOL, L_CONFIRM = range(11, 13) 

# D. Hapus Manual (Admin)
D_NOPOL, D_CONFIRM = range(13, 15)

# E. Upload File
U_LEASING_USER, U_LEASING_ADMIN, U_CONFIRM_UPLOAD = range(15, 18)

# F. Admin Reasoning (Reject Registration)
REJECT_REASON = 18

# G. Admin Action Reason (Ban/Unban/Delete User)
ADMIN_ACT_REASON = 19


# ##############################################################################
# BAGIAN 4: FUNGSI HELPER UTAMA
# ##############################################################################

async def post_init(application: Application):
    """
    Mengatur Menu Command.
    REVISI v4.13: Hanya menampilkan menu untuk USER BIASA. Menu Admin disembunyikan.
    """
    await application.bot.set_my_commands([
        ("start", "🔄 Restart / Menu"),
        ("cekkuota", "💳 Cek Sisa Kuota"),
        ("tambah", "➕ Input Manual"),
        ("lapor", "🗑️ Lapor Unit Selesai"),
        ("register", "📝 Daftar Mitra"),
        ("admin", "📩 Hubungi Admin"),
        ("panduan", "📖 Buku Panduan"),
    ])
    print("✅ [INIT] Command List Updated (User Focused)!")

def get_user(user_id):
    try:
        response = supabase.table('users').select("*").eq('user_id', user_id).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error get_user: {e}")
        return None

def get_agency_data(agency_name):
    try:
        res = supabase.table('agencies').select("*").ilike('name', f"%{agency_name}%").execute()
        return res.data[0] if res.data else None
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
    """Membersihkan text agar aman untuk HTML."""
    if not text: return "-"
    return html.escape(str(text))

def escape_markdown(text):
    """Fungsi Anti-Crash untuk teks Markdown."""
    if not text: return ""
    return str(text).replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")


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
            print(f"✅ Header found at row {i}")
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
            if not valid: raise ValueError("ZIP Kosong/Invalid")
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
# BAGIAN 6: FITUR ADMIN - REASONING REJECT & ACTION
# ##############################################################################

# --- A. REJECT PENDAFTARAN ---
async def reject_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    context.user_data['reject_target_uid'] = query.data.split("_")[1]
    await context.bot.send_message(chat_id=update.effective_chat.id, text="📝 **KONFIRMASI PENOLAKAN**\n\nKetik **ALASAN**:", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True))
    return REJECT_REASON

async def reject_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text
    if reason == "❌ BATAL": 
        await update.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    target_uid = context.user_data.get('reject_target_uid')
    update_user_status(target_uid, 'rejected')
    try: await context.bot.send_message(target_uid, f"⛔ **PENDAFTARAN DITOLAK**\n\nAlasan: {reason}", parse_mode='Markdown')
    except: pass
    await update.message.reply_text(f"✅ User Ditolak. Alasan: {reason}", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- B. ADMIN ACTION (BAN/UNBAN/DELETE) DENGAN ALASAN ---
async def admin_action_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    data_parts = query.data.split("_")
    action = data_parts[1] # ban, unban, del
    target_uid = data_parts[2]
    
    context.user_data['adm_act_type'] = action
    context.user_data['adm_act_uid'] = target_uid
    
    act_name = "BAN" if action == "ban" else "UNBAN" if action == "unban" else "HAPUS PERMANEN"
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🛡️ **TINDAKAN: {act_name}**\nTarget ID: `{target_uid}`\n\nSilakan ketik **ALASAN / CATATAN** untuk user ini:",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
    )
    return ADMIN_ACT_REASON

async def admin_action_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text
    if reason == "❌ BATAL": 
        await update.message.reply_text("🚫 Tindakan Dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
        
    action = context.user_data.get('adm_act_type')
    uid = context.user_data.get('adm_act_uid')
    
    if action == "ban":
        update_user_status(uid, 'rejected')
        msg_user = f"⛔ **AKUN ANDA DIBEKUKAN (BANNED)**\n\n📝 Alasan: {reason}\nHubungi Admin untuk banding."
        msg_adm = f"⛔ User `{uid}` berhasil di-BAN.\nAlasan: {reason}"
        
    elif action == "unban":
        update_user_status(uid, 'active')
        msg_user = f"✅ **AKUN ANDA DIPULIHKAN (UNBANNED)**\n\n📝 Catatan: {reason}\nSelamat bekerja kembali!"
        msg_adm = f"✅ User `{uid}` berhasil di-UNBAN.\nCatatan: {reason}"
        
    elif action == "del":
        supabase.table('users').delete().eq('user_id', uid).execute()
        msg_user = f"🗑️ **AKUN ANDA DIHAPUS**\n\n📝 Alasan: {reason}\nData Anda telah dihapus dari sistem."
        msg_adm = f"🗑️ User `{uid}` berhasil DIHAPUS PERMANEN.\nAlasan: {reason}"
    
    # Notifikasi
    try: await context.bot.send_message(uid, msg_user, parse_mode='Markdown')
    except: pass
    
    await update.message.reply_text(msg_adm, reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
    return ConversationHandler.END


# ##############################################################################
# BAGIAN 7: FITUR ADMIN - USER MANAGER & PANEL
# ##############################################################################

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cheat Sheet Perintah Admin (Semua fitur admin ada disini).
    """
    if update.effective_user.id != ADMIN_ID: return
    msg = (
        "🔐 **ADMIN CONTROL PANEL**\n━━━━━━━━━━━━━━━━━━\n\n"
        "👥 **USER MANAGER**\n"
        "• `/users` : Daftar User + Menu Kontrol\n"
        "• `/m_ID` : Buka Panel User Manual\n\n"
        "💰 **FINANCE**\n"
        "• `/topup [ID] [JML]` : Isi Kuota\n\n"
        "📊 **AUDIT DATA**\n"
        "• `/stats` : Statistik Global\n"
        "• `/leasing` : Audit Detail Leasing\n"
        "• `/hapus` : Hapus Data Manual\n\n"
        "⚙️ **SYSTEM**\n"
        "• `/setinfo [Pesan]` : Pasang Info\n"
        "• `/delinfo` : Hapus Info\n"
        "• `/testgroup` : Cek Group Log\n"
        "• `/addagency` : Tambah B2B"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan daftar user dengan HTML Mode & Pagination."""
    if update.effective_user.id != ADMIN_ID: return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
    try:
        res = supabase.table('users').select("*").execute()
        active_list = [u for u in res.data if u.get('status') == 'active']
        
        if not active_list: return await update.message.reply_text("📂 Belum ada user aktif.")

        msg_header = "📋 <b>DAFTAR MITRA AKTIF (" + str(len(active_list)) + ")</b>\nKlik command di samping nama untuk aksi.\n━━━━━━━━━━━━━━━━━━\n"
        current_msg = msg_header
        
        for i, u in enumerate(active_list, 1):
            nama = clean_text(u.get('nama_lengkap'))
            pt = clean_text(u.get('agency'))
            kota = clean_text(u.get('alamat'))
            uid = u.get('user_id')
            
            entry = f"{i}. 👤 <b>{nama}</b>\n   📍 {kota} | 🏢 {pt}\n   👉 Manage: /m_{uid}\n\n"
            
            if len(current_msg) + len(entry) > 3800:
                await update.message.reply_text(current_msg, parse_mode='HTML')
                current_msg = entry 
            else:
                current_msg += entry
        
        if current_msg: await update.message.reply_text(current_msg, parse_mode='HTML')
            
    except Exception as e: await update.message.reply_text(f"❌ Error List Users: {str(e)}")

async def manage_user_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk Magic Link /m_ID."""
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_uid = int(update.message.text.split('_')[1])
        u = get_user(target_uid)
        if not u: return await update.message.reply_text("❌ User tidak ditemukan.")
        
        nama = clean_text(u.get('nama_lengkap'))
        pt = clean_text(u.get('agency'))
        
        msg = (
            f"👮‍♂️ <b>USER MANAGER</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Nama:</b> {nama}\n"
            f"🏢 <b>Agency:</b> {pt}\n"
            f"📱 <b>ID:</b> <code>{target_uid}</code>\n"
            f"🔋 <b>Kuota:</b> {u.get('quota', 0)}\n"
            f"🛡️ <b>Status:</b> {str(u.get('status')).upper()}\n"
            f"━━━━━━━━━━━━━━━━━━\n👇 <b>Pilih Tindakan:</b>"
        )
        # REVISI: Tombol Ban/Unban/Del sekarang men-trigger ConversationHandler (adm_...)
        kb = [
            [InlineKeyboardButton("💰 +50 HIT", callback_data=f"adm_topup_{target_uid}_50"), InlineKeyboardButton("💰 +100 HIT", callback_data=f"adm_topup_{target_uid}_100")],
            [InlineKeyboardButton("⛔ BAN (Reason)", callback_data=f"adm_ban_{target_uid}"), InlineKeyboardButton("✅ UNBAN (Reason)", callback_data=f"adm_unban_{target_uid}")],
            [InlineKeyboardButton("🗑️ HAPUS (Reason)", callback_data=f"adm_del_{target_uid}")],
            [InlineKeyboardButton("❌ TUTUP PANEL", callback_data="close_panel")]
        ]
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    except: await update.message.reply_text("❌ Error ID.")


# ==============================================================================
# BAGIAN 8: FITUR ADMIN - AUDIT & SYSTEM
# ==============================================================================

async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg_wait = await update.message.reply_text("⏳ *Menghitung...*", parse_mode='Markdown')
    try:
        tot = supabase.table('kendaraan').select("*", count="exact", head=True).execute().count
        usr = supabase.table('users').select("*", count="exact", head=True).execute().count
        await msg_wait.edit_text(f"📊 **DASHBOARD STATISTIK**\n━━━━━━━━━━━━━━━━━━\n📂 Data: `{tot:,}`\n👥 Mitra: `{usr:,}`\n💡 _Cek /leasing untuk detail._", parse_mode='Markdown')
    except: await msg_wait.edit_text("❌ Error.")

async def get_leasing_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = await update.message.reply_text("⏳ *Mengaudit... (Mohon tunggu)*", parse_mode='Markdown')
    try:
        counts = Counter(); off = 0; BATCH = 1000
        while True:
            res = supabase.table('kendaraan').select("finance").range(off, off+BATCH-1).execute()
            data = res.data; 
            if not data: break
            counts.update([str(d.get('finance')).strip().upper() if d.get('finance') else "UNKNOWN" for d in data])
            if len(data) < BATCH: break
            off += BATCH
            if off%50000==0: await msg.edit_text(f"⏳ *Scan: {off:,} data...*", parse_mode='Markdown')
        
        rpt = "🏦 **AUDIT LEASING**\n━━━━━━━━━━━━━━━━━━\n"
        for k,v in counts.most_common():
            if k not in ["UNKNOWN", "NONE", "NAN", "-"]: rpt += f"🔹 **{k}:** `{v:,}`\n"
        if counts["UNKNOWN"]>0: rpt += f"\n❓ **NO NAME:** `{counts['UNKNOWN']:,}`"
        
        if len(rpt)>4000: rpt=rpt[:4000]+"..."
        await msg.edit_text(rpt, parse_mode='Markdown')
    except: await msg.edit_text("❌ Error.")

async def set_info(update, context):
    global GLOBAL_INFO; 
    if update.effective_user.id==ADMIN_ID: GLOBAL_INFO = " ".join(context.args); await update.message.reply_text(f"✅ Info: {GLOBAL_INFO}")

async def del_info(update, context):
    global GLOBAL_INFO; 
    if update.effective_user.id==ADMIN_ID: GLOBAL_INFO = ""; await update.message.reply_text("🗑️ Info Deleted.")

async def add_agency(update, context):
    if update.effective_user.id==ADMIN_ID:
        try:
            a = update.message.text.split(); supabase.table('agencies').insert({"name": " ".join(a[1:-2]), "group_id": int(a[-2]), "admin_id": int(a[-1])}).execute()
            await update.message.reply_text("✅ Agency Added.")
        except: await update.message.reply_text("⚠️ Format Error.")

async def contact_admin(update, context):
    u=get_user(update.effective_user.id); 
    if u and context.args: await context.bot.send_message(ADMIN_ID, f"📩 **MITRA:** {u['nama_lengkap']}\n💬 {' '.join(context.args)}"); await update.message.reply_text("✅ Terkirim.")

async def test_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try: 
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text="🔔 **TES NOTIFIKASI GROUP OK!**"); 
        await update.message.reply_text("✅ Koneksi Group Log OK.")
    except Exception as e: 
        await update.message.reply_text(f"❌ Gagal kirim ke group: {e}")

async def panduan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text_panduan = (
        "📖 **PANDUAN PENGGUNAAN ONEASPAL**\n\n"
        "1️⃣ **Cari Data Kendaraan**\n"
        "   - Ketik Nopol secara lengkap atau sebagian.\n"
        "   - Contoh: `B 1234 ABC` atau `1234`\n\n"
        "2️⃣ **Upload File (Mitra)**\n"
        "   - Kirim file Excel/CSV/ZIP ke bot ini.\n"
        "   - Bot akan membaca otomatis.\n\n"
        "3️⃣ **Upload Satuan / Kiriman**\n"
        "   - Gunakan perintah `/tambah` untuk input data manual.\n"
        "   - Cocok untuk data kiriman harian.\n\n"
        "4️⃣ **Lapor Unit Selesai**\n"
        "   - Gunakan perintah `/lapor` jika unit sudah ditarik/selesai.\n\n"
        "5️⃣ **Cek Kuota**\n"
        "   - Ketik `/cekkuota` untuk melihat sisa HIT.\n\n"
        "6️⃣ **Bantuan Admin**\n"
        "   - Ketik `/admin [pesan]` untuk menghubungi support."
    )
    await update.message.reply_text(text_panduan, parse_mode='Markdown')

async def notify_hit_to_group(context: ContextTypes.DEFAULT_TYPE, user_data, vehicle_data):
    hp_raw = user_data.get('no_hp', '-')
    hp_wa = '62' + hp_raw[1:] if hp_raw.startswith('0') else hp_raw
    report_text = (
        f"🚨 **UNIT DITEMUKAN! (HIT)**\n━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Penemu:** {user_data.get('nama_lengkap')} ({user_data.get('agency')})\n"
        f"📍 **Kota:** {user_data.get('kota', '-')}\n\n"
        f"🚙 **Unit:** {vehicle_data.get('type', '-')}\n"
        f"🔢 **Nopol:** `{vehicle_data.get('nopol', '-')}`\n"
        f"📅 **Tahun:** {vehicle_data.get('tahun', '-')}\n"
        f"🎨 **Warna:** {vehicle_data.get('warna', '-')}\n"
        f"----------------------------------\n"
        f"🔧 **Noka:** `{vehicle_data.get('noka', '-')}`\n"
        f"⚙️ **Nosin:** `{vehicle_data.get('nosin', '-')}`\n"
        f"----------------------------------\n"
        f"⚠️ **OVD:** {vehicle_data.get('ovd', '-')}\n"
        f"🏦 **Finance:** {vehicle_data.get('finance', '-')}\n"
        f"🏢 **Branch:** {vehicle_data.get('branch', '-')}\n━━━━━━━━━━━━━━━━━━"
    )
    kb = [[InlineKeyboardButton("📞 Hubungi Penemu (WA)", url=f"https://wa.me/{hp_wa}")]]
    try: await context.bot.send_message(chat_id=LOG_GROUP_ID, text=report_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    except: pass


# ==============================================================================
# BAGIAN 9: FITUR USER - KUOTA & TOPUP
# ==============================================================================

async def cek_kuota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return await update.message.reply_text("⛔ Akses Ditolak.")
    msg = (f"💳 **INFO KUOTA**\n━━━━━━━━━━━━━━━━━━\n👤 **Nama:** {u.get('nama_lengkap')}\n🏢 **Agency:** {u.get('agency')}\n🔋 **SISA KUOTA:** `{u.get('quota', 0)}` HIT\n━━━━━━━━━━━━━━━━━━\n💡 _Kuota berkurang jika HIT._")
    await update.message.reply_text(msg, parse_mode='Markdown')

async def admin_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid, amt = context.args[0], int(context.args[1])
        if topup_quota(tid, amt)[0]: await update.message.reply_text(f"✅ Sukses Topup {amt} ke {tid}.")
        else: await update.message.reply_text("❌ Gagal.")
    except: await update.message.reply_text("⚠️ Format: `/topup ID JML`")

async def handle_photo_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    u = get_user(update.effective_user.id); 
    if not u: return
    await update.message.reply_text("✅ **Bukti diterima!** Sedang diverifikasi...", quote=True)
    msg = f"💰 **TOPUP REQUEST**\n👤 {u['nama_lengkap']}\n🆔 `{u['user_id']}`\n🔋 Saldo: {u.get('quota',0)}\n📝 {update.message.caption or '-'}"
    kb = [[InlineKeyboardButton("✅ 50", callback_data=f"topup_{u['user_id']}_50"), InlineKeyboardButton("✅ 100", callback_data=f"topup_{u['user_id']}_100")], [InlineKeyboardButton("❌ TOLAK", callback_data=f"topup_{u['user_id']}_rej")]]
    await context.bot.send_photo(ADMIN_ID, update.message.photo[-1].file_id, caption=msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')


# ==============================================================================
# BAGIAN 10: FITUR UPLOAD (SMART SYSTEM - FIX PROGRESS & REPORT)
# ==============================================================================

async def upload_start(update, context):
    uid = update.effective_user.id
    if not get_user(uid): return await update.message.reply_text("⛔ Akses Ditolak.")
    context.user_data['upload_file_id'] = update.message.document.file_id
    context.user_data['upload_file_name'] = update.message.document.file_name
    
    # ALUR USER BIASA
    if uid != ADMIN_ID:
        await update.message.reply_text("📄 File diterima.\n**Leasing apa?**", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
        return U_LEASING_USER
    
    # ALUR ADMIN - SMART SCAN
    msg = await update.message.reply_text("⏳ **Analisa File...**", parse_mode='Markdown')
    try:
        f = await update.message.document.get_file()
        c = await f.download_as_bytearray()
        df = read_file_robust(c, update.message.document.file_name)
        df = fix_header_position(df)
        df, found = smart_rename_columns(df)
        context.user_data['df_records'] = df.to_dict(orient='records')
        
        if 'nopol' not in df.columns: return await msg.edit_text("❌ Gagal deteksi NOPOL.")
        
        fin = 'finance' in df.columns
        await msg.delete()
        
        report = (
            f"✅ **SCAN SUKSES (v4.13)**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 **Kolom Dikenali:** {', '.join(found)}\n"
            f"📁 **Total Baris:** {len(df)}\n"
            f"🏦 **Kolom Leasing:** {'✅ ADA' if fin else '⚠️ TIDAK ADA'}\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"👉 **MASUKKAN NAMA LEASING UNTUK DATA INI:**\n"
            f"_(Ketik 'SKIP' jika ingin menggunakan kolom leasing dari file)_"
        )
        
        await update.message.reply_text(report, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["SKIP"], ["❌ BATAL"]], resize_keyboard=True))
        return U_LEASING_ADMIN
    except Exception as e: await msg.edit_text(f"❌ Error: {e}")
    return ConversationHandler.END

async def upload_leasing_user(update, context):
    nm = update.message.text
    if nm == "❌ BATAL": return await cancel(update, context)
    u = get_user(update.effective_user.id)
    await context.bot.send_document(ADMIN_ID, context.user_data['upload_file_id'], caption=f"📥 **UPLOAD MITRA**\n👤 {u['nama_lengkap']}\n🏦 {nm}")
    await update.message.reply_text("✅ Terkirim ke Admin.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def upload_leasing_admin(update, context):
    nm = update.message.text.upper(); df = pd.DataFrame(context.user_data['df_records'])
    fin = nm if nm != 'SKIP' else ("UNKNOWN" if 'finance' not in df.columns else "SESUAI FILE")
    if nm != 'SKIP': df['finance'] = fin
    elif 'finance' not in df.columns: df['finance'] = 'UNKNOWN'
    
    df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
    df = df.drop_duplicates(subset=['nopol'], keep='last').replace({np.nan: None})
    valid = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch']
    for c in valid: 
        if c not in df.columns: df[c] = None
    
    sample = df.iloc[0] 
    context.user_data['final_data_records'] = df[valid].to_dict(orient='records')
    
    # REVISI: Menambahkan kolom LEASING di preview
    preview_msg = (
        f"🔎 **PREVIEW DATA (v4.14)**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏦 **Mode:** {fin}\n"
        f"📊 **Total:** {len(df)} Data\n\n"
        f"📝 **SAMPEL DATA BARIS 1:**\n"
        f"🔹 Leasing: {sample['finance']}\n"  # <-- INI TAMBAHANNYA
        f"🔹 Nopol: `{sample['nopol']}`\n"
        f"🔹 Unit: {sample['type']}\n"
        f"🔹 Noka: {sample['noka']}\n"
        f"🔹 OVD: {sample['ovd']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Klik **EKSEKUSI** untuk lanjut."
    )
    await update.message.reply_text(preview_msg, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["🚀 EKSEKUSI", "❌ BATAL"]], one_time_keyboard=True))
    return U_CONFIRM_UPLOAD

async def upload_confirm_admin(update, context):
    if update.message.text != "🚀 EKSEKUSI": return await cancel(update, context)
    
    status_msg = await update.message.reply_text("⏳ **MEMULAI UPLOAD...**", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
    data = context.user_data.get('final_data_records')
    suc = 0; fail = 0; BATCH = 1000
    start_time = time.time()
    
    try:
        for i in range(0, len(data), BATCH):
            batch = data[i:i+BATCH]
            try: 
                supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
                suc+=len(batch)
            except: 
                for x in batch: 
                    try: supabase.table('kendaraan').upsert([x], on_conflict='nopol').execute(); suc+=1
                    except: fail+=1
            if (i+BATCH)%2000==0: 
                try: await status_msg.edit_text(f"⏳ **MENGUPLOAD...**\n✅ {i+BATCH}/{len(data)} data terproses...", parse_mode='HTML')
                except: pass
                await asyncio.sleep(0.1)

        duration = round(time.time() - start_time, 2)
        report = (
            f"✅ **UPLOAD SUKSES 100%!**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 **Total Data:** {suc}\n"
            f"❌ **Gagal:** {fail}\n"
            f"⏱ **Waktu:** {duration} detik\n"
            f"🚀 **Status:** Database Updated Successfully!"
        )
        try: await status_msg.edit_text(report, parse_mode='HTML')
        except: await update.message.reply_text(report, parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ **CRASH SAAT UPLOAD:**\n{str(e)}", parse_mode='Markdown')
    
    context.user_data.pop('final_data_records', None)
    return ConversationHandler.END


# ==============================================================================
# BAGIAN 11: HANDLER CONVERSATION (REG, ADD, LAPOR)
# ==============================================================================

# --- LAPOR ---
async def lapor_delete_start(update, context):
    if not get_user(update.effective_user.id): return
    await update.message.reply_text("🗑️ **LAPOR UNIT SELESAI/AMAN**\n\nAnda melaporkan unit sudah Selesai/Lunas.\nAdmin akan verifikasi.\n\n👉 Masukkan **Nopol**:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True), parse_mode='Markdown')
    return L_NOPOL
async def lapor_delete_check(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    n = update.message.text.upper().replace(" ", "")
    if not supabase.table('kendaraan').select("*").eq('nopol', n).execute().data: 
        await update.message.reply_text(f"❌ Nopol `{n}` tidak ditemukan.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
        return ConversationHandler.END
    context.user_data['lapor_nopol'] = n
    await update.message.reply_text(f"⚠️ Lapor Hapus `{n}`?", reply_markup=ReplyKeyboardMarkup([["✅ KIRIM LAPORAN", "❌ BATAL"]]), parse_mode='Markdown')
    return L_CONFIRM
async def lapor_delete_confirm(update, context):
    if update.message.text == "✅ KIRIM LAPORAN":
        n = context.user_data['lapor_nopol']; u = get_user(update.effective_user.id)
        await update.message.reply_text("✅ Laporan terkirim.", reply_markup=ReplyKeyboardRemove())
        kb = [[InlineKeyboardButton("✅ Setujui", callback_data=f"del_acc_{n}_{u['user_id']}"), InlineKeyboardButton("❌ Tolak", callback_data=f"del_rej_{u['user_id']}")]]
        await context.bot.send_message(ADMIN_ID, f"🗑️ **REQ HAPUS**\nNopol: `{n}`\nPelapor: {u['nama_lengkap']}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return ConversationHandler.END

# --- REGISTER ---
async def register_start(update, context):
    if get_user(update.effective_user.id): return await update.message.reply_text("✅ Terdaftar.")
    await update.message.reply_text("📝 **PENDAFTARAN MITRA**\n1️⃣ Nama Lengkap:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]])); return R_NAMA
async def register_nama(update, context): context.user_data['r_nama'] = update.message.text; await update.message.reply_text("2️⃣ No HP (WA):"); return R_HP
async def register_hp(update, context): context.user_data['r_hp'] = update.message.text; await update.message.reply_text("3️⃣ Email:"); return R_EMAIL
async def register_email(update, context): context.user_data['r_email'] = update.message.text; await update.message.reply_text("4️⃣ Kota:"); return R_KOTA
async def register_kota(update, context): context.user_data['r_kota'] = update.message.text; await update.message.reply_text("5️⃣ Agency:"); return R_AGENCY
async def register_agency(update, context): context.user_data['r_agency'] = update.message.text; await update.message.reply_text("✅ Kirim?", reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ ULANGI"]])); return R_CONFIRM
async def register_confirm(update, context):
    if update.message.text != "✅ KIRIM": return await cancel(update, context)
    d = {"user_id": update.effective_user.id, "nama_lengkap": context.user_data['r_nama'], "no_hp": context.user_data['r_hp'], "email": context.user_data['r_email'], "alamat": context.user_data['r_kota'], "agency": context.user_data['r_agency'], "quota": 1000, "status": "pending"}
    try:
        supabase.table('users').insert(d).execute()
        await update.message.reply_text("✅ **PENDAFTARAN BERHASIL!**\nTunggu verifikasi Admin.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
        kb = [[InlineKeyboardButton("✅ Terima", callback_data=f"appu_{d['user_id']}"), InlineKeyboardButton("❌ Tolak", callback_data=f"reju_{d['user_id']}")]]
        await context.bot.send_message(ADMIN_ID, f"🔔 **NEW USER**\n👤 {d['nama_lengkap']}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    except: await update.message.reply_text("❌ Gagal.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- TAMBAH MANUAL ---
async def add_data_start(update, context):
    if not get_user(update.effective_user.id): return
    await update.message.reply_text("➕ **TAMBAH UNIT**\n1️⃣ Nopol:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]])); return A_NOPOL
async def add_nopol(update, context): context.user_data['a_nopol'] = update.message.text.upper(); await update.message.reply_text("2️⃣ Type Mobil:"); return A_TYPE
async def add_type(update, context): context.user_data['a_type'] = update.message.text; await update.message.reply_text("3️⃣ Leasing:"); return A_LEASING
async def add_leasing(update, context): context.user_data['a_leasing'] = update.message.text; await update.message.reply_text("4️⃣ Ket (OVD):"); return A_NOKIR
async def add_nokir(update, context): context.user_data['a_nokir'] = update.message.text; await update.message.reply_text("✅ Kirim?", reply_markup=ReplyKeyboardMarkup([["✅ KIRIM", "❌ BATAL"]])); return A_CONFIRM
async def add_confirm(update, context):
    if update.message.text != "✅ KIRIM": return await cancel(update, context)
    n = context.user_data['a_nopol']
    context.bot_data[f"prop_{n}"] = {"nopol": n, "type": context.user_data['a_type'], "finance": context.user_data['a_leasing'], "ovd": context.user_data['a_nokir']}
    await update.message.reply_text("✅ Terkirim ke Admin.", reply_markup=ReplyKeyboardRemove())
    kb = [[InlineKeyboardButton("✅ Terima", callback_data=f"v_acc_{n}_{update.effective_user.id}"), InlineKeyboardButton("❌ Tolak", callback_data="v_rej")]]
    await context.bot.send_message(ADMIN_ID, f"📥 **DATA BARU**\nNopol: `{n}`", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return ConversationHandler.END

# --- HAPUS MANUAL ---
async def delete_unit_start(update, context):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🗑️ **HAPUS MANUAL**\nNopol:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]])); return D_NOPOL
async def delete_unit_check(update, context):
    if update.message.text == "❌ BATAL": return await cancel(update, context)
    n = update.message.text.upper().replace(" ", "")
    context.user_data['del_nopol'] = n; await update.message.reply_text(f"Hapus `{n}`?", reply_markup=ReplyKeyboardMarkup([["✅ YA, HAPUS", "❌ BATAL"]])); return D_CONFIRM
async def delete_unit_confirm(update, context):
    if update.message.text == "✅ YA, HAPUS": supabase.table('kendaraan').delete().eq('nopol', context.user_data['del_nopol']).execute(); await update.message.reply_text("✅ Terhapus.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ==============================================================================
# BAGIAN 12: MAIN HANDLER (SEARCH & CALLBACK)
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GLOBAL_INFO
    info = f"📢 <b>INFO:</b> {GLOBAL_INFO}\n━━━━━━━━━━━━━━━━━━\n\n" if GLOBAL_INFO else ""
    msg = (f"{info}🤖 <b>Selamat Datang di Oneaspalbot</b>\n\n<b>Salam Satu Aspal!</b> 👋\nHalo, Rekan Mitra Lapangan.\n\n<b>Oneaspalbot</b> adalah asisten digital profesional untuk mempermudah pencarian data kendaraan secara real-time.\n\nCari data melalui:\n✅ Nomor Polisi (Nopol)\n✅ Nomor Rangka (Noka)\n✅ Nomor Mesin (Nosin)\n\n⚠️ <b>PENTING:</b> Akses bersifat PRIVATE. Anda wajib mendaftar dan menunggu verifikasi Admin.\n\n--- 👉 Jalankan perintah /register untuk mendaftar.")
    await update.message.reply_text(msg, parse_mode=constants.ParseMode.HTML)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return
    if u.get('quota', 0) <= 0: return await update.message.reply_text("⛔ **KUOTA HABIS**\nHubungi Admin.", parse_mode='Markdown')
    
    kw = re.sub(r'[^a-zA-Z0-9]', '', update.message.text.upper())
    if len(kw) < 3: return await update.message.reply_text("⚠️ Minimal 3 karakter.")
    
    await context.bot.send_chat_action(update.effective_chat.id, constants.ChatAction.TYPING)
    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.ilike.%{kw}%,noka.eq.{kw},nosin.eq.{kw}").execute()
        if res.data:
            d = res.data[0]; update_quota_usage(u['user_id'], u['quota'])
            info = f"📢 **INFO:** {GLOBAL_INFO}\n━━━━━━━━━━━━━━━━━━\n" if GLOBAL_INFO else ""
            txt = (f"{info}✅ **DATA DITEMUKAN**\n━━━━━━━━━━━━━━━━━━\n🚙 **Unit:** {d.get('type','-')}\n🔢 **Nopol:** `{d.get('nopol','-')}`\n📅 **Tahun:** {d.get('tahun','-')}\n🎨 **Warna:** {d.get('warna','-')}\n----------------------------------\n🔧 **Noka:** `{d.get('noka','-')}`\n⚙️ **Nosin:** `{d.get('nosin','-')}`\n----------------------------------\n⚠️ **OVD:** {d.get('ovd', '-')}\n🏦 **Finance:** {d.get('finance', '-')}\n🏢 **Branch:** {d.get('branch', '-')}\n━━━━━━━━━━━━━━━━━━\n⚠️ **CATATAN PENTING:**\nIni bukan alat yang SAH untuk penarikan. Konfirmasi ke PIC leasing.")
            await update.message.reply_text(txt, parse_mode='Markdown')
            await notify_hit_to_group(context, u, d)
        else:
            info = f"📢 **INFO:** {GLOBAL_INFO}\n\n" if GLOBAL_INFO else ""
            await update.message.reply_text(f"{info}❌ **DATA TIDAK DITEMUKAN**\n`{kw}`", parse_mode='Markdown')
    except: await update.message.reply_text("❌ Error Database.")

async def cancel(update, context): await update.message.reply_text("🚫 Dibatalkan.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

async def callback_handler(update, context):
    q = update.callback_query; await q.answer(); d = q.data
    
    # --- ADMIN CONTROL PANEL (REVISI v4.13) ---
    if d.startswith("adm_topup_"):
        topup_quota(int(d.split("_")[2]), int(d.split("_")[3])); await q.edit_message_text("✅ Topup Sukses.")
    elif d == "close_panel":
        await q.delete_message()
    
    # --- STANDARD FITUR ---
    elif d.startswith("topup_"):
        parts = d.split("_"); uid = int(parts[1])
        if parts[2] == "rej": await context.bot.send_message(uid, "❌ Topup DITOLAK."); await q.edit_message_caption("❌ Ditolak.")
        else: topup_quota(uid, int(parts[2])); await context.bot.send_message(uid, f"✅ Topup {parts[2]} Berhasil."); await q.edit_message_caption("✅ Sukses.")
    elif d.startswith("appu_"): update_user_status(d.split("_")[1], 'active'); await q.edit_message_text("✅ User DISETUJUI."); await context.bot.send_message(d.split("_")[1], "🎉 **AKUN AKTIF!**")
    elif d.startswith("v_acc_"): 
        n=d.split("_")[2]; item=context.bot_data.get(f"prop_{n}"); supabase.table('kendaraan').upsert(item).execute(); await q.edit_message_text("✅ Masuk DB."); await context.bot.send_message(d.split("_")[3], f"✅ Data `{n}` Disetujui.")
    elif d == "v_rej": await q.edit_message_text("❌ Data Ditolak.")
    elif d.startswith("del_acc_"): supabase.table('kendaraan').delete().eq('nopol', d.split("_")[2]).execute(); await q.edit_message_text("✅ Dihapus."); await context.bot.send_message(d.split("_")[3], "✅ Laporan Disetujui.")
    elif d.startswith("del_rej_"): await q.edit_message_text("❌ Ditolak."); await context.bot.send_message(d.split("_")[2], "❌ Laporan Ditolak.")


# ==============================================================================
# BAGIAN 13: SYSTEM RUNNER (ENTRY POINT)
# ==============================================================================

if __name__ == '__main__':
    print("🚀 ONEASPAL BOT v4.13 (MASTERPIECE STANDARD) STARTING...")
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    
    # 1. ADMIN ACTION REASONING HANDLER (PRIORITAS TERTINGGI)
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_action_start, pattern='^adm_(ban|unban|del)_')], 
        states={ADMIN_ACT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_action_complete)]}, 
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]
    ))

    # 2. REJECT REGISTRATION REASONING
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(reject_start, pattern='^reju_')], 
        states={REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, reject_complete)]}, 
        fallbacks=[CommandHandler('cancel', cancel)]
    ))

    # 3. UPLOAD HANDLER
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Document.ALL, upload_start)], 
        states={
            U_LEASING_USER: [MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), upload_leasing_user)], 
            U_LEASING_ADMIN: [MessageHandler(filters.TEXT, upload_leasing_admin)], 
            U_CONFIRM_UPLOAD: [MessageHandler(filters.TEXT, upload_confirm_admin)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)], 
        allow_reentry=True
    ))

    # 4. REGISTER HANDLER
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('register', register_start)], 
        states={
            R_NAMA:[MessageHandler(filters.TEXT, register_nama)], 
            R_HP:[MessageHandler(filters.TEXT, register_hp)], 
            R_EMAIL:[MessageHandler(filters.TEXT, register_email)], 
            R_KOTA:[MessageHandler(filters.TEXT, register_kota)], 
            R_AGENCY:[MessageHandler(filters.TEXT, register_agency)], 
            R_CONFIRM:[MessageHandler(filters.TEXT, register_confirm)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel)]
    ))
    
    # 5. TAMBAH DATA HANDLER
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('tambah', add_data_start)],
        states={
            A_NOPOL:   [MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), add_nopol)],
            A_TYPE:    [MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), add_type)],
            A_LEASING: [MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), add_leasing)],
            A_NOKIR:   [MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), add_nokir)],
            A_CONFIRM: [MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), add_confirm)]
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]
    ))

    # 6. LAPOR HANDLER
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('lapor', lapor_delete_start)], 
        states={
            L_NOPOL:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), lapor_delete_check)], 
            L_CONFIRM:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), lapor_delete_confirm)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]
    ))
    
    # 7. HAPUS MANUAL HANDLER
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('hapus', delete_unit_start)], 
        states={
            D_NOPOL:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), delete_unit_check)], 
            D_CONFIRM:[MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), delete_unit_confirm)]
        }, 
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)]
    ))

    # COMMANDS
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('cekkuota', cek_kuota))
    app.add_handler(CommandHandler('topup', admin_topup))
    app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('leasing', get_leasing_list)) 
    app.add_handler(CommandHandler('users', list_users))
    # app.add_handler(CommandHandler('ban', ban_user)) # Disabled manual cmd
    # app.add_handler(CommandHandler('unban', unban_user)) 
    # app.add_handler(CommandHandler('delete', delete_user)) 
    app.add_handler(CommandHandler('testgroup', test_group)) 
    app.add_handler(CommandHandler('panduan', panduan))
    app.add_handler(CommandHandler('setinfo', set_info)) 
    app.add_handler(CommandHandler('delinfo', del_info)) 
    app.add_handler(CommandHandler('admin', contact_admin))
    app.add_handler(CommandHandler('addagency', add_agency)) 
    app.add_handler(CommandHandler('adminhelp', admin_help)) 
    
    # MEDIA & CALLBACKS
    app.add_handler(MessageHandler(filters.Regex(r'^/m_\d+$'), manage_user_panel))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_topup))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ BOT ONLINE! (v4.13 - Masterpiece Standard)")
    app.run_polling()