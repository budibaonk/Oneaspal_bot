import os
import logging
import pandas as pd
import io
import numpy as np
import time
import re
import asyncio 
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, constants
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

# ==============================================================================
#                        1. KONFIGURASI SISTEM
# ==============================================================================

load_dotenv()
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
token: str = os.environ.get("TELEGRAM_TOKEN")

GLOBAL_INFO = ""
LOG_GROUP_ID = -1003627047676  

DEFAULT_ADMIN_ID = 7530512170
try:
    env_id = os.environ.get("ADMIN_ID")
    ADMIN_ID = int(env_id) if env_id else DEFAULT_ADMIN_ID
except ValueError:
    ADMIN_ID = DEFAULT_ADMIN_ID

print(f"✅ ADMIN ID: {ADMIN_ID}")

if not url or not key or not token:
    print("❌ ERROR: Cek .env (Credential Kosong)")
    exit()

try:
    supabase: Client = create_client(url, key)
except Exception as e:
    print(f"❌ Gagal koneksi Supabase: {e}")
    exit()

# ==============================================================================
#                        2. KAMUS DATA (NORMALISASI AGRESIF)
# ==============================================================================

# KAMUS ALIAS (Tanpa Spasi/Simbol)
COLUMN_ALIASES = {
    'nopol': ['nopolisi', 'nomorpolisi', 'nopol', 'noplat', 'nomorplat', 'nomorkendaraan', 'nokendaraan', 'nomer', 'tnkb', 'licenseplate', 'plat'],
    'type': ['type', 'tipe', 'unit', 'model', 'vehicle', 'jenis', 'deskripsiunit', 'merk', 'object', 'kendaraan', 'item', 'brand'],
    'tahun': ['tahun', 'year', 'thn', 'rakitan', 'th', 'yearofmanufacture'],
    'warna': ['warna', 'color', 'colour', 'cat', 'kelir'],
    'noka': ['noka', 'norangka', 'nomorrangka', 'chassis', 'chasis', 'vin', 'rangka', 'chassisno'],
    'nosin': ['nosin', 'nomesin', 'nomormesin', 'engine', 'mesin', 'engineno'],
    'finance': ['finance', 'leasing', 'lising', 'multifinance', 'cabang', 'partner', 'mitra', 'principal', 'company', 'client'],
    'ovd': ['ovd', 'overdue', 'dpd', 'keterlambatan', 'hari', 'telat', 'aging', 'od', 'bucket', 'daysoverdue'],
    'branch': ['branch', 'area', 'kota', 'pos', 'cabang', 'lokasi', 'wilayah', 'region', 'areaname']
}

# --- STATE CONVERSATION ---
R_NAMA, R_HP, R_EMAIL, R_KOTA, R_AGENCY, R_CONFIRM = range(6)
A_NOPOL, A_TYPE, A_LEASING, A_NOKIR, A_CONFIRM = range(6, 11)
L_NOPOL, L_CONFIRM = range(11, 13) 
D_NOPOL, D_CONFIRM = range(13, 15)
U_LEASING_USER, U_LEASING_ADMIN, U_CONFIRM_UPLOAD = range(15, 18)

# ==============================================================================
#                        3. HELPER FUNCTIONS
# ==============================================================================

async def post_init(application: Application):
    await application.bot.set_my_commands([
        ("start", "🔄 Restart / Menu Utama"), ("cekkuota", "💳 Cek Sisa Kuota"), 
        ("tambah", "➕ Tambah Unit Manual"), ("lapor", "🗑️ Lapor Unit Selesai"), 
        ("register", "📝 Daftar Mitra Baru"), ("admin", "📩 Hubungi Admin"), ("panduan", "📖 Petunjuk Penggunaan")
    ])

def get_user(user_id):
    try:
        res = supabase.table('users').select("*").eq('user_id', user_id).execute()
        return res.data[0] if res.data else None
    except: return None

def update_user_status(user_id, status):
    try: supabase.table('users').update({'status': status}).eq('user_id', user_id).execute()
    except: pass

def update_quota_usage(user_id, current_quota):
    try: supabase.table('users').update({'quota': current_quota - 1}).eq('user_id', user_id).execute()
    except: pass

def topup_quota(user_id, amount):
    try:
        u = get_user(user_id)
        if u:
            new = u.get('quota', 0) + amount
            supabase.table('users').update({'quota': new}).eq('user_id', user_id).execute()
            return True, new
        return False, 0
    except: return False, 0

def normalize_text(text):
    if not isinstance(text, str): return str(text).lower()
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()

def smart_rename_columns(df):
    new_cols = {}
    found_cols = []
    for original_col in df.columns:
        clean_col = normalize_text(original_col)
        renamed = False
        for standard_name, aliases in COLUMN_ALIASES.items():
            if clean_col == standard_name or clean_col in aliases:
                new_cols[original_col] = standard_name
                found_cols.append(standard_name)
                renamed = True
                break
        if not renamed: new_cols[original_col] = original_col
    df.rename(columns=new_cols, inplace=True)
    return df, found_cols

def read_file_robust(file_content, file_name):
    """Mencoba berbagai cara baca file Excel/CSV"""
    if file_name.lower().endswith('.xlsx'):
        return pd.read_excel(io.BytesIO(file_content), dtype=str)
    
    encodings = ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']
    separators = [';', ',', '\t']
    
    for enc in encodings:
        for sep in separators:
            try:
                file_stream = io.BytesIO(file_content)
                df = pd.read_csv(file_stream, sep=sep, dtype=str, encoding=enc)
                if len(df.columns) > 1: return df
            except: continue
                
    try: return pd.read_csv(io.BytesIO(file_content), sep=None, engine='python', dtype=str)
    except Exception as e: raise e

# ==============================================================================
#                 4. FITUR UTAMA (UPLOAD, QUOTA, ADMIN)
# ==============================================================================

async def cek_kuota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return await update.message.reply_text("⛔ Akun belum aktif.")
    msg = (f"💳 **INFO AKUN MITRA**\n━━━━━━━━━━━━━━━━━━\n👤 **Nama:** {u.get('nama_lengkap')}\n🏢 **Agency:** {u.get('agency')}\n📱 **ID:** `{u.get('user_id')}`\n━━━━━━━━━━━━━━━━━━\n🔋 **SISA KUOTA:** `{u.get('quota', 0)}` HIT\n━━━━━━━━━━━━━━━━━━")
    await update.message.reply_text(msg, parse_mode='Markdown')

async def admin_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        tid, amt = context.args[0], int(context.args[1])
        succ, bal = topup_quota(tid, amt)
        if succ: 
            await update.message.reply_text(f"✅ **TOPUP SUKSES**\nTarget: `{tid}`\nJumlah: +{amt}\nTotal: {bal}", parse_mode='Markdown')
            try: await context.bot.send_message(tid, f"🎉 **KUOTA BERTAMBAH!**\nAdmin menambah +{amt} kuota.\nTotal: {bal}")
            except: pass
        else: await update.message.reply_text("❌ User tidak ditemukan.")
    except: await update.message.reply_text("⚠️ Format: `/topup [ID] [JUMLAH]`")

# --- SMART UPLOAD (NUCLEAR FIX) ---
async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    doc = update.message.document
    
    if not user_data or user_data['status'] != 'active':
        if user_id != ADMIN_ID: return await update.message.reply_text("⛔ Akses Ditolak.")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.UPLOAD_DOCUMENT)
    context.user_data['upl_fid'] = doc.file_id
    context.user_data['upl_name'] = doc.file_name

    if user_id != ADMIN_ID:
        await update.message.reply_text(f"📄 File diterima.\n\n**Ini data Leasing apa?**", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True))
        return U_LEASING_USER
    else:
        msg = await update.message.reply_text("⏳ **Membaca file (Mode: Robust)...**")
        try:
            f = await doc.get_file(); content = await f.download_as_bytearray()
            df = read_file_robust(content, doc.file_name)
            df, found = smart_rename_columns(df)
            context.user_data['df_rec'] = df.to_dict(orient='records')
            
            if 'nopol' not in df.columns:
                detected = ", ".join(df.columns[:5])
                await msg.edit_text(f"❌ **GAGAL DETEKSI NOPOL**\nKolom terbaca: {detected}\n\nPastikan ada kolom: 'No Polisi' / 'Plat'.")
                return ConversationHandler.END

            has_fin = 'finance' in df.columns
            txt = (f"✅ **SMART SCAN SUKSES**\n━━━━━━━━━━━━━━━━━━\n📊 **Kolom:** {', '.join(found)}\n📁 **Baris:** {len(df)}\n🏦 **Leasing:** {'✅ ADA' if has_fin else '⚠️ TIDAK'}\n━━━━━━━━━━━━━━━━━━\n👉 **Masukkan Nama Leasing (atau SKIP):**")
            await msg.edit_text(txt, parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
            return U_LEASING_ADMIN
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}"); return ConversationHandler.END

async def upload_leasing_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nm = update.message.text
    if nm == "❌ BATAL": return await cancel(update, context)
    fid, fname = context.user_data['upl_fid'], context.user_data['upl_name']
    u = get_user(update.effective_user.id)
    cap = f"📥 **FILE MITRA**\n👤 {u['nama_lengkap']}\n🏦 {nm}\n📄 {fname}"
    await context.bot.send_document(ADMIN_ID, fid, caption=cap); await update.message.reply_text("✅ Terkirim ke Admin.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def upload_leasing_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nm = update.message.text.upper()
    df = pd.DataFrame(context.user_data['df_rec'])
    
    if nm != 'SKIP': df['finance'] = nm
    elif 'finance' not in df.columns: df['finance'] = 'UNKNOWN'
    else: nm = "SESUAI FILE"
    
    df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
    df = df.drop_duplicates(['nopol'], keep='last').replace({np.nan: None})
    
    valid = ['nopol','type','tahun','warna','noka','nosin','ovd','finance','branch']
    for c in valid: 
        if c not in df.columns: df[c] = None
    
    sample = df.iloc[0]
    context.user_data['final_data'] = df[valid].to_dict('records')
    context.user_data['final_leasing'] = nm
    
    txt = (
        f"🔎 **PREVIEW DATA**\n━━━━━━━━━━━━━━━━━━\n🏦 **Leasing:** {nm}\n📊 **Total:** {len(df)}\n\n"
        f"📝 **CONTOH BARIS 1:**\n🔹 Nopol: `{sample['nopol']}`\n🔹 Unit: {sample['type']}\n🔹 Noka: {sample['noka']}\n"
        f"━━━━━━━━━━━━━━━━━━\n⚠️ Klik **EKSEKUSI** jika data benar."
    )
    await update.message.reply_text(txt, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([["🚀 EKSEKUSI", "❌ BATAL"]], one_time_keyboard=True))
    return U_CONFIRM_UPLOAD

async def upload_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text != "🚀 EKSEKUSI": return await cancel(update, context)
    msg = await update.message.reply_text("⏳ **Mengupload...**", reply_markup=ReplyKeyboardRemove())
    data = context.user_data['final_data']
    suc, fail = 0, 0
    
    for i in range(0, len(data), 1000):
        batch = data[i:i+1000]
        try: supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute(); suc += len(batch)
        except:
            for item in batch:
                try: supabase.table('kendaraan').upsert([item], on_conflict='nopol').execute(); suc += 1
                except: fail += 1
    
    await msg.edit_text(f"✅ **SELESAI!**\n✅ Sukses: {suc}\n❌ Gagal: {fail}", parse_mode='Markdown')
    context.user_data.pop('final_data', None)
    return ConversationHandler.END

# ==============================================================================
#                 5. HANDLERS UTAMA (START & SEARCH - FULL TEXT)
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info_text = f"\n📢 **INFO:** {GLOBAL_INFO}\n━━━━━━━━━━━━━━━━━━\n" if GLOBAL_INFO else ""
    text = (
        f"{info_text}"
        "🤖 **Selamat Datang di Oneaspal_bot**\n\n"
        "**Salam Satu Aspal!** 👋\n"
        "Halo, Rekan Mitra Lapangan.\n\n"
        "**Oneaspal_bot** adalah asisten digital profesional untuk mempermudah pencarian data kendaraan secara real-time.\n\n"
        "Cari data melalui:\n"
        "✅ **Nomor Polisi (Nopol)**\n"
        "✅ **Nomor Rangka (Noka)**\n"
        "✅ **Nomor Mesin (Nosin)**\n\n"
        "⚠️ **PENTING:** Akses bersifat **PRIVATE**. Anda wajib mendaftar dan menunggu verifikasi Admin.\n\n"
        "--- \n"
        "👉 Jalankan perintah /register untuk mendaftar."
    )
    await update.message.reply_text(text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if not u or u['status'] != 'active': return
    
    # --- CEK KUOTA (VITAL) ---
    if u.get('quota', 0) <= 0:
        return await update.message.reply_text(
            "⛔ **KUOTA HABIS!**\n\n"
            "Sisa kuota pencarian Anda: **0**.\n"
            "Silakan hubungi Admin untuk melakukan Top Up / Donasi Sukarela.\n\n"
            "👉 Ketik `/admin Mohon info topup`",
            parse_mode='Markdown'
        )

    kw = re.sub(r'[^a-zA-Z0-9]', '', update.message.text.upper())
    if len(kw) < 3: return await update.message.reply_text("⚠️ Masukkan minimal 3 karakter.")
    
    await context.bot.send_chat_action(update.effective_chat.id, constants.ChatAction.TYPING)
    try:
        res = supabase.table('kendaraan').select("*").or_(f"nopol.ilike.%{kw}%,noka.eq.{kw},nosin.eq.{kw}").execute()
        if res.data:
            d = res.data[0]
            update_quota_usage(u['user_id'], u['quota'])
            
            header_info = f"📢 **INFO:** {GLOBAL_INFO}\n━━━━━━━━━━━━━━━━━━\n" if GLOBAL_INFO else ""
            text = (
                f"{header_info}"
                f"✅ **DATA DITEMUKAN**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🚙 **Unit:** {d.get('type','-')}\n"
                f"🔢 **Nopol:** `{d.get('nopol','-')}`\n"
                f"📅 **Tahun:** {d.get('tahun','-')}\n"
                f"🎨 **Warna:** {d.get('warna','-')}\n"
                f"----------------------------------\n"
                f"🔧 **Noka:** `{d.get('noka','-')}`\n"
                f"⚙️ **Nosin:** `{d.get('nosin','-')}`\n"
                f"----------------------------------\n"
                f"⚠️ **OVD:** {d.get('ovd', '-')}\n"
                f"🏦 **Finance:** {d.get('finance', '-')}\n"
                f"🏢 **Branch:** {d.get('branch', '-')}\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"⚠️ **CATATAN PENTING:**\n"
                f"Ini bukan alat yang SAH untuk penarikan atau menyita aset kendaraan, "
                f"Silahkan konfirmasi kepada PIC leasing terkait.\n"
                f"Terima kasih."
            )
            await update.message.reply_text(text, parse_mode='Markdown')
            await notify_hit_to_group(context, u, d)
        else:
            info = f"📢 **INFO:** {GLOBAL_INFO}\n\n" if GLOBAL_INFO else ""
            await update.message.reply_text(f"{info}❌ **DATA TIDAK DITEMUKAN**\n`{update.message.text}`", parse_mode='Markdown')
    except: await update.message.reply_text("❌ Terjadi kesalahan database.")

# --- HANDLER CONVERSATION LAIN (REG, ADD, LAPOR, DEL) ---
# (Struktur standar, teks disesuaikan agar rapi)

async def register_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if get_user(u.effective_user.id): return await u.message.reply_text("✅ Sudah terdaftar.")
    await u.message.reply_text("📝 **NAMA LENGKAP:**", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return R_NAMA
async def register_nama(u: Update, c: ContextTypes.DEFAULT_TYPE): c.user_data['r_nama'] = u.message.text; await u.message.reply_text("📱 **NO HP:**"); return R_HP
async def register_hp(u: Update, c: ContextTypes.DEFAULT_TYPE): c.user_data['r_hp'] = u.message.text; await u.message.reply_text("📧 **EMAIL:**"); return R_EMAIL
async def register_email(u: Update, c: ContextTypes.DEFAULT_TYPE): c.user_data['r_email'] = u.message.text; await u.message.reply_text("📍 **KOTA:**"); return R_KOTA
async def register_kota(u: Update, c: ContextTypes.DEFAULT_TYPE): c.user_data['r_kota'] = u.message.text; await u.message.reply_text("🏢 **AGENCY:**"); return R_AGENCY
async def register_agency(u: Update, c: ContextTypes.DEFAULT_TYPE):
    c.user_data['r_agency'] = u.message.text
    msg = (f"📋 **KONFIRMASI**\n👤 {c.user_data['r_nama']}\n📱 {c.user_data['r_hp']}\n⚠️ Klik **KIRIM SEKARANG**.")
    await u.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["✅ KIRIM SEKARANG", "❌ ULANGI"]], one_time_keyboard=True), parse_mode='Markdown'); return R_CONFIRM
async def register_confirm(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.message.text == "❌ ULANGI": return await cancel(u, c)
    data = {"user_id": u.effective_user.id, "nama_lengkap": c.user_data['r_nama'], "no_hp": c.user_data['r_hp'], "email": c.user_data['r_email'], "alamat": c.user_data['r_kota'], "agency": c.user_data['r_agency'], "quota": 1000, "status": "pending"}
    try: supabase.table('users').insert(data).execute(); await u.message.reply_text("✅ Terkirim!", reply_markup=ReplyKeyboardRemove()); kb=[[InlineKeyboardButton("✅ Acc", callback_data=f"appu_{data['user_id']}"), InlineKeyboardButton("❌ Rej", callback_data=f"reju_{data['user_id']}")]]
    except: pass
    await c.bot.send_message(ADMIN_ID, f"🔔 **DAFTAR BARU**\n👤 {data['nama_lengkap']}", reply_markup=InlineKeyboardMarkup(kb)); return ConversationHandler.END

async def add_start(u: Update, c: ContextTypes.DEFAULT_TYPE): await u.message.reply_text("➕ **NOPOL:**", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return A_NOPOL
async def add_nopol(u: Update, c: ContextTypes.DEFAULT_TYPE): c.user_data['a_nopol'] = u.message.text.upper(); await u.message.reply_text("🚙 **UNIT:**"); return A_TYPE
async def add_type(u: Update, c: ContextTypes.DEFAULT_TYPE): c.user_data['a_type'] = u.message.text; await u.message.reply_text("🏦 **LEASING:**"); return A_LEASING
async def add_leasing(u: Update, c: ContextTypes.DEFAULT_TYPE): c.user_data['a_leasing'] = u.message.text; await u.message.reply_text("📝 **KET:**"); return A_NOKIR
async def add_nokir(u: Update, c: ContextTypes.DEFAULT_TYPE): c.user_data['a_nokir'] = u.message.text; await u.message.reply_text("✅ Kirim?", reply_markup=ReplyKeyboardMarkup([["✅ YA", "❌ BATAL"]], one_time_keyboard=True)); return A_CONFIRM
async def add_confirm(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.message.text != "✅ YA": return await cancel(u, c)
    n = c.user_data['a_nopol']; await u.message.reply_text("✅ Terkirim ke Admin.", reply_markup=ReplyKeyboardRemove())
    c.bot_data[f"prop_{n}"] = {"nopol": n, "type": c.user_data['a_type'], "finance": c.user_data['a_leasing'], "ovd": c.user_data['a_nokir']}
    kb = [[InlineKeyboardButton("✅ Acc", callback_data=f"v_acc_{n}_{u.effective_user.id}"), InlineKeyboardButton("❌ Rej", callback_data="v_rej")]]
    await c.bot.send_message(ADMIN_ID, f"📥 **MANUAL**\n🔢 {n}", reply_markup=InlineKeyboardMarkup(kb)); return ConversationHandler.END

async def lapor_start(u: Update, c: ContextTypes.DEFAULT_TYPE): await u.message.reply_text("🗑️ **NOPOL:**", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return L_NOPOL
async def lapor_check(u: Update, c: ContextTypes.DEFAULT_TYPE):
    n = u.message.text.upper().replace(" ", ""); res = supabase.table('kendaraan').select("*").eq('nopol', n).execute()
    if not res.data: await u.message.reply_text("❌ Tidak ada."); return ConversationHandler.END
    c.user_data['ln'] = n; await u.message.reply_text(f"⚠️ Lapor {n}?", reply_markup=ReplyKeyboardMarkup([["✅ YA", "❌ BATAL"]], one_time_keyboard=True)); return L_CONFIRM
async def lapor_confirm(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.message.text == "✅ YA":
        n = c.user_data['ln']; await u.message.reply_text("✅ Terkirim.", reply_markup=ReplyKeyboardRemove())
        kb = [[InlineKeyboardButton("✅ Hapus", callback_data=f"del_acc_{n}_{u.effective_user.id}"), InlineKeyboardButton("❌ Tolak", callback_data=f"del_rej_{u.effective_user.id}")]]
        await c.bot.send_message(ADMIN_ID, f"🗑️ **REQ HAPUS**\n🔢 {n}", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

async def delete_start(u: Update, c: ContextTypes.DEFAULT_TYPE): 
    if u.effective_user.id != ADMIN_ID: return
    await u.message.reply_text("🗑️ **NOPOL:**", reply_markup=ReplyKeyboardMarkup([["❌ BATAL"]], resize_keyboard=True)); return D_NOPOL
async def delete_check(u: Update, c: ContextTypes.DEFAULT_TYPE):
    n = u.message.text.upper().replace(" ", ""); c.user_data['dn'] = n; await u.message.reply_text(f"⚠️ Hapus {n}?", reply_markup=ReplyKeyboardMarkup([["✅ YA", "❌ BATAL"]], one_time_keyboard=True)); return D_CONFIRM
async def delete_confirm(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.message.text == "✅ YA": supabase.table('kendaraan').delete().eq('nopol', c.user_data['dn']).execute(); await u.message.reply_text("✅ Dihapus.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def get_stats(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.effective_user.id != ADMIN_ID: return
    msg = await u.message.reply_text("⏳ *Counting...*"); rt = supabase.table('kendaraan').select("*", count="exact", head=True).execute(); ru = supabase.table('users').select("*", count="exact", head=True).execute()
    await msg.edit_text(f"📊 **STATS**\n📂 Data: `{rt.count:,}`\n👥 User: `{ru.count:,}`", parse_mode='Markdown')

async def notify_hit_to_group(context, user_data, vehicle_data):
    hp_raw = user_data.get('no_hp', '-'); hp_wa = '62' + hp_raw[1:] if hp_raw.startswith('0') else hp_raw
    txt = (f"🚨 **UNIT DITEMUKAN! (HIT)**\n━━━━━━━━━━━━━━━━━━\n👤 **Penemu:** {user_data.get('nama_lengkap')}\n📍 **Kota:** {user_data.get('kota', '-')}\n\n🚙 **Unit:** {vehicle_data.get('type')}\n🔢 **Nopol:** `{vehicle_data.get('nopol')}`\n🏦 **Finance:** {vehicle_data.get('finance')}")
    kb = [[InlineKeyboardButton("📞 Hubungi Penemu (WA)", url=f"https://wa.me/{hp_wa}")]]
    try: await context.bot.send_message(LOG_GROUP_ID, txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    except: pass

async def cancel(u: Update, c: ContextTypes.DEFAULT_TYPE): await u.message.reply_text("🚫 Batal.", reply_markup=ReplyKeyboardRemove()); return ConversationHandler.END

async def callback_handler(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); d = q.data
    if d.startswith("appu_"): update_user_status(d.split("_")[1], 'active'); await q.edit_message_text("✅ User Aktif.")
    elif d.startswith("reju_"): update_user_status(d.split("_")[1], 'rejected'); await q.edit_message_text("⛔ User Ditolak.")
    elif d.startswith("v_acc_"): n = d.split("_")[2]; item = c.bot_data.get(f"prop_{n}"); supabase.table('kendaraan').upsert(item).execute(); await q.edit_message_text("✅ Data Masuk.")
    elif d == "v_rej": await q.edit_message_text("❌ Ditolak.")
    elif d.startswith("del_acc_"): supabase.table('kendaraan').delete().eq('nopol', d.split("_")[2]).execute(); await q.edit_message_text("✅ Dihapus.")
    elif d.startswith("del_rej_"): await q.edit_message_text("❌ Ditolak.")

# ADMIN EXTRAS
async def list_users(u: Update, c): 
    if u.effective_user.id == ADMIN_ID: res=supabase.table('users').select("*").limit(10).execute(); await u.message.reply_text("\n".join([f"{x['user_id']} | {x['nama_lengkap']}" for x in res.data]))
async def ban_user(u: Update, c):
    if u.effective_user.id == ADMIN_ID: update_user_status(c.args[0], 'rejected'); await u.message.reply_text("⛔ Banned.")
async def unban_user(u: Update, c):
    if u.effective_user.id == ADMIN_ID: update_user_status(c.args[0], 'active'); await u.message.reply_text("✅ Unbanned.")
async def delete_user(u: Update, c):
    if u.effective_user.id == ADMIN_ID: supabase.table('users').delete().eq('user_id', c.args[0]).execute(); await u.message.reply_text("🗑️ Deleted.")
async def set_info(u: Update, c): global GLOBAL_INFO; GLOBAL_INFO = " ".join(c.args) if u.effective_user.id == ADMIN_ID else GLOBAL_INFO; await u.message.reply_text(f"✅ Info: {GLOBAL_INFO}")
async def del_info(u: Update, c): global GLOBAL_INFO; GLOBAL_INFO = "" if u.effective_user.id == ADMIN_ID else GLOBAL_INFO; await u.message.reply_text("🗑️ Info Deleted.")
async def contact_admin(u: Update, c): await c.bot.send_message(ADMIN_ID, f"📩 **PESAN**\n{u.message.text}"); await u.message.reply_text("✅ Terkirim.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(token).post_init(post_init).build()
    
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('register', register_start)], states={R_NAMA:[MessageHandler(filters.TEXT, register_nama)], R_HP:[MessageHandler(filters.TEXT, register_hp)], R_EMAIL:[MessageHandler(filters.TEXT, register_email)], R_KOTA:[MessageHandler(filters.TEXT, register_kota)], R_AGENCY:[MessageHandler(filters.TEXT, register_agency)], R_CONFIRM:[MessageHandler(filters.TEXT, register_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('tambah', add_start)], states={A_NOPOL:[MessageHandler(filters.TEXT, add_nopol)], A_TYPE:[MessageHandler(filters.TEXT, add_type)], A_LEASING:[MessageHandler(filters.TEXT, add_leasing)], A_NOKIR:[MessageHandler(filters.TEXT, add_nokir)], A_CONFIRM:[MessageHandler(filters.TEXT, add_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('lapor', lapor_start)], states={L_NOPOL:[MessageHandler(filters.TEXT, lapor_check)], L_CONFIRM:[MessageHandler(filters.TEXT, lapor_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler('hapus', delete_start)], states={D_NOPOL:[MessageHandler(filters.TEXT, delete_check)], D_CONFIRM:[MessageHandler(filters.TEXT, delete_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    app.add_handler(ConversationHandler(entry_points=[MessageHandler(filters.Document.ALL, upload_start)], states={U_LEASING_USER: [MessageHandler(filters.TEXT, upload_leasing_user)], U_LEASING_ADMIN: [MessageHandler(filters.TEXT, upload_leasing_admin)], U_CONFIRM_UPLOAD: [MessageHandler(filters.TEXT, upload_confirm)]}, fallbacks=[CommandHandler('cancel', cancel)]))
    
    app.add_handler(CommandHandler('start', start)); app.add_handler(CommandHandler('cekkuota', cek_kuota))
    app.add_handler(CommandHandler('topup', admin_topup)); app.add_handler(CommandHandler('stats', get_stats))
    app.add_handler(CommandHandler('users', list_users)); app.add_handler(CommandHandler('ban', ban_user))
    app.add_handler(CommandHandler('unban', unban_user)); app.add_handler(CommandHandler('delete', delete_user))
    app.add_handler(CommandHandler('setinfo', set_info)); app.add_handler(CommandHandler('delinfo', del_info))
    app.add_handler(CommandHandler('admin', contact_admin)); app.add_handler(CommandHandler('panduan', panduan))
    
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ BOT ONLINE v1.9.6 (FINAL UI + ROBUST LOGIC)")
    app.run_polling()