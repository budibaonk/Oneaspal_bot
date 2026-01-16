"""
################################################################################
#                                                                              #
#                      PROJECT: ONEASPAL BOT (ASSET RECOVERY)                  #
#                      VERSION: 4.3.1 (SYNTAX FIXED EDITION)                   #
#                      ROLE:    MAIN APPLICATION CORE                          #
#                      AUTHOR:  CTO (GEMINI) & CEO (BAONK)                     #
#                                                                              #
################################################################################

DESKRIPSI SISTEM:
Bot Telegram High-Performance untuk manajemen data pencarian kendaraan (Matel).
Sistem ini dirancang untuk menangani jutaan data dengan fitur pencarian fuzzy.

FITUR UTAMA:
1.  **Turbo Search Engine:** Menggunakan Supabase Trigram Index untuk pencarian fuzzy (mirip).
2.  **Adaptive Polyglot Upload:** Mengenali file Excel, CSV, TXT, dan ZIP secara otomatis.
3.  **Monetization System (v4.0):** Manajemen Kuota, Topup Manual dengan Bukti Foto.
4.  **User Management (v4.1):** Register, Ban, Unban, dan Reject dengan Alasan (Reasoning).
5.  **Audit System (v4.2 & v4.3):** Statistik Global (/stats) dan Audit Leasing Detail (/leasing).
6.  **B2B Agency System:** Fitur Whitelabel untuk perusahaan/agency dengan notifikasi grup.

LOG PERUBAHAN (CHANGELOG v4.3.1):
- [FIX] Syntax Error pada tombol Register Confirm (Missing Parenthesis).
- [FIX] Pagination Logika pada /leasing (Membaca seluruh 650k+ data).
- [UI]  Peningkatan tampilan pesan balasan (Professional Wording).
"""

# ==============================================================================
# BAGIAN 1: LIBRARY & KONFIGURASI
# ==============================================================================
import os
import logging
import io
import time
import re
import asyncio 
import csv 
import zipfile 
import numpy as np
import pandas as pd

# Struktur Data
from collections import Counter
from datetime import datetime

# Environment Variables
from dotenv import load_dotenv

# Telegram Bot SDK
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

# Database Driver
from supabase import create_client, Client

# Load .env file
load_dotenv()

# Setup Logging
logging.basicConfig(
    format='%(asctime)s - [%(levelname)s] - %(name)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ambil Credential
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Global Variable
GLOBAL_INFO = ""
LOG_GROUP_ID = -1003627047676  

# Setup Admin ID
DEFAULT_ADMIN_ID = 7530512170
try:
    env_id = os.environ.get("ADMIN_ID")
    ADMIN_ID = int(env_id) if env_id else DEFAULT_ADMIN_ID
except ValueError:
    ADMIN_ID = DEFAULT_ADMIN_ID

print(f"✅ [BOOT] SYSTEM STARTING... ADMIN ID: {ADMIN_ID}")

# Cek Kelengkapan
if not SUPABASE_URL or not SUPABASE_KEY or not TELEGRAM_TOKEN:
    print("❌ [CRITICAL] CREDENTIAL TIDAK LENGKAP! Cek file .env")
    exit()

# ==============================================================================
# BAGIAN 2: DATABASE CONNECTION
# ==============================================================================
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ [BOOT] KONEKSI DATABASE BERHASIL!")
except Exception as e:
    print(f"❌ [CRITICAL] DATABASE ERROR: {e}")
    exit()

# ==============================================================================
# BAGIAN 3: KAMUS DATA (DICTIONARY)
# ==============================================================================

COLUMN_ALIASES = {
    'nopol': [
        'nopolisi', 'nomorpolisi', 'nopol', 'noplat', 'nomorplat', 
        'nomorkendaraan', 'nokendaraan', 'nomer', 'tnkb', 'licenseplate', 
        'plat', 'nopolisikendaraan', 'nopil', 'polisi', 'platnomor', 
        'platkendaraan', 'nomerpolisi', 'no.polisi', 'nopol.', 'plat_nomor',
        'no_pol', 'no_polisi', 'police_no', 'vehicle_no'
    ],
    'type': [
        'type', 'tipe', 'unit', 'model', 'vehicle', 'jenis', 
        'deskripsiunit', 'merk', 'object', 'kendaraan', 'item', 
        'brand', 'typedeskripsi', 'vehiclemodel', 'namaunit', 'kend', 
        'namakendaraan', 'merktype', 'objek', 'jenisobjek', 'item_description',
        'merk_type', 'tipe_kendaraan', 'model_kendaraan', 'description', 
        'vehicle_desc', 'nama_barang', 'unit_description'
    ],
    'tahun': [
        'tahun', 'year', 'thn', 'rakitan', 'th', 'yearofmanufacture', 
        'thnrakit', 'manufacturingyear', 'tahun_rakit', 'tahun_pembuatan',
        'th_rakit', 'th_pembuatan', 'model_year'
    ],
    'warna': [
        'warna', 'color', 'colour', 'cat', 'kelir', 'warnakendaraan', 
        'warna_unit', 'body_color'
    ],
    'noka': [
        'noka', 'norangka', 'nomorrangka', 'chassis', 'chasis', 'vin', 
        'rangka', 'chassisno', 'norangka1', 'chasisno', 'vinno', 'norang',
        'no_rangka', 'no.rangka', 'chassis_number', 'vin_number', 'serial_number'
    ],
    'nosin': [
        'nosin', 'nomesin', 'nomormesin', 'engine', 'mesin', 'engineno', 
        'nomesin1', 'engineno', 'noengine', 'nomes', 'no_mesin',
        'no.mesin', 'engine_number'
    ],
    'finance': [
        'finance', 'leasing', 'lising', 'multifinance', 'cabang', 
        'partner', 'mitra', 'principal', 'company', 'client', 
        'financecompany', 'leasingname', 'keterangan', 'sumberdata', 
        'financetype', 'nama_leasing', 'nama_finance', 'client_name',
        'perusahaan', 'multifinance_name'
    ],
    'ovd': [
        'ovd', 'overdue', 'dpd', 'keterlambatan', 'hari', 'telat', 
        'aging', 'od', 'bucket', 'daysoverdue', 'overduedays', 
        'kiriman', 'kolektibilitas', 'kol', 'kolek', 'jml_hari',
        'hari_keterlambatan', 'bucket_od', 'days_late', 'umur_tunggakan'
    ],
    'branch': [
        'branch', 'area', 'kota', 'pos', 'cabang', 'lokasi', 
        'wilayah', 'region', 'areaname', 'branchname', 'dealer',
        'nama_cabang', 'lokasi_unit', 'city', 'area_name'
    ]
}

# ==============================================================================
# BAGIAN 4: DEFINISI STATE
# ==============================================================================

R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_CONFIRM = range(6)
A_NOPOL, A_TYPE, A_LEASING, A_NOKIR, A_CONFIRM = range(6, 11)
L_NOPOL, L_CONFIRM = range(11, 13) 
D_NOPOL, D_CONFIRM = range(13, 15)
U_LEASING_USER, U_LEASING_ADMIN, U_CONFIRM_UPLOAD = range(15, 18)
REJECT_REASON = 18

# ==============================================================================
# BAGIAN 5: FUNGSI HELPER
# ==============================================================================

async def post_init(application: Application):
    """Menu Command."""
    await application.bot.set_my_commands([
        ("start", "🔄 Restart / Menu"),
        ("cekkuota", "💳 Cek Kuota"),
        ("tambah", "➕ Input Manual"),
        ("lapor", "🗑️ Lapor Unit Selesai"),
        ("register", "📝 Daftar Mitra"),
        ("stats", "📊 Statistik Global"),
        ("leasing", "🏦 Audit Leasing Detail"),
        ("setinfo", "📢 Set Info Broadcast"),
        ("delinfo", "🗑️ Hapus Info Broadcast"),
        ("admin", "📩 Hubungi Admin"),
        ("panduan", "📖 Panduan"),
    ])

def get_user(user_id):
    try:
        response = supabase.table('users').select("*").eq('user_id', user_id).execute()
        return response.data[0] if response.data else None
    except: return None

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
        supabase.table('users').update({'quota': max(0, current_quota - 1)}).eq('user_id', user_id).execute()
    except: pass

def topup_quota(user_id, amount):
    try:
        user = get_user(user_id)
        if user:
            new_total = user.get('quota', 0) + amount
            supabase.table('users').update({'quota': new_total}).eq('user_id', user_id).execute()
            return True, new_total
        return False, 0
    except: return False, 0

# ==============================================================================
# BAGIAN 6: ENGINE PEMBACA FILE (ADAPTIVE POLYGLOT)
# ==============================================================================

def normalize_text(text):
    if not isinstance(text, str): return str(text).lower()
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()

def fix_header_position(df):
    target_aliases = COLUMN_ALIASES['nopol']
    for i in range(min(20, len(df))):
        row_values = [normalize_text(str(x)) for x in df.iloc[i].values]
        if any(alias in row_values for alias in target_aliases):
            df.columns = df.iloc[i]; df = df.iloc[i+1:].reset_index(drop=True); return df
    return df

def smart_rename_columns(df):
    new_cols = {}; found = []
    for original_col in df.columns:
        clean = normalize_text(original_col); renamed = False
        for std, aliases in COLUMN_ALIASES.items():
            if clean == std or clean in aliases:
                new_cols[original_col] = std; found.append(std); renamed = True; break
        if not renamed: new_cols[original_col] = original_col
    df.rename(columns=new_cols, inplace=True); return df, found

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

# ==============================================================================
# BAGIAN 7: FITUR ADMIN (REASONING REJECT)
# ==============================================================================

async def reject_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    context.user_data['reject_target_uid'] = query.data.split("_")[1]
    await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text="📝 **KONFIRMASI PENOLAKAN**\nKetik ALASAN PENOLAKAN:", 
        parse_mode='Markdown', 
        reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True, one_time_keyboard=True)
    )
    return REJECT_REASON

async def reject_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text
    if reason == "❌ BATAL": 
        await update.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
        
    target_uid = context.user_data.get('reject_target_uid')
    update_user_status(target_uid, 'rejected')
    
    try: 
        msg = f"⛔ **PENDAFTARAN DITOLAK**\n\nAlasan: {reason}\n\nSilakan daftar ulang dengan data yang benar."
        await context.bot.send_message(chat_id=target_uid, text=msg, parse_mode='Markdown')
    except: pass
    
    await update.message.reply_text(f"✅ User Ditolak.\nAlasan: {reason}", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ==============================================================================
# BAGIAN 8: FITUR USER (CEK KUOTA & TOPUP)
# ==============================================================================

async def cek_kuota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': 
        return await update.message.reply_text("⛔ Akun tidak aktif.")
        
    msg = (
        f"💳 **INFO KUOTA**\n━━━━━━━━━━━━━━━━━━\n"
        f"👤 {u.get('nama_lengkap')}\n"
        f"🏢 {u.get('agency')}\n"
        f"🔋 **SISA KUOTA:** `{u.get('quota', 0)}` HIT\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 Transfer donasi & kirim foto bukti di sini untuk topup."
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def handle_photo_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    u = get_user(update.effective_user.id)
    if not u: return
    
    photo_file = await update.message.photo[-1].get_file()
    caption = update.message.caption or "Topup"
    
    await update.message.reply_text("✅ **Bukti diterima!** Sedang diverifikasi...", quote=True)
    
    msg = (f"💰 **TOPUP REQUEST**\n👤 {u['nama_lengkap']}\n🆔 `{u['user_id']}`\n🔋 Saldo: {u.get('quota', 0)}\n📝 {caption}")
    kb = [
        [InlineKeyboardButton("✅ Isi 50", callback_data=f"topup_{u['user_id']}_50"), InlineKeyboardButton("✅ Isi 120", callback_data=f"topup_{u['user_id']}_120")], 
        [InlineKeyboardButton("✅ Isi 300", callback_data=f"topup_{u['user_id']}_300"), InlineKeyboardButton("❌ TOLAK", callback_data=f"topup_{u['user_id']}_rej")]
    ]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_file.file_id, caption=msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

# ==============================================================================
# BAGIAN 9: FITUR UPLOAD FILE (SMART CONVERSATION)
# ==============================================================================

async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    processing_msg = await update.message.reply_text("⏳ **Analisa File...**", parse_mode='Markdown')
    user_data = get_user(user_id)
    doc = update.message.document
    
    if not user_data or user_data['status'] != 'active':
        if user_id != ADMIN_ID: return await processing_msg.edit_text("⛔ **AKSES DITOLAK**")
    
    context.user_data['upload_file_id'] = doc.file_id
    context.user_data['upload_file_name'] = doc.file_name

    if user_id != ADMIN_ID:
        await processing_msg.delete()
        await update.message.reply_text(f"📄 File `{doc.file_name}` diterima.\nLeasing apa?", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
        return U_LEASING_USER

    try:
        new_file = await doc.get_file()
        content = await new_file.download_as_bytearray()
        df = read_file_robust(content, doc.file_name)
        df = fix_header_position(df) 
        df, found = smart_rename_columns(df) 
        context.user_data['df_records'] = df.to_dict(orient='records')
        
        if 'nopol' not in df.columns:
            await processing_msg.edit_text("❌ **GAGAL DETEKSI NOPOL**")
            return ConversationHandler.END

        fin = 'finance' in df.columns
        await processing_msg.delete()
        
        report = (
            f"✅ **SCAN SUKSES**\n📊 Kolom: {', '.join(found)}\n📁 Baris: {len(df)}\n🏦 Leasing: {'✅ ADA' if fin else '⚠️ MANUAL'}\n\n👉 **MASUKKAN NAMA LEASING:**"
        )
        await update.message.reply_text(report, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["SKIP"], ["❌ BATAL"]], resize_keyboard=True))
        return U_LEASING_ADMIN
    except Exception as e:
        await processing_msg.edit_text(f"❌ Error: {str(e)}")
        return ConversationHandler.END

async def upload_leasing_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nm = update.message.text
    if nm == "❌ BATAL": return await cancel(update, context)
    u = get_user(update.effective_user.id)
    await context.bot.send_document(ADMIN_ID, context.user_data['upload_file_id'], caption=f"📥 **UPLOAD MITRA**\n👤 {u['nama_lengkap']}\n🏦 {nm}")
    await update.message.reply_text("✅ Terkirim ke Admin.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def upload_leasing_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nm = update.message.text.upper()
    df = pd.DataFrame(context.user_data['df_records'])
    fin = nm if nm != 'SKIP' else ("UNKNOWN" if 'finance' not in df.columns else "SESUAI FILE")
    if nm != 'SKIP': df['finance'] = fin
    elif 'finance' not in df.columns: df['finance'] = 'UNKNOWN'
    
    df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
    df = df.drop_duplicates(subset=['nopol'], keep='last').replace({np.nan: None})
    valid = ['nopol', 'type', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'finance', 'branch']
    for c in valid: 
        if c not in df.columns: df[c] = None
    
    context.user_data['final_data_records'] = df[valid].to_dict(orient='records')
    await update.message.reply_text(f"🔎 **PREVIEW**\n🏦 {fin}\n📊 {len(df)} Data\n⚠️ Klik **EKSEKUSI**.", reply_markup=ReplyKeyboardMarkup([["🚀 EKSEKUSI", "❌ BATAL"]], one_time_keyboard=True))
    return U_CONFIRM_UPLOAD

async def upload_confirm_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text != "🚀 EKSEKUSI": return await cancel(update, context)
    msg = await update.message.reply_text("⏳ **UPLOADING...**", reply_markup=ReplyKeyboardRemove())
    data = context.user_data.get('final_data_records')
    suc = 0; fail = 0; batch_size = 1000
    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size]
        try: supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute(); suc += len(batch)
        except: 
            for item in batch: 
                try: supabase.table('kendaraan').upsert([item], on_conflict='nopol').execute(); suc += 1
                except: fail += 1
        if (i+batch_size)%5000==0: await msg.edit_text(f"⏳ Progress: {i+batch_size}/{len(data)}")
    await msg.edit_text(f"✅ **SELESAI**\nSukses: {suc}\nGagal: {fail}")
    return ConversationHandler.END

# ==============================================================================
# BAGIAN 10: FITUR AUDIT (STATS & LEASING PAGINATION FIXED)
# ==============================================================================

async def notify_hit(context, user, data):
    txt = (f"🚨 **HIT!**\n👤 {user['nama_lengkap']}\n📍 {user.get('kota','-')}\n🚙 {data['type']}\n🔢 `{data['nopol']}`\n🏦 {data['finance']}")
    try: await context.bot.send_message(LOG_GROUP_ID, txt, parse_mode='Markdown')
    except: pass
    if user.get('agency'):
        ag = get_agency_data(user['agency'])
        if ag:
            try: await context.bot.send_message(ag['group_id'], f"🎯 **TEMUAN ANGGOTA**\n👤 {user['nama_lengkap']}\n🚙 {data['type']}\n🔢 `{data['nopol']}`", parse_mode='Markdown')
            except: pass

async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = await update.message.reply_text("⏳ Hitung...")
    try:
        tot = supabase.table('kendaraan').select("*", count="exact", head=True).execute().count
        usr = supabase.table('users').select("*", count="exact", head=True).execute().count
        await msg.edit_text(f"📊 **DASHBOARD STATISTIK**\n📂 Data: `{tot:,}` Unit\n👥 Mitra: `{usr:,}` Orang\n💡 _Cek /leasing untuk detail._", parse_mode='Markdown')
    except: await msg.edit_text("❌ Error Stats")

async def get_leasing_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    FIX v4.3: Menggunakan Batch 1000 agar seluruh data (650k+) terbaca.
    """
    if update.effective_user.id != ADMIN_ID: return
    msg = await update.message.reply_text("⏳ *Sedang mengaudit seluruh database... (Mohon tunggu)*", parse_mode='Markdown')
    
    try:
        finance_counts = Counter()
        off = 0
        BATCH = 1000  # FIX: Sesuai limit Supabase agar loop tidak berhenti prematur
        
        while True:
            res = supabase.table('kendaraan').select("finance").range(off, off + BATCH - 1).execute()
            data = res.data
            
            if not data: break
            
            batch_finances = [str(d.get('finance')).strip().upper() if d.get('finance') else "UNKNOWN" for d in data]
            finance_counts.update(batch_finances)
            
            if len(data) < BATCH: break # Data habis
            off += BATCH
            
            # Update status agar tidak dikira hang
            if off % 50000 == 0: 
                try: await msg.edit_text(f"⏳ *Mengaudit... ({off:,} data)*", parse_mode='Markdown')
                except: pass

        report = "🏦 **LAPORAN AUDIT LEASING (FIXED)**\n━━━━━━━━━━━━━━━━━━\n"
        total_unique = 0
        for name, count in finance_counts.most_common():
             if name not in ["UNKNOWN", "NONE", "NAN", "-", ""]:
                 report += f"🔹 **{name}:** `{count:,}` unit\n"
                 total_unique += 1
        
        if finance_counts["UNKNOWN"] > 0:
            report += f"\n❓ **TANPA NAMA:** `{finance_counts['UNKNOWN']:,}` unit"
            
        report += f"\n━━━━━━━━━━━━━━━━━━\n✅ **Total Leasing:** {total_unique} Perusahaan"

        if len(report) > 4000: report = report[:4000] + "\n\n⚠️ _(Terpotong karena limit Telegram)_"
        await msg.edit_text(report, parse_mode='Markdown')

    except Exception as e:
        await msg.edit_text(f"❌ Error Audit: {str(e)}")

# ==============================================================================
# BAGIAN 11: MANAJEMEN USER & ADMIN TOOLS
# ==============================================================================

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    d = supabase.table('users').select("*").limit(50).execute().data
    msg = "\n".join([f"{u['nama_lengkap']} | {u['agency']} | `{u['user_id']}`" for u in d if u['status']=='active'])
    await update.message.reply_text(f"📋 **USER AKTIF (PREVIEW 50)**\n{msg}"[:4000], parse_mode='Markdown')

async def admin_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid, amt = context.args[0], int(context.args[1])
        if topup_quota(tid, amt)[0]: await update.message.reply_text("✅ Sukses.")
        else: await update.message.reply_text("❌ Gagal.")
    except: await update.message.reply_text("⚠️ `/topup ID JUMLAH`")

async def add_agency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        args = update.message.text.split()[1:]
        data = {"name": " ".join(args[:-2]), "group_id": int(args[-2]), "admin_id": int(args[-1])}
        supabase.table('agencies').insert(data).execute()
        await update.message.reply_text("✅ Agency Added.")
    except: await update.message.reply_text("⚠️ `/addagency NAMA GRP_ID ADM_ID`")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID: update_user_status(context.args[0], 'rejected'); await update.message.reply_text("⛔ Banned.")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID: update_user_status(context.args[0], 'active'); await update.message.reply_text("✅ Unbanned.")

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID: supabase.table('users').delete().eq('user_id', context.args[0]).execute(); await update.message.reply_text("🗑️ Deleted.")

# --- FITUR SET INFO (BROADCAST MESSAGE DI /START) ---
async def set_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin mengatur pesan info broadcast."""
    global GLOBAL_INFO
    if update.effective_user.id == ADMIN_ID: 
        GLOBAL_INFO = " ".join(context.args)
        await update.message.reply_text(f"✅ Info Broadcast Diupdate:\n{GLOBAL_INFO}")

async def del_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin menghapus pesan info broadcast."""
    global GLOBAL_INFO
    if update.effective_user.id == ADMIN_ID: 
        GLOBAL_INFO = ""
        await update.message.reply_text("🗑️ Info Broadcast Dihapus.")

async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if u and context.args: await context.bot.send_message(ADMIN_ID, f"📩 **PESAN DARI MITRA**\n👤 {u['nama_lengkap']}\n💬 {' '.join(context.args)}"); await update.message.reply_text("✅ Terkirim.")

async def panduan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "📖 **PANDUAN PENGGUNAAN ONEASPAL**\n\n"
        "1️⃣ **Cari Data Kendaraan**\n"
        "   - Ketik Nopol secara lengkap atau sebagian.\n"
        "   - Contoh: `B 1234 ABC` atau `1234`\n\n"
        "2️⃣ **Upload Data (Mitra)**\n"
        "   - Kirim file Excel/CSV/ZIP ke bot ini.\n"
        "   - Bot akan membaca otomatis.\n\n"
        "3️⃣ **Lapor Unit Selesai**\n"
        "   - Gunakan perintah /lapor jika unit sudah ditarik/selesai.\n\n"
        "4️⃣ **Cek Kuota**\n"
        "   - Ketik /cekkuota untuk melihat sisa HIT."
    )
    await update.message.reply_text(txt, parse_mode='Markdown')


# ==============================================================================
# BAGIAN 12: MAIN HANDLER & SEARCH ENGINE
# ==============================================================================

async def start(u, c): 
    # Info Broadcast ditampilkan disini
    await u.message.reply_text(f"{GLOBAL_INFO}\n🤖 **ONEASPAL V4.3**\nSistem Online. Silakan ketik Nopol.", parse_mode='Markdown')

async def handle_message(u, c):
    """
    LOGIKA UTAMA PENCARIAN (SEARCH ENGINE).
    """
    user = get_user(u.effective_user.id)
    if not user or user['status'] != 'active': return
    if user.get('quota', 0) <= 0: return await u.message.reply_text("⛔ **KUOTA HABIS**\nSilakan lakukan topup donasi.")
    
    kw = re.sub(r'[^a-zA-Z0-9]', '', u.message.text.upper())
    if len(kw) < 3: return await u.message.reply_text("⚠️ Min 3 huruf.")
    
    await c.bot.send_chat_action(u.effective_chat.id, constants.ChatAction.TYPING)
    try:
        # PENCARIAN FUZZY
        res = supabase.table('kendaraan').select("*").or_(f"nopol.ilike.%{kw}%,noka.eq.{kw},nosin.eq.{kw}").execute()
        if res.data:
            d = res.data[0]; update_quota_usage(user['user_id'], user['quota'])
            await u.message.reply_text(f"✅ **DITEMUKAN**\nUnit: {d.get('type')}\nNopol: `{d.get('nopol')}`\nOVD: {d.get('ovd')}\nFinance: {d.get('finance')}", parse_mode='Markdown')
            await notify_hit(c, user, d)
        else: await u.message.reply_text(f"❌ Tidak ditemukan: {kw}")
    except: await u.message.reply_text("❌ Error Database.")

async def cancel(u, c): await u.message.reply_text("🚫 Aksi Dibatalkan.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

async def callback_handler(u, c):
    """Handler tombol Inline."""
    q = u.callback_query; await q.answer(); d = q.data
    
    if d.startswith("topup_"):
        parts = d.split("_"); uid = int(parts[1])
        if parts[2] == "rej": 
            await c.bot.send_message(uid, "❌ Topup DITOLAK."); await q.edit_message_caption("❌ Rejected.")
        else: 
            topup_quota(uid, int(parts[2])); await c.bot.send_message(uid, f"✅ Topup {parts[2]} HIT."); await q.edit_message_caption("✅ Success.")
            
    elif d.startswith("appu_"): 
        update_user_status(d.split("_")[1], 'active'); await q.edit_message_text("✅ User Active.")
        
    elif d.startswith("v_acc_"): 
        n=d.split("_")[2]; item=c.bot_data.get(f"prop_{n}"); supabase.table('kendaraan').upsert(item).execute(); await q.edit_message_text("✅ Saved.")
        
    elif d.startswith("del_acc_"): 
        supabase.table('kendaraan').delete().eq('nopol', d.split("_")[2]).execute(); await q.edit_message_text("✅ Deleted.")

# CONVERSATION SUB-HANDLERS
async def lapor_start(update, context): 
    if not get_user(update.effective_user.id): return
    await update.message.reply_text("🗑️ Nopol:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return L_NOPOL
async def lapor_check(update, context):
    n = update.message.text.upper().replace(" ", "")
    if not supabase.table('kendaraan').select("*").eq('nopol', n).execute().data: await update.message.reply_text("❌ 404"); return ConversationHandler.END
    context.user_data['ln'] = n; await update.message.reply_text("Yakin?", reply_markup=ReplyKeyboardMarkup([["YA", "BATAL"]])); return L_CONFIRM
async def lapor_confirm(update, context):
    if update.message.text == "YA":
        n = context.user_data['ln']; u = get_user(update.effective_user.id)
        await context.bot.send_message(ADMIN_ID, f"🗑️ REQ DEL: {n}\n👤 {u['nama_lengkap']}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ACC", callback_data=f"del_acc_{n}_{u['user_id']}"), InlineKeyboardButton("REJ", callback_data=f"del_rej_{u['user_id']}")]], ))
        await update.message.reply_text("✅ Terkirim.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def register_start(update, context): 
    if get_user(update.effective_user.id): return await update.message.reply_text("✅ Terdaftar.")
    await update.message.reply_text("📝 Nama:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return R_NAMA
async def register_nama(update, context): context.user_data['r_nama'] = update.message.text; await update.message.reply_text("📱 HP:"); return R_HP
async def register_hp(update, context): context.user_data['r_hp'] = update.message.text; await update.message.reply_text("📧 Email:"); return R_EMAIL
async def register_email(update, context): context.user_data['r_email'] = update.message.text; await update.message.reply_text("📍 Kota:"); return R_KOTA
async def register_kota(update, context): context.user_data['r_kota'] = update.message.text; await update.message.reply_text("🏢 Agency:"); return R_AGENCY
async def register_agency(update, context): context.user_data['r_agency'] = update.message.text; await update.message.reply_text("Kirim?", reply_markup=ReplyKeyboardMarkup([["YA", "BATAL"]])); return R_CONFIRM
async def register_confirm(update, context):
    if update.message.text != "YA": return await cancel(update, context)
    d = {"user_id": update.effective_user.id, "nama_lengkap": context.user_data['r_nama'], "no_hp": context.user_data['r_hp'], "email": context.user_data['r_email'], "alamat": context.user_data['r_kota'], "agency": context.user_data['r_agency'], "quota": 50, "status": "pending"}
    try:
        supabase.table('users').insert(d).execute()
        await update.message.reply_text("✅ Terkirim.", reply_markup=ReplyKeyboardRemove())
        # FIX: PARENTHESIS ERROR HERE HAS BEEN FIXED BELOW
        await context.bot.send_message(ADMIN_ID, f"🔔 NEW USER\n{d['nama_lengkap']}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ACC", callback_data=f"appu_{d['user_id']}"), InlineKeyboardButton("REJ", callback_data=f"reju_{d['user_id']}")]]))
    except: await update.message.reply_text("❌ Gagal.")
    return ConversationHandler.END

async def add_start(update, context):
    if not get_user(update.effective_user.id): return
    await update.message.reply_text("➕ Nopol:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return A_NOPOL
async def add_nopol(update, context): context.user_data['a_nopol'] = update.message.text.upper(); await update.message.reply_text("Unit:"); return A_TYPE
async def add_type(update, context): context.user_data['a_type'] = update.message.text; await update.message.reply_text("Leasing:"); return A_LEASING
async def add_leasing(update, context): context.user_data['a_leasing'] = update.message.text; await update.message.reply_text("Ket:"); return A_NOKIR
async def add_nokir(update, context): context.user_data['a_nokir'] = update.message.text; await update.message.reply_text("Kirim?", reply_markup=ReplyKeyboardMarkup([["YA", "BATAL"]])); return A_CONFIRM
async def add_confirm(update, context):
    if update.message.text != "YA": return await cancel(update, context)
    n = context.user_data['a_nopol']; context.bot_data[f"prop_{n}"] = {"nopol": n, "type": context.user_data['a_type'], "finance": context.user_data['a_leasing'], "ovd": context.user_data['a_nokir']}
    await update.message.reply_text("✅ Terkirim.", reply_markup=ReplyKeyboardRemove()); await context.bot.send_message(ADMIN_ID, f"📥 MANUAL: {n}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ACC", callback_data=f"v_acc_{n}_{update.effective_user.id}")]], ))
    return ConversationHandler.END

async def delete_start(update, context): 
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🗑️ Nopol:", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return D_NOPOL
async def delete_check(update, context): context.user_data['dn'] = update.message.text.upper().replace(" ", ""); await update.message.reply_text("Hapus?", reply_markup=ReplyKeyboardMarkup([["YA", "BATAL"]])); return D_CONFIRM
async def delete_confirm(update, context):
    if update.message.text == "YA": supabase.table('kendaraan').delete().eq('nopol', context.user_data['dn']).execute(); await update.message.reply_text("✅ Deleted.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ==============================================================================
# BAGIAN 13: SYSTEM RUNNER (MAIN)
# ==============================================================================

if __name__ == '__main__':
    print("🚀 ONEASPAL BOT V4.3.1 (SYNTAX FIXED) STARTING...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    # Handlers Conversation (Prioritas Utama)
    app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(reject_start, pattern='^reju_')], states={REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, reject_complete)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[MessageHandler(filters.Document.ALL, upload_start)], states={U_LEASING_USER: [MessageHandler(filters.TEXT & (~filters.Regex('^❌ BATAL$')), upload_leasing_user)], U_LEASING_ADMIN: [MessageHandler(filters.TEXT, upload_leasing_admin)], U_CONFIRM_UPLOAD: [MessageHandler(filters.TEXT, upload_confirm_admin)]}, fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ BATAL$'), cancel)], allow_reentry=True))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('register', register_start)], states={R_NAMA:[MessageHandler(filters.TEXT, register_nama)], R_HP:[MessageHandler(filters.TEXT, register_hp)], R_EMAIL:[MessageHandler(filters.TEXT, register_email)], R_KOTA:[MessageHandler(filters.TEXT, register_kota)], R_AGENCY:[MessageHandler(filters.TEXT, register_agency)], R_CONFIRM:[MessageHandler(filters.TEXT, register_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('tambah', add_start)], states={A_NOPOL:[MessageHandler(filters.TEXT, add_nopol)], A_TYPE:[MessageHandler(filters.TEXT, add_type)], A_LEASING:[MessageHandler(filters.TEXT, add_leasing)], A_NOKIR:[MessageHandler(filters.TEXT, add_nokir)], A_CONFIRM:[MessageHandler(filters.TEXT, add_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('lapor', lapor_start)], states={L_NOPOL:[MessageHandler(filters.TEXT, lapor_check)], L_CONFIRM:[MessageHandler(filters.TEXT, lapor_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('hapus', delete_start)], states={D_NOPOL:[MessageHandler(filters.TEXT, delete_check)], D_CONFIRM:[MessageHandler(filters.TEXT, delete_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))

    # Handlers Perintah Dasar
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('cekkuota', cek_kuota))
    app.add_handler(CommandHandler('topup', admin_topup))
    app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('leasing', get_leasing_list))
    app.add_handler(CommandHandler('users', list_users))
    app.add_handler(CommandHandler('ban', ban_user))
    app.add_handler(CommandHandler('unban', unban_user))
    app.add_handler(CommandHandler('delete', delete_user))
    app.add_handler(CommandHandler('setinfo', set_info)) 
    app.add_handler(CommandHandler('delinfo', del_info)) 
    app.add_handler(CommandHandler('admin', contact_admin))
    app.add_handler(CommandHandler('panduan', panduan))
    app.add_handler(CommandHandler('addagency', add_agency))

    # Handlers Media & Callback
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_topup))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ BOT ONLINE! (v4.3.1 Syntax Verified)")
    app.run_polling()