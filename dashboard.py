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
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
from dotenv import load_dotenv

# ##############################################################################
# BAGIAN 1: KONFIGURASI HALAMAN & TEMA CYBERPUNK
# ##############################################################################
st.set_page_config(
    page_title="One Aspal Command",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CSS MASTER (LENGKAP: UI GRID + GLASSMORPHISM) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Orbitron:wght@500;700;900&display=swap');

    .stApp { background-color: #0e1117; font-family: 'Inter', sans-serif; font-size: 14px; }
    
    h1, h2, h3 { font-family: 'Orbitron', sans-serif !important; color: #ffffff; text-transform: uppercase; letter-spacing: 1px; }
    
    /* GLASS MORPHISM METRIC CARDS */
    div[data-testid="metric-container"] {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px; padding: 15px; backdrop-filter: blur(10px);
        transition: border-color 0.3s;
    }
    div[data-testid="metric-container"]:hover { border-color: #00f2ff; }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #00f2ff !important; font-family: 'Orbitron', sans-serif; font-size: 1.5rem !important;
    }

    /* NEON BUTTONS */
    .stButton>button {
        background: linear-gradient(90deg, #0061ff 0%, #60efff 100%);
        color: #000; border: none; border-radius: 6px; height: 40px;
        font-weight: 700; font-family: 'Orbitron', sans-serif; font-size: 0.9rem; width: 100%;
    }
    .stButton>button:hover { box-shadow: 0 0 15px rgba(0, 242, 255, 0.4); color: #000; }

    /* LEADERBOARD TABLE */
    .leaderboard-row {
        background: rgba(0, 242, 255, 0.03);
        padding: 12px 15px; margin-bottom: 6px; border-radius: 6px;
        border-left: 3px solid #00f2ff; display: flex; justify-content: space-between; align-items: center;
    }
    .leaderboard-val { font-family: 'Orbitron'; color: #00f2ff; font-weight: bold; }

    /* INFO GRID (PERSONIL) */
    .tech-box { background: rgba(0, 242, 255, 0.05); border-left: 3px solid #00f2ff; padding: 15px; border-radius: 5px; margin-bottom: 20px; color: #ddd; }
    .info-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 10px; }
    .info-item { background: rgba(255,255,255,0.05); padding: 10px; border-radius: 5px; }
    .info-label { color: #888; font-size: 0.75rem; display: block; text-transform: uppercase; }
    .info-value { color: #fff; font-weight: bold; font-family: 'Orbitron'; font-size: 1rem; }

    header {visibility: hidden;} footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ##############################################################################
# BAGIAN 2: KONEKSI & DATABASE OPS
# ##############################################################################
load_dotenv()
URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

@st.cache_resource
def init_connection():
    try: return create_client(URL, KEY)
    except: return None

supabase = init_connection()

if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False
if 'upload_stage' not in st.session_state: st.session_state['upload_stage'] = 'idle'
if 'upload_data_cache' not in st.session_state: st.session_state['upload_data_cache'] = None
if 'upload_found_cols' not in st.session_state: st.session_state['upload_found_cols'] = []

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

def get_active_hunters_30m():
    try:
        t = datetime.now(timezone.utc) - timedelta(minutes=30)
        res = supabase.table('finding_logs').select('user_id').gte('created_at', t.isoformat()).execute()
        return pd.DataFrame(res.data)['user_id'].nunique() if res.data else 0
    except: return 0

def add_user_quota(user_id, days):
    try:
        res = supabase.table('users').select('expiry_date').eq('user_id', user_id).execute()
        now = datetime.utcnow()
        if res.data and res.data[0]['expiry_date']:
            current_exp = datetime.fromisoformat(res.data[0]['expiry_date'].replace('Z', ''))
            base_date = current_exp if current_exp > now else now
        else: base_date = now
        new_exp = base_date + timedelta(days=days)
        supabase.table('users').update({'expiry_date': new_exp.isoformat()}).eq('user_id', user_id).execute()
        return True
    except: return False

# ##############################################################################
# BAGIAN 3: ENGINE PINTAR (HEADER SCANNER & SMART RENAME)
# ##############################################################################
COLUMN_ALIASES = {
    'nopol': ['nopolisi', 'nomorpolisi', 'nopol', 'noplat', 'tnkb', 'licenseplate', 'plat', 'police_no', 'no polisi', 'plate_number', 'platenumber', 'plate_no'],
    'type': ['type', 'tipe', 'unit', 'model', 'vehicle', 'jenis', 'deskripsiunit', 'merk', 'object', 'kendaraan', 'item', 'brand', 'tipeunit'],
    'tahun': ['tahun', 'year', 'thn', 'rakitan', 'th', 'yearofmanufacture'],
    'warna': ['warna', 'color', 'colour', 'cat'],
    'noka': ['noka', 'norangka', 'nomorrangka', 'chassis', 'chasis', 'vin', 'rangka', 'no rangka', 'chassis_number'],
    'nosin': ['nosin', 'nomesin', 'nomormesin', 'engine', 'mesin', 'no mesin', 'engine_number'],
    'finance': ['finance', 'leasing', 'lising', 'multifinance', 'mitra', 'principal', 'client'],
    'ovd': ['ovd', 'overdue', 'dpd', 'keterlambatan', 'odh', 'hari', 'telat', 'aging', 'days_overdue', 'lates', 'over_due', 'od'],
    'branch': ['branch', 'area', 'kota', 'pos', 'cabang', 'lokasi', 'wilayah']
}

def normalize_text(text): return ''.join(e for e in str(text) if e.isalnum()).lower()

def fix_header_position(df):
    """Mencari baris header asli di tengah tumpukan baris sampah (MTF Fix)."""
    target_aliases = [normalize_text(a) for a in COLUMN_ALIASES['nopol']]
    for i in range(min(30, len(df))):
        row_vals = [normalize_text(str(x)) for x in df.iloc[i].values]
        if any(alias in row_vals for alias in target_aliases):
            df.columns = df.iloc[i]
            df = df.iloc[i+1:].reset_index(drop=True)
            return df
    return df

def smart_rename_columns(df):
    new = {}; found = []
    df.columns = [str(c).strip().replace('"', '').replace("'", "").replace('\ufeff', '') for c in df.columns]
    for col in df.columns:
        clean = normalize_text(col)
        for std, aliases in COLUMN_ALIASES.items():
            if clean == std or clean in [normalize_text(a) for a in aliases]:
                if std not in new.values(): # Anti-Duplicate Fix
                    new[col] = std; found.append(std)
                break
        if col not in new: new[col] = col
    df.rename(columns=new, inplace=True); df = df.loc[:, ~df.columns.duplicated()]
    return df, found

def standardize_leasing_name(n):
    c = str(n).upper().strip().replace('"', '').replace("'", "")
    return "UNKNOWN" if c in ['NAN', 'NULL', ''] else c

def read_file_robust(f):
    fname = f.name.lower()
    content = f.getvalue()
    if fname.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            v = [x for x in z.namelist() if x.endswith(('.csv','.xlsx','.xls','.txt'))]
            if v: content = z.read(v[0]); fname = v[0].lower(); f = io.BytesIO(content)
    else: f = io.BytesIO(content)
    try:
        if fname.endswith(('.xlsx', '.xls')): return pd.read_excel(f, dtype=str)
        else:
            try: return pd.read_csv(f, sep=';', dtype=str, on_bad_lines='skip')
            except: return pd.read_csv(f, sep=',', dtype=str, on_bad_lines='skip')
    except: return pd.DataFrame()

# ##############################################################################
# BAGIAN 4: LOGIN & DASHBOARD UI
# ##############################################################################
def get_img_as_base64(file):
    with open(file, "rb") as f: return base64.b64encode(f.read()).decode()

if not st.session_state['authenticated']:
    c_l1, c_l2, c_l3 = st.columns([1, 6, 1])
    with c_l2:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        if os.path.exists("logo.png"):
            b64 = get_img_as_base64("logo.png")
            st.markdown(f'<div style="display:flex;justify-content:center;margin-bottom:20px;"><img src="data:image/png;base64,{b64}" width="200" style="border-radius:10px;"></div>', unsafe_allow_html=True)
        st.markdown("<h2 style='text-align:center;color:#00f2ff;'>SYSTEM LOGIN</h2>", unsafe_allow_html=True)
        pwd = st.text_input("PASSPHRASE", type="password", label_visibility="collapsed")
        if pwd == ADMIN_PASSWORD: st.session_state['authenticated'] = True; st.rerun()
    st.stop()

# --- DASHBOARD HEADER ---
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", width=200)
    st.markdown("### OPERATIONS")
    if st.button("🔄 REFRESH SYSTEM"): st.cache_data.clear(); st.rerun()
    if st.button("🚪 LOGOUT"): st.session_state['authenticated'] = False; st.rerun()

st.markdown("## ONE ASPAL COMMANDO v8.1")
st.markdown("---")

# --- GLOBAL STATS ---
df_u = get_all_users()
total_assets = get_total_asset_count()
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("ASSETS", f"{total_assets:,}", "DATABASE")
m2.metric("LIVE USERS", f"{get_active_hunters_30m()}", "30M ACTIVE")
m3.metric("MITRA", f"{len(df_u[df_u['role']!='pic']) if not df_u.empty else 0}", "REGISTERED")
m4.metric("READY", f"{len(df_u[(df_u['status']=='active') & (pd.to_numeric(df_u['quota'], errors='coerce').fillna(0)>0)]) if not df_u.empty else 0}", "ACTIVE & QUOTA>0")
m5.metric("PIC HQ", f"{len(df_u[df_u['role']=='pic']) if not df_u.empty else 0}", "LEASING HQ")
st.write("")

tab1, tab2, tab3, tab4 = st.tabs(["🏆 LEADERBOARD", "🛡️ PERSONIL", "📤 UPLOAD", "🗑️ HAPUS"])

# --- TAB 1: LEADERBOARD ---
with tab1:
    st.markdown("### 🏆 TOP 10 RANGERS (HIT COUNT)")
    hits = get_hit_counts()
    if not df_u.empty and not hits.empty:
        df_r = df_u.copy()
        df_r['h'] = df_r['user_id'].map(hits).fillna(0).astype(int)
        df_r = df_r[df_r['role']!='pic'].sort_values('h', ascending=False).head(10)
        for i, r in enumerate(df_r.iterrows(), 1):
            row = r[1]
            st.markdown(f'<div class="leaderboard-row"><div><b>#{i} {row["nama_lengkap"]}</b><br><small style="color:#888;">{row["agency"]}</small></div><div class="leaderboard-val">{row["h"]} HITS</div></div>', unsafe_allow_html=True)

# --- TAB 2: PERSONIL (LENGKAP DENGAN UI GRID v7.3) ---
with tab2:
    if df_u.empty: st.warning("NO USER DATA.")
    else:
        div = st.radio("SELECT DIVISION", ["🛡️ MATEL", "🏦 PIC"], horizontal=True, label_visibility="collapsed")
        target = df_u[df_u['role'] != 'pic'] if "MATEL" in div else df_u[df_u['role'] == 'pic']
        target = target.sort_values('nama_lengkap')
        user_list = [f"{r['nama_lengkap']} | {r['agency']}" for i, r in target.iterrows()]
        sel_name = st.selectbox("SEARCH AGENT", user_list, label_visibility="collapsed")
        
        if sel_name:
            uid = target[target['nama_lengkap'] == sel_name.split(' | ')[0]].iloc[0]['user_id']
            u = target[target['user_id'] == uid].iloc[0]
            real_hits = hits.get(uid, 0)
            
            st.markdown(f"""
            <div class="tech-box">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h3 style="margin:0;">{u['nama_lengkap']}</h3>
                    <span style="color:#00f2ff; font-weight:bold;">{u['agency']}</span>
                </div>
                <hr style="border-color:rgba(255,255,255,0.1); margin:12px 0;">
                <div class="info-grid">
                    <div class="info-item"><span class="info-label">STATUS</span><span class="info-value" style="color:{'#0f0' if u['status']=='active' else '#f00'}">{u['status'].upper()}</span></div>
                    <div class="info-item"><span class="info-label">EXPIRY DATE</span><span class="info-value">{str(u['expiry_date'])[:10]}</span></div>
                    <div class="info-item"><span class="info-label">QUOTA (SISA)</span><span class="info-value">{u.get('quota',0):,}</span></div>
                    <div class="info-item"><span class="info-label">USAGE (TODAY)</span><span class="info-value">{u.get('daily_usage',0)}x</span></div>
                    <div class="info-item" style="grid-column: span 2; border: 1px solid #00f2ff;"><span class="info-label">LIFETIME HITS</span><span class="info-value" style="color:#00f2ff; font-size:1.4rem;">{real_hits} UNITS FOUND</span></div>
                </div>
            </div>""", unsafe_allow_html=True)
            
            c_days, c_ext = st.columns([1, 2])
            with c_days: days = st.number_input("DAYS", 1, 30, 30, label_visibility="collapsed")
            with c_ext:
                if st.button(f"➕ EXTEND ACCESS (+{days} DAYS)"):
                    if add_user_quota(uid, days): st.success("OK"); time.sleep(1); st.rerun()
            
            b_ban, b_del = st.columns(2)
            with b_ban:
                if st.button("⛔ FREEZE ACCOUNT" if u['status']=='active' else "✅ ACTIVATE"):
                    supabase.table('users').update({'status': 'banned' if u['status']=='active' else 'active'}).eq('user_id', uid).execute(); st.rerun()
            with b_del:
                if st.button("🗑️ PERMANENT DELETE"):
                    supabase.table('users').delete().eq('user_id', uid).execute(); st.rerun()

# --- TAB 3: UPLOAD (ULTRA ROBUST + HP FIX) ---
with tab3:
    st.markdown("### 📤 UPLOAD INTELLIGENCE")
    if st.session_state['upload_stage'] == 'idle':
        up = st.file_uploader("DROP FILE", type=['xlsx','csv','txt','zip'], label_visibility="collapsed")
        if up and st.button("🔍 ANALISA FILE"):
            df_raw = read_file_robust(up)
            if not df_raw.empty:
                df_fixed = fix_header_position(df_raw) # MTF FIX: Cari baris header di manapun
                df_renamed, found = smart_rename_columns(df_fixed)
                if 'nopol' in df_renamed.columns:
                    st.session_state['upload_data_cache'] = df_renamed
                    st.session_state['upload_found_cols'] = found
                    st.session_state['upload_stage'] = 'preview'
                    st.rerun()
                else: st.error("❌ CRITICAL: Kolom NOPOL tidak terdeteksi (Scan gagal).")

    elif st.session_state['upload_stage'] == 'preview':
        dfc = st.session_state['upload_data_cache']
        found = st.session_state['upload_found_cols']
        st.info(f"✅ **SCAN BERHASIL:** Ditemukan {', '.join([x.upper() for x in found])} | 📊 **TOTAL:** {len(dfc):,} Data")
        st.dataframe(dfc.head(), use_container_width=True)
        
        has_f = 'finance' in dfc.columns
        l_in = ""
        c_l1, c_l2 = st.columns([2,1])
        with c_l1:
            if not has_f:
                st.error("⚠️ **LEASING TIDAK TERDETEKSI!**")
                l_in = st.text_input("👉 Masukkan Nama Leasing (WAJIB):").strip().upper()
            else:
                st.success("✅ **LEASING TERDETEKSI OTOMATIS**")
                if st.checkbox("Timpa nama leasing?"): l_in = st.text_input("Ketik Nama Baru:").strip().upper()
        
        b1, b2 = st.columns(2)
        with b1:
            if st.button("❌ BATAL / RESET"):
                st.session_state['upload_stage'] = 'idle'
                st.rerun()
        with b2:
            if st.button("🚀 UPDATE DATABASE", disabled=(not has_f and not l_in)):
                if l_in: dfc['finance'] = standardize_leasing_name(l_in)
                elif has_f: dfc['finance'] = dfc['finance'].apply(standardize_leasing_name)
                dfc['nopol'] = dfc['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
                v_cols = ['nopol', 'type', 'finance', 'tahun', 'warna', 'noka', 'nosin', 'ovd', 'branch']
                for x in v_cols: dfc[x] = dfc[x].fillna("-") if x in dfc.columns else "-"
                
                recs = json.loads(json.dumps(dfc[v_cols].to_dict('records'), default=str))
                pb = st.progress(0, text="🚀 Memasukkan data...")
                for i in range(0, len(recs), 1000):
                    supabase.table('kendaraan').upsert(recs[i:i+1000], on_conflict='nopol').execute()
                    pb.progress(min((i+1000)/len(recs), 1.0))
                st.success("✅ BERHASIL!"); st.session_state['upload_stage'] = 'idle'; time.sleep(2); st.rerun()

# --- TAB 4: HAPUS ---
with tab4:
    st.markdown("### 🗑️ PURGE DATA PROTOCOL")
    del_file = st.file_uploader("TARGET LIST (NOPOL)", type=['xlsx','csv','txt'])
    if del_file and st.button("🔥 EXECUTE DELETE"):
        df_del = read_file_robust(del_file)
        df_del, _ = smart_rename_columns(df_del)
        if 'nopol' in df_del.columns:
            targets = list(set(df_del['nopol'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper().tolist()))
            pb_del = st.progress(0, text="🔥 Menghapus unit...")
            for i in range(0, len(targets), 200):
                supabase.table('kendaraan').delete().in_('nopol', targets[i:i+200]).execute()
                pb_del.progress(min((i+200)/targets.size if targets.size > 0 else 1, 1.0))
            st.success("✅ PURGE COMPLETED."); time.sleep(1); st.rerun()