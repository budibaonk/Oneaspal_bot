################################################################################
#                                                                              #
#                      PROJECT: ONEASPAL COMMAND CENTER                        #
#                      VERSION: 10.4 (FIX: BROADCAST TOKEN & DEBUGGER)         #
#                      ROLE:    ADMIN DASHBOARD CORE                           #
#                      AUTHOR:  CTO (GEMINI) & CEO (BAONK)                     #
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

# ##############################################################################
# BAGIAN 1: KONFIGURASI & INIT
# ##############################################################################
st.set_page_config(
    page_title="One Aspal Command",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# DEFINISI ZONA WAKTU
TZ_JAKARTA = pytz.timezone('Asia/Jakarta')

# LOAD ENVIRONMENT
load_dotenv()
URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
# [FIX] Pastikan Token diambil dengan berbagai cara agar tidak Null
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_TOKEN")

# [FIX] Import ClientOptions
try:
    from supabase.lib.client_options import ClientOptions
except ImportError:
    from supabase import ClientOptions

# --- AUTO REFRESH LOGIC ---
try:
    from streamlit_autorefresh import st_autorefresh
    count = st_autorefresh(interval=30 * 60 * 1000, key="auto_refresh_radar")
    auto_refresh_status = "🟢 AUTO (30m)"
except ImportError:
    auto_refresh_status = "⚪ MANUAL"

# --- CSS MASTER (VISUAL) ---
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

@st.cache_resource
def init_connection():
    try:
        opts = ClientOptions(postgrest_client_timeout=600)
        return create_client(URL, KEY, options=opts)
    except:
        return create_client(URL, KEY)

supabase = init_connection()

if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False
if 'upload_stage' not in st.session_state: st.session_state['upload_stage'] = 'idle'
if 'upload_data_cache' not in st.session_state: st.session_state['upload_data_cache'] = None
if 'upload_found_cols' not in st.session_state: st.session_state['upload_found_cols'] = []
if 'upload_result' not in st.session_state: st.session_state['upload_result'] = None

# --- CORE FUNCTIONS ---
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
        if res.data: current_exp_str = res.data[0].get('expiry_date')
        base = now
        if current_exp_str:
            try:
                parsed = datetime.fromisoformat(current_exp_str.replace('Z', '+00:00'))
                if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
                if parsed > now: base = parsed
            except: pass
        new_exp = base + timedelta(days=days)
        supabase.table('users').update({'expiry_date': new_exp.isoformat()}).eq('user_id', uid).execute()
        return True, f"Sukses! Exp: {new_exp.strftime('%d-%m-%Y')}"
    except Exception as e: return False, str(e)

# [FIX] FUNGSI KIRIM PESAN LEBIH ROBUST & INFORMATIF
def send_telegram_message(user_id, text):
    if not BOT_TOKEN: 
        print("❌ TOKEN MISSING")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": user_id, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=5)
        # Hanya return True jika status 200 OK
        if r.status_code == 200: return True
        else:
            print(f"⚠️ API ERROR ({user_id}): {r.text}")
            return False
    except Exception as e: 
        print(f"❌ NET ERROR ({user_id}): {e}")
        return False

def delete_user_with_reason(uid, reason):
    try:
        msg = f"⛔ <b>AKUN DINONAKTIFKAN</b>\n\nMaaf, akun One Aspal Anda telah dihapus.\n📝 <b>Alasan:</b> {reason}"
        send_telegram_message(uid, msg)
        supabase.table('users').delete().eq('user_id', uid).execute()
        return True
    except: return False

# ##############################################################################
# BAGIAN 2: PARSER ENGINE
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
        if any(a in vals for a in target): df.columns = df.iloc[i]; return df.iloc[i+1:].reset_index(drop=True)
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
                        # Helper for Topaz
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
                        row = {'nopol': nopol, 'type': get_val('TIPE;', details, ['NOKA;', 'NOSIN;']), 'finance': None}
                        data_list.append(row)
                return pd.DataFrame(data_list)
            except: return pd.DataFrame()
        if filename.endswith('.ZIP'):
            with zipfile.ZipFile(file_up) as z:
                v = [x for x in z.namelist() if x.endswith(('.csv','.xlsx','.xls'))]
                if v: file_up = io.BytesIO(z.read(v[0])); file_up.name = v[0]
        if file_up.name.upper().endswith(('.XLSX', '.XLS')): 
            try: return pd.read_excel(file_up, dtype=str)
            except: return pd.read_excel(file_up, engine='openpyxl', dtype=str)
        return pd.read_csv(file_up, sep=None, engine='python', dtype=str, on_bad_lines='skip')
    except: return pd.DataFrame()

def standardize_leasing_name(n): return str(n).upper().strip() if str(n).upper().strip() not in ['NAN','NULL',''] else "UNKNOWN"

# ##############################################################################
# BAGIAN 3: LOGIN
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
# BAGIAN 4: SIDEBAR
# ##############################################################################
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", width=220)
    st.caption(f"ONE ASPAL SYSTEM\nStatus: {auto_refresh_status}")
    # [FIX] Visual Indicator for Token
    if not BOT_TOKEN:
        st.error("⚠️ BOT TOKEN MISSING!")
    else:
        st.success("✅ BOT TOKEN ACTIVE")

st.markdown("## ONE ASPAL COMMANDO v10.4")
st.markdown("<span style='color: #00f2ff; font-family: Orbitron; font-size: 0.8rem;'>⚡ LIVE INTELLIGENCE COMMAND CENTER</span>", unsafe_allow_html=True)
st.markdown("---")

df_u = get_all_users()
m1, m2, m3, m4 = st.columns(4)
m1.metric("ASSETS", f"{get_total_asset_count():,}", "DB")
m2.metric("LIVE", f"{get_live_users_count()}", "<30m")
m3.metric("USERS", f"{len(df_u)}", "TOTAL")
m4.metric("ACTIVE", f"{len(df_u[df_u['status']=='active']) if not df_u.empty else 0}", "ACC")

# ##############################################################################
# BAGIAN 5: TABS (MAIN UI)
# ##############################################################################
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🏆 TOP", "🛡️ USERS", "📤 UPLOAD", "🗑️ PURGE", "📡 LIVE", "💀 EXPIRED"])

with tab1:
    hits = get_hit_counts()
    if not df_u.empty and not hits.empty:
        df_r = df_u.copy(); df_r['h'] = df_r['user_id'].map(hits).fillna(0).astype(int)
        for i, r in enumerate(df_r[df_r['role']!='pic'].sort_values('h', ascending=False).head(10).iterrows(), 1):
            st.markdown(f'<div class="leaderboard-row"><div><b>#{i} {r[1]["nama_lengkap"]}</b><br><small>{r[1]["agency"]}</small></div><div class="leaderboard-val">{r[1]["h"]} HITS</div></div>', unsafe_allow_html=True)

with tab2:
    if not df_u.empty:
        target = df_u.sort_values(by="nama_lengkap", key=lambda col: col.str.lower())
        sel = st.selectbox("SEARCH AGENT", [f"{r['nama_lengkap']} | {r['agency']}" for i, r in target.iterrows()], label_visibility="collapsed")
        if sel:
            uid = target[target['nama_lengkap']==sel.split(' | ')[0]].iloc[0]['user_id']
            u = target[target['user_id']==uid].iloc[0]
            st.markdown(f'''<div class="tech-box"><h3>{u["nama_lengkap"]}</h3><div class="info-grid"><div class="info-item"><span class="info-label">ROLE</span><span class="info-value">{u["role"].upper()}</span></div><div class="info-item"><span class="info-label">STATUS</span><span class="info-value" style="color:{'#0f0' if u["status"]=="active" else "#f00"}">{u["status"].upper()}</span></div><div class="info-item"><span class="info-label">EXPIRY</span><span class="info-value">{str(u["expiry_date"])[:10]}</span></div></div></div>''', unsafe_allow_html=True)
            c1, c2 = st.columns([1, 2])
            with c1: 
                days = st.number_input("HARI", 1, 365, 30, key="d_add")
                if st.button("➕ TAMBAH"):
                    ok, msg = add_user_quota(uid, days)
                    if ok: st.success(msg); time.sleep(1); st.rerun()
            with c2:
                if st.button("⛔ FREEZE/UNFREEZE"):
                    ns = 'banned' if u['status']=='active' else 'active'
                    update_user_status(uid, ns); st.rerun()

with tab3:
    if st.session_state['upload_stage'] == 'idle':
        up = st.file_uploader("DROP FILE", type=['xlsx','xls','csv','txt','zip','topaz'], key="up_f")
        if up and st.button("🔍 ANALISA"):
            df = read_file_robust(up)
            if not df.empty:
                df, cols = smart_rename_columns(fix_header_position(df))
                if 'nopol' in df.columns:
                    st.session_state['upload_data_cache'], st.session_state['upload_found_cols'], st.session_state['upload_stage'] = df, cols, 'preview'
                    st.rerun()
                else: st.error("❌ NO NOPOL COLUMN")
    elif st.session_state['upload_stage'] == 'preview':
        df = st.session_state['upload_data_cache']
        st.info(f"DATA: {len(df)}")
        if st.button("🚀 EKSEKUSI"):
            BATCH_SIZE = 500
            df['nopol'] = df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
            df = df.dropna(subset=['nopol']).drop_duplicates(subset=['nopol'])
            df['data_month'] = datetime.now(TZ_JAKARTA).strftime('%m%y')
            req = ['type','finance','tahun','warna','noka','nosin','ovd','branch','data_month']
            for c in req:
                if c not in df.columns: df[c] = None
            recs = df[['nopol']+req].to_dict('records')
            pb = st.progress(0); s=0; f=0
            for i in range(0, len(recs), BATCH_SIZE):
                try:
                    supabase.table('kendaraan').upsert(recs[i:i+BATCH_SIZE], on_conflict='nopol').execute()
                    s += len(recs[i:i+BATCH_SIZE])
                except: f += len(recs[i:i+BATCH_SIZE])
                pb.progress(min((i+BATCH_SIZE)/len(recs), 1.0))
            st.session_state['upload_result'] = {'suc':s,'fail':f}
            st.session_state['upload_stage'] = 'complete'; st.rerun()
    elif st.session_state['upload_stage'] == 'complete':
        r = st.session_state['upload_result']
        st.success(f"DONE. ✅ {r['suc']} | ❌ {r['fail']}")
        if st.button("AGAIN"): st.session_state['upload_stage']='idle'; st.rerun()

with tab4:
    up = st.file_uploader("PURGE", type=['xlsx','csv'])
    if up and st.button("🔥 DELETE"):
        df = read_file_robust(up); df, _ = smart_rename_columns(df)
        if 'nopol' in df.columns:
            t = list(set(df['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper().tolist()))
            pb = st.progress(0); BATCH=1000
            for i in range(0, len(t), BATCH):
                supabase.table('kendaraan').delete().in_('nopol', t[i:i+BATCH]).execute()
                pb.progress(min((i+BATCH)/len(t), 1.0))
            st.success("PURGED"); time.sleep(1); st.rerun()

with tab5:
    st.markdown("### 📡 REALTIME OPERATIONS")
    try:
        users_resp = supabase.table('users').select('nama_lengkap, agency, role, last_seen, no_hp').execute()
        if users_resp.data:
            df = pd.DataFrame(users_resp.data)
            df['last_seen'] = pd.to_datetime(df['last_seen']).dt.tz_convert(TZ_JAKARTA)
            df = df.sort_values('last_seen', ascending=False).head(50)
            df['TIME'] = df['last_seen'].dt.strftime('%H:%M:%S')
            st.dataframe(df[['TIME','nama_lengkap','agency','role']], hide_index=True, use_container_width=True)
    except: st.info("No Data")

# --- TAB 6: EXPIRED USERS (FIXED BROADCAST) ---
with tab6:
    st.markdown("### 💀 DAFTAR USER HABIS MASA AKTIF")
    
    # [FIX] WARNING JIKA TOKEN TIDAK ADA
    if not BOT_TOKEN:
        st.error("⛔ BROADCAST NON-AKTIF KARENA TOKEN BOT KOSONG! Cek file .env Anda.")
    
    if st.button("🔄 REFRESH DATA"): st.cache_data.clear(); st.rerun()

    try:
        now_str = datetime.now(TZ_JAKARTA).strftime('%Y-%m-%d')
        res = supabase.table('users').select('*').lt('expiry_date', now_str).neq('status', 'banned').execute()
        
        if res.data:
            df = pd.DataFrame(res.data)
            df['PILIH'] = False
            edited = st.data_editor(df[['PILIH','nama_lengkap','no_hp','expiry_date','user_id']], hide_index=True, use_container_width=True, key="ed_exp")
            
            targets = edited[edited['PILIH']==True]
            
            if not targets.empty:
                if st.button(f"📢 KIRIM KE {len(targets)} USER", type="primary"):
                    # [FIX] STOP JIKA TOKEN KOSONG
                    if not BOT_TOKEN:
                        st.error("❌ TOKEN BOT KOSONG/TIDAK TERBACA. Broadcast dibatalkan.")
                        st.stop()
                        
                    s_count, f_count = 0, 0
                    pb = st.progress(0, "Sending...")
                    
                    for i, (idx, row) in enumerate(targets.iterrows(), 1):
                        msg = (
                            f"🔔 <b>PENGINGAT MASA AKTIF</b>\n\n"
                            f"Halo <b>{row['nama_lengkap']}</b>,\n"
                            f"Masa aktif akun One Aspal Anda telah berakhir pada <b>{str(row['expiry_date'])[:10]}</b>.\n\n"
                            f"Silakan hubungi Admin atau ketik /infobayar\n"
                        )
                        # Kirim Pesan dengan Fungsi Baru
                        ok = send_telegram_message(row['user_id'], msg)
                        if ok: s_count += 1
                        else: f_count += 1
                        pb.progress(i/len(targets))
                        time.sleep(0.1)
                        
                    st.success(f"SELESAI. ✅ {s_count} | ❌ {f_count}")
                    if f_count > 0: st.warning("Jika banyak yang gagal, pastikan User belum memblokir bot.")
                    time.sleep(2); st.rerun()
            else:
                st.info("Pilih user dulu untuk dibroadcast.")
        else:
            st.success("Tidak ada user expired hari ini.")
    except Exception as e:
        st.error(f"Error fetch data: {e}")

st.markdown("<br><hr><br>", unsafe_allow_html=True)
if st.button("🚪 LOGOUT"): st.session_state['authenticated'] = False; st.rerun()