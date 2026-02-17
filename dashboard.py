################################################################################
#                                                                              #
#  PROJECT: ONEASPAL COMMAND CENTER                                            #
#  VERSION: 10.8                                                               #
#  ROLE   : ADMIN DASHBOARD CORE                                               #
#  AUTHOR : CTO (GEMINI) & CEO (BAONK)                                         #
#                                                                              #
#  UPDATE LOG v10.8:                                                           #
#  1. Integrated Daily Log System for Admin uploads.                           #
#  2. Added 'data_month' auto-stamping (MMYY) for consistency.                 #
#  3. Optimized session state to prevent duplicate logging on refresh.         #
#                                                                              #
################################################################################

import streamlit as st
import pandas as pd
import time
import json
import os
import base64
import re
import numpy as np
import io
import zipfile
import pytz 
import requests 
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
from dotenv import load_dotenv
# 👇 [BARU] TAMBAHKAN INI
from utils_log import catat_log_kendaraan

# DEFINISI ZONA WAKTU
TZ_JAKARTA = pytz.timezone('Asia/Jakarta')

# [FIX] Import ClientOptions
try:
    from supabase.lib.client_options import ClientOptions
except ImportError:
    from supabase import ClientOptions

# ##############################################################################
# BAGIAN 1: KONFIGURASI HALAMAN
# ##############################################################################
st.set_page_config(
    page_title="One Aspal Command",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- AUTO REFRESH ---
try:
    from streamlit_autorefresh import st_autorefresh
    count = st_autorefresh(interval=30 * 60 * 1000, key="auto_refresh_radar")
    auto_refresh_status = "🟢 AUTO (30m)"
except ImportError:
    auto_refresh_status = "⚪ MANUAL"

# --- CSS MASTER ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Orbitron:wght@500;700;900&display=swap');
    .stApp { background-color: #0e1117 !important; font-family: 'Inter', sans-serif; font-size: 14px; }
    p, span, div, li { color: #e0e0e0; }
    h1, h2, h3, h4, h5, h6 { font-family: 'Orbitron', sans-serif !important; color: #ffffff !important; text-transform: uppercase; letter-spacing: 1px; }
    div[data-testid="stMetricLabel"] { color: #a0a0a0 !important; font-size: 0.8rem !important; }
    div[data-testid="stMetricValue"] { color: #00f2ff !important; font-family: 'Orbitron', sans-serif; font-size: 1.5rem !important; }
    div[data-testid="metric-container"] { background: rgba(255, 255, 255, 0.05) !important; border: 1px solid rgba(255, 255, 255, 0.1) !important; border-radius: 12px; padding: 10px; backdrop-filter: blur(10px); }
    .stButton>button { background: linear-gradient(90deg, #0061ff 0%, #60efff 100%) !important; color: #000000 !important; border: none; border-radius: 8px; height: 45px; font-weight: 800; font-family: 'Orbitron', sans-serif; width: 100%; transition: all 0.3s; }
    .leaderboard-row { background: rgba(0, 242, 255, 0.04); padding: 15px; margin-bottom: 8px; border-radius: 8px; border-left: 4px solid #00f2ff; display: flex; justify-content: space-between; align-items: center; }
    .leaderboard-val { font-family: 'Orbitron'; color: #00f2ff !important; font-weight: bold; font-size: 1.1rem; }
    .tech-box { background: rgba(0, 242, 255, 0.05); border-left: 4px solid #00f2ff; padding: 20px; border-radius: 8px; color: #ddd; margin-bottom: 20px; }
    .info-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-top: 15px; }
    .info-item { background: rgba(255,255,255,0.05); padding: 12px; border-radius: 6px; }
    .info-label { color: #aaa !important; font-size: 0.8rem; display: block; margin-bottom: 4px; text-transform: uppercase; }
    .info-value { color: #ffffff !important; font-weight: bold; font-family: 'Orbitron'; font-size: 1.1rem; }
    header {visibility: hidden;} 
    .footer-text { text-align: center; color: #888; font-family: 'Orbitron', sans-serif; font-size: 0.8rem; margin-top: 20px; opacity: 0.7; }
    .footer-quote { text-align: center; color: #00f2ff; font-style: italic; font-size: 0.9rem; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# ##############################################################################
# BAGIAN 2: LOGIKA KONEKSI & DATABASE
# ##############################################################################
load_dotenv()
URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# [FIX] TOKEN MANUAL AGAR BROADCAST JALAN
MANUAL_TOKEN = "8428069329:AAFCv-44aK7F2Ry1kO5nLDS0430shirK9CM" 
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN") or MANUAL_TOKEN

@st.cache_resource
def init_connection():
    try:
        opts = ClientOptions(postgrest_client_timeout=600)
        return create_client(URL, KEY, options=opts)
    except Exception as e:
        return create_client(URL, KEY)

supabase = init_connection()

# --- SESSION STATE INIT ---
if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False
if 'upload_stage' not in st.session_state: st.session_state['upload_stage'] = 'idle'
if 'upload_data_cache' not in st.session_state: st.session_state['upload_data_cache'] = None
if 'upload_found_cols' not in st.session_state: st.session_state['upload_found_cols'] = []
if 'upload_result' not in st.session_state: st.session_state['upload_result'] = None
if 'broadcast_logs' not in st.session_state: st.session_state['broadcast_logs'] = {}

# --- DATABASE CRUD FUNCTIONS ---
def get_total_asset_count():
    try: return supabase.table('kendaraan').select('*', count='exact', head=True).execute().count
    except: return 0

def get_all_users():
    try:
        res = supabase.table('users').select('*').execute()
        df = pd.DataFrame(res.data)
        if not df.empty: df['user_id'] = df['user_id'].astype(str)
        return df
    except: return pd.DataFrame()

def get_hit_counts():
    try:
        res = supabase.table('finding_logs').select('user_id').execute()
        df = pd.DataFrame(res.data)
        return df['user_id'].astype(str).value_counts() if not df.empty else pd.Series()
    except: return pd.Series()

def get_live_users_count():
    try:
        res = supabase.table('users').select('last_seen').execute()
        df = pd.DataFrame(res.data)
        if 'last_seen' not in df.columns: return 0
        TZ = pytz.timezone('Asia/Jakarta')
        df['last_seen'] = pd.to_datetime(df['last_seen'], errors='coerce')
        if df['last_seen'].dt.tz is None: df['last_seen'] = df['last_seen'].dt.tz_localize('UTC').dt.tz_convert(TZ)
        else: df['last_seen'] = df['last_seen'].dt.tz_convert(TZ)
        now = datetime.now(TZ)
        limit = now - timedelta(minutes=30)
        return len(df[df['last_seen'] >= limit])
    except: return 0

def get_daily_active_users():
    try:
        res = supabase.table('users').select('last_seen').execute()
        df = pd.DataFrame(res.data)
        if 'last_seen' not in df.columns: return 0
        TZ = pytz.timezone('Asia/Jakarta')
        df['last_seen'] = pd.to_datetime(df['last_seen'], errors='coerce')
        if df['last_seen'].dt.tz is None: df['last_seen'] = df['last_seen'].dt.tz_localize('UTC').dt.tz_convert(TZ)
        else: df['last_seen'] = df['last_seen'].dt.tz_convert(TZ)
        today_start = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        return len(df[df['last_seen'] >= today_start])
    except: return 0

def update_user_status(uid, stat):
    try: supabase.table('users').update({'status': stat}).eq('user_id', uid).execute(); return True
    except: return False

def add_user_quota(uid, days):
    try:
        res = supabase.table('users').select('expiry_date').eq('user_id', uid).execute()
        now = datetime.now(timezone.utc)
        current_exp_str = None
        if res.data and len(res.data) > 0:
            current_exp_str = res.data[0].get('expiry_date')

        base = now
        if current_exp_str:
            try:
                clean_str = current_exp_str.replace('Z', '+00:00')
                parsed_date = datetime.fromisoformat(clean_str)
                if parsed_date.tzinfo is None:
                    parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                if parsed_date > now: base = parsed_date
                else: base = now
            except ValueError: base = now

        new_exp_dt = base + timedelta(days=days)
        new_exp_str = new_exp_dt.isoformat()
        supabase.table('users').update({'expiry_date': new_exp_str}).eq('user_id', uid).execute()
        return True, f"Sukses! Expired baru: {new_exp_dt.strftime('%d-%m-%Y')}"

    except Exception as e:
        print(f"❌ ERROR ADD QUOTA: {e}") 
        return False, str(e)
    
def send_telegram_message(user_id, text):
    if not BOT_TOKEN: 
        print("❌ BROADCAST GAGAL: Token Bot Kosong!")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": user_id, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=5)
        if r.status_code == 200: return True
        else:
            print(f"⚠️ Telegram Error ({user_id}): {r.text}")
            return False
    except Exception as e: 
        print(f"❌ Net Error ({user_id}): {e}")
        return False

def delete_user_with_reason(uid, reason):
    try:
        msg = f"⛔ <b>AKUN DINONAKTIFKAN</b>\n\nMaaf, akun One Aspal Anda telah dihapus oleh Admin.\n\n📝 <b>Alasan:</b>\n{reason}\n\nTerima kasih."
        send_telegram_message(uid, msg)
        supabase.table('users').delete().eq('user_id', uid).execute()
        return True
    except: return False

# ##############################################################################
# BAGIAN 3: ENGINE PINTAR & PARSER
# ##############################################################################
COLUMN_ALIASES = {
    'nopol': ['nopolisi', 'nomorpolisi', 'nopol', 'noplat', 'tnkb', 'licenseplate', 'plat', 'police_no', 'no polisi'],
    'type': ['type', 'tipe', 'unit', 'model', 'vehicle', 'jenis', 'deskripsiunit', 'merk', 'object', 'kendaraan'],
    'tahun': ['tahun', 'year', 'thn', 'rakitan', 'th'],
    'warna': ['warna', 'color', 'colour', 'cat'],
    'noka': ['noka', 'norangka', 'nomorrangka', 'chassis', 'chasis', 'vin', 'rangka', 'no rangka'],
    'nosin': ['nosin', 'nomesin', 'nomormesin', 'engine', 'mesin', 'no mesin', 'engine_number'],
    'finance': ['finance', 'leasing', 'lising', 'multifinance', 'mitra', 'principal', 'client'],
    'ovd': ['ovd', 'overdue', 'dpd', 'keterlambatan', 'odh', 'hari', 'telat', 'aging'],
    'branch': ['branch', 'area', 'kota', 'pos', 'cabang', 'lokasi', 'wilayah']
}
def normalize_text(t): return ''.join(e for e in str(t) if e.isalnum()).lower()
def fix_header_position(df):
    target = [normalize_text(a) for a in COLUMN_ALIASES['nopol']]
    for i in range(min(30, len(df))):
        vals = [normalize_text(str(x)) for x in df.iloc[i].values]
        if any(a in vals for a in target):
            df.columns = df.iloc[i]; return df.iloc[i+1:].reset_index(drop=True)
    return df
def smart_rename_columns(df):
    new, found = {}, []
    df.columns = [str(c).strip().replace('\ufeff', '') for c in df.columns]
    for col in df.columns:
        clean = normalize_text(col)
        for std, aliases in COLUMN_ALIASES.items():
            if clean == std or clean in [normalize_text(a) for a in aliases]:
                if std not in new.values(): new[col] = std; found.append(std)
                break
        if col not in new: new[col] = col
    df.rename(columns=new, inplace=True); return df.loc[:, ~df.columns.duplicated()], found

def read_file_robust(file_up):
    try:
        filename = file_up.name.upper()
        if filename.endswith('.TOPAZ'):
            try:
                content = file_up.getvalue().decode('utf-8', errors='ignore')
                lines = content.splitlines()
                data_list = []
                for line in lines:
                    if not line.strip() or 'NOPOLISI' in line: continue
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        nopol = parts[0].strip()
                        details = parts[1]
                        def get_val(k, t, nk_list):
                            try:
                                if k in t:
                                    start = t.find(k) + len(k)
                                    sub = t[start:]
                                    for nk in nk_list:
                                        if nk in sub: sub = sub.split(nk)[0]
                                    return sub.strip()
                            except: pass
                            return None
                        row = {
                            'nopol': nopol,
                            'type': get_val('TIPE;', details, ['NOKA;', 'NOSIN;']),
                            'noka': get_val('NOKA;', details, ['NOSIN;', 'WARNA;']),
                            'nosin': get_val('NOSIN;', details, ['WARNA;', 'OD;']),
                            'warna': get_val('WARNA;', details, ['OD;', 'OVERDUE']),
                            'ovd': get_val('OD;', details, []),
                            'finance': None, 'tahun': None
                        }
                        data_list.append(row)
                return pd.DataFrame(data_list)
            except Exception as e:
                st.error(f"Error parsing TOPAZ: {e}")
                return pd.DataFrame()

        if filename.endswith('.ZIP'):
            with zipfile.ZipFile(file_up) as z:
                v = [x for x in z.namelist() if x.endswith(('.csv','.xlsx','.xls'))]
                if v: file_up = io.BytesIO(z.read(v[0])); file_up.name = v[0]
        
        if file_up.name.upper().endswith(('.XLSX', '.XLS')): 
            try: return pd.read_excel(file_up, dtype=str)
            except: return pd.read_excel(file_up, engine='openpyxl', dtype=str)
        
        return pd.read_csv(file_up, sep=None, engine='python', dtype=str, on_bad_lines='skip')
    except: return pd.DataFrame()

def standardize_leasing_name(n): return "UNKNOWN" if str(n).upper().strip() in ['NAN','NULL',''] else str(n).upper().strip()

# ##############################################################################
# BAGIAN 4: LOGIN SCREEN
# ##############################################################################
if not st.session_state['authenticated']:
    c1, c2, c3 = st.columns([1, 6, 1])
    with c2:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        if os.path.exists("logo.png"):
            b64 = base64.b64encode(open("logo.png", "rb").read()).decode()
            st.markdown(f'<div style="display:flex;justify-content:center;margin-bottom:30px;"><img src="data:image/png;base64,{b64}" width="220" style="border-radius:15px; filter: drop-shadow(0 0 10px rgba(0,242,255,0.3));"></div>', unsafe_allow_html=True)
        st.markdown("<h2 style='text-align:center;color:#00f2ff;'>SYSTEM LOGIN</h2>", unsafe_allow_html=True)
        pwd = st.text_input("PASSPHRASE", type="password", label_visibility="collapsed", key="login_pwd")
        if pwd == ADMIN_PASSWORD: st.session_state['authenticated'] = True; st.rerun()
    st.stop()

# ##############################################################################
# BAGIAN 5: SIDEBAR & HEADER
# ##############################################################################
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", width=220)
    st.caption(f"ONE ASPAL SYSTEM\nStatus: {auto_refresh_status}")
    if not BOT_TOKEN or "MANUAL" in BOT_TOKEN: 
        st.success("✅ TOKEN BOT AKTIF")
    else:
        st.error("⚠️ TOKEN BOT HILANG")

st.markdown("## ONE ASPAL COMMANDO v10.7")
st.markdown("<span style='color: #00f2ff; font-family: Orbitron; font-size: 0.8rem;'>⚡ LIVE INTELLIGENCE COMMAND CENTER</span>", unsafe_allow_html=True)
st.markdown("---")

df_u = get_all_users()
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("ASSETS", f"{get_total_asset_count():,}", "DATABASE")
m2.metric("LIVE USERS", f"{get_live_users_count()}", "ACTIVE < 30M")
m3.metric("DAILY ACTIVE", f"{get_daily_active_users()}", "24H VISITOR") 
m4.metric("MITRA", f"{len(df_u[df_u['role']!='pic']) if not df_u.empty else 0}", "REGISTERED")

jml_aktif = len(df_u[df_u['status'] == 'active']) if not df_u.empty else 0
jml_non_aktif = len(df_u) - jml_aktif if not df_u.empty else 0
m5.metric("STATUS AKUN", f"{jml_aktif} Aktif", f"{jml_non_aktif} Non-Aktif/Banned",delta_color="off")
m6.metric("PIC LEASING", f"{len(df_u[df_u['role']=='pic']) if not df_u.empty else 0}", "INTERNAL")
st.write("")

# ##############################################################################
# BAGIAN 6: FITUR TABS
# ##############################################################################
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🏆 LEADERBOARD", "🛡️ PERSONIL", "📤 UPLOAD", "🗑️ HAPUS", "📡 LIVE OPS", "💀 EXPIRED"])

# --- TAB 1: LEADERBOARD ---
with tab1:
    hits = get_hit_counts()
    if not df_u.empty and not hits.empty:
        df_r = df_u.copy(); df_r['h'] = df_r['user_id'].map(hits).fillna(0).astype(int)
        for i, r in enumerate(df_r[df_r['role']!='pic'].sort_values('h', ascending=False).head(10).iterrows(), 1):
            st.markdown(f'<div class="leaderboard-row"><div><b>#{i} {r[1]["nama_lengkap"]}</b><br><small>{r[1]["agency"]}</small></div><div class="leaderboard-val">{r[1]["h"]} HITS</div></div>', unsafe_allow_html=True)

# --- TAB 2: MANAJEMEN PERSONIL (USER) ---
with tab2:
    if not df_u.empty:
        div = st.radio("DIV", ["🛡️ MATEL", "🏦 PIC LEASING"], horizontal=True, label_visibility="collapsed", key="radio_role_select")
        target = df_u[df_u['role']!='pic'] if "MATEL" in div else df_u[df_u['role']=='pic']
        target = target.sort_values(by="nama_lengkap", key=lambda col: col.str.lower())
        sel = st.selectbox("SEARCH AGENT", [f"{r['nama_lengkap']} | {r['agency']}" for i, r in target.iterrows()], label_visibility="collapsed", key="select_agent_search")
        
        if sel:
            uid = target[target['nama_lengkap']==sel.split(' | ')[0]].iloc[0]['user_id']
            u = target[target['user_id']==uid].iloc[0]
            st.markdown(f'''<div class="tech-box"><h3>{u["nama_lengkap"]}</h3><hr style="border-color:rgba(255,255,255,0.1); margin:15px 0;"><div class="info-grid"><div class="info-item"><span class="info-label">ROLE</span><span class="info-value" style="color:#00f2ff;">{u["role"].upper()}</span></div><div class="info-item"><span class="info-label">STATUS</span><span class="info-value" style="color:{'#0f0' if u["status"]=="active" else "#f00"}">{u["status"].upper()}</span></div><div class="info-item"><span class="info-label">NO HP / WA</span><span class="info-value">{u.get("no_hp", "-")}</span></div><div class="info-item"><span class="info-label">PT / AGENCY</span><span class="info-value">{u.get("agency", "-")}</span></div><div class="info-item"><span class="info-label">DOMISILI</span><span class="info-value">{u.get("alamat", "-")}</span></div><div class="info-item"><span class="info-label">EXPIRY</span><span class="info-value">{str(u["expiry_date"])[:10]}</span></div><div class="info-item"><span class="info-label">QUOTA</span><span class="info-value">{u.get("quota",0)}</span></div><div class="info-item" style="grid-column:span 2;border:1px solid #00f2ff;"><span class="info-label">LIFETIME HITS</span><span class="info-value" style="color:#00f2ff;">{hits.get(uid,0)} FOUND</span></div></div></div>''', unsafe_allow_html=True)
            st.write("---")
            c_day, c_btn = st.columns([1, 2])
            with c_day: days_add = st.number_input("JUMLAH HARI", min_value=1, max_value=365, value=30, label_visibility="collapsed", key="num_days_add")
            with c_btn:
                if st.button(f"➕ PERPANJANG MASA AKTIF", key="btn_add_quota", use_container_width=True):
                    is_success, msg_feedback = add_user_quota(uid, days_add)
                    if is_success: st.toast(f"✅ {msg_feedback}", icon="🎉"); time.sleep(1); st.rerun()
                    else: st.error(f"❌ GAGAL: {msg_feedback}")
            st.divider()
            b1, b2, b3, b4 = st.columns(4) 
            with b1:
                btn_label = "⛔ FREEZE AKUN" if u['status']=='active' else "✅ BUKA FREEZE"
                if st.button(btn_label, key="btn_freeze", use_container_width=True):
                    new_stat = 'banned' if u['status']=='active' else 'active'
                    update_user_status(uid, new_stat); st.toast(f"Status: {new_stat.upper()}", icon="🔄"); time.sleep(1); st.rerun()
            with b2:
                if st.button("🗑️ HAPUS AKUN", key="btn_del_req", use_container_width=True): st.session_state[f'del_confirm_{uid}'] = True
            with b3:
                 if u['role'] == 'matel':
                    if st.button("⬆️ JADI KORLAP", key="btn_promote", type="primary", use_container_width=True):
                        supabase.table('users').update({'role': 'korlap'}).eq('user_id', uid).execute()
                        st.success(f"✅ {u['nama_lengkap']} naik pangkat jadi KORLAP!"); time.sleep(1); st.rerun()
                 elif u['role'] == 'korlap':
                    if st.button("⬇️ TURUNKAN MATEL", key="btn_demote", use_container_width=True):
                        supabase.table('users').update({'role': 'matel'}).eq('user_id', uid).execute()
                        st.warning(f"⚠️ {u['nama_lengkap']} turun pangkat jadi MATEL."); time.sleep(1); st.rerun()
            with b4:
                if u['role'] != 'pic':
                    if st.button("👮 JADI PIC LEASING", key="btn_pic", use_container_width=True):
                         supabase.table('users').update({'role': 'pic'}).eq('user_id', uid).execute()
                         st.info(f"ℹ️ {u['nama_lengkap']} dimutasi jadi PIC LEASING."); time.sleep(1); st.rerun()

            if st.session_state.get(f'del_confirm_{uid}', False):
                st.warning("⚠️ KONFIRMASI PENGHAPUSAN")
                del_reason = st.text_input("📝 ALASAN MENGHAPUS (Wajib Diisi):", key=f"reason_{uid}")
                cd1, cd2 = st.columns(2)
                with cd1:
                    if st.button("❌ BATAL", key=f"cancel_{uid}"): st.session_state[f'del_confirm_{uid}'] = False; st.rerun()
                with cd2:
                    if st.button("✅ KONFIRMASI HAPUS", key=f"confirm_{uid}"):
                        if del_reason.strip():
                            if delete_user_with_reason(uid, del_reason): st.success("User dihapus."); st.session_state[f'del_confirm_{uid}'] = False; time.sleep(1); st.rerun()
                            else: st.error("Gagal menghapus user.")
                        else: st.error("Isi alasan dulu.")

# --- TAB 3: UPLOAD FILE ---
with tab3:
    if st.session_state['upload_stage'] == 'idle':
        up = st.file_uploader("DROP FILE", type=['xlsx','xls','csv','txt','zip','topaz'], label_visibility="collapsed", key="file_up_analyze")
        
        if up and st.button("🔍 ANALISA", key="btn_analyze"):
            df = read_file_robust(up) 
            if not df.empty:
                df, cols = smart_rename_columns(fix_header_position(df))
                if 'nopol' in df.columns: 
                    st.session_state['upload_data_cache'], st.session_state['upload_found_cols'], st.session_state['upload_stage'] = df, cols, 'preview'
                    st.rerun()
                else: st.error("❌ NOPOL NOT FOUND. Pastikan ada kolom NOPOL di file Anda.")
            else: st.error("❌ Gagal membaca file atau file kosong.")

    elif st.session_state['upload_stage'] == 'preview':
        df = st.session_state['upload_data_cache']
        st.info(f"✅ TERDETEKSI: {len(df)} Baris Data | Kolom: {st.session_state['upload_found_cols']}")
        st.dataframe(df.head(), use_container_width=True)
        l_in = st.text_input("🏦 NAMA LEASING (Opsional - Jika kosong di file):", key="input_leasing_name") if 'finance' not in df.columns else ""
        c1, c2 = st.columns(2)
        with c1: 
            if st.button("❌ BATAL / RESET", key="btn_reset"): 
                st.session_state['upload_stage']='idle'; st.rerun()
        with c2:
            if st.button("🚀 EKSEKUSI UPDATE", key="btn_update"):
                # 1. PERSIAPAN DATA
                if l_in: df['finance'] = standardize_leasing_name(l_in)
                
                # Bersihkan Nopol
                df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
                df['nopol'] = df['nopol'].replace({'': np.nan, 'NAN': np.nan, 'NONE': np.nan})
                df = df.dropna(subset=['nopol'])
                df = df.drop_duplicates(subset=['nopol'])
                
                # Tambah Kode Bulan (MMYY)
                now = datetime.now(TZ_JAKARTA)
                code_version = now.strftime('%m%y') 
                df['data_month'] = code_version

                # Pastikan Kolom Lengkap
                required_cols = ['type','finance','tahun','warna','noka','nosin','ovd','branch','data_month']
                for c in required_cols:
                    if c not in df.columns: df[c] = None 
                    else: df[c] = df[c].replace({np.nan: None, "": None})
                
                # Konversi ke Records
                recs = df[['nopol'] + required_cols].to_dict('records')
                total_recs = len(recs)
                
                # 2. PROSES UPLOAD (BATCHING)
                BATCH_SIZE = 200 
                s, f = 0, 0
                pb = st.progress(0, f"Memproses {total_recs} data (Mode Aman: Batch {BATCH_SIZE})...")
                last_error = ""
                
                for i in range(0, total_recs, BATCH_SIZE):
                    batch = recs[i:i+BATCH_SIZE]
                    success_batch = False
                    
                    # Retry Logic (5x)
                    for attempt in range(5):
                        try: 
                            supabase.table('kendaraan').upsert(batch, on_conflict='nopol').execute()
                            s += len(batch)
                            success_batch = True
                            break
                        except Exception as e: 
                            wait_time = (attempt + 1) * 2
                            time.sleep(wait_time) 
                            if attempt == 4: 
                                f += len(batch)
                                last_error = str(e)
                    
                    # Update Progress Bar
                    pb.progress(min((i+BATCH_SIZE)/total_recs, 1.0))
                
                # 3. SIMPAN HASIL KE SESSION
                st.session_state['upload_result'] = {'suc': s, 'fail': f, 'err': last_error, 'leasing': l_in}
                st.session_state['upload_stage'] = 'complete'
                st.rerun()

    elif st.session_state.get('upload_stage') == 'complete':
        r = st.session_state.get('upload_result', {})
        suc = r.get('suc', 0)
        fail = r.get('fail', 0)
        
        if fail == 0: 
            st.success(f"✅ SUKSES TOTAL! {suc} Data Berhasil Diupdate.")
            
            # --- [BARU] INTEGRASI LOG HARIAN ---
            # Hanya mencatat jika belum dicatat (mencegah duplikat saat refresh)
            if 'log_recorded' not in st.session_state:
                try:
                    leasing_log = standardize_leasing_name(r.get('leasing')) if r.get('leasing') else "MIXED/AUTO"
                    catat_log_kendaraan(
                        sumber="DASHBOARD_ADMIN",
                        leasing=leasing_log,
                        jumlah=suc
                    )
                    st.session_state['log_recorded'] = True
                    st.caption("📝 Aktivitas telah dicatat di Log Harian.")
                except Exception as log_e:
                    print(f"Log Error: {log_e}")
            # -----------------------------------
            
        else:
            st.warning(f"⚠️ SELESAI DENGAN CATATAN\n✅ Sukses: {suc}\n❌ Gagal: {fail}")
            if r.get('err'): st.error(f"🔍 Info Error: {r['err']}")
        
        if st.button("⬅️ UPLOAD LAGI", key="btn_back"): 
            st.session_state['upload_stage']='idle'
            if 'log_recorded' in st.session_state: del st.session_state['log_recorded']
            st.rerun()

# --- TAB 4: HAPUS MASSAL ---
with tab4:
    up = st.file_uploader("PURGE LIST", type=['xlsx','csv'], key="file_up_purge")
    if up and st.button("🔥 EXECUTE", key="btn_purge"):
        df = read_file_robust(up); df, _ = smart_rename_columns(df)
        if 'nopol' in df.columns:
            t = list(set(df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper().tolist()))
            pb = st.progress(0, "Deleting..."); batch = 1000 
            for i in range(0, len(t), batch):
                try: supabase.table('kendaraan').delete().in_('nopol', t[i:i+batch]).execute()
                except: pass
                pb.progress(min((i+batch)/len(t), 1.0))
            st.success("DELETED"); time.sleep(1); st.rerun()

# --- TAB 5: LIVE OPS MONITORING ---
with tab5:
    st.markdown("### 📡 REALTIME OPERATIONS CENTER (TODAY'S ACTIVITY)")
    users_resp = supabase.table('users').select('nama_lengkap, agency, role, last_seen, status, no_hp').execute()
    if users_resp.data:
        df_live = pd.DataFrame(users_resp.data)
        if 'last_seen' in df_live.columns:
            TZ = pytz.timezone('Asia/Jakarta')
            df_live['last_seen'] = pd.to_datetime(df_live['last_seen'], errors='coerce')
            if df_live['last_seen'].dt.tz is None: df_live['last_seen'] = df_live['last_seen'].dt.tz_localize('UTC').dt.tz_convert(TZ)
            else: df_live['last_seen'] = df_live['last_seen'].dt.tz_convert(TZ)
            now = datetime.now(TZ)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            df_display = df_live.dropna(subset=['last_seen']).copy()
            df_display = df_display[df_display['last_seen'] >= today_start]
            if not df_display.empty:
                limit_30m = now - timedelta(minutes=30)
                def get_status_label(row):
                    t = row['last_seen']
                    if pd.isna(t): return "⚫ OFFLINE"
                    if t >= limit_30m: return "🟢 ONLINE"
                    return "🟡 IDLE"
                df_display['STATUS'] = df_display.apply(get_status_label, axis=1)
                df_display['TIME'] = df_display['last_seen'].dt.strftime('%H:%M:%S')
                final_view = df_display[['STATUS', 'TIME', 'nama_lengkap', 'agency', 'role', 'no_hp']]
                final_view.columns = ['STATUS', 'LAST ACTIVE', 'USER', 'AGENCY', 'ROLE', 'NO. HP']
                final_view = final_view.sort_values(by='LAST ACTIVE', ascending=False)
                st.dataframe(final_view, hide_index=True, use_container_width=True, column_config={"STATUS": st.column_config.TextColumn("STATUS", width="small"), "LAST ACTIVE": st.column_config.TextColumn("JAM (WIB)", width="small")})
            else: st.info("💤 Belum ada aktivitas user hari ini (Sejak 00:00 WIB).")
        else: st.warning("⚠️ Database belum mencatat waktu (Kolom last_seen kosong).")


# --- TAB 6: DAFTAR USER EXPIRED (AUDIT & RETENSI + PUSH REMINDER) ---
with tab6:
    st.markdown("### 💀 DAFTAR USER HABIS MASA AKTIF")
    st.info("Halaman ini mengambil data LANGSUNG dari server (Real-time Audit).")
    
    if not BOT_TOKEN:
        st.error("⚠️ TOKEN BOT TIDAK TERDETEKSI. Broadcast tidak akan terkirim.")

    # TOMBOL CLEAR STATUS & REFRESH
    cr1, cr2 = st.columns([1, 1])
    with cr1:
        if st.button("🧹 CLEAR STATUS BROADCAST", type="secondary"):
            st.session_state['broadcast_logs'] = {}
            st.rerun()
    with cr2:
        if st.button("🔄 REFRESH DATA SERVER", type="secondary"):
            st.cache_data.clear()
            st.rerun()

    try:
        now_str = datetime.now(TZ_JAKARTA).strftime('%Y-%m-%d')
        
        response = supabase.table('users').select('*')\
            .lt('expiry_date', now_str)\
            .neq('status', 'banned')\
            .execute()
        
        data_expired = response.data
        
        if data_expired:
            df_audit = pd.DataFrame(data_expired)
            
            # [FIX CRITICAL] Handle format tanggal ISO
            df_audit['tgl_exp_obj'] = pd.to_datetime(df_audit['expiry_date'], format='mixed', errors='coerce').dt.date
            df_audit = df_audit.sort_values(by='tgl_exp_obj', ascending=True)

            c1, c2 = st.columns(2)
            c1.metric("TOTAL EXPIRED", f"{len(df_audit)} User", "Target Penagihan", delta_color="inverse")
            c2.metric("TERLAMA SEJAK", f"{df_audit['tgl_exp_obj'].iloc[0]}", "Prioritas")
            st.divider()

            # Apply format tampilan
            df_audit['expiry_date_str'] = pd.to_datetime(df_audit['expiry_date'], format='mixed', errors='coerce').dt.strftime('%Y-%m-%d')
            
            # MAPPING STATUS
            df_audit['STATUS_BROADCAST'] = df_audit['user_id'].map(st.session_state['broadcast_logs']).fillna("⏳ Menunggu")

            # =========================================================
            # [NEW FEATURE] LOGIC SELECT ALL
            # =========================================================
            # 1. Tambahkan kolom default False
            df_audit.insert(0, "PILIH", False)
            
            cols_show = ['PILIH', 'STATUS_BROADCAST', 'nama_lengkap', 'no_hp', 'agency', 'role', 'expiry_date_str', 'status', 'user_id']
            cols_exist = [c for c in cols_show if c in df_audit.columns]
            
            df_show = df_audit[cols_exist].copy()

            # 2. Tombol Select All (Di atas tabel)
            c_sel, c_space = st.columns([2, 5])
            with c_sel:
                select_all = st.checkbox("✅ PILIH SEMUA USER", value=False, key="select_all_toggle")
            
            # 3. Override nilai jika Select All dicentang
            if select_all:
                df_show['PILIH'] = True

            edited_df = st.data_editor(
                df_show,
                column_config={
                    "PILIH": st.column_config.CheckboxColumn("TAGIH?", default=False),
                    "STATUS_BROADCAST": st.column_config.TextColumn("STATUS KIRIM", width="medium"),
                    "nama_lengkap": "Nama User",
                    "no_hp": "WhatsApp",
                    "agency": "Agency",
                    "expiry_date_str": "Tgl Expired",
                    "status": "Status DB",
                    "user_id": st.column_config.TextColumn("User ID", disabled=True)
                },
                hide_index=True,
                use_container_width=True,
                height=400,
                key="audit_direct_fetch"
            )

            targets = edited_df[edited_df['PILIH'] == True]
            
            col_act1, col_act2 = st.columns([1, 2])
            
            with col_act1:
                csv = df_show.drop(columns=['PILIH']).to_csv(index=False).encode('utf-8')
                st.download_button("📥 DOWNLOAD CSV", csv, f"DATA_EXPIRED_REALTIME_{now_str}.csv", "text/csv")

            with col_act2:
                if not targets.empty:
                    if st.button(f"📢 KIRIM KE {len(targets)} USER", type="primary", use_container_width=True):
                        
                        if not BOT_TOKEN:
                            st.error("❌ BROADCAST DIBATALKAN: Token Bot Kosong/Tidak Terbaca.")
                            st.stop()
                            
                        succ_count, fail_count = 0, 0
                        prog_bar = st.progress(0, "Mengirim Notifikasi...")
                        total_targets = len(targets)
                        
                        for i, (idx, row) in enumerate(targets.iterrows(), 1):
                            msg_reminder = (
                                f"🔔 <b>PENGINGAT MASA AKTIF</b>\n\n"
                                f"Halo <b>{row['nama_lengkap']}</b>,\n"
                                f"Masa aktif akun One Aspal Anda telah berakhir pada tanggal <b>{row['expiry_date_str']}</b>.\n\n"
                                f"⛔ Akses pencarian data Anda telah dinonaktifkan sementara.\n"
                                f"Silakan hubungi Admin untuk perpanjangan, atau ketik /infobayar \n\n"
                                f"<i>Tetap Semangat! 🦅</i>"
                            )
                            try:
                                is_sent = send_telegram_message(row['user_id'], msg_reminder)
                                if is_sent: 
                                    succ_count += 1
                                    st.session_state['broadcast_logs'][row['user_id']] = "✅ TERKIRIM"
                                else: 
                                    fail_count += 1
                                    st.session_state['broadcast_logs'][row['user_id']] = "❌ GAGAL API"
                            except: 
                                fail_count += 1
                                st.session_state['broadcast_logs'][row['user_id']] = "❌ ERROR NET"
                            
                            prog_bar.progress(min(i / total_targets, 1.0))
                            time.sleep(0.1)
                            
                        st.toast(f"Selesai! ✅ {succ_count} | ❌ {fail_count}", icon="📨")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.button("📢 PILIH USER DULU", disabled=True, use_container_width=True)

        else:
            st.success("✅ REAL-TIME CHECK: Tidak ada user expired di Database Server.", icon="🌟")
            
    except Exception as e:
        st.error(f"❌ Gagal mengambil data server: {e}")

st.markdown("<br><hr style='border-color: #00f2ff; opacity: 0.3;'><br>", unsafe_allow_html=True)
cf1, cf2, cf3 = st.columns([1, 2, 1])
with cf1:
    if st.button("🔄 REFRESH SYSTEM", key="footer_refresh"): st.cache_data.clear(); st.rerun()
with cf3:
    if st.button("🚪 LOGOUT SESSION", key="footer_logout"): st.session_state['authenticated'] = False; st.rerun()
st.markdown("""<div class="footer-quote">"EAGLE ONE, STANDING BY. EYES ON THE STREET, DATA IN THE CLOUD."</div><div class="footer-text">SYSTEM INTELLIGENCE SECURED & ENCRYPTED<br>COPYRIGHT © 2026 <b>BUDIB40NK</b> | ALL RIGHTS RESERVED<br>OPERATIONAL COMMAND CENTER v10.7</div>""", unsafe_allow_html=True)